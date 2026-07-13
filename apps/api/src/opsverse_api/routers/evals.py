import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/evals", tags=["evals"])


def _reports_dir(request: Request) -> Path:
    return Path(request.app.state.settings.reports_dir)


@router.get("/reports")
async def list_reports(request: Request) -> list[dict[str, Any]]:
    """Summaries of all eval/benchmark reports on disk.

    Interim source: `*-summary.json` files written by the eval harnesses.
    Phase 4 replaces this with Postgres-backed eval_runs.
    """
    reports_dir = _reports_dir(request)
    if not reports_dir.is_dir():
        return []
    summaries = []
    for path in sorted(reports_dir.glob("*-summary.json")):
        try:
            summaries.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return summaries


@router.get("/reports/{name}")
async def get_report(name: str, request: Request) -> dict[str, Any]:
    path = (_reports_dir(request) / f"{name}-summary.json").resolve()
    # the name is caller-controlled: never let it escape the reports dir
    if path.parent != _reports_dir(request).resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="report not found")
    return json.loads(path.read_text(encoding="utf-8"))
