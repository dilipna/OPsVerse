import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from opsverse_api import deps
from opsverse_api.db.models import RequestLedger
from opsverse_rag.chat import ChatDelta, ChatDone, ChatError, ChatSources, SourceInfo


def make_events(error: bool = False):
    yield ChatSources(
        sources=[
            SourceInfo(
                index=1,
                id="c1",
                source="k8s.md",
                score=0.9,
                text="HPA scales on metrics",
            )
        ],
        degraded=["rerank_skipped"],
    )
    yield ChatDelta(text="HPA scales ")
    yield ChatDelta(text="pods [1].")
    if error:
        yield ChatError(message="generation failed: boom")
    else:
        yield ChatDone(
            model="gemini/gemini-2.5-flash",
            cited=[1],
            prompt_tokens=120,
            completion_tokens=15,
            cost_usd=0.00012,
            latency_ms=850.0,
            first_token_ms=400.0,
            degraded=["rerank_skipped"],
        )


class FakeChatService:
    def __init__(self, error: bool = False):
        self.error = error
        self.last_query = None
        self.last_image = None

    async def stream_chat(
        self, query, *, history=None, k=None, filters=None, image_b64=None, image_mime="image/png"
    ):
        self.last_query = query
        self.last_image = image_b64
        for event in make_events(self.error):
            yield event


def wire(env, error: bool = False) -> FakeChatService:
    fake = FakeChatService(error)
    env.app.dependency_overrides[deps.get_chat_service] = lambda: fake
    env.app.dependency_overrides[deps.get_chat_service_ws] = lambda: fake
    # the ledger writer reads the sessionmaker off app.state
    env.app.state.db_sessionmaker = env.sessionmaker
    return fake


async def test_chat_sse_stream(env):
    wire(env)
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://t") as client:
        resp = await client.post("/v1/chat", json={"query": "how does HPA scale?"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    body = resp.text
    events = [block for block in body.split("\n\n") if block.strip()]
    names = [block.split("\n")[0].removeprefix("event: ") for block in events]
    assert names == ["sources", "delta", "delta", "done"]
    assert '"source":"k8s.md"' in events[0].split("\n")[1]

    async with env.sessionmaker() as session:
        row = (await session.execute(sa.select(RequestLedger))).scalar_one()
    assert row.route == "/v1/chat"
    assert row.status == "degraded"
    assert row.prompt_tokens == 120
    assert row.meta["cited"] == [1]


async def test_chat_non_streaming(env):
    wire(env)
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://t") as client:
        resp = await client.post("/v1/chat", json={"query": "how does HPA scale?", "stream": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "HPA scales pods [1]."
    assert data["sources"]["sources"][0]["source"] == "k8s.md"
    assert data["done"]["cited"] == [1]
    assert data["error"] is None


class RecordingLedger:
    """Async-sessionmaker stand-in that records added rows.

    The WS test needs it twice over: the test sqlite connection is bound to
    the pytest event loop and can't be used from TestClient's portal loop,
    and the lifespan (which TestClient runs) rebuilds db_sessionmaker from
    real settings — without rewiring, ledger writes land in the developer's
    live Postgres.
    """

    def __init__(self):
        self.rows = []

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, row):
        self.rows.append(row)

    async def commit(self):
        return None


def test_chat_websocket_multi_turn(env):
    from fastapi.testclient import TestClient

    fake = wire(env)
    ledger = RecordingLedger()
    with TestClient(env.app) as client:
        env.app.state.db_sessionmaker = ledger  # lifespan just clobbered it
        with client.websocket_connect("/v1/chat/stream") as ws:
            # bad payload -> error event, socket stays usable
            ws.send_json({"nope": True})
            assert ws.receive_json()["type"] == "error"

            for turn in range(2):
                ws.send_json({"query": f"turn {turn}", "image_base64": "aGk=", "k": 3})
                types = [ws.receive_json()["type"] for _ in range(4)]
                assert types == ["sources", "delta", "delta", "done"]
    assert fake.last_query == "turn 1"
    assert fake.last_image == "aGk="

    # both turns hit the recording ledger — guards the rewiring above
    assert len(ledger.rows) == 2
    assert {row.route for row in ledger.rows} == {"/v1/chat/stream"}
    assert all(row.meta["has_image"] for row in ledger.rows)


async def test_chat_error_recorded(env):
    wire(env, error=True)
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://t") as client:
        resp = await client.post("/v1/chat", json={"query": "q", "stream": False})
    assert resp.json()["error"] == "generation failed: boom"

    async with env.sessionmaker() as session:
        row = (await session.execute(sa.select(RequestLedger))).scalar_one()
    assert row.status == "error"
    assert row.model is None
