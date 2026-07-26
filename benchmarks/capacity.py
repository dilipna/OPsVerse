"""Turn raw serving measurements into the capacity answers an operator needs.

`report.py` answers "what did each engine do?". This answers the three
questions that actually decide a deployment, using the same committed JSON:

1. **SLO-constrained goodput.** Raw throughput counts tokens the user may have
   already given up waiting for. Goodput counts only throughput delivered at a
   concurrency level that still meets a latency SLO. An engine that is fast at
   a concurrency nobody can be served at has a goodput of zero there.

2. **Cost per million tokens.** Throughput becomes a budget only after it is
   divided by what the hardware costs. The GPU hourly rate is an *assumption*
   supplied on the command line, never measured here, and is labelled as such
   in the output.

3. **Marginal scaling efficiency / saturation.** Whether the device still has
   headroom at the top of the sweep. If throughput is still climbing when the
   sweep ends, the maximum has *not* been found and must not be reported as if
   it had.

It also emits a measurement-confidence section: the `n` behind every probe and
an empirical repeatability bound derived from repeated runs of the same
configuration. A number without its `n` is an anecdote; this file refuses to
print one without the other.

    python benchmarks/capacity.py --results benchmarks/results \\
        --slo-ttft-p95 1.0 --slo-latency-p95 30 --gpu-cost-per-hour 0.35 \\
        --out docs/reports/capacity-and-slo-v1.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

SECONDS_PER_HOUR = 3600
TOKENS_PER_MILLION = 1_000_000

# Below this marginal efficiency, added concurrency is buying little enough
# throughput that the device is treated as approaching saturation.
SATURATION_EFFICIENCY = 0.25


@dataclass(frozen=True)
class Slo:
    """A latency contract. Both bounds must hold for a level to be serviceable."""

    ttft_p95_s: float
    latency_p95_s: float

    def describe(self) -> str:
        return f"p95 TTFT ≤ {self.ttft_p95_s:g}s and p95 end-to-end ≤ {self.latency_p95_s:g}s"

    def admits(self, level: dict[str, Any]) -> bool:
        return (
            level["ttft_s"]["p95"] <= self.ttft_p95_s
            and level["latency_s"]["p95"] <= self.latency_p95_s
        )


def config_label(session: dict[str, Any]) -> str:
    return f"{session['meta']['engine']}/{session['meta']['quant']}"


def is_control(session: dict[str, Any]) -> bool:
    """Diagnostic runs exist to isolate one variable, not to serve traffic.

    They are deliberately partial sweeps, so including them in a "best vs worst"
    comparison manufactures a flattering ratio out of a missing measurement.
    They stay in the tables and stay out of the headline.
    """
    return "CONTROL" in str(session["meta"].get("notes", "")).upper()


def sorted_levels(session: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(session.get("levels", []), key=lambda level: level["concurrency"])


def serviceable_levels(session: dict[str, Any], slo: Slo) -> list[dict[str, Any]]:
    return [level for level in sorted_levels(session) if slo.admits(level)]


def goodput(session: dict[str, Any], slo: Slo) -> tuple[int, float] | None:
    """Best (concurrency, throughput) among levels that meet the SLO.

    Returns None when no measured level meets it — reported as a real failure
    rather than silently falling back to the fastest level.
    """
    admitted = serviceable_levels(session, slo)
    if not admitted:
        return None
    best = max(admitted, key=lambda level: level["throughput_tokens_s"])
    return best["concurrency"], best["throughput_tokens_s"]


def cost_per_million_tokens(throughput_tokens_s: float, gpu_cost_per_hour: float) -> float | None:
    if throughput_tokens_s <= 0:
        return None
    tokens_per_hour = throughput_tokens_s * SECONDS_PER_HOUR
    return gpu_cost_per_hour / (tokens_per_hour / TOKENS_PER_MILLION)


def scaling_steps(session: dict[str, Any]) -> list[dict[str, Any]]:
    """Marginal throughput efficiency between adjacent concurrency levels.

    efficiency = throughput_ratio / concurrency_ratio. 1.0 is linear scaling;
    above 1.0 means the lower level was leaving the device idle.
    """
    steps = []
    levels = sorted_levels(session)
    for lower, upper in pairwise(levels):
        conc_ratio = upper["concurrency"] / lower["concurrency"]
        low_tp = lower["throughput_tokens_s"]
        if conc_ratio <= 0 or low_tp <= 0:
            continue
        tp_ratio = upper["throughput_tokens_s"] / low_tp
        steps.append(
            {
                "from": lower["concurrency"],
                "to": upper["concurrency"],
                "throughput_ratio": tp_ratio,
                "efficiency": tp_ratio / conc_ratio,
            }
        )
    return steps


def saturation_verdict(session: dict[str, Any]) -> str:
    """Whether the sweep actually found the device's ceiling."""
    steps = scaling_steps(session)
    if not steps:
        return "not assessable (needs ≥2 concurrency levels)"
    last = steps[-1]
    top = sorted_levels(session)[-1]["concurrency"]
    if last["efficiency"] >= SATURATION_EFFICIENCY:
        return (
            f"**not saturated** — throughput still rising at c={top} "
            f"({last['efficiency'] * 100:.0f}% marginal efficiency). Peak throughput is "
            f"un-measured; the sweep ended before the device did."
        )
    return (
        f"saturated by c={top} — the last step returned only "
        f"{last['efficiency'] * 100:.0f}% marginal efficiency."
    )


