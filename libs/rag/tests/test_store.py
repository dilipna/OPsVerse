from types import SimpleNamespace

import pytest
from qdrant_client import models

from opsverse_rag.schemas import SearchFilters, SearchMode, SparseVec
from opsverse_rag.store import QdrantStore


class FakeClient:
    def __init__(self):
        self.calls: list[dict] = []

    async def query_points(self, **kwargs):
        self.calls.append(kwargs)
        point = models.ScoredPoint(
            id="11111111-1111-1111-1111-111111111111",
            version=0,
            score=0.9,
            payload={
                "text": "some chunk",
                "source": "guide.md",
                "document_id": "22222222-2222-2222-2222-222222222222",
                "tool": "kubernetes",
            },
        )
        # the store only reads .points off the response
        return SimpleNamespace(points=[point])


DENSE_VEC = [0.1] * 4
SPARSE_VEC = SparseVec(indices=[1, 5], values=[0.5, 0.2])


async def test_hybrid_builds_rrf_with_two_prefetch():
    client = FakeClient()
    store = QdrantStore(client, "kb")  # type: ignore[arg-type]
    hits = await store.query(
        mode=SearchMode.HYBRID,
        k=5,
        dense=DENSE_VEC,
        sparse=SPARSE_VEC,
        filters=SearchFilters(tool="kubernetes"),
    )
    call = client.calls[0]
    assert isinstance(call["query"], models.FusionQuery)
    assert [p.using for p in call["prefetch"]] == ["dense", "sparse"]
    assert all(p.filter is not None for p in call["prefetch"])
    assert call["limit"] == 5
    assert hits[0].tool == "kubernetes" and hits[0].score == 0.9


async def test_dense_mode_uses_named_vector_and_filter():
    client = FakeClient()
    store = QdrantStore(client, "kb")  # type: ignore[arg-type]
    await store.query(mode=SearchMode.DENSE, k=3, dense=DENSE_VEC)
    call = client.calls[0]
    assert call["using"] == "dense"
    assert call["query"] == DENSE_VEC
    assert call["query_filter"] is None


async def test_hybrid_requires_both_vectors():
    store = QdrantStore(FakeClient(), "kb")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="hybrid"):
        await store.query(mode=SearchMode.HYBRID, k=3, dense=DENSE_VEC, sparse=None)
