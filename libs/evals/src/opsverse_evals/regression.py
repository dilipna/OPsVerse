"""Regression gate: assert eval reports stay above pinned thresholds.

DeepEval-style assertions without the dependency: thresholds live in
evalsets/regression-thresholds.json, pinned to measured baselines on frozen
eval sets minus explicit slack (the "note" on each threshold records the
measured value it was pinned against). A missing report, mode, or metric is
a violation, not a silent pass — gates that skip when the data disappears
are how regressions ship.

Usage (exit 1 on any violation -> usable as a CI gate):
    uv run python -m opsverse_evals.regression \
        [--reports docs/reports] [--thresholds evalsets/regression-thresholds.json]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class Threshold(BaseModel):
    report: str  # report name, e.g. retrieval-ablation-v1
    mode: str  # results key, e.g. hybrid | chat
    metric: str  # e.g. chunk:mrr@10 | judge:faithfulness
    min_score: float
    note: str = ""


def load_thresholds(path: Path) -> list[Threshold]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Threshold.model_validate(t) for t in payload["thresholds"]]


def check_report(report: dict[str, Any] | None, threshold: Threshold) -> str | None:
    """One assertion against one report. Returns a violation message or None."""
    where = f"{threshold.report}: {threshold.mode}/{threshold.metric}"
    if report is None:
        return f"{where}: report missing"
    mode = (report.get("results") or {}).get(threshold.mode)
    if mode is None:
        return f"{where}: mode missing from results"
    score = mode.get(threshold.metric)
    if not isinstance(score, int | float):
        return f"{where}: metric missing from results"
    if score < threshold.min_score:
        return f"{where}: {score:.4f} < min {threshold.min_score}"
    return None


def run_gate(reports_dir: Path, thresholds: list[Threshold]) -> list[str]:
    reports: dict[str, dict[str, Any]] = {}
    for path in sorted(reports_dir.glob("*-summary.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("report"):
            reports[payload["report"]] = payload

    violations: list[str] = []
    for threshold in thresholds:
        violation = check_report(reports.get(threshold.report), threshold)
        if violation:
            violations.append(violation)
            print(f"FAIL {violation}")
        else:
            score = reports[threshold.report]["results"][threshold.mode][threshold.metric]
            print(
                f"PASS {threshold.report}: {threshold.mode}/{threshold.metric}"
                f" {score:.4f} >= {threshold.min_score}"
            )
    return violations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=Path("docs/reports"))
    parser.add_argument(
        "--thresholds", type=Path, default=Path("evalsets/regression-thresholds.json")
    )
    args = parser.parse_args()
    violations = run_gate(args.reports, load_thresholds(args.thresholds))
    if violations:
        print(f"\n{len(violations)} regression(s)")
        sys.exit(1)
    print("\nall thresholds met")


if __name__ == "__main__":
    main()
