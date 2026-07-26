"""Unit tests for the capacity/SLO analysis.

The properties under test are honesty properties, matching `test_report.py`:
an engine that meets no SLO level must report "none" rather than quietly
falling back to its fastest level; a sweep that never found the ceiling must
say so; and no headline number may be rendered without its `n`.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bench_capacity", REPO / "benchmarks" / "capacity.py")
assert SPEC and SPEC.loader
capacity = importlib.util.module_from_spec(SPEC)
sys.modules["bench_capacity"] = capacity
SPEC.loader.exec_module(capacity)


def level(concurrency: int, *, tput: float, ttft_p95: float, lat_p95: float, requests: int = 32):
    return {
        "concurrency": concurrency,
        "requests": requests,
        "ok": requests,
        "errors": 0,
        "ttft_s": {"p50": ttft_p95 / 2, "p95": ttft_p95},
        "itl_s": {"p50": 0.02, "p95": 0.03},
        "latency_s": {"p50": lat_p95 / 1.2, "p95": lat_p95},
        "tokens_per_s_per_req": {"p50": 20.0, "p95": 25.0},
        "throughput_tokens_s": tput,
    }


def session(engine: str, quant: str, levels, **extra):
    data = {
        "_file": f"{engine}-{quant}.json",
        "meta": {
            "engine": engine,
            "quant": quant,
            "model": "OpsLM-v1",
            "measured_at": "2026-07-25T00:00:00Z",
            "gpu": "Tesla T4",
        },
        "levels": levels,
    }
    data.update(extra)
    return data


STRICT = capacity.Slo(ttft_p95_s=1.0, latency_p95_s=30.0)


def test_goodput_picks_highest_throughput_level_meeting_slo():
    s = session(
        "vllm",
        "fp16",
        [
            level(1, tput=17.0, ttft_p95=0.12, lat_p95=16.0),
            level(16, tput=233.0, ttft_p95=0.17, lat_p95=13.0),
        ],
    )
    assert capacity.goodput(s, STRICT) == (16, 233.0)


def test_goodput_is_none_when_no_level_meets_slo():
    """The failure must surface, not degrade into the fastest level."""
    s = session("ollama", "q4", [level(4, tput=34.0, ttft_p95=16.9, lat_p95=21.0)])
    assert capacity.goodput(s, STRICT) is None


def test_goodput_excludes_faster_levels_that_violate_slo():
    """A high-throughput level that blows the latency budget must not be chosen."""
    s = session(
        "ollama",
        "q4",
        [
            level(1, tput=37.0, ttft_p95=0.66, lat_p95=5.0),
            level(16, tput=999.0, ttft_p95=64.0, lat_p95=80.0),
        ],
    )
    assert capacity.goodput(s, STRICT) == (1, 37.0)


def test_cost_per_million_tokens_arithmetic():
    # 100 tok/s = 360_000 tok/hour = 0.36M tok/hour; $0.36/hr -> $1.00 per 1M
    assert capacity.cost_per_million_tokens(100.0, 0.36) == 1.0


def test_cost_is_none_for_zero_throughput():
    assert capacity.cost_per_million_tokens(0.0, 0.35) is None


def test_scaling_efficiency_detects_superlinear_step():
    """4x concurrency yielding >4x throughput means the low level was GPU-idle."""
    s = session(
        "vllm",
        "fp16",
        [
            level(1, tput=17.42, ttft_p95=0.12, lat_p95=16.0),
            level(4, tput=89.66, ttft_p95=0.13, lat_p95=11.0),
        ],
    )
    (step,) = capacity.scaling_steps(s)
    assert step["efficiency"] > 1.0


def test_saturation_verdict_flags_unfinished_sweep():
    s = session(
        "vllm",
        "fp16",
        [
            level(4, tput=89.66, ttft_p95=0.13, lat_p95=11.0),
            level(16, tput=233.18, ttft_p95=0.17, lat_p95=13.0),
        ],
    )
    assert "not saturated" in capacity.saturation_verdict(s)


def test_saturation_verdict_reports_flat_engine_as_saturated():
    s = session(
        "ollama",
        "q4",
        [
            level(4, tput=34.61, ttft_p95=16.9, lat_p95=21.0),
            level(16, tput=33.21, ttft_p95=64.6, lat_p95=80.0),
        ],
    )
    assert "saturated by" in capacity.saturation_verdict(s)


def test_repeatability_bounds_noise_across_two_runs():
    sessions = [
        session("vllm", "fp16", [level(1, tput=17.42, ttft_p95=0.12, lat_p95=16.0)]),
        session("vllm", "fp16-noprefix", [level(1, tput=21.32, ttft_p95=0.10, lat_p95=13.0)]),
    ]
    rows = capacity.repeatability(sessions)
    assert len(rows) == 1
    assert "+/-22%" in rows[0]


def test_repeatability_silent_without_a_repeat():
    sessions = [session("vllm", "fp16", [level(1, tput=17.42, ttft_p95=0.12, lat_p95=16.0)])]
    assert capacity.repeatability(sessions) == []


def test_every_probe_row_carries_its_n():
    s = session(
        "vllm",
        "fp16",
        [level(1, tput=17.42, ttft_p95=0.12, lat_p95=16.0, requests=32)],
        prefix_cache={"measured": True, "ttft_reduction": 0.4778, "warm_requests": 4},
        structured_output={"guided_on": {"json_parse_rate": 1.0, "n": 4}},
    )
    rows = capacity.probe_sample_sizes([s])
    assert rows, "expected probe rows"
    for row in rows:
        assert "n=" in row, f"row rendered without its n: {row}"


def test_render_labels_the_cost_assumption():
    """Cost rests on an assumed rate; the report must never present it as measured."""
    s = session("vllm", "fp16", [level(1, tput=17.42, ttft_p95=0.12, lat_p95=16.0)])
    text = capacity.render([s], STRICT, 0.35)
    assert "assumption, not a measurement" in text


def test_control_runs_are_excluded_from_the_headline_comparison():
    """A partial control sweep must not become the 'worst engine' strawman."""
    sessions = [
        session(
            "vllm",
            "fp16",
            [
                level(1, tput=17.42, ttft_p95=0.12, lat_p95=16.0),
                level(16, tput=233.18, ttft_p95=0.17, lat_p95=13.0),
            ],
        ),
        session(
            "vllm",
            "fp16-noprefixcache",
            [level(1, tput=21.32, ttft_p95=0.10, lat_p95=13.0)],
            **{"meta_notes": None},
        ),
        session("ollama", "q4_k_m", [level(1, tput=37.22, ttft_p95=0.66, lat_p95=5.0)]),
    ]
    sessions[1]["meta"]["notes"] = "CONTROL: prefix caching disabled"
    text = capacity.render(sessions, STRICT, 0.35)
    # 233.18 / 37.22 = 6.3x against ollama, NOT 10.9x against the control.
    assert "6.3x the goodput" in text
    assert "10.9x" not in text
    assert "*(control)*" in text


def test_is_control_detects_control_note():
    s = session("vllm", "fp16-noprefixcache", [])
    s["meta"]["notes"] = "CONTROL: prefix caching disabled — isolates the cache effect"
    assert capacity.is_control(s)
    assert not capacity.is_control(session("vllm", "fp16", []))


def test_render_marks_an_engine_that_meets_no_slo_level():
    s = session("ollama", "q4", [level(16, tput=33.21, ttft_p95=64.6, lat_p95=80.0)])
    text = capacity.render([s], STRICT, 0.35)
    assert "**none**" in text
