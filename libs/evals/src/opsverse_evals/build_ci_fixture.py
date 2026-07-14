"""Build the committed CI retrieval fixture from the DVC corpus export.

Takes the first N cases of a frozen retrieval eval set, keeps their gold
chunks, and adds a seeded sample of distractor chunks from the rest of the
corpus — small enough to commit to git and embed inside a CI job, real
enough that retrieval-stack regressions (chunking, fusion, store) move the
numbers. Run locally whenever the fixture needs regenerating (requires
data/corpus, i.e. `dvc pull` first); commit the outputs.

Usage:
    uv run python -m opsverse_evals.build_ci_fixture
"""

import argparse
import json
import random
from pathlib import Path
from typing import Any

from opsverse_evals.schemas import RetrievalDataset

SEED = 42


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def build(
    corpus_dir: Path, dataset_path: Path, n_cases: int, n_distractors: int, out_dir: Path
) -> None:
    documents = {d["id"]: d for d in load_jsonl(corpus_dir / "documents.jsonl")}
    chunks = load_jsonl(corpus_dir / "chunks.jsonl")
    dataset = RetrievalDataset.load_jsonl(dataset_path)

    cases = dataset.cases[:n_cases]
    gold_ids = {cid for case in cases for cid in case.relevant_chunk_ids}
    by_id = {c["id"]: c for c in chunks}
    missing = gold_ids - by_id.keys()
    if missing:
        raise SystemExit(f"{len(missing)} gold chunks not in corpus export: {sorted(missing)[:3]}")

    pool = sorted(c["id"] for c in chunks if c["id"] not in gold_ids)
    distractor_ids = set(random.Random(SEED).sample(pool, min(n_distractors, len(pool))))

    records = []
    for chunk_id in sorted(gold_ids | distractor_ids):
        chunk = by_id[chunk_id]
        doc = documents[chunk["document_id"]]
        records.append(
            {
                "id": chunk["id"],
                "document_id": chunk["document_id"],
                "ord": chunk["ord"],
                "text": chunk["text"],
                "section": chunk.get("section"),
                "language": chunk.get("language"),
                "source": doc["uri"],
                "tool": doc.get("tool"),
                "doc_type": doc.get("doc_type"),
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "ci-corpus.jsonl").open("w", encoding="utf-8") as sink:
        for record in records:
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")

    fixture = RetrievalDataset(
        name="retrieval-ci",
        version="1",
        generator_model=dataset.generator_model,
        corpus_stats={
            "documents": len({r["document_id"] for r in records}),
            "chunks": len(records),
        },
        cases=cases,
    )
    fixture.save_jsonl(out_dir / "retrieval-ci.jsonl")
    print(
        f"fixture: {len(records)} chunks ({len(gold_ids)} gold + {len(distractor_ids)}"
        f" distractors), {len(cases)} cases -> {out_dir}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    parser.add_argument("--dataset", type=Path, default=Path("evalsets/retrieval-v1.jsonl"))
    parser.add_argument("--cases", type=int, default=25)
    parser.add_argument("--distractors", type=int, default=175)
    parser.add_argument("--out", type=Path, default=Path("evalsets/ci"))
    args = parser.parse_args()
    build(args.corpus, args.dataset, args.cases, args.distractors, args.out)


if __name__ == "__main__":
    main()
