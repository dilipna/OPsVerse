import anyio.to_thread

from opsverse_rag.embeddings import Embedder
from opsverse_rag.rerank import Reranker
from opsverse_rag.schemas import RetrievedChunk, SearchFilters, SearchMode
from opsverse_rag.store import QdrantStore

RERANK_POOL_FACTOR = 3  # fetch k*3 candidates when reranking


class Retriever:
    def __init__(self, store: QdrantStore, embedder: Embedder, reranker: Reranker | None = None):
        self._store = store
        self._embedder = embedder
        self._reranker = reranker

    async def search(
        self,
        query: str,
        *,
        k: int = 8,
        mode: SearchMode = SearchMode.HYBRID,
        rerank: bool = False,
        filters: SearchFilters | None = None,
    ) -> list[RetrievedChunk]:
        dense = None
        sparse = None
        if mode in (SearchMode.DENSE, SearchMode.HYBRID):
            dense = (await anyio.to_thread.run_sync(self._embedder.embed_dense, [query]))[0]
        if mode in (SearchMode.SPARSE, SearchMode.HYBRID):
            sparse = (await anyio.to_thread.run_sync(self._embedder.embed_sparse, [query]))[0]

        use_reranker = rerank and self._reranker is not None
        fetch_k = k * RERANK_POOL_FACTOR if use_reranker else k
        hits = await self._store.query(
            mode=mode, k=fetch_k, dense=dense, sparse=sparse, filters=filters
        )

        if use_reranker and hits:
            assert self._reranker is not None
            texts = [hit.text for hit in hits]
            scores = await anyio.to_thread.run_sync(self._reranker.rerank, query, texts)
            for hit, score in zip(hits, scores, strict=True):
                hit.rerank_score = float(score)
            hits.sort(key=lambda h: h.rerank_score or float("-inf"), reverse=True)
            hits = hits[:k]
        return hits