def repeatability(sessions: list[dict[str, Any]]) -> list[str]:
    """Spread between independent runs of the same engine at the same concurrency.

    Different configurations of one engine still share a decode path, so where
    two runs measure the same concurrency they bound run-to-run noise — which
    is the only honest basis for saying whether a single-run delta is real.
    """
    by_key: dict[tuple[str, int], list[tuple[str, dict[str, Any]]]] = {}
    for session in sessions:
        engine = session["meta"]["engine"]
        for level in sorted_levels(session):
            by_key.setdefault((engine, level["concurrency"]), []).append(
                (config_label(session), level)
            )

    rows = []
    for (engine, conc), entries in sorted(by_key.items()):
        if len(entries) < 2:
            continue
        values = [level["throughput_tokens_s"] for _, level in entries]
        lo, hi = min(values), max(values)
        if lo <= 0:
            continue
        spread = (hi - lo) / lo
        labels = ", ".join(f"`{label}`" for label, _ in entries)
        rows.append(
            f"| {engine} | c={conc} | {labels} | "
            f"{lo:.2f} - {hi:.2f} tok/s | **+/-{spread * 100:.0f}%** |"
        )
    return rows


def probe_sample_sizes(sessions: list[dict[str, Any]]) -> list[str]:
    """Every probe's n, stated next to its headline number."""
    rows = []
    for session in sessions:
        label = config_label(session)
        prefix = session.get("prefix_cache", {})
        if prefix.get("measured"):
            rows.append(
                f"| `{label}` | prefix-cache TTFT reduction | "
                f"{prefix['ttft_reduction'] * 100:.1f}% | "
                f"n={prefix.get('warm_requests', '?')} warm vs 1 cold |"
            )
        structured = session.get("structured_output", {})
        guided_on = structured.get("guided_on") or {}
        if guided_on:
            rows.append(
                f"| `{label}` | guided JSON parse rate | "
                f"{guided_on.get('json_parse_rate')} | n={guided_on.get('n', '?')} |"
            )
        for level in sorted_levels(session):
            rows.append(
                f"| `{label}` | throughput @ c={level['concurrency']} | "
                f"{level['throughput_tokens_s']:.2f} tok/s | "
                f"n={level.get('requests', '?')} requests |"
            )
    return rows


