"""Generate a 2-turn conversational eval set — the gap no eval set covers.

Every eval set in this project (`retrieval-v1/v2/v3`, `retrieval-golden-v1`) is
single-turn: one self-contained question per case. Production chat is not:
`stream_chat` in `libs/rag/chat.py` sends only the *current* turn's raw text to
the retriever (`retrieval_query = query`, see that module) — conversation
history reaches the generator's prompt but never reaches retrieval. A follow-up
like *"what about for StatefulSets?"* has no entity for the retriever to search
on unless the prior turn is folded in somewhere.

This builds cases that exercise exactly that gap: for each sampled chunk, an
LLM writes a two-turn conversation where turn 2 is *elliptical* — a pronoun or
"what about X instead" that only resolves given turn 1. Turn 2 is answerable
from the chunk alone once resolved; turn 1 exists only to establish the
referent and is not itself graded.

Free-tier aware: throttled, 429-backoff, resumable.

Usage:
    uv run python -m opsverse_evals.multiturn_evalset --n 50 \
        --out evalsets/multiturn-v1.jsonl
"""

import argparse
import asyncio
import json
import random
from pathlib import Path

from opsverse_core.llm import LiteLLMClient, LLMError
from opsverse_core.settings import get_settings
from opsverse_evals.judge import parse_json_reply
from opsverse_evals.schemas import MultiTurnCase, MultiTurnDataset

PROMPT = """\
You are building a MULTI-TURN retrieval benchmark for a DevOps/MLOps documentation
search engine. Below is one documentation excerpt.

Write a two-turn user conversation where:
- TURN 1 asks a natural, self-contained question about a topic CLOSELY RELATED to
  this excerpt (a sibling concept, the more general category, or a similar
  tool/config) -- something an engineer would plausibly ask right before this
  excerpt's topic comes up. Do NOT answer turn 1 from this excerpt; it exists only
  to establish context.
- TURN 2 asks about THIS excerpt's specific content, but MUST use a pronoun,
  "that", "it", or an elliptical phrase ("what about for X instead", "and for Y?")
  that only makes sense given turn 1. If turn 1 were deleted, turn 2 alone would be
  ambiguous or incomplete -- that is the point.

Turn 2 must be answerable from this excerpt alone, once its reference is resolved.

Rules:
- Do not mention "the excerpt" or "the document".
- If the excerpt has no substantive content to ask about, mark unanswerable.

Return ONLY JSON:
{{"turn1_question": "...", "turn2_question": "...", "answerable": true|false}}

Excerpt (source: {source}, section: {section}):
---
{text}
---
"""

MIN_CHARS = 400


def sample_chunks(corpus: Path, n_pool: int, seed: int = 20260901) -> list[dict]:
    rows = []
    with corpus.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            if len(rec.get("text", "")) >= MIN_CHARS:
                rows.append(rec)
    random.Random(seed).shuffle(rows)
    return rows[:n_pool]


async def generate(
    corpus: Path,
    documents: Path,
    n: int,
    out: Path,
    interval_s: float,
    model: str | None = None,
) -> None:
    settings = get_settings()
    generator_model = model or settings.eval_generator_model
    llm = LiteLLMClient(
        [generator_model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=60,
        max_tokens=512,
        reasoning_effort=settings.chat_reasoning_effort,
    )

    docs_by_id = {}
    with documents.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                d = json.loads(line)
                docs_by_id[d["id"]] = d

    pool = sample_chunks(corpus, n * 6)
    print(f"candidate pool: {len(pool)} chunks (>= {MIN_CHARS} chars)")

    partial = out.with_suffix(".partial.jsonl")
    partial.parent.mkdir(parents=True, exist_ok=True)
    cases: list[MultiTurnCase] = []
    done: set[str] = set()
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line:
                c = MultiTurnCase.model_validate_json(line)
                cases.append(c)
                done.add(c.id)
        print(f"resuming: {len(cases)} cases already generated")

    skipped = 0
    with partial.open("a", encoding="utf-8") as sink:
        for chunk in pool:
            if len(cases) >= n:
                break
            if chunk["id"] in done:
                continue
            doc = docs_by_id.get(chunk["document_id"], {})
            prompt = PROMPT.format(
                source=doc.get("uri", "unknown"),
                section=chunk.get("section") or "-",
                text=chunk["text"][:4000],
            )
            reply = None
            for attempt in range(5):
                try:
                    reply = await llm.complete([{"role": "user", "content": prompt}])
                    break
                except LLMError as exc:
                    rate_limited = "RateLimit" in str(exc) or "429" in str(exc)
                    wait = (40.0 if rate_limited else 15.0) * (attempt + 1)
                    print(
                        f"  LLM error ({attempt + 1}), backing off {wait:.0f}s: {str(exc)[:140]}",
                        flush=True,
                    )
                    await asyncio.sleep(wait)
            if reply is None:
                skipped += 1
                continue

            parsed = parse_json_reply(reply.text)
            if (
                not parsed
                or not parsed.get("answerable")
                or not parsed.get("turn1_question")
                or not parsed.get("turn2_question")
            ):
                skipped += 1
                continue

            case = MultiTurnCase(
                id=chunk["id"],
                turn1_question=str(parsed["turn1_question"]).strip(),
                turn2_question=str(parsed["turn2_question"]).strip(),
                relevant_chunk_ids=[chunk["id"]],
                relevant_document_ids=[chunk["document_id"]],
                source=doc.get("uri", "unknown"),
                tool=doc.get("tool"),
            )
            cases.append(case)
            sink.write(case.model_dump_json() + "\n")
            sink.flush()
            print(
                f"[{len(cases)}/{n}] T1: {case.turn1_question[:40]!r} "
                f"-> T2: {case.turn2_question[:40]!r}",
                flush=True,
            )
            await asyncio.sleep(interval_s)

    ds = MultiTurnDataset(
        name="multiturn-v1",
        version="1",
        generator_model=generator_model,
        cases=cases,
    )
    ds.save_jsonl(out)
    print(f"\nwrote {out}: {len(cases)} cases ({skipped} skipped)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus/chunks.jsonl"))
    parser.add_argument("--documents", type=Path, default=Path("data/corpus/documents.jsonl"))
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path("evalsets/multiturn-v1.jsonl"))
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    asyncio.run(generate(args.corpus, args.documents, args.n, args.out, args.interval, args.model))


if __name__ == "__main__":
    main()
