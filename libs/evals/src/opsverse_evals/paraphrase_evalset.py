"""Paraphrase a frozen retrieval eval set into a new one, keeping gold labels.

Why: one-question-per-chunk generation reuses the gold chunk's vocabulary,
which flatters lexical (BM25) retrieval — the v2 ablation's "sparse wins"
verdict carries exactly that bias. Paraphrasing every question with an LLM
(same meaning, different incidental wording; technical identifiers with no
synonym stay) while keeping the original gold chunk/document labels produces
a set that measures paraphrase robustness — the regime real users are in.

The output is a new frozen eval set (hash it into the contamination policy).

Usage:
    uv run python -m opsverse_evals.paraphrase_evalset \
        --source evalsets/retrieval-v2.jsonl --out evalsets/retrieval-v3.jsonl
"""

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

from opsverse_core.llm import LiteLLMClient, LLMError
from opsverse_core.settings import get_settings
from opsverse_evals.contamination import normalize_question
from opsverse_evals.judge import parse_json_reply
from opsverse_evals.schemas import RetrievalCase, RetrievalDataset

PROMPT = """\
Rewrite this DevOps documentation search question so it keeps EXACTLY the same
meaning but uses different wording: synonyms, different sentence structure,
a different way into the same need. Keep technical identifiers that have no
synonym (resource kinds, command names, flag names, version numbers) but
rephrase everything around them. Do not add or remove constraints.

Original question: {question}

Return ONLY JSON: {{"question": "<the rewritten question>"}}"""


def token_overlap(a: str, b: str) -> float:
    """Jaccard over normalized word sets — how much vocabulary survived."""
    ta, tb = set(normalize_question(a).split()), set(normalize_question(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def acceptable_paraphrase(original: str, candidate: str) -> bool:
    """Reject empty/identical rewrites; a paraphrase must change *something*."""
    if len(candidate.strip()) < 12:
        return False
    return normalize_question(candidate) != normalize_question(original)


async def paraphrase(source: Path, out: Path, interval_s: float, model: str | None) -> None:
    settings = get_settings()
    generator_model = model or settings.eval_generator_model
    llm = LiteLLMClient(
        [generator_model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=60,
        max_tokens=512,
        reasoning_effort=settings.chat_reasoning_effort,
    )
    dataset = RetrievalDataset.load_jsonl(source)

    partial = out.with_suffix(".partial.jsonl")
    done: dict[str, RetrievalCase] = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line:
                case = RetrievalCase.model_validate_json(line)
                done[case.id] = case
        print(f"resuming: {len(done)} already paraphrased")

    overlaps: list[float] = []
    skipped = 0
    with partial.open("a", encoding="utf-8") as sink:
        for i, case in enumerate(dataset.cases, 1):
            if case.id in done:
                overlaps.append(token_overlap(case.question, done[case.id].question))
                continue
            reply = None
            for attempt in range(5):
                try:
                    reply = await llm.complete(
                        [{"role": "user", "content": PROMPT.format(question=case.question)}]
                    )
                    break
                except LLMError as exc:
                    rate_limited = "RateLimit" in str(exc) or "429" in str(exc)
                    wait = (40.0 if rate_limited else 15.0) * (attempt + 1)
                    print(f"  LLM error, backing off {wait:.0f}s: {str(exc)[:160]}", flush=True)
                    await asyncio.sleep(wait)
            parsed = parse_json_reply(reply.text) if reply else None
            candidate = str(parsed.get("question", "")).strip() if parsed else ""
            if not acceptable_paraphrase(case.question, candidate):
                # keep the original rather than drop the case: gold labels and
                # case count must stay comparable to the source set
                candidate = case.question
                skipped += 1
            new_case = case.model_copy(update={"question": candidate})
            done[case.id] = new_case
            overlaps.append(token_overlap(case.question, candidate))
            sink.write(new_case.model_dump_json() + "\n")
            sink.flush()
            print(f"[{i}/{len(dataset.cases)}] {candidate[:80]}", flush=True)
            await asyncio.sleep(interval_s)

    stem_version = out.stem.rsplit("-v", 1)[-1]
    result = RetrievalDataset(
        name=out.stem,
        version=stem_version if stem_version.isdigit() else "1",
        generator_model=generator_model,
        corpus_stats=dataset.corpus_stats,
        cases=[done[c.id] for c in dataset.cases],  # source order preserved
    )
    result.save_jsonl(out)
    print(
        f"wrote {len(result.cases)} cases -> {out} "
        f"(kept-original: {skipped}; mean vocab overlap with source: "
        f"{statistics.mean(overlaps):.2f})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("evalsets/retrieval-v2.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("evalsets/retrieval-v3.jsonl"))
    parser.add_argument("--interval", type=float, default=6.5)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    try:
        asyncio.run(paraphrase(args.source, args.out, args.interval, args.model))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
