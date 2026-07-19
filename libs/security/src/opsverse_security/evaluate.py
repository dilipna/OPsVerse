"""Measure the injection heuristic as a classifier on a labeled red-team set.

Reports TPR (recall on attacks), specificity (1 - FPR on benign DevOps
text), precision, and the confusion matrix, then writes a report in the same
shape docs/reports serves. Honest by construction: benign cases are real
DevOps sentences that deliberately share surface vocabulary with attacks
("ignore files", "override entrypoint", "system:masters", "forget cached
layers"), so specificity here is a real measurement, not a softball.

Usage:
    uv run python -m opsverse_security.evaluate            # prints + writes report
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opsverse_security.injection import scan_injection


def evaluate(dataset_path: Path) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    misses: list[str] = []
    false_alarms: list[str] = []
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        flagged = scan_injection(row["text"]).is_suspicious
        attack = row["label"] == "injection"
        if attack and flagged:
            tp += 1
        elif attack and not flagged:
            fn += 1
            misses.append(row["id"])
        elif not attack and flagged:
            fp += 1
            false_alarms.append(row["id"])
        else:
            tn += 1

    def ratio(num: int, den: int) -> float:
        return round(num / den, 4) if den else 0.0

    return {
        "tpr_recall": ratio(tp, tp + fn),
        "specificity": ratio(tn, tn + fp),
        "precision": ratio(tp, tp + fp),
        "attacks": tp + fn,
        "benign": tn + fp,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "missed_attacks": misses,
        "false_alarms": false_alarms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evalsets/security-redteam-v1.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("docs/reports"))
    args = parser.parse_args()

    metrics = evaluate(args.dataset)
    report = {
        "report": "security-redteam-v1",
        "kind": "security-detection",
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "dataset": "security-redteam-v1",
        "cases": metrics["attacks"] + metrics["benign"],
        # mode -> metric -> value, matching the eval page's generic renderer
        "results": {
            "injection-heuristic": {
                "tpr_recall": metrics["tpr_recall"],
                "specificity": metrics["specificity"],
                "precision": metrics["precision"],
            }
        },
        "detail": metrics,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "security-redteam-v1-summary.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=1))


if __name__ == "__main__":
    main()
