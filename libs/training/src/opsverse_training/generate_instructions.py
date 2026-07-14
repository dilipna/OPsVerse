"""Generate a synthetic instruction dataset from the ingested corpus.

Three formats (tradeoff/"X vs Y" pairs are a later addition — they need
cross-document chunk pairing, and shipping three grounded formats beats four
sloppy ones):
- qa:        realistic question a DevOps engineer would ask + grounded answer
- explain:   config/code excerpt -> what it does and why it's written that way
- diagnosis: realistic failure symptom this doc resolves -> diagnosis + fix

Pipeline per docs/eval-contamination-policy.md: generate -> validate ->
quality-filter -> dedup (exact + near-dup) -> decontaminate vs frozen eval
sets -> JSONL + manifest (with a mandatory decontamination entry). Free-tier
aware: throttled, backoff on errors, resumable via a .partial.jsonl keyed by
(chunk, format).

Usage:
    uv run python -m opsverse_training.generate_instructions --n 60
    # then: dvc add data/instructions && dvc push
"""

import argparse
import asyncio
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from opsverse_core.llm import LiteLLMClient, LLMError
from opsverse_core.settings import get_settings
from opsverse_evals.contamination import ContaminationGuard
from opsverse_evals.judge import parse_json_reply
from opsverse_training.quality import Deduper, quality_drop_reason
from opsverse_training.schemas import DatasetManifest, Format, InstructionPair, Message

PROMPTS: dict[Format, str] = {
    "qa": """\
You are creating training data for a DevOps/MLOps assistant. Below is one
documentation excerpt. Write ONE realistic question a working engineer would
ask (do not mention any excerpt or document — the question must stand alone),
and answer it using only facts from the excerpt. The answer must be
self-contained, technically precise, and never refer to "the excerpt",
"the context", or "the documentation above".

Return ONLY JSON: {{"user": "...", "assistant": "..."}}
If the excerpt is boilerplate with nothing worth teaching, return {{"skip": true}}.

Excerpt (source: {source}, tool: {tool}):
---
{text}
---""",
    "explain": """\
You are creating training data for a DevOps/MLOps assistant. Below is a
configuration/code excerpt. Write a user message that shows the relevant
config/code snippet and asks what it does (as an engineer pasting a snippet
would), and an assistant reply explaining what it does, section by section,
and why it is written that way. Ground every statement in the excerpt; the
reply must never refer to "the excerpt" or "the context".

Return ONLY JSON: {{"user": "...", "assistant": "..."}}
If the excerpt contains no config or code worth explaining, return {{"skip": true}}.

Excerpt (source: {source}, tool: {tool}):
---
{text}
---""",
    "diagnosis": """\
You are creating training data for a DevOps/MLOps assistant. Below is a
documentation excerpt. Invent ONE realistic failure scenario that this
excerpt's content would resolve: the user message describes the symptom the
way a stressed engineer would (error message, what they tried), and the
assistant reply diagnoses the likely cause and gives the fix, grounded in
facts from the excerpt. The reply must never refer to "the excerpt" or
"the context".

Return ONLY JSON: {{"user": "...", "assistant": "..."}}
If no plausible failure maps to this excerpt, return {{"skip": true}}.

Excerpt (source: {source}, tool: {tool}):
---
{text}
---""",
}

# One chunk per document (the corpus repeats similar content across pages),
# meatiest chunk first, deterministic order so re-runs sample identically.
SAMPLE_SQL = sa.text("""
    SELECT chunk_id, document_id, text, section, source, tool, doc_type FROM (
        SELECT DISTINCT ON (c.document_id)
            c.id::text AS chunk_id, c.document_id::text AS document_id, c.text,
            c.section, d.uri AS source, d.tool, d.doc_type
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE c.embedding_status = 'embedded' AND length(c.text) >= 300
        ORDER BY c.document_id, c.token_count DESC
    ) picked
    ORDER BY md5(document_id)
""")


def git_rev() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def plan_tasks(rows: list[Any], n: int) -> list[tuple[Any, Format]]:
    """Round-robin formats over distinct documents: n tasks, one per chunk."""
    formats: list[Format] = ["qa", "explain", "diagnosis"]
    return [(row, formats[i % len(formats)]) for i, row in enumerate(rows[:n])]


