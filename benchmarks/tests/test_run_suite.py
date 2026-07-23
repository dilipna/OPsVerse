"""Unit tests for the measurement-session aggregation.

The networked parts of `run_suite.py` need a served model; everything that
turns raw timings into a reportable claim must be correct without one, because
those are the functions whose output ends up in a committed report.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bench_run_suite", REPO / "benchmarks" / "run_suite.py"
)
assert SPEC and SPEC.loader
run_suite = importlib.util.module_from_spec(SPEC)
sys.modules["bench_run_suite"] = run_suite
SPEC.loader.exec_module(run_suite)

RequestResult = run_suite.RequestResult
SuiteConfig = run_suite.SuiteConfig
batching_efficiency = run_suite.batching_efficiency
json_parse_rate = run_suite.json_parse_rate
suite_metadata = run_suite.suite_metadata
summarize_prefix_probe = run_suite.summarize_prefix_probe


def level(concurrency: int, *, throughput: float, p95: float, ok: int = 8) -> dict:
    return {
        "concurrency": concurrency,
        "requests": 8,
        "ok": ok,
        "errors": 8 - ok,
        "ttft_s": {"p50": 0.1, "p95": 0.2},
        "itl_s": {"p50": 0.01, "p95": 0.02},
        "latency_s": {"p50": p95 / 2, "p95": p95},
        "tokens_per_s_per_req": {"p50": 20.0, "p95": 25.0},
        "throughput_tokens_s": throughput,
    }


class TestJsonParseRate:
    def test_counts_only_json_objects(self):
        assert json_parse_rate(['{"a": 1}', "not json"]) == 0.5

    def test_unwraps_fenced_blocks(self):
        # A fenced-but-valid object is a formatting quirk, not a structure
        # failure; counting it as a failure would overstate guided decoding's win.
        assert json_parse_rate(['```json\n{"a": 1}\n```']) == 1.0

    def test_bare_array_is_not_an_object(self):
        # The probe's schema is an object; a top-level array is not usable output.
        assert json_parse_rate(["[1, 2, 3]"]) == 0.0

    def test_empty_input_is_zero_not_a_crash(self):
        assert json_parse_rate([]) == 0.0
        assert json_parse_rate([""]) == 0.0


class TestPrefixProbe:
    def test_reports_reduction_from_warm_p50(self):
        cold = RequestResult(ttft_s=1.0, latency_s=2.0, output_tokens=10, ok=True)
        warm = [
            RequestResult(ttft_s=t, latency_s=2.0, output_tokens=10, ok=True)
            for t in (0.4, 0.5, 0.6)
        ]
        result = summarize_prefix_probe(cold, warm)
        assert result["measured"] is True
        assert result["warm_ttft_s_p50"] == 0.5
        assert result["ttft_reduction"] == 0.5

    def test_noise_does_not_become_negative_speedup(self):
        # A warm request is never legitimately slower; noise must clamp to "no benefit"
        # rather than being reported as a negative improvement.
        cold = RequestResult(ttft_s=0.4, latency_s=2.0, output_tokens=10, ok=True)
        warm = [RequestResult(ttft_s=0.5, latency_s=2.0, output_tokens=10, ok=True)]
        assert summarize_prefix_probe(cold, warm)["ttft_reduction"] == 0.0

    def test_failed_cold_request_is_not_measured(self):
        cold = RequestResult(ttft_s=None, latency_s=2.0, output_tokens=0, ok=False)
        warm = [RequestResult(ttft_s=0.5, latency_s=2.0, output_tokens=10, ok=True)]
        assert summarize_prefix_probe(cold, warm)["measured"] is False

    def test_no_successful_warm_requests_is_not_measured(self):
        cold = RequestResult(ttft_s=1.0, latency_s=2.0, output_tokens=10, ok=True)
        warm = [RequestResult(ttft_s=None, latency_s=2.0, output_tokens=0, ok=False)]
        assert summarize_prefix_probe(cold, warm)["measured"] is False


class TestBatchingEfficiency:
    def test_scaling_and_inflation_across_the_sweep(self):
        levels = [
            level(1, throughput=20.0, p95=2.0),
            level(4, throughput=60.0, p95=3.0),
            level(16, throughput=100.0, p95=8.0),
        ]
        result = batching_efficiency(levels)
        assert result["measured"] is True
        assert result["from_concurrency"] == 1
        assert result["to_concurrency"] == 16
        assert result["throughput_scaling"] == 5.0
        assert result["p95_latency_inflation"] == 4.0

    def test_serialized_server_shows_no_scaling(self):
        # A server without continuous batching: throughput flat, latency linear.
        levels = [level(1, throughput=20.0, p95=2.0), level(8, throughput=20.0, p95=16.0)]
        result = batching_efficiency(levels)
        assert result["throughput_scaling"] == 1.0
        assert result["p95_latency_inflation"] == 8.0

    def test_levels_with_zero_successes_are_ignored(self):
        levels = [level(1, throughput=20.0, p95=2.0), level(16, throughput=0.0, p95=0.0, ok=0)]
        assert batching_efficiency(levels)["measured"] is False

    def test_single_level_cannot_show_scaling(self):
        assert batching_efficiency([level(1, throughput=20.0, p95=2.0)])["measured"] is False

    def test_empty_sweep_is_not_measured(self):
        assert batching_efficiency([])["measured"] is False


class TestSuiteMetadata:
    def test_stamps_the_identity_a_report_needs(self):
        meta = suite_metadata(
            SuiteConfig(base_url="http://x/v1", model="OpsLM-v1", engine="vllm", quant="awq")
        )
        for key in ("engine", "quant", "model", "endpoint", "measured_at", "gpu"):
            assert key in meta, f"reports quote {key}; a file without it is uninterpretable"
        assert meta["engine"] == "vllm"
        assert meta["quant"] == "awq"

    def test_extra_fields_are_merged(self):
        meta = suite_metadata(
            SuiteConfig(
                base_url="http://x/v1",
                model="m",
                engine="ollama",
                quant="q4_k_m",
                extra={"vllm_version": "0.6.3"},
            )
        )
        assert meta["vllm_version"] == "0.6.3"
