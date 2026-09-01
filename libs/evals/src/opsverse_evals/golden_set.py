"""Build a golden retrieval set with pooled, graded, multi-label relevance.

Why this exists
---------------
The shipped eval sets (`retrieval-v1/v2/v3`) label each question with the single
chunk it was generated from. ADR-0018 showed what that costs: `recall@k` becomes
`hit@k`, `precision@k` becomes `hit@k/k`, and contextual precision becomes
`mrr@k`. Rank-aware and set-based metrics cannot say anything independent when
there is exactly one relevant item.

This module fixes the *labels*, not the metrics.

Two pieces of standard IR methodology are applied:

**Pooling (TREC-style).** Candidates are pooled from *every* retrieval mode
(dense, sparse, hybrid, hybrid+rerank), deduplicated, and judged together. If
you judge only one system's top-k you learn what that system already believed:
its misses are never labelled, so its recall is flattered. Pooling roughly
doubles the judged set here (~19 candidates/query vs 10 for hybrid alone) and
lets every mode be scored against labels it did not choose.

**Position-randomised grading.** LLM judges favour items shown first. Candidates
are shuffled with a per-query deterministic seed before being shown to the
judge, so rank in the prompt carries no information about rank in any system.
The shuffle is reproducible from the seed, so the run can be re-derived.

Grades are TREC-conventional (3 fully answers / 2 substantially relevant /
1 on-topic / 0 irrelevant), and the whole pool for one query is graded in a
single call so the judge grades *comparatively* rather than in isolation.

Free-tier aware: throttled, 429-backoff, and resumable — each finished query is
appended to a `.partial.jsonl` immediately and re-runs skip it.

Usage:
    uv run python -m opsverse_evals.golden_set --n 100 \
        --out evalsets/retrieval-golden-v1.jsonl
"""

import argparse
import asyncio
import json
import random
from pathlib import Path

from opsverse_core.llm import LiteLLMClient, LLMError
from opsverse_core.settings import get_settings
from opsverse_evals.judge import parse_json_reply
from opsverse_evals.schemas import (
    GradedRetrievalCase,
    GradedRetrievalDataset,
    RetrievalDataset,
)

PROMPT = """\
You are grading search results for a DevOps/MLOps documentation search engine.

Question:
{question}

Below are {n} candidate documentation excerpts, labelled C1..C{n} in random order.
Grade EVERY candidate for how well it answers THE QUESTION ABOVE, on this scale:

  3 = fully answers the question on its own
  2 = substantially relevant; answers part of it or gives most of what is needed
  1 = on-topic / same technology, but does not answer the question
  0 = not relevant to the question

Grade on content only. Ignore formatting, length, and the order shown -- the
order is random and carries no meaning. Judge each candidate independently
against the question, but stay consistent across candidates.

Return ONLY a JSON object mapping every label to its grade, e.g.:
{{"C1": 0, "C2": 3, "C3": 1}}

Candidates:
{candidates}
"""

# Must be >= the window the question generator saw (`generate_retrieval_set.py`
# formats `text[:4000]`). Grading against a shorter excerpt asks the judge to
# find an answer that was, by construction, written from text it cannot see.
# Measured: 35% of corpus chunks exceed 900 chars, so a 900-char window graded
# seed chunks as low as 1 ("on-topic, does not answer") purely from truncation.
EXCERPT_CHARS = 4000


def load_chunk_text(corpus: Path) -> dict[str, str]:
    """chunk_id -> text, from the committed corpus dump."""
    texts: dict[str, str] = {}
    with corpus.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            texts[rec["id"]] = rec.get("text", "")
    return texts


