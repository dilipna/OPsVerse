import json
from pathlib import Path
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from opsverse_api.db.models import EvalRun
from opsverse_api.deps import get_session

router = APIRouter(prefix="/evals", tags=["evals"])


def _reports_dir(request: Request) -> Path:
    return Path(request.app.state.settings.reports_dir)


def _disk_reports(reports_dir: Path) -> dict[str, dict[str, Any]]:
    """Committed *-summary.json artifacts — history that predates eval_runs
    (or ran on another machine against a database this one doesn't have)."""
    reports: dict[str, dict[str, Any]] = {}
    if not reports_dir.is_dir():
        return reports
    for path in sorted(reports_dir.glob("*-summary.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("report"):
            reports[payload["report"]] = payload
    return reports


async def _db_reports(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Finished eval_runs, keyed by report name; later runs win a name."""
    runs = (
        (
            await session.execute(
                sa.select(EvalRun)
                .where(EvalRun.status == "done", EvalRun.summary.is_not(None))
                .order_by(EvalRun.finished_at)
            )
        )
        .scalars()
        .all()
    )
    reports: dict[str, dict[str, Any]] = {}
    for run in runs:
        summary = run.summary
        if isinstance(summary, dict) and summary.get("report"):
            reports[summary["report"]] = summary
    return reports


@router.get("/reports")
async def list_reports(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[dict[str, Any]]:
    """All eval reports: Postgres eval_runs merged over committed artifacts."""
    merged = _disk_reports(_reports_dir(request)) | await _db_reports(session)
    return sorted(merged.values(), key=lambda r: str(r.get("report", "")))


@router.get("/reports/{name}")
async def get_report(
    name: str, request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict[str, Any]:
    db_reports = await _db_reports(session)
    if name in db_reports:
        return db_reports[name]
    path = (_reports_dir(request) / f"{name}-summary.json").resolve()
    # the name is caller-controlled: never let it escape the reports dir
    if path.parent != _reports_dir(request).resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="report not found")
    return json.loads(path.read_text(encoding="utf-8"))
