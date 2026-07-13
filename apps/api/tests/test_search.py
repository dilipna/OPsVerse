from httpx import ASGITransport, AsyncClient

from opsverse_api import deps
from opsverse_rag import RetrievedChunk


class FakeRetriever:
    def __init__(self):
        self.last_kwargs = None

    async def search(self, query, **kwargs):
        self.last_kwargs = {"query": query, **kwargs}
        return [
            RetrievedChunk(
                id="1", score=0.9, text="HPA scales pods", source="k8s.md", document_id="d1"
            )
        ]


async def test_search_route(env):
    fake = FakeRetriever()
    env.app.dependency_overrides[deps.get_retriever] = lambda: fake
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://t") as client:
        resp = await client.post(
            "/v1/search",
            json={"query": "how does HPA scale", "k": 3, "filters": {"tool": "kubernetes"}},
        )
    assert resp.status_code == 200
    hits = resp.json()["hits"]
    assert hits[0]["text"] == "HPA scales pods"
    assert fake.last_kwargs is not None
    assert fake.last_kwargs["k"] == 3
    assert fake.last_kwargs["filters"].tool == "kubernetes"


async def test_search_validates_query(env):
    env.app.dependency_overrides[deps.get_retriever] = lambda: FakeRetriever()
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://t") as client:
        resp = await client.post("/v1/search", json={"query": ""})
    assert resp.status_code == 422
