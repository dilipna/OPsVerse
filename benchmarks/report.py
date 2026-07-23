"""Join measurement-session JSON files into a committed benchmark report.

`run_suite.py` writes one JSON per (engine, quantization). This reads a
directory of them and renders the comparison tables — including the
quality-vs-latency Pareto frontier, which is the artifact that answers "which
configuration should we actually serve?".

Quality is not measured here. It comes from the Phase-4 eval harness run
against the *same* served configuration, supplied via `--quality`:

    python benchmarks/report.py --results benchmarks/results \\
        --quality fp16=0.94 --quality awq=0.91 --quality q4_k_m=0.88 \\
        --out docs/reports/inference-benchmark-v1.md

Configurations without a quality score still appear in the latency tables but
are excluded from the frontier — a speed-only frontier would recommend the
fastest quantization by construction, which is precisely the mistake the
frontier exists to prevent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from techniques.frontier import ConfigPoint, frontier_table


def load_sessions(results_dir: Path) -> list[dict[str, Any]]:
    """Load every *.json in the directory, newest measurement last.

    Sorted by the `measured_at` stamp rather than filename so re-running one
    configuration does not reorder the report.
    """
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


def config_label(session: dict[str, Any]) -> str:
    return f"{session['meta']['engine']}/{session['meta']['quant']}"


def level_at(session: dict[str, Any], concurrency: int) -> dict[str, Any] | None:
    for level in session.get("levels", []):
        if level.get("concurrency") == concurrency:
            return level
    return None


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def latency_table(sessions: list[dict[str, Any]], concurrency: int) -> list[str]:
    """Per-configuration serving metrics at one concurrency level."""
    rows = [
        "| Config | TTFT p50 (s) | TTFT p95 (s) | ITL p50 (s) | Throughput (tok/s) | Errors |",
        "|---|---|---|---|---|---|",
    ]
    for session in sessions:
        level = level_at(session, concurrency)
        if level is None:
            continue
        rows.append(
            f"| `{config_label(session)}` "
            f"| {_fmt(level['ttft_s']['p50'], 3)} "
            f"| {_fmt(level['ttft_s']['p95'], 3)} "
            f"| {_fmt(level['itl_s']['p50'], 4)} "
            f"| {_fmt(level['throughput_tokens_s'])} "
            f"| {level['errors']} |"
        )
    return rows if len(rows) > 2 else []


def batching_table(sessions: list[dict[str, Any]]) -> list[str]:
    rows = [
        "| Config | Sweep | Throughput scaling | p95 latency inflation |",
        "|---|---|---|---|",
    ]
    for session in sessions:
        batching = session.get("batching", {})
        if not batching.get("measured"):
            continue
        sweep = f"{batching['from_concurrency']}→{batching['to_concurrency']}"
        rows.append(
            f"| `{config_label(session)}` | {sweep} "
            f"| {_fmt(batching['throughput_scaling'])}x "
            f"| {_fmt(batching['p95_latency_inflation'])}x |"
        )
    return rows if len(rows) > 2 else []


def probe_table(sessions: list[dict[str, Any]]) -> list[str]:
    rows = [
        "| Config | Prefix-cache TTFT reduction | JSON parse rate (guided off → on) |",
        "|---|---|---|",
    ]
    for session in sessions:
        prefix = session.get("prefix_cache", {})
        prefix_cell = (
            f"{prefix['ttft_reduction'] * 100:.1f}%" if prefix.get("measured") else "not measured"
        )
        structured = session.get("structured_output", {})
        if structured:
            off = structured.get("guided_off", {}).get("json_parse_rate")
            on = structured.get("guided_on", {}).get("json_parse_rate")
            structured_cell = f"{_fmt(off)} → {_fmt(on)}"
        else:
            structured_cell = "not measured"
        rows.append(f"| `{config_label(session)}` | {prefix_cell} | {structured_cell} |")
    return rows if len(rows) > 2 else []


def build_frontier(
    sessions: list[dict[str, Any]], quality: dict[str, float], concurrency: int
) -> tuple[list[str], list[str]]:
    """Render the quality-vs-latency frontier, plus warnings about what was left out.

    Latency axis is p50 total latency at the given concurrency, converted to ms.
    """
    points: list[ConfigPoint] = []
    missing: list[str] = []
    for session in sessions:
        label = config_label(session)
        score = quality.get(session["meta"]["quant"]) or quality.get(label)
        level = level_at(session, concurrency)
        if level is None:
            continue
        if score is None:
            missing.append(label)
            continue
        points.append(
            ConfigPoint(label=label, latency_ms=level["latency_s"]["p50"] * 1000, quality=score)
        )

    warnings = []
    if missing:
        warnings.append(
            f"> Excluded from the frontier (no quality score supplied): "
            f"{', '.join(f'`{m}`' for m in missing)}. "
            f"Run the Phase-4 eval against these configurations and pass `--quality`."
        )
    if not points:
        return [], warnings

    rows = [
        "| Config | Latency p50 (ms) | Quality | On frontier | Recommended |",
        "|---|---|---|---|---|",
    ]
    for row in frontier_table(points):
        rows.append(
            f"| `{row['label']}` | {_fmt(row['latency_ms'], 1)} | {_fmt(row['quality'], 3)} "
            f"| {_fmt(row['on_frontier'])} | {'**yes**' if row['recommended'] else 'no'} |"
        )
    return rows, warnings


def render(
    sessions: list[dict[str, Any]], quality: dict[str, float], concurrency_levels: list[int]
) -> str:
    if not sessions:
        raise SystemExit("no result files found — run benchmarks/run_suite.py first")

    hardware = sorted({str(s["meta"].get("gpu") or "CPU") for s in sessions})
    dates = sorted(
        {s["meta"]["measured_at"][:10] for s in sessions if s["meta"].get("measured_at")}
    )

    out = [
        "# Inference benchmark — OpsLM",
        "",
        "> Generated by `benchmarks/report.py` from the raw session JSON committed in",
        "> `benchmarks/results/`. Every number below was measured; nothing is projected.",
        "",
        "## Measurement conditions",
        "",
        f"- **Hardware:** {', '.join(hardware)}",
        f"- **Measured:** {', '.join(dates) or 'unknown'}",
        f"- **Configurations:** {len(sessions)}",
        "- **Output tokens** are approximated by streamed-chunk count (see `harness.py`).",
        "  The approximation is identical across engines, so comparisons hold even where",
        "  the absolute token count does not.",
        "",
    ]

    for session in sessions:
        meta = session["meta"]
        note = f" — {meta['notes']}" if meta.get("notes") else ""
        out.append(
            f"- `{config_label(session)}` · model `{meta['model']}` · `{session['_file']}`{note}"
        )
    out.append("")

    for level in concurrency_levels:
        table = latency_table(sessions, level)
        if table:
            out += [f"## Serving metrics at concurrency {level}", "", *table, ""]

    batching = batching_table(sessions)
    if batching:
        out += [
            "## Continuous batching",
            "",
            "Throughput scaling well above 1.0 with sub-linear p95 inflation is continuous",
            "batching doing its job: concurrent requests share decode passes instead of",
            "queueing. Both halves of the trade are shown — batching buys throughput and",
            "costs per-request tail latency.",
            "",
            *batching,
            "",
        ]

    probes = probe_table(sessions)
    if probes:
        out += [
            "## Feature probes",
            "",
            "Prefix-cache reduction isolates prefill reuse across requests sharing a long",
            "system prompt. Guided decoding should reach a 1.0 parse rate by construction —",
            "the informative number is the unguided baseline it is compared against.",
            "",
            *probes,
            "",
        ]

    frontier_rows, warnings = build_frontier(sessions, quality, concurrency_levels[0])
    out += ["## Quantization: quality vs. latency frontier", ""]
    if frontier_rows:
        out += [
            "Configurations off the frontier are strictly dominated — something else is",
            "both faster and better — and should never be served. The recommended row is",
            "the frontier knee (closest to the ideal corner after normalizing both axes).",
            "",
            *frontier_rows,
            "",
        ]
    else:
        out += ["No configuration has both a latency measurement and a quality score yet.", ""]
    if warnings:
        out += [*warnings, ""]

    return "\n".join(out) + "\n"


def parse_quality(pairs: list[str]) -> dict[str, float]:
    quality = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise SystemExit(f"--quality expects key=value, got {pair!r}")
        try:
            quality[key.strip()] = float(value)
        except ValueError as exc:
            raise SystemExit(f"--quality value for {key!r} is not a number: {value!r}") from exc
    return quality


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("benchmarks/results"))
    parser.add_argument(
        "--quality",
        action="append",
        default=[],
        metavar="QUANT=SCORE",
        help="eval score for a quant or engine/quant label, e.g. fp16=0.94",
    )
    parser.add_argument("--concurrency", default="1,4,16")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    sessions = load_sessions(args.results)
    markdown = render(
        sessions,
        parse_quality(args.quality),
        [int(c) for c in args.concurrency.split(",")],
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    print(f"wrote {args.out} from {len(sessions)} session(s)")


if __name__ == "__main__":
    main()
