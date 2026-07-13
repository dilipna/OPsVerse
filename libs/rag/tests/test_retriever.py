from opsverse_rag.retriever import Retriever
from opsverse_rag.schemas import RetrievedChunk, SearchMode, SparseVec


class FakeEmbedder:
    dense_dim = 4

    def embed_dense(self, texts):
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    def embed_sparse(self, texts):
        return [SparseVec(indices=[1], values=[1.0]) for _ in texts]


def _hit(hit_id: str, text: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(id=hit_id, score=score, text=text, source="a.md", document_id="d1")


class FakeStore:
    def __init__(self, hits):
        self.hits = hits
        self.last_kwargs = None

    async def query(self, **kwargs):
        self.last_kwargs = kwargs
        return list(self.hits)


class FakeReranker:
    def rerank(self, query, texts):
        # reverse the original order
        return [float(i) for i in range(len(texts))]


async def test_search_embeds_only_what_mode_needs():
    store = FakeStore([_hit("1", "a", 0.9)])
    retriever = Retriever(store, FakeEmbedder())  # type: ignore[arg-type]
    await retriever.search("q", mode=SearchMode.SPARSE)
    assert store.last_kwargs is not None
    assert store.last_kwargs["dense"] is None
    assert store.last_kwargs["sparse"] is not None


async def test_rerank_reorders_and_truncates():
    hits = [_hit(str(i), f"text {i}", 1.0 - i / 10) for i in range(6)]
    store = FakeStore(hits)
    retriever = Retriever(store, FakeEmbedder(), reranker=FakeReranker())  # type: ignore[arg-type]
    result = await retriever.search("q", k=2, rerank=True)

    # fetched a larger candidate pool for the reranker
    assert store.last_kwargs is not None
    assert store.last_kwargs["k"] == 6
    # FakeReranker scores ascending by position -> last candidate wins
    assert [r.id for r in result] == ["5", "4"]
    assert result[0].rerank_score == 5.0


async def test_no_rerank_keeps_store_order():
    hits = [_hit("1", "a", 0.9), _hit("2", "b", 0.8)]
    retriever = Retriever(FakeStore(hits), FakeEmbedder())  # type: ignore[arg-type]
    result = await retriever.search("q", k=2)
    assert [r.id for r in result] == ["1", "2"]
    assert result[0].rerank_score is None
