"""Contextual recall: does retrieval bring back enough to actually answer?

The generator-side half of the golden set, and the metric ADR-0018 declined to
implement until reference answers existed. They now do (`golden_answers.py`).

For each query and each retrieval mode, the mode's top-k retrieved chunks are
assembled into the context the generator would have seen, and a judge decides
which of the reference answer's atomic claims that context **supports**.

    contextual_recall = supported_claims / total_claims

This measures something none of the existing metrics do:

* `hit@k` asks "did we find the chunk the question was written from?" - on this
  corpus it is saturated at 0.97-0.99 and cannot discriminate (ADR-0019).
* `faithfulness` (rag_suite) asks "is the answer supported by whatever context
  we retrieved?" - it is reference-free, so a system that retrieves little and
  answers narrowly scores *well*.
* `contextual_recall` asks "was the retrieved context sufficient to produce the
  correct answer?" A retriever that misses half the needed facts is penalised
  here and nowhere else.

Runs offline against committed ranked lists, so it re-scores the same retrieval
runs - no Qdrant, no re-retrieval. Resumable: each (mode, query) verdict is
appended immediately and re-runs skip it.

Usage:
    uv run python -m opsverse_evals.generator_eval --out docs/reports/generator-golden-v1.md
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opsverse_core.llm import LiteLLMClient, LLMError
from opsverse_core.settings import get_settings
from opsverse_evals.golden_set import EXCERPT_CHARS, load_chunk_text
from opsverse_evals.judge import parse_json_reply
from opsverse_evals.schemas import GoldenAnswerSet
from opsverse_evals.stats import bootstrap_ci, paired_permutation_test

K = 10
BASELINE = "hybrid"

PROMPT = """\
You are checking whether a set of retrieved documentation excerpts CONTAINS the
information needed to support each claim below.

For each claim, answer true only if the excerpts actually state or directly imply
it. Answer false if the excerpts are merely on the same topic, or if supporting
the claim would require outside knowledge. Do not use anything you know beyond
the excerpts.

Claims:
{claims}

Return ONLY a JSON object mapping each claim number to true/false, e.g.:
{{"1": true, "2": false}}

