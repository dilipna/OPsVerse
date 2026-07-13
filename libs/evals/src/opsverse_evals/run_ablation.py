"""Run the retrieval ablation: dense vs sparse vs hybrid vs hybrid+rerank.

Reads a RetrievalDataset, runs every case through the in-process Retriever in
each mode, and writes a Markdown report plus raw per-case JSON results.

Usage:
    uv run python -m opsverse_evals.run_ablation \
        --dataset evalsets/retrieval-v1.jsonl --out docs/reports
"""

import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdrant_client import AsyncQdrantClient

from opsverse_core.settings import get_settings
from opsverse_evals.metrics import hit_at_k, mrr_at_k, ndcg_at_k
from opsverse_evals.schemas import RetrievalDataset
from opsverse_rag import QdrantStore, Retriever, SearchMode
from opsverse_rag.embeddings import FastEmbedEmbedder
from opsverse_rag.rerank import CrossEncoderReranker

K = 10  # ranking depth for all metrics

MODES: list[tuple[str, SearchMode, bool]] = [
    ("dense", SearchMode.DENSE, False),
    ("sparse", SearchMode.SPARSE, False),
    ("hybrid", SearchMode.HYBRID, False),
    ("hybrid+rerank", SearchMode.HYBRID, True),
]


def build_retriever(settings) -> Retriever:
    embedder = FastEmbedEmbedder(
        settings.embedding_model, settings.sparse_model, settings.embedding_dim
    )
    store = QdrantStore(
        AsyncQdrantClient(url=settings.qdrant_url), settings.qdrant_collection, embedder.dense_dim
    )
    return Retriever(store, embedder, CrossEncoderReranker(settings.reranker_model))


async def run(dataset_path: Path, out_dir: Path) -> None:
    settings = get_settings()
    dataset = RetrievalDataset.load_jsonl(dataset_path)
    retriever = build_retriever(settings)
    print(f"{len(dataset.cases)} cases, modes: {[m[0] for m in MODES]}")

    results: dict[str, dict[str, Any]] = {}
    raw: dict[str, list[dict[str, Any]]] = {}
    for label, mode, rerank in MODES:
        per_case: list[dict[str, Any]] = []
        t0 = time.perf_counter()
        for case in dataset.cases:
            hits = await retriever.search(case.question, k=K, mode=mode, rerank=rerank)
            chunk_ids = [h.id for h in hits]
            doc_ids = [h.document_id for h in hits]
            rel_c, rel_d = set(case.relevant_chunk_ids), set(case.relevant_document_ids)
            per_case.append(
                {
                    "case_id": case.id,
                    "retrieved_chunk_ids": chunk_ids,
                    "chunk": {
                        "hit@1": hit_at_k(chunk_ids, rel_c, 1),
                        "hit@3": hit_at_k(chunk_ids, rel_c, 3),
                        "hit@5": hit_at_k(chunk_ids, rel_c, 5),
                        "hit@10": hit_at_k(chunk_ids, rel_c, 10),
                        "mrr@10": mrr_at_k(chunk_ids, rel_c, 10),
                        "ndcg@10": ndcg_at_k(chunk_ids, rel_c, 10),
                    },
                    "doc": {
                        "hit@1": hit_at_k(doc_ids, rel_d, 1),
                        "hit@5": hit_at_k(doc_ids, rel_d, 5),
                        "mrr@10": mrr_at_k(doc_ids, rel_d, 10),
                    },
                }
            )
        elapsed = time.perf_counter() - t0
        summary = {
            "latency_ms_per_query": round(elapsed / len(dataset.cases) * 1000, 1),
        }
        for level in ("chunk", "doc"):
            for metric in per_case[0][level]:
                summary[f"{level}:{metric}"] = round(
                    statistics.mean(c[level][metric] for c in per_case), 4
                )
        results[label] = summary
        raw[label] = per_case
        print(f"{label}: {summary}")

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    raw_path = out_dir / f"retrieval-ablation-v{dataset.version}-raw.json"
    raw_path.write_text(
        json.dumps({"dataset": dataset.name, "k": K, "results": raw}, indent=1),
        encoding="utf-8",
    )
    # summary JSON is what the API/web eval page serves (Phase 4 moves this
    # into Postgres eval_runs)
    summary_path = out_dir / f"retrieval-ablation-v{dataset.version}-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "report": f"retrieval-ablation-v{dataset.version}",
                "kind": "retrieval-ablation",
                "date": stamp,
                "dataset": dataset.name,
                "cases": len(dataset.cases),
                "generator_model": dataset.generator_model,
                "corpus_stats": dataset.corpus_stats,
                "k": K,
                "results": results,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    report_path = out_dir / f"retrieval-ablation-v{dataset.version}.md"
    report_path.write_text(render_report(dataset, results, stamp), encoding="utf-8")
    print(f"wrote {report_path}, {summary_path} and {raw_path}")


def render_report(dataset: RetrievalDataset, results: dict[str, dict[str, Any]], date: str) -> str:
    chunk_metrics = [
        "chunk:hit@1",
        "chunk:hit@3",
        "chunk:hit@5",
        "chunk:hit@10",
        "chunk:mrr@10",
        "chunk:ndcg@10",
    ]
    doc_metrics = ["doc:hit@1", "doc:hit@5", "doc:mrr@10"]

    def table(metrics: list[str]) -> str:
        header = "| mode | " + " | ".join(m.split(":")[1] for m in metrics) + " | ms/query |"
        sep = "|---" * (len(metrics) + 2) + "|"
        rows = [
            "| "
            + " | ".join(
                [label]
                + [f"{results[label][m]:.3f}" for m in metrics]
                + [str(results[label]["latency_ms_per_query"])]
            )
            + " |"
            for label in results
        ]
        return "\n".join([header, sep, *rows])

    return f"""# Retrieval Ablation — {dataset.name} ({date})

Dataset: **{len(dataset.cases)} questions**, generated by `{dataset.generator_model}`
from the ingested corpus ({dataset.corpus_stats.get("documents")} docs /
{dataset.corpus_stats.get("chunks")} chunks; one question per document, gold label =
source chunk). Ranking depth k={K}. Embeddings: `{get_settings().embedding_model}`
(dense) + `{get_settings().sparse_model}` (sparse), reranker
`{get_settings().reranker_model}` (see ADR-0003).

## Chunk-level (strict: exact gold chunk must be retrieved)

{table(chunk_metrics)}

## Document-level (any chunk of the gold document counts)

{table(doc_metrics)}

## Reading the numbers

- **Chunk-level is a lower bound.** The corpus contains near-duplicate content
  across documents (e.g. similar compose examples), so a retrieval that surfaces
  an equivalent-but-different chunk scores 0 at chunk level. Document-level
  credit corrects for the within-document half of that; cross-document
  duplicates still depress both.
- Latency is per query, sequential, CPU-only embeddings/rerank on the dev
  machine — comparative, not absolute.
- Raw per-case results: `retrieval-ablation-v{dataset.version}-raw.json`.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evalsets/retrieval-v1.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("docs/reports"))
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.out))


if __name__ == "__main__":
    main()
