"""Record eval reports as eval_runs rows — Postgres is the source of truth.

The *-summary.json files under docs/reports stay committed to git so a fresh
clone still has history to show, but every harness also records its report
here; /v1/evals/reports merges both with Postgres winning on name collisions.
"""

import json
import subprocess
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine


def git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


async def record_report(
    engine: AsyncEngine,
    suite: str,
    report: dict[str, Any],
    *,
    model: str | None = None,
    judge_model: str | None = None,
    params: dict[str, Any] | None = None,
) -> str:
    """Insert a finished eval_runs row whose summary is the renderable report."""
    run_id = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO eval_runs"
                " (id, suite, dataset, model, judge_model, git_sha, status, params, summary,"
                "  started_at, finished_at)"
                " VALUES (:id, :suite, :ds, :model, :judge, :sha, 'done', :params, :summary,"
                "  now(), now())"
            ),
            {
                "id": run_id,
                "suite": suite,
                "ds": str(report.get("dataset", "")),
                "model": model,
                "judge": judge_model,
                "sha": git_sha(),
                "params": json.dumps(params or {}),
                "summary": json.dumps(report),
            },
        )
    return run_id