Retrieved excerpts:
{context}
"""


async def judge_mode(
    llm: LiteLLMClient,
    answers: GoldenAnswerSet,
    ranked_by_case: dict[str, list[str]],
    texts: dict[str, str],
    mode: str,
    sink,
    done: set[tuple[str, str]],
    results: dict[tuple[str, str], float],
    interval_s: float,
    k: int = K,
) -> None:
    for ans in answers.answers:
        key = (mode, ans.id)
        if key in done:
            continue
        ranked = ranked_by_case.get(ans.id)
        if not ranked or not ans.claims:
            continue
        context = "\n\n---\n\n".join(
            texts[cid][:EXCERPT_CHARS] for cid in ranked[:k] if texts.get(cid)
        )
        numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(ans.claims, 1))
        prompt = PROMPT.format(claims=numbered, context=context)

        reply = None
        for attempt in range(5):
            try:
                reply = await llm.complete([{"role": "user", "content": prompt}])
                break
            except LLMError as exc:
                rate_limited = "RateLimit" in str(exc) or "429" in str(exc)
                wait = (40.0 if rate_limited else 15.0) * (attempt + 1)
                print(
                    f"  LLM error ({attempt + 1}), backing off {wait:.0f}s: {str(exc)[:120]}",
                    flush=True,
                )
                await asyncio.sleep(wait)
        if reply is None:
            continue

        parsed = parse_json_reply(reply.text)
        if not isinstance(parsed, dict):
            continue
        supported = 0
        graded = 0
        for i in range(1, len(ans.claims) + 1):
            v = parsed.get(str(i))
            if v is None:
                continue
            graded += 1
            if v is True or str(v).lower() == "true":
                supported += 1
        if graded == 0:
            continue
        recall = supported / len(ans.claims)
        results[key] = recall
        sink.write(
            json.dumps(
                {
                    "mode": mode,
                    "id": ans.id,
                    "supported": supported,
                    "claims": len(ans.claims),
                    "contextual_recall": recall,
                }
            )
            + "\n"
        )
        sink.flush()
        print(
            f"  [{mode}] {supported}/{len(ans.claims)} claims supported | {ans.question[:44]}",
            flush=True,
        )
        await asyncio.sleep(interval_s)


async def run(
    answers_path: Path,
    raw_path: Path,
    corpus: Path,
    out: Path,
    interval_s: float,
    model: str | None = None,
) -> None:
    settings = get_settings()
    judge_model = model or settings.eval_generator_model
    llm = LiteLLMClient(
        [judge_model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=90,
        max_tokens=800,
        reasoning_effort=settings.chat_reasoning_effort,
    )

    answers = GoldenAnswerSet.load_jsonl(answers_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    texts = load_chunk_text(corpus)

    partial = out.with_suffix(".partial.jsonl")
    partial.parent.mkdir(parents=True, exist_ok=True)
    done: set[tuple[str, str]] = set()
    results: dict[tuple[str, str], float] = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            key = (rec["mode"], rec["id"])
            done.add(key)
            results[key] = rec["contextual_recall"]
        print(f"resuming: {len(done)} verdicts already judged")

    modes = list(raw["results"].keys())
    total = len(modes) * len(answers.answers)
    print(f"{len(answers.answers)} queries x {len(modes)} modes = {total} judgements")

    with partial.open("a", encoding="utf-8") as sink:
        for mode in modes:
            ranked_by_case = {c["case_id"]: c["retrieved_chunk_ids"] for c in raw["results"][mode]}
            await judge_mode(
                llm, answers, ranked_by_case, texts, mode, sink, done, results, interval_s
            )

    summary = summarise(results, answers, judge_model, modes)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out.write_text(render(summary, stamp), encoding="utf-8")
    summary_path = out.with_name("generator-golden-v1-summary.json")
    summary_path.write_text(
        json.dumps(
            {"report": "generator-golden-v1", "kind": "generator-golden", "date": stamp, **summary},
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out} and {summary_path}")
    for mode, m in summary["modes"].items():
        print(
            f"  {mode:<16} contextual_recall {m['mean']:.4f} [{m['ci_lo']:.4f}, {m['ci_hi']:.4f}]"
        )


def summarise(
    results: dict[tuple[str, str], float],
    answers: GoldenAnswerSet,
    judge_model: str,
    modes: list[str],
) -> dict[str, Any]:
    order = [a.id for a in answers.answers]
    vectors: dict[str, list[float]] = {}
    for mode in modes:
        vec = [results[(mode, qid)] for qid in order if (mode, qid) in results]
        if vec:
            vectors[mode] = vec

    summary: dict[str, Any] = {
        "judge_model": judge_model,
        "queries": len(order),
        "total_claims": sum(len(a.claims) for a in answers.answers),
        "mean_claims_per_query": round(
            sum(len(a.claims) for a in answers.answers) / len(answers.answers), 2
        )
        if answers.answers
        else 0,
        "modes": {m: bootstrap_ci(v).as_dict() for m, v in vectors.items()},
        "comparisons": {},
    }
    base = vectors.get(BASELINE)
    if base:
        for mode, vec in vectors.items():
            if mode == BASELINE or len(vec) != len(base):
                continue
            summary["comparisons"][f"{mode}_vs_{BASELINE}"] = paired_permutation_test(
                vec, base
            ).as_dict()
    return summary


def render(s: dict[str, Any], date: str) -> str:
    lines = [
        "# Generator golden eval v1 - contextual recall",
        "",
        f"Generated {date} by `opsverse_evals.generator_eval` (judge: `{s['judge_model']}`).",
        f"**{s['queries']} queries, {s['total_claims']} atomic claims** "
        f"(mean {s['mean_claims_per_query']}/query) from `evalsets/golden-answers-v1.jsonl`.",
        "",
        "## What this measures, that nothing else did",
        "",
        "`contextual_recall` = share of the reference answer's atomic claims that a mode's",
        'retrieved context actually **supports**. It answers *"was what we retrieved enough to',
        'produce the right answer?"*',
        "",
        "- `hit@10` asks only whether the seed chunk was found, and is **saturated** at",
        "  0.97-0.99 on this corpus "
        "([ADR-0019](../adr/0019-golden-set-pooled-graded-relevance.md)).",
        "- `faithfulness` (in `rag_suite`) is **reference-free**: it asks whether the answer",
        "  matches the retrieved context, so a system that retrieves little and answers",
        "  narrowly scores *well*. Contextual recall is what catches that.",
        "",
        "## Results (mean with 95% bootstrap CI)",
        "",
        "| mode | contextual recall |",
        "|---|---|",
    ]
    for mode, m in s["modes"].items():
        lines.append(
            f"| {mode} | **{m['mean']:.3f}** <sub>[{m['ci_lo']:.3f}, {m['ci_hi']:.3f}]</sub> "
            f"(n={m['n']}) |"
        )

    if s["comparisons"]:
        lines += [
            "",
            f"## Is any gap real? (paired permutation test vs `{BASELINE}`)",
            "",
            "| comparison | delta | 95% CI | p | verdict |",
            "|---|---|---|---|---|",
        ]
        for pair, c in s["comparisons"].items():
            verdict = "**significant**" if c["significant"] else "not significant"
            lines.append(
                f"| {pair} | {c['delta']:+.4f} | [{c['ci_lo']:+.4f}, {c['ci_hi']:+.4f}] | "
                f"{c['p_value']:.4f} | {verdict} |"
            )

    lines += [
        "",
        "## Honest limits",
        "",
        "- **The reference answers are LLM-written, not human-authored.** They are independent",
        "  of every retrieval mode (grounded in the pooled *judged-relevant* chunks, not in any",
        "  system's output), which is what makes the comparison fair - but that is not the same",
        "  as human ground truth. A human-authored reference set is the next step and is not",
        "  claimed here.",
        "- **The claim-support judge is the same model family that wrote the claims.** Shared",
        "  blind spots are possible. A different judge model would be a cheap, worthwhile check.",
        "- Claims are graded against the **top-10** retrieved context only, matching what the",
        "  generator would actually see.",
        f"- n = {s['queries']} queries. Gaps inside the CIs are not resolvable at this size.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", type=Path, default=Path("evalsets/golden-answers-v1.jsonl"))
    parser.add_argument(
        "--raw", type=Path, default=Path("docs/reports/retrieval-ablation-v2-raw.json")
    )
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus/chunks.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("docs/reports/generator-golden-v1.md"))
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    asyncio.run(run(args.answers, args.raw, args.corpus, args.out, args.interval, args.model))


if __name__ == "__main__":
    main()
