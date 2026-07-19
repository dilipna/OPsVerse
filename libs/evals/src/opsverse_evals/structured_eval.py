"""Structured-output / tool-calling fidelity eval.

Measures whether a model reliably emits well-formed, schema-correct structured
output — the capability that (a) top AI-Engineer JDs probe as "tool-use
reliability" and (b) SFT can silently degrade. So this is both a standalone
quality gate and the Phase-5 check "does fine-tuning break JSON/function
calling?" — run it on base vs OpsLM and compare.

Scoring is fully deterministic (JSON parse + required-key check + exact field
match on the checkable fields), so there is no judge and no quota beyond the
generation itself. Three metrics per run:
  - json_parse_rate:  fraction whose output is valid JSON
  - schema_valid_rate: fraction with all required keys present
  - field_accuracy:   fraction of checkable expected fields that matched

Usage:
    uv run python -m opsverse_evals.structured_eval --n 12
"""

import argparse
import asyncio
import json
import re
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine

from opsverse_core.llm import LiteLLMClient, LLMError
from opsverse_core.settings import get_settings
from opsverse_evals.reporting import record_report

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort JSON object from a model reply: strip markdown fences, then
    fall back to the first {...} span. Returns None if nothing parses."""
    candidates: list[str] = []
    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text.strip())
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _norm(value: Any) -> Any:
    """Compare leniently: case-insensitive strings, int-like floats collapsed."""
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_norm(v) for v in value]
    return value


def score_case(
    parsed: dict[str, Any] | None, required: list[str], expected: dict[str, Any]
) -> dict[str, Any]:
    """Deterministic per-case scoring."""
    if parsed is None:
        return {
            "parseable": 0.0,
            "schema_valid": 0.0,
            "field_hits": 0,
            "field_total": len(expected),
        }
    schema_valid = all(key in parsed for key in required)
    hits = sum(
        1 for key, want in expected.items() if key in parsed and _norm(parsed[key]) == _norm(want)
    )
    return {
        "parseable": 1.0,
        "schema_valid": 1.0 if schema_valid else 0.0,
        "field_hits": hits,
        "field_total": len(expected),
    }


def aggregate(scores: list[dict[str, Any]]) -> dict[str, float]:
    if not scores:
        return {"json_parse_rate": 0.0, "schema_valid_rate": 0.0, "field_accuracy": 0.0}
    total_fields = sum(s["field_total"] for s in scores) or 1
    return {
        "json_parse_rate": round(statistics.mean(s["parseable"] for s in scores), 4),
        "schema_valid_rate": round(statistics.mean(s["schema_valid"] for s in scores), 4),
        "field_accuracy": round(sum(s["field_hits"] for s in scores) / total_fields, 4),
    }


async def run(
    dataset_path: Path, n: int, out_dir: Path, model: str | None, interval_s: float
) -> None:
    settings = get_settings()
    gen_model = model or settings.eval_generator_model
    llm = LiteLLMClient(
        [gen_model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=60,
        max_tokens=512,
        reasoning_effort=settings.chat_reasoning_effort,
    )
    cases = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][:n]

    scores: list[dict[str, Any]] = []
    for i, case in enumerate(cases, 1):
        prompt = case["prompt"] + "\n\nReturn ONLY a JSON object, no prose."
        try:
            reply = await llm.complete([{"role": "user", "content": prompt}])
            parsed = extract_json(reply.text)
        except LLMError as exc:
            print(f"[{i}/{len(cases)}] LLM error: {str(exc)[:120]}")
            parsed = None
        score = score_case(parsed, case["required_keys"], case["expected"])
        scores.append(score)
        print(
            f"[{i}/{len(cases)}] {case['id']}: parse={score['parseable']:.0f} "
            f"schema={score['schema_valid']:.0f} "
            f"fields={score['field_hits']}/{score['field_total']}"
        )
        await asyncio.sleep(interval_s)

    results = aggregate(scores)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    report = {
        "report": "structured-output-v1",
        "kind": "structured-output",
        "date": stamp,
        "dataset": "structured-output-v1",
        "cases": len(cases),
        "generator_model": gen_model,
        # mode -> metric -> value, matching the eval page's generic renderer
        "results": {"json-fidelity": results},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "structured-output-v1-summary.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8"
    )
    engine = create_async_engine(settings.database_url)
    run_id = await record_report(
        engine, "structured-output", report, model=gen_model, params={"n": len(cases)}
    )
    await engine.dispose()
    print(json.dumps(results, indent=1))
    print(f"eval_runs row {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evalsets/structured-output-v1.jsonl"))
    parser.add_argument("--n", type=int, default=12)
    parser.add_argument("--out", type=Path, default=Path("docs/reports"))
    parser.add_argument("--model", default=None, help="override eval_generator_model")
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.n, args.out, args.model, args.interval))


if __name__ == "__main__":
    main()
