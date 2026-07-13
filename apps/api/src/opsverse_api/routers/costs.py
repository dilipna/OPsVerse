from datetime import UTC, datetime, timedelta
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from opsverse_api.db.models import RequestLedger
from opsverse_api.deps import get_session

router = APIRouter(prefix="/costs", tags=["costs"])


class ModelCosts(BaseModel):
    model: str | None
    route: str
    requests: int
    errors: int
    degraded: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    avg_latency_ms: float | None
    avg_first_token_ms: float | None


class CostSummary(BaseModel):
    since: datetime
    totals: ModelCosts
    by_model: list[ModelCosts]


def _row_to_costs(row, model: str | None = None, route: str = "*") -> ModelCosts:
    return ModelCosts(
        model=model,
        route=route,
        requests=row.requests or 0,
        errors=row.errors or 0,
        degraded=row.degraded or 0,
        prompt_tokens=row.prompt_tokens or 0,
        completion_tokens=row.completion_tokens or 0,
        cost_usd=float(row.cost_usd or 0),
        avg_latency_ms=round(row.avg_latency_ms, 1) if row.avg_latency_ms is not None else None,
        avg_first_token_ms=(
            round(row.avg_first_token_ms, 1) if row.avg_first_token_ms is not None else None
        ),
    )


_AGG = (
    sa.func.count().label("requests"),
    sa.func.sum(sa.case((RequestLedger.status == "error", 1), else_=0)).label("errors"),
    sa.func.sum(sa.case((RequestLedger.status == "degraded", 1), else_=0)).label("degraded"),
    sa.func.sum(RequestLedger.prompt_tokens).label("prompt_tokens"),
    sa.func.sum(RequestLedger.completion_tokens).label("completion_tokens"),
    sa.func.sum(RequestLedger.cost_usd).label("cost_usd"),
    sa.func.avg(RequestLedger.latency_ms).label("avg_latency_ms"),
    sa.func.avg(RequestLedger.first_token_ms).label("avg_first_token_ms"),
)


@router.get("/summary", response_model=CostSummary)
async def cost_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24 * 7,
) -> CostSummary:
    since = datetime.now(UTC) - timedelta(hours=hours)
    where = RequestLedger.created_at >= since

    total_row = (await session.execute(sa.select(*_AGG).where(where))).one()
    by_model_rows = (
        await session.execute(
            sa.select(RequestLedger.model, RequestLedger.route, *_AGG)
            .where(where)
            .group_by(RequestLedger.model, RequestLedger.route)
            .order_by(sa.desc("cost_usd"))
        )
    ).all()

    return CostSummary(
        since=since,
        totals=_row_to_costs(total_row),
        by_model=[_row_to_costs(row, model=row.model, route=row.route) for row in by_model_rows],
    )
