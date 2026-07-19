"""Unit tests for the benchmark measurement math (the part that must be
correct regardless of which GPU server produced the raw timings)."""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bench_harness", REPO / "benchmarks" / "harness.py")
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
# register before exec: @dataclass resolves its module via sys.modules
sys.modules["bench_harness"] = harness
SPEC.loader.exec_module(harness)

RequestResult = harness.RequestResult
percentile = harness.percentile
summarize = harness.summarize


def test_percentile_interpolates():
    assert percentile([], 50) == 0.0
    assert percentile([5.0], 95) == 5.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert percentile([1.0, 2.0, 3.0, 4.0], 0) == 1.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 100) == 4.0


def test_tokens_per_s():
    assert RequestResult(0.1, 2.0, 100, ok=True).tokens_per_s == 50.0
    # guard against divide-by-zero
    assert RequestResult(None, 0.0, 0, ok=True).tokens_per_s == 0.0


def test_summarize_excludes_errors_and_computes_throughput():
    results = [
        RequestResult(ttft_s=0.10, latency_s=1.0, output_tokens=100, ok=True),
        RequestResult(ttft_s=0.20, latency_s=2.0, output_tokens=200, ok=True),
        RequestResult(ttft_s=None, latency_s=0.5, output_tokens=0, ok=False),  # error, dropped
    ]
    summary = summarize(results, wall_clock_s=2.0)
    assert summary == {
        "requests": 3,
        "ok": 2,
        "errors": 1,
        "ttft_s": {"p50": 0.15, "p95": 0.195},
        "latency_s": {"p50": 1.5, "p95": 1.95},
        "tokens_per_s_per_req": {"p50": 100.0, "p95": 100.0},
        # 300 output tokens over 2.0s wall clock; errors contribute 0 tokens
        "throughput_tokens_s": 150.0,
    }


def test_summarize_empty_is_safe():
    summary = summarize([], wall_clock_s=0.0)
    assert summary["ok"] == 0
    assert summary["throughput_tokens_s"] == 0.0
    assert summary["ttft_s"] == {"p50": 0.0, "p95": 0.0}
