"""Per-client rate limits (threat model T-10)."""

import pytest
from httpx import ASGITransport, AsyncClient

from rype_api import deps
from rype_api.ratelimit import WINDOW_S, RateLimiter
from rype_core.settings import get_settings


@pytest.fixture
def limits(monkeypatch):
    def apply(**values: str) -> None:
        for key, value in values.items():
            monkeypatch.setenv(f"RYPE_{key.upper()}", value)
        get_settings.cache_clear()

    yield apply
    get_settings.cache_clear()


def client_for(env) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=env.app), base_url="http://test")


class FakeRetriever:
    async def search(self, *args, **kwargs):
        return []


async def test_search_returns_429_with_retry_after(env, limits):
    limits(rate_limit_search_per_minute="3")
    env.app.dependency_overrides[deps.get_retriever] = FakeRetriever
    async with client_for(env) as client:
        codes = [
            (await client.post("/v1/search", json={"query": "pods"})).status_code for _ in range(5)
        ]
        blocked = await client.post("/v1/search", json={"query": "pods"})
    assert codes[:3] == [200, 200, 200]
    assert codes[3:] == [429, 429]
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["retry-after"]) <= WINDOW_S


async def test_random_api_keys_do_not_reset_the_budget(env, limits):
    limits(rate_limit_search_per_minute="2", admin_api_key="real-admin-key")
    env.app.dependency_overrides[deps.get_retriever] = FakeRetriever
    async with client_for(env) as client:
        codes = [
            (
                await client.post(
                    "/v1/search", json={"query": "pods"}, headers={"X-API-Key": f"fake-{i}"}
                )
            ).status_code
            for i in range(4)
        ]
        admin = await client.post(
            "/v1/search", json={"query": "pods"}, headers={"X-API-Key": "real-admin-key"}
        )
    assert codes == [200, 200, 429, 429]
    assert admin.status_code == 200  # the verified admin has its own budget


async def test_zero_disables_a_group(env, limits):
    limits(rate_limit_search_per_minute="0")
    env.app.dependency_overrides[deps.get_retriever] = FakeRetriever
    async with client_for(env) as client:
        codes = {
            (await client.post("/v1/search", json={"query": "q"})).status_code for _ in range(30)
        }
    assert codes == {200}


async def test_window_resets():
    now = [1000.0 * WINDOW_S]
    limiter = RateLimiter(clock=lambda: now[0])
    assert [(await limiter.hit("chat", "ip:a"))[0] for _ in range(3)] == [1, 2, 3]
    now[0] += WINDOW_S
    assert (await limiter.hit("chat", "ip:a"))[0] == 1


class FakeRedis:
    def __init__(self, fail: bool = False):
        self.counts: dict[str, int] = {}
        self.ttl: dict[str, int] = {}
        self.fail = fail

    async def incr(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        self.ttl[key] = seconds


async def test_redis_counters_are_shared_and_expire():
    redis = FakeRedis()
    replica_a, replica_b = RateLimiter(redis), RateLimiter(redis)
    await replica_a.hit("chat", "ip:a")
    count, _ = await replica_b.hit("chat", "ip:a")
    assert count == 2  # both replicas see one budget
    assert list(redis.ttl.values()) == [WINDOW_S * 2]


async def test_redis_outage_falls_back_to_local_limits():
    limiter = RateLimiter(FakeRedis(fail=True))
    counts = [(await limiter.hit("chat", "ip:a"))[0] for _ in range(3)]
    assert counts == [1, 2, 3]  # still counting, not unlimited


def test_websocket_charges_the_chat_budget_per_message(env, limits):
    from fastapi.testclient import TestClient

    from rype_rag.chat import ChatDelta

    class OneLineService:
        async def stream_chat(self, query, **kwargs):
            yield ChatDelta(text="ok")

    class NoLedger:  # _write_ledger is best-effort; make it fail fast and quietly
        def __call__(self):
            raise RuntimeError("no database in this test")

    limits(rate_limit_chat_per_minute="2")
    env.app.dependency_overrides[deps.get_chat_service_ws] = OneLineService
    with TestClient(env.app) as client:
        env.app.state.db_sessionmaker = NoLedger()
        with client.websocket_connect("/v1/chat/stream") as ws:
            replies = []
            for _ in range(3):
                ws.send_json({"query": "pods"})
                replies.append(ws.receive_json())
    assert [r["type"] for r in replies] == ["delta", "delta", "error"]
    assert replies[2]["message"] == "rate limit exceeded"
    assert 1 <= replies[2]["retry_after"] <= WINDOW_S
