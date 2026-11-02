"""Security telemetry: what the controls caught, and when it needs a human.

Detection without a response path is only logging. This endpoint turns the
request ledger and the document table into an answer for an operator:

- how many queries tripped injection signals (flagged, not blocked: T-02);
- how many answers the output guard had to rewrite (T-03). A rewrite means
  the model *produced* an image, off-allowlist link or credential, which is
  the observable symptom of a poisoned document that got past the ingest
  scan (T-01), so any non-zero count raises an alert;
- how many documents ingest quarantined, and which URIs, for review.

No query or answer text is returned; the ledger never stores it.
Admin-only, because it tells an attacker which signals they are tripping.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from opsverse_api.db.models import Document, RequestLedger
from opsverse_api.deps import get_session, require_admin

router = APIRouter(prefix="/security", tags=["security"], dependencies=[Depends(require_admin)])

MAX_LEDGER_ROWS = 10_000
RECENT_EVENTS = 20


class SecurityEvent(BaseModel):
    request_id: str
    created_at: datetime
    route: str
    injection_flags: list[str]
    output_guard: dict[str, int]


class SecuritySummary(BaseModel):
    since: datetime
    requests: int
    flagged_queries: int
    injection_signals: dict[str, int]
    guarded_answers: int
    output_guard_findings: dict[str, int]
    quarantined_documents: int
    quarantined_uris: list[str]
    alerts: list[str]
    recent_events: list[SecurityEvent]
    truncated: bool


def _flags(meta: dict[str, Any]) -> list[str]:
    value = meta.get("injection_flags") or []
    return [str(v) for v in value] if isinstance(value, list) else []


def _guard(meta: dict[str, Any]) -> dict[str, int]:
    value = meta.get("output_guard") or {}
    if not isinstance(value, dict):
        return {}
    return {str(k): int(v) for k, v in value.items() if isinstance(v, int | float)}


@router.get("/summary", response_model=SecuritySummary)
async def security_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24,
) -> SecuritySummary:
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = (
        (
            await session.execute(
                sa.select(RequestLedger)
                .where(RequestLedger.created_at >= since)
                .order_by(RequestLedger.created_at.desc())
                .limit(MAX_LEDGER_ROWS + 1)
            )
        )
        .scalars()
        .all()
    )
    truncated = len(rows) > MAX_LEDGER_ROWS
    rows = rows[:MAX_LEDGER_ROWS]

    signals: Counter[str] = Counter()
    findings: Counter[str] = Counter()
    flagged = guarded = 0
    events: list[SecurityEvent] = []
    for row in rows:
        meta = row.meta or {}
        flags, guard = _flags(meta), _guard(meta)
        signals.update(flags)
        findings.update(guard)
        flagged += bool(flags)
        guarded += bool(guard)
        if (flags or guard) and len(events) < RECENT_EVENTS:
            events.append(
                SecurityEvent(
                    request_id=str(row.id),
                    created_at=row.created_at,
                    route=row.route,
                    injection_flags=flags,
                    output_guard=guard,
                )
            )

    quarantined = (
        (
            await session.execute(
                sa.select(Document.uri)
                .where(Document.status == "quarantined", Document.created_at >= since)
                .order_by(Document.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    alerts: list[str] = []
    if guarded:
        alerts.append(
            f"The output guard rewrote {guarded} answer(s). The model produced an image, an "
            "off-allowlist link or a credential, which suggests a retrieved document is "
            "steering it. Review the recent events and the documents they retrieved."
        )
    if quarantined:
        alerts.append(
            f"{len(quarantined)} document(s) were quarantined at ingest. Review them before "
            "releasing any back into retrieval."
        )
    if truncated:
        alerts.append(f"Only the latest {MAX_LEDGER_ROWS} requests were scanned; narrow `hours`.")

    return SecuritySummary(
        since=since,
        requests=len(rows),
        flagged_queries=flagged,
        injection_signals=dict(signals.most_common()),
        guarded_answers=guarded,
        output_guard_findings=dict(findings.most_common()),
        quarantined_documents=len(quarantined),
        quarantined_uris=list(quarantined[:50]),
        alerts=alerts,
        recent_events=events,
        truncated=truncated,
    )
