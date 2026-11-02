"""Security telemetry endpoint: aggregation, alerts and access control."""

import pytest
from httpx import ASGITransport, AsyncClient

from opsverse_api.db.models import Document, RequestLedger
from opsverse_core.settings import get_settings


def client_for(env) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=env.app), base_url="http://test")


async def seed(env):
    async with env.sessionmaker() as session:
        session.add_all(
            [
                RequestLedger(route="/v1/chat", status="ok", meta={"injection_flags": []}),
                RequestLedger(
                    route="/v1/chat",
                    status="ok",
                    meta={"injection_flags": ["override_instructions", "obfuscation"]},
                ),
                RequestLedger(
                    route="/v1/chat/stream",
                    status="ok",
                    meta={
                        "injection_flags": [],
                        "output_guard": {"image_removed": 1, "link_removed": 2},
                    },
                ),
                RequestLedger(route="/v1/chat", status="error", meta={"output_guard": "corrupt"}),
                Document(
                    source_type="url",
                    uri="https://example.org/bad.md",
                    sha256="0" * 64,
                    status="quarantined",
                ),
                Document(
                    source_type="url",
                    uri="https://example.org/ok.md",
                    sha256="1" * 64,
                    status="ready",
                ),
            ]
        )
        await session.commit()


async def test_summary_counts_signals_findings_and_quarantine(env):
    await seed(env)
    async with client_for(env) as client:
        resp = await client.get("/v1/security/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["requests"] == 4
    assert body["flagged_queries"] == 1
    assert body["injection_signals"] == {"override_instructions": 1, "obfuscation": 1}
    assert body["guarded_answers"] == 1
    assert body["output_guard_findings"] == {"link_removed": 2, "image_removed": 1}
    assert body["quarantined_documents"] == 1
    assert body["quarantined_uris"] == ["https://example.org/bad.md"]
    assert len(body["alerts"]) == 2
    assert "output guard rewrote 1 answer" in body["alerts"][0]
    assert {e["route"] for e in body["recent_events"]} == {"/v1/chat", "/v1/chat/stream"}
    assert body["truncated"] is False


async def test_quiet_window_has_no_alerts(env):
    async with client_for(env) as client:
        body = (await client.get("/v1/security/summary")).json()
    assert body["requests"] == 0
    assert body["alerts"] == []


@pytest.fixture
def admin_key(monkeypatch):
    monkeypatch.setenv("OPSVERSE_ADMIN_API_KEY", "k-admin")
    get_settings.cache_clear()
    yield "k-admin"
    get_settings.cache_clear()


async def test_summary_is_admin_only(env, admin_key):
    async with client_for(env) as client:
        anonymous = await client.get("/v1/security/summary")
        admin = await client.get("/v1/security/summary", headers={"X-API-Key": admin_key})
    assert anonymous.status_code == 401
    assert admin.status_code == 200