def build_pools(raw_path: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """case_id -> pooled candidate ids, and case_id -> contributing modes."""
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    pools: dict[str, list[str]] = {}
    contributors: dict[str, list[str]] = {}
    for mode, cases in raw["results"].items():
        for case in cases:
            cid = case["case_id"]
            seen = pools.setdefault(cid, [])
            for chunk_id in case["retrieved_chunk_ids"]:
                if chunk_id not in seen:
                    seen.append(chunk_id)
            modes = contributors.setdefault(cid, [])
            if mode not in modes:
                modes.append(mode)
    return pools, contributors


async def build(
    evalset: Path,
    raw: Path,
    corpus: Path,
    out: Path,
    n: int,
    interval_s: float,
    model: str | None = None,
) -> None:
    settings = get_settings()
    judge_model = model or settings.eval_generator_model
    llm = LiteLLMClient(
        [judge_model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=90,
        max_tokens=1024,
        reasoning_effort=settings.chat_reasoning_effort,
    )

    dataset = RetrievalDataset.load_jsonl(evalset)
    pools, contributors = build_pools(raw)
    texts = load_chunk_text(corpus)
    print(f"{len(dataset.cases)} questions, {len(texts)} chunks in corpus")

    partial = out.with_suffix(".partial.jsonl")
    partial.parent.mkdir(parents=True, exist_ok=True)
    cases: list[GradedRetrievalCase] = []
    done: set[str] = set()
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line:
                case = GradedRetrievalCase.model_validate_json(line)
                cases.append(case)
                done.add(case.id)
        print(f"resuming: {len(cases)} queries already graded")

    skipped = 0
    with partial.open("a", encoding="utf-8") as sink:
        for src in dataset.cases:
            if len(cases) >= n:
                break
            if src.id in done:
                continue
            pool = list(pools.get(src.id, []))
            # the originating chunk is relevant by construction; guarantee it is
            # judged even if no retriever surfaced it
            for gold in src.relevant_chunk_ids:
                if gold not in pool:
                    pool.append(gold)
            pool = [cid for cid in pool if texts.get(cid)]
            if len(pool) < 2:
                skipped += 1
                continue

            # deterministic per-query shuffle: kills position bias, stays reproducible
            order = list(pool)
            random.Random(f"golden-v1:{src.id}").shuffle(order)
            labels = {f"C{i}": cid for i, cid in enumerate(order, 1)}
            blocks = "\n\n".join(
                f"[{label}]\n{texts[cid][:EXCERPT_CHARS]}" for label, cid in labels.items()
            )
            prompt = PROMPT.format(question=src.question, n=len(order), candidates=blocks)

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
                        f"{str(exc)[:160]}",
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

            grades: dict[str, int] = {}
            for label, cid in labels.items():
                raw_grade = parsed.get(label)
                if raw_grade is None:
                    continue
                try:
                    grade = int(raw_grade)
                except (TypeError, ValueError):
                    continue
                grades[cid] = max(0, min(3, grade))
            # a judge that graded almost nothing is a failed call, not a label set
            if len(grades) < max(2, len(order) // 2):
                skipped += 1
                continue

            case = GradedRetrievalCase(
                id=src.id,
                question=src.question,
                grades=grades,
                seed_grade=grades.get(src.relevant_chunk_ids[0])
                if src.relevant_chunk_ids
                else None,
                pool_size=len(order),
                pool_contributors=contributors.get(src.id, []),
                seed_chunk_id=src.relevant_chunk_ids[0] if src.relevant_chunk_ids else None,
            )
            cases.append(case)
            sink.write(case.model_dump_json() + "\n")
            sink.flush()
            n_rel = len(case.relevant_ids())
            print(
                f"[{len(cases)}/{n}] pool={len(order)} relevant>=2: {n_rel} | {src.question[:58]}",
                flush=True,
            )
            await asyncio.sleep(interval_s)

    golden = GradedRetrievalDataset(
        name="retrieval-golden-v1",
        version="1",
        judge_model=judge_model,
        relevance_threshold=2,
        notes=(
            "Pooled across dense/sparse/hybrid/hybrid+rerank top-10 (TREC-style), "
            "graded 0-3 by LLM judge, candidate order randomised per query with a "
            "deterministic seed to remove position bias."
        ),
        cases=cases,
    )
    golden.save_jsonl(out)
    multi = sum(1 for c in cases if len(c.relevant_ids()) > 1)
    graded_seed = [c for c in cases if c.seed_grade is not None]
    if graded_seed:
        recovered = sum(1 for c in graded_seed if (c.seed_grade or 0) >= 2)
        pct = 100 * recovered / len(graded_seed)
        print(
            f"seed-recovery: {recovered}/{len(graded_seed)} ({pct:.0f}%) of originating "
            "chunks graded >=2 -- a judge-sanity check, not a retrieval score"
        )
    print(f"\nwrote {out}: {len(cases)} queries ({skipped} skipped)")
    print(f"queries with >1 relevant chunk: {multi}/{len(cases)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evalset", type=Path, default=Path("evalsets/retrieval-v2.jsonl"))
    parser.add_argument(
        "--raw", type=Path, default=Path("docs/reports/retrieval-ablation-v2-raw.json")
    )
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus/chunks.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("evalsets/retrieval-golden-v1.jsonl"))
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--interval", type=float, default=6.5, help="seconds between LLM calls")
    parser.add_argument("--model", default=None, help="override eval_generator_model")
    args = parser.parse_args()

    asyncio.run(
        build(
            args.evalset,
            args.raw,
            args.corpus,
            args.out,
            args.n,
            args.interval,
            args.model,
        )
    )


if __name__ == "__main__":
    main()
