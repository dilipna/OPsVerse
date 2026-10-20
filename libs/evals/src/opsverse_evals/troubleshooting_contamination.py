"""Check new troubleshooting questions against the actual committed SFT inputs."""

import argparse
import hashlib
import json
from pathlib import Path

from opsverse_evals.contamination import jaccard, normalize_question, shingles

ROOT = Path(__file__).resolve().parents[4]


def run() -> dict:
    cases_path = ROOT / "evalsets/troubleshooting-v1/cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]
    questions = []
    data_hashes = {}
    for split in ("train", "val"):
        path = ROOT / f"data/sft/{split}.jsonl"
        data_hashes[split] = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            questions.extend(
                message["content"] for message in row["messages"] if message["role"] == "user"
            )
    known = [shingles(q) for q in questions]
    normalized = {normalize_question(q) for q in questions}
    rows = []
    for case in cases:
        candidate = case["issue"]
        score = max((jaccard(shingles(candidate), s) for s in known), default=0)
        rows.append(
            {
                "id": case["id"],
                "exact": normalize_question(candidate) in normalized,
                "max_shingle_jaccard": score,
                "flagged": score >= 0.6,
            }
        )
    return {
        "dataset_sha256": hashlib.sha256(
            cases_path.read_text(encoding="utf-8").encode()
        ).hexdigest(),
        "sft_sha256": data_hashes,
        "sft_inputs": len(questions),
        "cases": rows,
        "flagged": sum(row["flagged"] or row["exact"] for row in rows),
        "limitations": "Exact/lexical overlap only. Semantic and pretraining overlap unknown. "
        "No cases silently excluded; source documentation overlap is expected.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = run()
    target = ROOT / "docs/reports/troubleshooting-contamination-v1.json"
    if args.check:
        if json.loads(target.read_text(encoding="utf-8")) != report:
            raise SystemExit("Contamination report is stale")
        print("Contamination report matches committed inputs")
    else:
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
