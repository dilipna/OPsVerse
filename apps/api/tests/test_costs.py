from httpx import ASGITransport, AsyncClient

from opsverse_api.db.models import RequestLedger


async def seed(env):
    async with env.sessionmaker() as session:
        session.add_all(
            [
                RequestLedger(
                    route="/v1/chat",
                    model="gemini/gemini-3.5-flash",
                    status="ok",
                    prompt_tokens=1000,
                    completion_tokens=200,
                    cost_usd=0.003,
                    latency_ms=20000.0,
                    first_token_ms=18000.0,
                    meta={},
                ),
                RequestLedger(
                    route="/v1/chat",
                    model="gemini/gemini-3.5-flash",
                    status="degraded",
                    prompt_tokens=500,
                    completion_tokens=100,
                    cost_usd=0.001,
                    latency_ms=10000.0,
                    first_token_ms=9000.0,
                    meta={},
                ),
                RequestLedger(route="/v1/chat/stream", model=None, status="error", meta={}),
            ]
        )
        await session.commit()


async def test_cost_summary(env):
    await seed(env)
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://t") as client:
        resp = await client.get("/v1/costs/summary")
    assert resp.status_code == 200
    data = resp.json()

    totals = data["totals"]
    assert totals["requests"] == 3
    assert totals["errors"] == 1
    assert totals["degraded"] == 1
    assert totals["prompt_tokens"] == 1500
    assert abs(totals["cost_usd"] - 0.004) < 1e-9
    assert totals["avg_latency_ms"] == 15000.0

    by_model = {(m["model"], m["route"]): m for m in data["by_model"]}
    flash = by_model[("gemini/gemini-3.5-flash", "/v1/chat")]
    assert flash["requests"] == 2
    assert flash["completion_tokens"] == 300
    assert by_model[(None, "/v1/chat/stream")]["errors"] == 1
