"""RAG answer-quality suite: faithfulness + answer relevance, judge-cached.

Runs questions from a retrieval eval set through the live /v1/chat endpoint
(non-streaming), judges each answer with a cached LLM judge, and records an
eval_runs row with per-case eval_results in Postgres, plus a *-summary.json
report the /evals page serves.

Usage:
    uv run python -m opsverse_evals.rag_suite --n 20                 # smoke
    uv run python -m opsverse_evals.rag_suite --n 20 --run-id <id>   # resume
"""

import argparse
import asyncio
import json
import statistics
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from opsverse_core.llm import LiteLLMClient
from opsverse_core.settings import get_settings
from opsverse_evals.judge import CachedJudge, JudgeError
from opsverse_evals.schemas import RetrievalDataset

FAITHFULNESS_PROMPT = """\
You are grading a RAG assistant's answer for faithfulness to its sources.

Sources given to the assistant:
{context}

Assistant's answer:
{answer}

List every factual claim the answer makes, and for each decide whether it is
supported by the sources above. A refusal or "the context does not contain
this" statement is not a claim. Return ONLY JSON:
{{"claims": [{{"claim": "...", "supported": true|false}}, ...]}}"""

RELEVANCE_PROMPT = """\
You are grading whether an answer addresses the user's question.

Question: {question}

Answer:
{answer}

Score how directly the answer addresses the question on a 0.0-1.0 scale
(1.0 = fully addresses it; a justified "the sources don't cover this" with
pointers still scores >= 0.5; an off-topic answer scores near 0).
Return ONLY JSON: {{"score": <float>, "reason": "<one sentence>"}}"""


def git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def faithfulness_score(verdict: dict[str, Any]) -> tuple[float, int]:
    claims = verdict.get("claims") or []
    if not claims:
        return 1.0, 0  # nothing asserted -> nothing unfaithful
    supported = sum(1 for c in claims if c.get("supported"))
    return supported / len(claims), len(claims)


async def _existing_case_ids(engine: AsyncEngine, run_id: str) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            sa.text("SELECT DISTINCT case_id FROM eval_results WHERE run_id = :r"),
            {"r": run_id},
        )
        return {row.case_id for row in rows}


async def run_suite(
    dataset_path: Path,
    n: int,
    api: str,
    run_id: str | None,
    out_dir: Path,
    interval_s: float,
) -> None:
    settings = get_settings()
    dataset = RetrievalDataset.load_jsonl(dataset_path)
    cases = dataset.cases[:n]
    engine = create_async_engine(settings.database_url)
    judge_llm = LiteLLMClient(
        [settings.eval_generator_model],
        {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
        timeout_s=60,
        max_tokens=1024,
        reasoning_effort=settings.chat_reasoning_effort,
    )
    judge = CachedJudge(judge_llm, engine, settings.eval_generator_model)

    if run_id is None:
        run_id = str(uuid.uuid4())
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO eval_runs"
                    " (id, suite, dataset, model, judge_model, git_sha, status, params,"
                    "  started_at)"
                    " VALUES (:id, 'rag-quality', :ds, :model, :judge, :sha, 'running',"
                    "  :params, now())"
                ),
                {
                    "id": run_id,
                    "ds": dataset.name,
                    "model": settings.chat_model,
                    "judge": judge.judge_model,
                    "sha": git_sha(),
                    "params": json.dumps({"n": n, "k": settings.chat_context_k}),
                },
            )
        print(f"run: {run_id}")
    done_ids = await _existing_case_ids(engine, run_id)
    if done_ids:
        print(f"resuming run {run_id}: {len(done_ids)} cases already judged")

    async with httpx.AsyncClient(timeout=180.0) as client:
        for i, case in enumerate(cases, 1):
            if case.id in done_ids:
                continue
            resp = await client.post(
                f"{api}/v1/chat", json={"query": case.question, "stream": False}
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                print(f"[{i}/{len(cases)}] chat error, skipping: {data['error'][:120]}")
                continue
            answer = data["answer"]
            context = "\n\n".join(
                f"[{s['index']}] {s['source']}\n{s['text']}" for s in data["sources"]["sources"]
            )

            scores: dict[str, tuple[float, dict[str, Any]]] = {}
            try:
                verdict = await judge.judge(
                    FAITHFULNESS_PROMPT.format(context=context or "(none)", answer=answer)
                )
                score, n_claims = faithfulness_score(verdict)
                scores["faithfulness"] = (score, {"claims": n_claims, "verdict": verdict})
                verdict = await judge.judge(
                    RELEVANCE_PROMPT.format(question=case.question, answer=answer)
                )
                scores["answer_relevance"] = (
                    max(0.0, min(1.0, float(verdict.get("score", 0.0)))),
                    {"verdict": verdict},
                )
            except (JudgeError, ValueError, TypeError) as exc:
                print(f"[{i}/{len(cases)}] judge failed, skipping case: {exc}")
                continue
            # deterministic, judge-free metric: did the answer cite anything?
            cited = data["done"]["cited"] if data.get("done") else []
            scores["citation_used"] = (1.0 if cited else 0.0, {"cited": cited})

            async with engine.begin() as conn:
                for metric, (score, raw) in scores.items():
                    await conn.execute(
                        sa.text(
                            "INSERT INTO eval_results (id, run_id, case_id, metric, score, raw,"
                            " created_at) VALUES (:id, :r, :c, :m, :s, :raw, now())"
                            " ON CONFLICT (run_id, case_id, metric) DO NOTHING"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "r": run_id,
                            "c": case.id,
                            "m": metric,
                            "s": score,
                            "raw": json.dumps(raw),
                        },
                    )
            line = ", ".join(f"{m}={s[0]:.2f}" for m, s in scores.items())
            print(f"[{i}/{len(cases)}] {line}  ({case.question[:60]}…)", flush=True)
            await asyncio.sleep(interval_s)

    # summarise
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                sa.text("SELECT metric, score FROM eval_results WHERE run_id = :r"),
                {"r": run_id},
            )
        ).all()
    by_metric: dict[str, list[float]] = {}
    for row in rows:
        by_metric.setdefault(row.metric, []).append(row.score)
    summary = {
        metric: {"mean": round(statistics.mean(vals), 4), "n": len(vals)}
        for metric, vals in sorted(by_metric.items())
    }
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "UPDATE eval_runs SET status='done', summary=:s, finished_at=now() WHERE id = :r"
            ),
            {"s": json.dumps(summary), "r": run_id},
        )
    await engine.dispose()

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    report = {
        "report": "rag-quality-smoke",
        "kind": "rag-quality",
        "date": stamp,
        "dataset": dataset.name,
        "cases": len(cases),
        "generator_model": get_settings().chat_model,
        "corpus_stats": dataset.corpus_stats,
        "k": get_settings().chat_context_k,
        "run_id": run_id,
        "judge_model": judge.judge_model,
        "judge_cache": {"hits": judge.cache_hits, "misses": judge.cache_misses},
        # same shape the /evals page renders for ablation reports:
        # mode -> metric -> value
        "results": {"chat": {f"judge:{m}": v["mean"] for m, v in summary.items()}},
    }
    (out_dir / "rag-quality-smoke-summary.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8"
    )
    print(json.dumps(summary, indent=1))
    print(f"judge cache: {judge.cache_hits} hits / {judge.cache_misses} misses")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evalsets/retrieval-v1.jsonl"))
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--api", default="http://localhost:8100")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out", type=Path, default=Path("docs/reports"))
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    asyncio.run(run_suite(args.dataset, args.n, args.api, args.run_id, args.out, args.interval))


if __name__ == "__main__":
    main()
