"""Quality-vs-latency Pareto frontier for quantization configs."""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "frontier", REPO / "benchmarks" / "techniques" / "frontier.py"
)
assert SPEC and SPEC.loader
frontier = importlib.util.module_from_spec(SPEC)
sys.modules["frontier"] = frontier
SPEC.loader.exec_module(frontier)

ConfigPoint = frontier.ConfigPoint
pareto_frontier = frontier.pareto_frontier
knee_point = frontier.knee_point
frontier_table = frontier.frontier_table


def test_dominated_config_is_dropped():
    pts = [
        ConfigPoint("fp16", latency_ms=100.0, quality=0.99),
        ConfigPoint("q8", latency_ms=70.0, quality=0.98),
        ConfigPoint("q4", latency_ms=40.0, quality=0.94),
        # strictly worse than q8 on both axes -> dominated, must be dropped
        ConfigPoint("bad", latency_ms=80.0, quality=0.95),
    ]
    labels = {p.label for p in pareto_frontier(pts)}
    assert labels == {"fp16", "q8", "q4"}
    assert "bad" not in labels


def test_all_on_frontier_when_none_dominates():
    pts = [
        ConfigPoint("a", latency_ms=30.0, quality=0.90),
        ConfigPoint("b", latency_ms=60.0, quality=0.95),
        ConfigPoint("c", latency_ms=90.0, quality=0.99),
    ]
    assert len(pareto_frontier(pts)) == 3  # a classic latency/quality trade-off


def test_knee_prefers_balanced_config():
    pts = [
        ConfigPoint("fp16", latency_ms=100.0, quality=0.99),
        ConfigPoint("q8", latency_ms=55.0, quality=0.975),  # balanced knee
        ConfigPoint("q4", latency_ms=40.0, quality=0.90),
    ]
    assert knee_point(pareto_frontier(pts)).label == "q8"
    assert knee_point([]) is None


def test_table_marks_frontier_recommendation_and_floor():
    pts = [
        ConfigPoint("fp16", latency_ms=100.0, quality=0.99),
        ConfigPoint("q8", latency_ms=55.0, quality=0.975),
        ConfigPoint("q4", latency_ms=40.0, quality=0.90),
        ConfigPoint("dominated", latency_ms=80.0, quality=0.93),
    ]
    rows = frontier_table(pts, quality_floor=0.95)
    by_label = {r["label"]: r for r in rows}

    assert rows[0]["label"] == "q4"  # sorted fastest-first
    assert by_label["dominated"]["on_frontier"] is False
    assert by_label["q8"]["recommended"] is True
    assert by_label["q4"]["meets_floor"] is False  # 0.90 < 0.95 floor
    assert by_label["fp16"]["meets_floor"] is True
    assert sum(r["recommended"] for r in rows) == 1  # exactly one recommendation