async def generate(n: int, out_dir: Path, interval_s: float, model: str | None) -> None:
    settings = get_settings()
    generator_model = model or settings.eval_generator_model
    llm = LiteLLMClient(
        [generator_model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=90,
        max_tokens=2048,
        reasoning_effort=settings.chat_reasoning_effort,
    )
    guard = ContaminationGuard.from_evalsets_dir(Path("evalsets"))

    out_dir.mkdir(parents=True, exist_ok=True)
    partial = out_dir / "instructions-v1.partial.jsonl"
    pairs: list[InstructionPair] = []
    if partial.exists():
        pairs = [
            InstructionPair.model_validate_json(line)
            for line in partial.read_text(encoding="utf-8").splitlines()
            if line
        ]
        print(f"resuming: {len(pairs)} pairs already generated")
    done_ids = {p.id for p in pairs}
    deduper = Deduper()
    for pair in pairs:
        deduper.add(pair.user_text)

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        rows = (await conn.execute(SAMPLE_SQL)).mappings().all()
        n_docs = (await conn.execute(sa.text("SELECT count(*) FROM documents"))).scalar_one()
        n_chunks = (await conn.execute(sa.text("SELECT count(*) FROM chunks"))).scalar_one()
    await engine.dispose()
    print(f"candidate documents: {len(rows)} (corpus: {n_docs} docs / {n_chunks} chunks)")

    drops: Counter[str] = Counter()
    with partial.open("a", encoding="utf-8") as sink:
        for row, fmt in plan_tasks(list(rows), n):
            pair_id = f"{row['chunk_id']}:{fmt}"
            if pair_id in done_ids:
                continue
            prompt = PROMPTS[fmt].format(
                source=row["source"], tool=row["tool"] or "-", text=row["text"][:6000]
            )
            reply = None
            for attempt in range(5):
                try:
                    reply = await llm.complete([{"role": "user", "content": prompt}])
                    break
                except LLMError as exc:
                    rate_limited = "RateLimit" in str(exc) or "429" in str(exc)
                    wait = (40.0 if rate_limited else 15.0) * (attempt + 1)
                    print(f"  LLM error, backing off {wait:.0f}s: {str(exc)[:160]}", flush=True)
                    await asyncio.sleep(wait)
            if reply is None:
                drops["llm_failed"] += 1
                continue
            parsed = parse_json_reply(reply.text)
            if not parsed or parsed.get("skip") or not parsed.get("user"):
                drops["skipped_by_generator"] += 1
                continue
            user = str(parsed.get("user", "")).strip()
            assistant = str(parsed.get("assistant", "")).strip()
            if reason := quality_drop_reason(user, assistant):
                drops[reason] += 1
                continue
            if deduper.is_duplicate(user):
                drops["duplicate"] += 1
                continue
            if guard.is_contaminated(user):
                drops["eval_contaminated"] += 1
                continue
            pair = InstructionPair(
                id=pair_id,
                format=fmt,
                messages=[
                    Message(role="user", content=user),
                    Message(role="assistant", content=assistant),
                ],
                source_chunk_ids=[row["chunk_id"]],
                tool=row["tool"],
                doc_type=row["doc_type"],
                generator_model=generator_model,
            )
            deduper.add(user)
            pairs.append(pair)
            sink.write(pair.model_dump_json() + "\n")
            sink.flush()
            print(f"[{len(pairs)}] {fmt}: {user[:70]}", flush=True)
            await asyncio.sleep(interval_s)

    (out_dir / "instructions-v1.jsonl").write_text(
        "".join(p.model_dump_json() + "\n" for p in pairs), encoding="utf-8"
    )
    manifest = DatasetManifest(
        name="instructions",
        version="1",
        generator_model=generator_model,
        git_rev=git_rev(),
        corpus={"documents": n_docs, "chunks": n_chunks},
        examples=len(pairs),
        by_format=dict(Counter(p.format for p in pairs)),
        by_tool=dict(Counter(p.tool or "unknown" for p in pairs)),
        drops_by_reason=dict(drops),
        decontamination={
            "policy": "docs/eval-contamination-policy.md",
            "guard": "opsverse_evals.contamination.ContaminationGuard",
            "eval_questions_protected": len(guard.hashes),
            "dropped": drops.get("eval_contaminated", 0),
        },
    )
    (out_dir / "manifest.json").write_text(manifest.model_dump_json(indent=1), encoding="utf-8")
    print(f"\nwrote {len(pairs)} pairs -> {out_dir / 'instructions-v1.jsonl'}")
    print(f"drops: {dict(drops)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=60, help="generation tasks to attempt")
    parser.add_argument("--out", type=Path, default=Path("data/instructions"))
    parser.add_argument("--interval", type=float, default=6.5)
    parser.add_argument("--model", default=None, help="override eval_generator_model")
    args = parser.parse_args()
    try:
        asyncio.run(generate(args.n, args.out, args.interval, args.model))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
