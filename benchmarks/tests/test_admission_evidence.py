"""Adversarial cases from the audit, evaluated through actual capacity selection."""

import copy

import pytest
from test_capacity import STRICT, capacity, level, session


@pytest.mark.parametrize(
    "patch",
    [
        {"requests": 100, "ok": 1, "errors": 99},
        {"requests": 100, "ok": 0, "errors": 100},
        {"requests": 19, "ok": 19, "errors": 0},
        {"requests": 32, "ok": 32, "errors": 1},
        {"requests": True},
        {"ttft_s": {}},
        {"ttft_s": None},
        {"latency_s": {"p95": float("nan")}},
        {"throughput_tokens_s": float("inf")},
        {"throughput_tokens_s": -1},
        {"ttft_samples": 31},
        {"concurrency": 0},
    ],
)
def test_fast_bad_run_cannot_displace_reliable_run(patch):
    bad = level(16, tput=999, ttft_p95=0.1, lat_p95=1)
    bad.update(patch)
    good = level(1, tput=37, ttft_p95=0.5, lat_p95=5)
    assert capacity.goodput(session("test", "fp16", [good, bad]), STRICT) == (1, 37)
    assert STRICT.reasons(bad)


@pytest.mark.parametrize("missing", ["requests", "ok", "errors", "ttft_s", "latency_s"])
def test_missing_evidence_rejected(missing):
    row = level(1, tput=10, ttft_p95=0.1, lat_p95=1)
    del row[missing]
    assert not STRICT.admits(row)


def identified(run_id):
    s = session("vllm", "fp16", [level(1, tput=20, ttft_p95=0.1, lat_p95=1)])
    s["meta"].update({field: "pinned" for field in capacity.IDENTITY_FIELDS})
    s["meta"].update(engine="vllm", quant="fp16", prefix_caching=True, run_id=run_id)
    return s


def test_matching_runs_report_range_and_deduplicate_run_ids():
    a, b = identified("a"), identified("b")
    b["levels"][0]["throughput_tokens_s"] = 22
    rows = capacity.repeatability([a, b, copy.deepcopy(a)])
    assert len(rows) == 1
    assert "n=2 distinct runs" in rows[0]
    assert "relative range 10.0%" in rows[0]
    assert "+/-" not in rows[0]


@pytest.mark.parametrize("field", capacity.IDENTITY_FIELDS)
def test_each_configuration_dimension_separates_repeats(field):
    a, b = identified("a"), identified("b")
    b["meta"][field] = "different"
    assert capacity.repeatability([a, b]) == []


def test_request_count_separates_repeats():
    a, b = identified("a"), identified("b")
    b["levels"][0].update(requests=64, ok=64)
    assert capacity.repeatability([a, b]) == []


@pytest.mark.parametrize(
    "kwargs", [{"ttft_p95_s": float("nan")}, {"max_error_rate": 1}, {"min_successes": 0}]
)
def test_invalid_policy_rejected(kwargs):
    config = {"ttft_p95_s": 1, "latency_p95_s": 30} | kwargs
    with pytest.raises(ValueError):
        capacity.Slo(**config)
