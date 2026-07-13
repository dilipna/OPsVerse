"""Generate a labeled retrieval eval set from the ingested corpus.

For each sampled chunk, an LLM writes one realistic question that the chunk
answers; the chunk (and its document) become the gold labels. Free-tier aware:
throttled, 429-backoff, and resumable — completed cases are appended to a
partial JSONL immediately, and re-runs skip chunks already done.

Usage:
    uv run python -m opsverse_evals.generate_retrieval_set --n 100 \
        --out evalsets/retrieval-v1.jsonl
"""

import argparse
import asyncio
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from opsverse_core.llm import LiteLLMClient, LLMError
from opsverse_core.settings import get_settings
from opsverse_evals.judge import parse_json_reply
from opsverse_evals.schemas import RetrievalCase, RetrievalDataset

PROMPT = """\
You are building a retrieval benchmark for a DevOps/MLOps documentation search engine.
Below is one documentation excerpt. Write ONE question that a DevOps engineer would
realistically type into a search box, and that THIS excerpt specifically answers.

Rules:
- The question must be answerable from this excerpt alone.
- Make it specific to this excerpt's content (name the technology/config involved);
  avoid questions that dozens of unrelated documents would also answer.
- Do NOT mention "the excerpt", "the document", or quote file paths.
- If the excerpt is boilerplate with no substantive content to ask about
  (e.g. bare directory listings, licence text), mark it unanswerable.

Return ONLY a JSON object: {{"question": "...", "answerable": true|false}}

Excerpt (source: {source}, section: {section}):
---
{text}
---
"""

SAMPLE_SQL = sa.text("""
    SELECT DISTINCT ON (c.document_id)
        c.id::text AS chunk_id, c.document_id::text AS document_id, c.text,
        c.section, d.uri AS source, d.tool, d.doc_type
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.embedding_status = 'embedded' AND length(c.text) >= 250
    ORDER BY c.document_id, c.token_count DESC
""")


async def generate(n: int, out: Path, interval_s: float, model: str | None = None) -> None:
    settings = get_settings()
    generator_model = model or settings.eval_generator_model
    llm = LiteLLMClient(
        [generator_model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=60,
        max_tokens=512,
        reasoning_effort=settings.chat_reasoning_effort,
    )

    partial = out.with_suffix(".partial.jsonl")
    partial.parent.mkdir(parents=True, exist_ok=True)
    done_ids: set[str] = set()
    cases: list[RetrievalCase] = []
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line:
                case = RetrievalCase.model_validate_json(line)
                cases.append(case)
                done_ids.add(case.id)
        print(f"resuming: {len(cases)} cases already generated")

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        rows = (await conn.execute(SAMPLE_SQL)).mappings().all()
        n_chunks = (await conn.execute(sa.text("SELECT count(*) FROM chunks"))).scalar_one()
        n_docs = (await conn.execute(sa.text("SELECT count(*) FROM documents"))).scalar_one()
    await engine.dispose()
    print(f"candidate chunks: {len(rows)} (corpus: {n_docs} docs / {n_chunks} chunks)")

    seen_questions = {c.question.strip().lower() for c in cases}
    skipped = 0
    with partial.open("a", encoding="utf-8") as sink:
        for row in rows:
            if len(cases) >= n:
                break
            if row["chunk_id"] in done_ids:
                continue
            prompt = PROMPT.format(
                source=row["source"], section=row["section"] or "-", text=row["text"][:4000]
            )
            reply = None
            for attempt in range(5):
                try:
                    reply = await llm.complete([{"role": "user", "content": prompt}])
                    break
                except LLMError as exc:
                    # Free-tier throttling is the common failure; every error
                    # is worth a backoff-retry before giving up on the chunk.
                    rate_limited = "RateLimit" in str(exc) or "429" in str(exc)
                    wait = (40.0 if rate_limited else 15.0) * (attempt + 1)
                    print(
                        f"  LLM error (attempt {attempt + 1}), backing off {wait:.0f}s: "
                        f"{str(exc)[:160]}",
                        flush=True,
                    )
                    await asyncio.sleep(wait)
            if reply is None:
                skipped += 1
                continue
            parsed = parse_json_reply(reply.text)
            if not parsed or not parsed.get("answerable") or not parsed.get("question"):
                skipped += 1
                continue
            question = str(parsed["question"]).strip()
            if len(question) < 12 or question.lower() in seen_questions:
                skipped += 1
                continue
            seen_questions.add(question.lower())
            case = RetrievalCase(
                id=row["chunk_id"],
                question=question,
                relevant_chunk_ids=[row["chunk_id"]],
                relevant_document_ids=[row["document_id"]],
                source=row["source"],
                tool=row["tool"],
                doc_type=row["doc_type"],
                section=row["section"],
            )
            cases.append(case)
            sink.write(case.model_dump_json() + "\n")
            sink.flush()
            print(f"[{len(cases)}/{n}] {question}", flush=True)
            await asyncio.sleep(interval_s)

    dataset = RetrievalDataset(
        name=out.stem,
        version="1",
        generator_model=generator_model,
        corpus_stats={"documents": n_docs, "chunks": n_chunks},
        cases=cases,
    )
    dataset.save_jsonl(out)
    print(f"wrote {len(cases)} cases -> {out} (skipped {skipped})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--out", type=Path, default=Path("evalsets/retrieval-v1.jsonl"))
    parser.add_argument("--interval", type=float, default=6.5, help="seconds between LLM calls")
    parser.add_argument("--model", default=None, help="override eval_generator_model")
    args = parser.parse_args()
    try:
        asyncio.run(generate(args.n, args.out, args.interval, args.model))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