def render(sessions: list[dict[str, Any]], slo: Slo, gpu_cost_per_hour: float) -> str:
    if not sessions:
        raise SystemExit("no result files found — run benchmarks/run_suite.py first")

    hardware = sorted({str(s["meta"].get("gpu") or "CPU") for s in sessions})
    out = [
        "# Capacity & SLO analysis — OpsLM serving",
        "",
        "> Generated by `benchmarks/capacity.py` from the same committed session JSON",
        "> in `benchmarks/results/` that produces `inference-benchmark-v1.md`. No number",
        "> here is hand-entered. The GPU hourly rate is the one assumption, and it is",
        "> flagged wherever it is used.",
        "",
        f"- **Hardware:** {', '.join(hardware)}",
        f"- **SLO:** {slo.describe()}",
        f"- **Assumed GPU cost:** ${gpu_cost_per_hour:.2f}/hour "
        "*(assumption, not a measurement — pass `--gpu-cost-per-hour` to change it)*",
        "",
        "## 1. SLO-constrained goodput",
        "",
        "Raw throughput counts tokens generated for requests the user may have already",
        "abandoned. **Goodput** counts only throughput delivered at a concurrency that",
        "still meets the SLO. This is the number that decides how many users one GPU",
        "actually serves.",
        "",
        "| Config | Max serviceable concurrency | Goodput | Cost / 1M tokens "
        "| Levels passing SLO |",
        "|---|---|---|---|---|",
    ]

    by_engine: dict[str, tuple[str, float]] = {}
    for session in sessions:
        label = config_label(session)
        levels = sorted_levels(session)
        passing = serviceable_levels(session, slo)
        passing_desc = (
            ", ".join(f"c={level['concurrency']}" for level in passing) if passing else "**none**"
        )
        control_tag = " *(control)*" if is_control(session) else ""
        result = goodput(session, slo)
        if result is None:
            out.append(
                f"| `{label}`{control_tag} | **none** | — | — | {passing_desc} of "
                f"{len(levels)} measured |"
            )
            continue
        conc, tput = result
        if not is_control(session):
            engine = session["meta"]["engine"]
            if engine not in by_engine or tput > by_engine[engine][1]:
                by_engine[engine] = (label, tput)
        cost = cost_per_million_tokens(tput, gpu_cost_per_hour)
        cost_cell = f"${cost:.2f}" if cost is not None else "—"
        out.append(
            f"| `{label}`{control_tag} | **c={conc}** | **{tput:.2f} tok/s** | {cost_cell} | "
            f"{passing_desc} of {len(levels)} measured |"
        )

    out.append("")
    if len(by_engine) >= 2:
        ranked = sorted(by_engine.values(), key=lambda pair: pair[1], reverse=True)
        (best_label, best_tp), (worst_label, worst_tp) = ranked[0], ranked[-1]
        best_cost = cost_per_million_tokens(best_tp, gpu_cost_per_hour)
        worst_cost = cost_per_million_tokens(worst_tp, gpu_cost_per_hour)
        out += [
            f"**`{best_label}` delivers {best_tp / worst_tp:.1f}x the goodput of "
            f"`{worst_label}` under this SLO** — and at ${best_cost:.2f} vs "
            f"${worst_cost:.2f} per million tokens, the same ratio in cost.",
            "",
            "This is a *different, smaller* number than the headline throughput-scaling",
            "figure, and it is the more defensible one: it is the advantage that survives",
            "holding both engines to the same user-facing latency contract. Control runs are",
            "excluded from this comparison — they are partial sweeps by design, so ranking",
            "them against a full sweep would manufacture a ratio out of a missing measurement.",
            "",
        ]

    out += ["## 2. Scaling efficiency — did the sweep find the ceiling?", ""]
    out += [
        "Marginal efficiency = throughput ratio ÷ concurrency ratio between adjacent",
        "levels. 1.0 is linear; **above 1.0 means the lower level was leaving the GPU",
        "idle**, which is the signature of a device waiting on a single sequence.",
        "",
        "| Config | Step | Throughput ratio | Marginal efficiency |",
        "|---|---|---|---|",
    ]
    for session in sessions:
        label = config_label(session)
        for step in scaling_steps(session):
            out.append(
                f"| `{label}` | c={step['from']}→{step['to']} | "
                f"{step['throughput_ratio']:.2f}x | {step['efficiency'] * 100:.0f}% |"
            )
    out.append("")
    for session in sessions:
        if len(sorted_levels(session)) >= 2:
            out.append(f"- `{config_label(session)}`: {saturation_verdict(session)}")
    out.append("")

    out += [
        "## 3. Measurement confidence",
        "",
        "Every headline number with the `n` it rests on. Small `n` is not hidden here;",
        "it is the first thing a reviewer should be able to check.",
        "",
        "| Config | Metric | Value | n |",
        "|---|---|---|---|",
        *probe_sample_sizes(sessions),
        "",
    ]

    repeat_rows = repeatability(sessions)
    if repeat_rows:
        out += [
            "### Run-to-run repeatability",
            "",
            "Where two independent sessions measured the same engine at the same",
            "concurrency, their spread bounds the noise floor. **A single-run difference",
            "smaller than this spread is not evidence of anything.**",
            "",
            "| Engine | Concurrency | Sessions | Throughput range | Spread |",
            "|---|---|---|---|---|",
            *repeat_rows,
            "",
        ]

    out += [
        "## What this analysis does not establish",
        "",
        "- **Peak throughput is unknown** for any configuration whose sweep ended while",
        "  still scaling — the ceiling is above the last measured point, not at it.",
        "- **One GPU, one model, one prompt shape.** Nothing here generalizes to a",
        "  different sequence-length mix without re-measurement.",
        "- **Cost is arithmetic on an assumed hourly rate**, not an observed bill.",
        "- **Output tokens are approximated by streamed-chunk count** (see `harness.py`),",
        "  so absolute tok/s carries that approximation; ratios between engines do not,",
        "  because the approximation is identical on both sides.",
        "",
    ]
    return "\n".join(out) + "\n"


def load_sessions(results_dir: Path) -> list[dict[str, Any]]:
    sessions = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}: not valid JSON ({exc})") from exc
        if "meta" not in data:
            raise SystemExit(f"{path}: missing 'meta' — produced by an older harness?")
        data["_file"] = path.name
        sessions.append(data)
    return sorted(sessions, key=lambda s: s["meta"].get("measured_at", ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("benchmarks/results"))
    parser.add_argument("--slo-ttft-p95", type=float, default=1.0)
    parser.add_argument("--slo-latency-p95", type=float, default=30.0)
    parser.add_argument("--gpu-cost-per-hour", type=float, default=0.35)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    sessions = load_sessions(args.results)
    markdown = render(
        sessions,
        Slo(ttft_p95_s=args.slo_ttft_p95, latency_p95_s=args.slo_latency_p95),
        args.gpu_cost_per_hour,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    print(f"wrote {args.out} from {len(sessions)} session(s)")


if __name__ == "__main__":
    main()
