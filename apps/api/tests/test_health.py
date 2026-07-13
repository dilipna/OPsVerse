from fastapi.testclient import TestClient

from opsverse_api.main import create_app
from opsverse_api.routers import health


def test_live_returns_ok():
    with TestClient(create_app()) as client:
        resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_reports_degraded_when_a_check_fails(monkeypatch):
    async def passing(request):
        return None

    async def failing(request):
        raise ConnectionError("boom")

    monkeypatch.setattr(health, "CHECKS", {"good": passing, "bad": failing})
    with TestClient(create_app()) as client:
        resp = client.get("/health/ready")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["good"]["ok"] is True
    assert body["checks"]["bad"]["ok"] is False
    assert "ConnectionError" in body["checks"]["bad"]["error"]


def test_ready_is_200_when_all_checks_pass(monkeypatch):
    async def passing(request):
        return None

    monkeypatch.setattr(health, "CHECKS", {"only": passing})
    with TestClient(create_app()) as client:
        resp = client.get("/health/ready")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert resp.json()["checks"]["only"]["latency_ms"] >= 0
