"""Retrieval smoke gate: embed the committed CI fixture and assert thresholds.

Everything this needs is in git — no API keys, no DVC pull: it embeds
evalsets/ci/ci-corpus.jsonl into a throwaway Qdrant collection (CPU
fastembed), runs the retrieval-ci cases in hybrid mode, and checks the
metrics against the retrieval-ci-smoke thresholds in
evalsets/regression-thresholds.json. Exit 1 on any violation.

Usage (locally against the compose Qdrant, or in CI against a service):
    uv run python -m opsverse_evals.ci_retrieval_smoke
"""

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

from qdrant_client import AsyncQdrantClient

from opsverse_core.settings import get_settings
from opsverse_evals.build_ci_fixture import load_jsonl
from opsverse_evals.metrics import hit_at_k, mrr_at_k
from opsverse_evals.regression import check_report, load_thresholds
from opsverse_evals.schemas import RetrievalDataset
from opsverse_rag import QdrantStore, Retriever, SearchMode
from opsverse_rag.embeddings import FastEmbedEmbedder
from opsverse_rag.store import ChunkPoint

K = 10
EMBED_BATCH = 64
REPORT_NAME = "retrieval-ci-smoke"


async def run(chunks_path: Path, dataset_path: Path, qdrant_url: str, collection: str) -> dict:
    settings = get_settings()
    records = load_jsonl(chunks_path)
    dataset = RetrievalDataset.load_jsonl(dataset_path)
    embedder = FastEmbedEmbedder(
        settings.embedding_model, settings.sparse_model, settings.embedding_dim
    )
    client = AsyncQdrantClient(url=qdrant_url)
    store = QdrantStore(client, collection, embedder.dense_dim)
    if await client.collection_exists(collection):
        await client.delete_collection(collection)  # throwaway: always fresh
    await store.ensure_collection()

    t0 = time.perf_counter()
    for i in range(0, len(records), EMBED_BATCH):
        batch = records[i : i + EMBED_BATCH]
        texts = [r["text"] for r in batch]
        dense = embedder.embed_dense(texts)
        sparse = embedder.embed_sparse(texts)
        await store.upsert(
            [
                ChunkPoint(
                    id=r["id"],
                    dense=d,
                    sparse=s,
                    payload={k: v for k, v in r.items() if k != "id"},
                )
                for r, d, s in zip(batch, dense, sparse, strict=True)
            ]
        )
    print(f"embedded {len(records)} fixture chunks in {time.perf_counter() - t0:.1f}s")

    retriever = Retriever(store, embedder)  # no reranker in CI: not on the chat path
    per_case = []
    t0 = time.perf_counter()
    for case in dataset.cases:
        hits = await retriever.search(case.question, k=K, mode=SearchMode.HYBRID)
        chunk_ids = [h.id for h in hits]
        doc_ids = [h.document_id for h in hits]
        per_case.append(
            {
                "chunk:hit@5": hit_at_k(chunk_ids, set(case.relevant_chunk_ids), 5),
                "chunk:mrr@10": mrr_at_k(chunk_ids, set(case.relevant_chunk_ids), K),
                "doc:hit@5": hit_at_k(doc_ids, set(case.relevant_document_ids), 5),
                "doc:mrr@10": mrr_at_k(doc_ids, set(case.relevant_document_ids), K),
            }
        )
    elapsed = time.perf_counter() - t0
    await client.delete_collection(collection)
    await client.close()

    results = {m: round(statistics.mean(c[m] for c in per_case), 4) for m in per_case[0]}
    results["latency_ms_per_query"] = round(elapsed / len(per_case) * 1000, 1)
    return {
        "report": REPORT_NAME,
        "kind": "retrieval-ci-smoke",
        "dataset": dataset.name,
        "cases": len(per_case),
        "corpus_stats": dataset.corpus_stats,
        "k": K,
        "results": {"hybrid": results},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=Path("evalsets/ci/ci-corpus.jsonl"))
    parser.add_argument("--dataset", type=Path, default=Path("evalsets/ci/retrieval-ci.jsonl"))
    parser.add_argument("--qdrant", default=None, help="default: OPSVERSE_QDRANT_URL")
    parser.add_argument("--collection", default="opsverse_ci_smoke")
    parser.add_argument(
        "--thresholds", type=Path, default=Path("evalsets/regression-thresholds.json")
    )
    args = parser.parse_args()

    qdrant_url = args.qdrant or get_settings().qdrant_url
    report = asyncio.run(run(args.chunks, args.dataset, qdrant_url, args.collection))
    print(report["results"]["hybrid"])

    thresholds = [t for t in load_thresholds(args.thresholds) if t.report == REPORT_NAME]
    if not thresholds:
        print(f"no thresholds pinned for {REPORT_NAME} — refusing to pass an empty gate")
        sys.exit(1)
    violations = [v for t in thresholds if (v := check_report(report, t))]
    for violation in violations:
        print(f"FAIL {violation}")
    if violations:
        sys.exit(1)
    print(f"all {len(thresholds)} thresholds met")


if __name__ == "__main__":
    main()
