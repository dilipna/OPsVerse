"""Unit tests for report rendering.

The report is the artifact a reviewer actually reads, so the properties under
test are honesty properties: a configuration without a quality score must not
silently reach the frontier, and a missing measurement must render as "not
measured" rather than as a zero.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bench_report", REPO / "benchmarks" / "report.py")
assert SPEC and SPEC.loader
report = importlib.util.module_from_spec(SPEC)
sys.modules["bench_report"] = report
SPEC.loader.exec_module(report)


def session(engine: str, quant: str, *, latency_p50: float, quality_probe: bool = True) -> dict:
    data = {
        "_file": f"{engine}-{quant}.json",
        "meta": {
            "engine": engine,
            "quant": quant,
            "model": "OpsLM-v1",
            "endpoint": "http://localhost:8000/v1",
            "measured_at": "2026-07-23T10:00:00Z",
            "gpu": "Tesla T4",
            "notes": "",
        },
        "levels": [
            {
                "concurrency": 1,
                "requests": 8,
                "ok": 8,
                "errors": 0,
                "ttft_s": {"p50": 0.15, "p95": 0.3},
                "itl_s": {"p50": 0.02, "p95": 0.03},
                "latency_s": {"p50": latency_p50, "p95": latency_p50 * 1.5},
                "tokens_per_s_per_req": {"p50": 20.0, "p95": 25.0},
                "throughput_tokens_s": 40.0,
            }
        ],
        "batching": {
            "measured": True,
            "from_concurrency": 1,
            "to_concurrency": 16,
            "throughput_scaling": 4.2,
            "p95_latency_inflation": 3.1,
        },
    }
    if quality_probe:
        data["prefix_cache"] = {"measured": True, "ttft_reduction": 0.42}
        data["structured_output"] = {
            "guided_off": {"json_parse_rate": 0.75},
            "guided_on": {"json_parse_rate": 1.0},
        }
    return data


class TestFrontier:
    def test_dominated_config_is_marked_off_frontier(self):
        sessions = [
            session("vllm", "fp16", latency_p50=2.0),
            session("vllm", "awq", latency_p50=1.0),
        ]
        # awq is both faster and better -> fp16 is strictly dominated.
        rows, warnings = report.build_frontier(sessions, {"fp16": 0.90, "awq": 0.94}, 1)
        body = "\n".join(rows)
        assert "`vllm/awq`" in body
        assert not warnings
        awq_row = next(r for r in rows if "vllm/awq" in r)
        fp16_row = next(r for r in rows if "vllm/fp16" in r)
        assert "| yes |" in awq_row
        assert "| no |" in fp16_row

    def test_config_without_quality_is_excluded_and_warned_about(self):
        sessions = [
            session("vllm", "fp16", latency_p50=2.0),
            session("ollama", "q4_k_m", latency_p50=0.5),
        ]
        rows, warnings = report.build_frontier(sessions, {"fp16": 0.90}, 1)
        body = "\n".join(rows)
        # Without this, the fastest config wins the frontier purely by being fast.
        assert "q4_k_m" not in body
        assert warnings and "ollama/q4_k_m" in warnings[0]

    def test_quality_can_be_keyed_by_engine_and_quant(self):
        sessions = [session("vllm", "fp16", latency_p50=2.0)]
        rows, warnings = report.build_frontier(sessions, {"vllm/fp16": 0.9}, 1)
        assert rows and not warnings

    def test_no_quality_scores_yields_no_frontier(self):
        rows, warnings = report.build_frontier([session("vllm", "fp16", latency_p50=2.0)], {}, 1)
        assert rows == []
        assert warnings


class TestTables:
    def test_unmeasured_probe_renders_as_text_not_zero(self):
        rows = report.probe_table([session("vllm", "fp16", latency_p50=1.0, quality_probe=False)])
        body = "\n".join(rows)
        assert "not measured" in body
        assert "0.0%" not in body

    def test_latency_table_skips_missing_concurrency_level(self):
        assert report.latency_table([session("vllm", "fp16", latency_p50=1.0)], 999) == []

    def test_render_reports_hardware_and_date(self):
        out = report.render([session("vllm", "fp16", latency_p50=1.0)], {"fp16": 0.9}, [1])
        assert "Tesla T4" in out
        assert "2026-07-23" in out


class TestLoading:
    def test_rejects_files_without_meta(self, tmp_path):
        (tmp_path / "old.json").write_text(json.dumps({"levels": []}), encoding="utf-8")
        with pytest.raises(SystemExit, match="missing 'meta'"):
            report.load_sessions(tmp_path)

    def test_rejects_invalid_json(self, tmp_path):
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(SystemExit, match="not valid JSON"):
            report.load_sessions(tmp_path)

    def test_orders_by_measurement_time(self, tmp_path):
        older = session("vllm", "awq", latency_p50=1.0)
        older["meta"]["measured_at"] = "2026-01-01T00:00:00Z"
        newer = session("vllm", "fp16", latency_p50=2.0)
        (tmp_path / "a-newer.json").write_text(json.dumps(newer), encoding="utf-8")
        (tmp_path / "z-older.json").write_text(json.dumps(older), encoding="utf-8")
        loaded = report.load_sessions(tmp_path)
        assert [s["meta"]["quant"] for s in loaded] == ["awq", "fp16"]

    def test_empty_directory_renders_a_clear_error(self, tmp_path):
        with pytest.raises(SystemExit, match="no result files"):
            report.render(report.load_sessions(tmp_path), {}, [1])


class TestQualityParsing:
    def test_rejects_missing_equals(self):
        with pytest.raises(SystemExit, match="key=value"):
            report.parse_quality(["fp16"])

    def test_rejects_non_numeric_score(self):
        with pytest.raises(SystemExit, match="not a number"):
            report.parse_quality(["fp16=high"])

    def test_parses_valid_pairs(self):
        assert report.parse_quality(["fp16=0.94", "awq=0.91"]) == {"fp16": 0.94, "awq": 0.91}
