"""Unit tests for the model registry loader and join logic.

The properties under test are honesty properties, same as the benchmark report:
an unmeasured field must render as `pending` (never a stale or assumed number),
a measured field must come from the newest matching artifact, and a structurally
broken registry must fail loudly rather than render a half-table.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("registry_mod", REPO / "registry" / "registry.py")
assert SPEC and SPEC.loader
registry = importlib.util.module_from_spec(SPEC)
sys.modules["registry_mod"] = registry
SPEC.loader.exec_module(registry)


def bench_session(engine: str, quant: str, *, latency: float, measured_at: str) -> dict:
    return {
        "meta": {"engine": engine, "quant": quant, "measured_at": measured_at, "gpu": "Tesla T4"},
        "levels": [
            {
                "concurrency": 1,
                "ok": 8,
                "errors": 0,
                "latency_s": {"p50": latency, "p95": latency * 1.5},
                "throughput_tokens_s": 40.0,
            },
            {"concurrency": 16, "ok": 8, "errors": 0, "throughput_tokens_s": 300.0},
        ],
    }


class TestMatchBenchmark:
    def test_matches_on_engine_and_quant(self):
        sessions = [bench_session("vllm", "fp16", latency=1.0, measured_at="2026-07-24T00:00:00Z")]
        got = registry.match_benchmark({"engine": "vllm", "quant": "fp16"}, sessions)
        assert got is sessions[0]

    def test_null_key_matches_nothing(self):
        # A dropped variant (awq) has benchmark_key: null and must never bind to a file.
        sessions = [bench_session("vllm", "awq", latency=1.0, measured_at="2026-07-24T00:00:00Z")]
        assert registry.match_benchmark(None, sessions) is None

    def test_newest_measurement_wins(self):
        old = bench_session("vllm", "fp16", latency=2.0, measured_at="2026-01-01T00:00:00Z")
        new = bench_session("vllm", "fp16", latency=1.0, measured_at="2026-07-24T00:00:00Z")
        got = registry.match_benchmark({"engine": "vllm", "quant": "fp16"}, [old, new])
        assert got is new

    def test_no_match_returns_none(self):
        sessions = [bench_session("ollama", "q4_k_m", latency=1.0, measured_at="2026-07-24Z")]
        assert registry.match_benchmark({"engine": "vllm", "quant": "fp16"}, sessions) is None


class TestBenchmarkSummary:
    def test_unmeasured_is_pending_not_zero(self):
        summary = registry.benchmark_summary(None)
        assert summary == {"latency_p50": "pending", "throughput": "pending"}

    def test_measured_reports_latency_and_top_throughput(self):
        session = bench_session("vllm", "fp16", latency=1.5, measured_at="2026-07-24T00:00:00Z")
        summary = registry.benchmark_summary(session)
        assert summary["latency_p50"] == "1.50s"
        assert summary["throughput"] == "300 tok/s @ c16"


class TestEvalLabel:
    def test_pending_when_no_report(self):
        assert "pending" in registry.eval_label({"eval": {"report": None}})

    def test_pending_when_report_missing(self):
        label = registry.eval_label({"eval": {"report": "docs/reports/does-not-exist.json"}})
        assert "pending" in label and "not found" in label

    def test_reads_score_from_existing_report(self, tmp_path, monkeypatch):
        report = tmp_path / "opslm-before-after.json"
        report.write_text(json.dumps({"score": 0.91}), encoding="utf-8")
        monkeypatch.setattr(registry, "REPO", tmp_path)
        assert registry.eval_label({"eval": {"report": "opslm-before-after.json"}}) == "0.91"


class TestLoadRegistry:
    def test_rejects_missing_model_fields(self, tmp_path):
        (tmp_path / "m.json").write_text(json.dumps({"models": [{"name": "x"}]}), encoding="utf-8")
        with pytest.raises(SystemExit, match="missing"):
            registry.load_registry(tmp_path / "m.json")

    def test_rejects_missing_variant_fields(self, tmp_path):
        bad = {
            "models": [
                {
                    "name": "x",
                    "version": "1",
                    "status": "production",
                    "base_model": "b",
                    "variants": [{"quant": "fp16"}],
                }
            ]
        }
        (tmp_path / "m.json").write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(SystemExit, match="variant"):
            registry.load_registry(tmp_path / "m.json")

    def test_rejects_empty_models(self, tmp_path):
        (tmp_path / "m.json").write_text(json.dumps({"models": []}), encoding="utf-8")
        with pytest.raises(SystemExit, match="non-empty"):
            registry.load_registry(tmp_path / "m.json")

    def test_loads_the_committed_registry(self):
        # The real registry must always be valid — this is the CI guard.
        models = registry.load_registry(registry.DEFAULT_REGISTRY)
        names = {m["name"] for m in models}
        assert "OpsLM-v1" in names


class TestRender:
    def test_dropped_variant_shows_pending_not_a_number(self):
        models = registry.load_registry(registry.DEFAULT_REGISTRY)
        out = registry.render(models, [])  # no benchmark sessions yet
        assert "# Model registry" in out
        assert "pending" in out
        # the AWQ note must survive into the rendered doc
        assert "AutoAWQ" in out

    def test_measured_variant_shows_the_number(self):
        models = registry.load_registry(registry.DEFAULT_REGISTRY)
        session = bench_session("vllm", "fp16", latency=0.8, measured_at="2026-07-24T00:00:00Z")
        out = registry.render(models, [session])
        assert "0.80s" in out
