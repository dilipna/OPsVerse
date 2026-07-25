"""Lightweight, file-based model registry for the OpsVerse platform.

A registry answers one question a serving platform must always be able to
answer: *which model version, in which quantization, is deployed where — and
what does it cost and score?* The static facts (base model, fine-tuning method,
adapter shape, deployment status) are authored in `registry/models.json`. The
**measured** facts — latency, throughput, eval score — are joined in here from
the artifacts that produced them (`benchmarks/results/*.json`, `docs/reports/`),
never hand-copied, so a number in the registry can never disagree with the file
it came from.

Fields with no measurement yet render as `pending`, exactly like the benchmark
report. The registry is honest about what has not been measured rather than
leaving a plausible-looking blank.

Usage:
    python registry/registry.py --out docs/model-registry.md
    python registry/registry.py --check          # validate schema, CI-friendly
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = Path(__file__).resolve().parent / "models.json"
DEFAULT_RESULTS = REPO / "benchmarks" / "results"

REQUIRED_MODEL_FIELDS = ("name", "version", "status", "base_model")
REQUIRED_VARIANT_FIELDS = ("quant", "artifact", "serving_engine", "status")


def load_registry(path: Path) -> list[dict[str, Any]]:
    """Load and schema-check the registry. Raises SystemExit with a precise
    message on any structural problem — a malformed registry should fail loudly
    in CI, not render a half-empty table."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"registry not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON ({exc})") from exc

    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise SystemExit(f"{path}: 'models' must be a non-empty list")

    for model in models:
        missing = [f for f in REQUIRED_MODEL_FIELDS if f not in model]
        if missing:
            raise SystemExit(f"{path}: model {model.get('name', '?')!r} missing {missing}")
        for variant in model.get("variants", []):
            vmissing = [f for f in REQUIRED_VARIANT_FIELDS if f not in variant]
            if vmissing:
                raise SystemExit(
                    f"{path}: {model['name']} variant {variant.get('quant', '?')!r} "
                    f"missing {vmissing}"
                )
    return models


def load_benchmarks(results_dir: Path) -> list[dict[str, Any]]:
    """Load committed benchmark sessions. Absent directory is not an error — the
    registry renders `pending` for every measured field until a run lands."""
    if not results_dir.is_dir():
        return []
    sessions = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # a broken result file must not take the whole registry down
        if "meta" in data:
            sessions.append(data)
    return sessions


def match_benchmark(
    key: dict[str, str] | None, sessions: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Find the benchmark session for a variant's (engine, quant) key.

    Newest wins when a config was re-measured, so the registry reflects the
    latest run rather than an arbitrary file-order pick.
    """
    if not key:
        return None
    matches = [
        s
        for s in sessions
        if s["meta"].get("engine") == key.get("engine")
        and s["meta"].get("quant") == key.get("quant")
    ]
    if not matches:
        return None
    return max(matches, key=lambda s: s["meta"].get("measured_at", ""))


def _level_at(session: dict[str, Any], concurrency: int) -> dict[str, Any] | None:
    for level in session.get("levels", []):
        if level.get("concurrency") == concurrency:
            return level
    return None


def benchmark_summary(session: dict[str, Any] | None) -> dict[str, str]:
    """Condense a session into the two registry columns: single-stream latency
    and system throughput at the top of the sweep. `pending` when unmeasured."""
    if session is None:
        return {"latency_p50": "pending", "throughput": "pending"}
    single = _level_at(session, 1)
    levels = [lv for lv in session.get("levels", []) if lv.get("ok", 0) > 0]
    latency = f"{single['latency_s']['p50']:.2f}s" if single and single.get("ok") else "pending"
    if levels:
        top = max(levels, key=lambda lv: lv["concurrency"])
        throughput = f"{top['throughput_tokens_s']:.0f} tok/s @ c{top['concurrency']}"
    else:
        throughput = "pending"
    return {"latency_p50": latency, "throughput": throughput}


def eval_label(model: dict[str, Any]) -> str:
    """Eval score, or an honest pending marker. A score is only shown if the
    registry points at a real report file that exists and carries one."""
    ev = model.get("eval", {})
    report = ev.get("report")
    if not report:
        return "pending (before/after eval needs a serving session)"
    report_path = REPO / report
    if not report_path.exists():
        return f"pending (report {report} not found)"
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return f"pending (report {report} unreadable)"
    return str(data.get("score", "pending"))


def render(models: list[dict[str, Any]], sessions: list[dict[str, Any]]) -> str:
    out = [
        "# Model registry — OpsVerse",
        "",
        "> Generated by `registry/registry.py` from `registry/models.json`, with",
        "> latency/throughput joined from `benchmarks/results/` and eval scores from",
        "> `docs/reports/`. Measured fields are never hand-copied; `pending` means",
        '> not yet measured, not "assumed fine".',
        "",
    ]
    for model in models:
        ft = model.get("fine_tuning", {})
        ds = model.get("dataset", {})
        out += [
            f"## {model['name']}  ·  `{model['status']}`",
            "",
            f"- **Base model:** `{model['base_model']}`"
            + (f"  ·  **Hub:** `{model['hub']}`" if model.get("hub") else ""),
            f"- **Fine-tuning:** {ft.get('method', '—')}"
            + (
                f" (r={ft['lora_r']}, alpha={ft['lora_alpha']}, "
                f"{ft.get('trainable_pct', '?')}% params)"
                if ft.get("lora_r")
                else ""
            ),
            f"- **Dataset:** {ds.get('train', '—')} train / {ds.get('val', '—')} val"
            + (" · decontaminated" if ds.get("decontaminated") else ""),
            f"- **Eval (vs. base):** {eval_label(model)}",
            f"- **Decision record:** {model.get('adr', '—')}",
            "",
            f"_{model.get('deployment', '')}_",
            "",
        ]
        variants = model.get("variants", [])
        if not variants:
            out += ["No serving variants yet.", ""]
            continue
        out += [
            "| Quant | Artifact | Engine | Status | Latency p50 | Throughput |",
            "|---|---|---|---|---|---|",
        ]
        for v in variants:
            summary = benchmark_summary(match_benchmark(v.get("benchmark_key"), sessions))
            out.append(
                f"| `{v['quant']}` | {v['artifact']} | {v['serving_engine']} "
                f"| {v['status']} | {summary['latency_p50']} | {summary['throughput']} |"
            )
        out.append("")
        for v in variants:
            if v.get("note"):
                out.append(f"> `{v['quant']}`: {v['note']}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the registry schema and exit (no output written)",
    )
    args = parser.parse_args()

    models = load_registry(args.registry)
    if args.check:
        variants = sum(len(m.get("variants", [])) for m in models)
        print(f"registry OK: {len(models)} models, {variants} variants")
        return

    markdown = render(models, load_benchmarks(args.results))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
