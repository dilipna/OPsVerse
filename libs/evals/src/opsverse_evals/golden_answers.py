"""Write reference answers for the golden queries, decomposed into atomic claims.

This is the generator-side half of the golden set. `golden_set.py` produced
graded relevance over a pooled candidate set; this uses the chunks that set
judged **relevant (grade >= 2)** to write a reference answer per query, then
splits it into atomic, independently-checkable claims.

Why write the answer from the *judged* chunks rather than from a system's
output: a reference derived from what one retriever returned would score that
retriever highest by construction. Grounding it in the judged-relevant set makes
it independent of every mode, so all four can be scored against the same bar.

**The circularity that remains, stated plainly.** The reference answer is
LLM-written and the claim-support judgements are LLM-made. That is not the same
as human ground truth, and this file does not pretend otherwise: what it buys is
a reference that is independent *of the retrieval systems under test*, not one
independent of language models. A human-authored reference set is the honest
next step and is recorded as such in the report.

Free-tier aware: throttled, 429-backoff, resumable.

Usage:
    uv run python -m opsverse_evals.golden_answers --n 100 \
        --out evalsets/golden-answers-v1.jsonl
"""

import argparse
import asyncio
from pathlib import Path

from opsverse_core.llm import LiteLLMClient, LLMError
from opsverse_core.settings import get_settings
from opsverse_evals.golden_set import EXCERPT_CHARS, load_chunk_text
from opsverse_evals.judge import parse_json_reply
from opsverse_evals.schemas import GoldenAnswer, GoldenAnswerSet, GradedRetrievalDataset

PROMPT = """\
You are writing the reference answer for a DevOps/MLOps documentation benchmark.

Question:
{question}

Below are the documentation excerpts that expert judges marked RELEVANT to this
question. Write the answer that a correct system should give, using ONLY these
excerpts.

Then decompose your answer into atomic factual claims. Each claim must be:
- independently checkable against documentation,
- a single fact (do not join two facts with "and"),
- self-contained (no "it", "this", "the above" - name the subject),
- stated without reference to the excerpts themselves.

Aim for 3-8 claims. If the excerpts genuinely do not answer the question, return
an empty claims list.

Return ONLY JSON:
{{"answer": "...", "claims": ["...", "..."]}}

Relevant excerpts:
{context}
"""


async def build(
    golden_path: Path,
    corpus: Path,
    out: Path,
    n: int,
    interval_s: float,
    model: str | None = None,
) -> None:
    settings = get_settings()
    generator_model = model or settings.eval_generator_model
    llm = LiteLLMClient(
        [generator_model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=90,
        max_tokens=1500,
        reasoning_effort=settings.chat_reasoning_effort,
    )

    golden = GradedRetrievalDataset.load_jsonl(golden_path)
    texts = load_chunk_text(corpus)
    print(f"{len(golden.cases)} golden queries, {len(texts)} chunks")

    partial = out.with_suffix(".partial.jsonl")
    partial.parent.mkdir(parents=True, exist_ok=True)
    answers: list[GoldenAnswer] = []
    done: set[str] = set()
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line:
                a = GoldenAnswer.model_validate_json(line)
                answers.append(a)
                done.add(a.id)
        print(f"resuming: {len(answers)} answers already written")

    skipped = 0
    with partial.open("a", encoding="utf-8") as sink:
        for case in golden.cases:
            if len(answers) >= n:
                break
            if case.id in done:
                continue
            relevant = [
                cid for cid in case.relevant_ids(golden.relevance_threshold) if texts.get(cid)
            ]
            if not relevant:
                skipped += 1
                continue
            context = "\n\n---\n\n".join(texts[cid][:EXCERPT_CHARS] for cid in relevant)
            prompt = PROMPT.format(question=case.question, context=context)

            reply = None
            for attempt in range(5):
                try:
                    reply = await llm.complete([{"role": "user", "content": prompt}])
                    break
                except LLMError as exc:
                    rate_limited = "RateLimit" in str(exc) or "429" in str(exc)
                    wait = (40.0 if rate_limited else 15.0) * (attempt + 1)
                    print(
                        f"  LLM error (attempt {attempt + 1}), backing off {wait:.0f}s: "
                        f"{str(exc)[:140]}",
                        flush=True,
                    )
                    await asyncio.sleep(wait)
            if reply is None:
                skipped += 1
                continue

            parsed = parse_json_reply(reply.text)
            if not isinstance(parsed, dict):
                skipped += 1
                continue
            answer_text = str(parsed.get("answer", "")).strip()
            raw_claims = parsed.get("claims")
            claims = (
                [str(c).strip() for c in raw_claims if str(c).strip()]
                if isinstance(raw_claims, list)
                else []
            )
            if not answer_text or not claims:
                skipped += 1
                continue

            record = GoldenAnswer(
                id=case.id,
                question=case.question,
                reference_answer=answer_text,
                claims=claims,
                source_chunk_ids=relevant,
            )
            answers.append(record)
            sink.write(record.model_dump_json() + "\n")
            sink.flush()
            print(
                f"[{len(answers)}/{n}] {len(claims)} claims from {len(relevant)} chunks "
                f"| {case.question[:52]}",
                flush=True,
            )
            await asyncio.sleep(interval_s)

    ds = GoldenAnswerSet(
        name="golden-answers-v1",
        version="1",
        generator_model=generator_model,
        notes=(
            "Reference answers written from judged-relevant chunks (grade >= 2) of "
            "retrieval-golden-v1, decomposed into atomic claims. Independent of any "
            "retrieval mode's output; NOT human-authored."
        ),
        answers=answers,
    )
    ds.save_jsonl(out)
    n_claims = sum(len(a.claims) for a in answers)
    mean_claims = n_claims / len(answers) if answers else 0
    print(f"\nwrote {out}: {len(answers)} answers ({skipped} skipped)")
    print(f"total claims: {n_claims} (mean {mean_claims:.1f}/query)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=Path("evalsets/retrieval-golden-v1.jsonl"))
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus/chunks.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("evalsets/golden-answers-v1.jsonl"))
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    asyncio.run(build(args.golden, args.corpus, args.out, args.n, args.interval, args.model))


if __name__ == "__main__":
    main()
