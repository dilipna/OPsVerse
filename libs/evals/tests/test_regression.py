import json
from pathlib import Path

from opsverse_evals.regression import Threshold, check_report, load_thresholds, run_gate

REPORT = {
    "report": "retrieval-ablation-v1",
    "results": {"hybrid": {"chunk:mrr@10": 0.6432, "chunk:hit@5": 0.83}},
}


def t(metric="chunk:mrr@10", min_score=0.6, mode="hybrid"):
    return Threshold(report="retrieval-ablation-v1", mode=mode, metric=metric, min_score=min_score)


def test_check_report_passes_above_threshold():
    assert check_report(REPORT, t()) is None


def test_check_report_fails_below_threshold():
    violation = check_report(REPORT, t(min_score=0.7))
    assert violation is not None and "0.6432 < min 0.7" in violation


def test_missing_data_is_a_violation_not_a_pass():
    for report, threshold, expected in [
        (None, t(), "report missing"),
        (REPORT, t(mode="chat"), "mode missing"),
        (REPORT, t(metric="chunk:ndcg@10"), "metric missing"),
    ]:
        violation = check_report(report, threshold)
        assert violation is not None and expected in violation


def test_run_gate_end_to_end(tmp_path: Path):
    (tmp_path / "retrieval-ablation-v1-summary.json").write_text(json.dumps(REPORT))
    passing = [t(), t(metric="chunk:hit@5", min_score=0.78)]
    assert run_gate(tmp_path, passing) == []
    failing = [*passing, t(min_score=0.99)]
    assert len(run_gate(tmp_path, failing)) == 1


def test_repo_thresholds_file_is_valid_and_currently_green():
    root = Path(__file__).resolve().parents[3]
    thresholds = load_thresholds(root / "evalsets" / "regression-thresholds.json")
    assert thresholds, "thresholds file must not be empty"
    assert run_gate(root / "docs" / "reports", thresholds) == []
