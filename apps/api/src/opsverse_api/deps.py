from collections.abc import AsyncIterator

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from opsverse_core.object_store import ObjectStore
from opsverse_rag import QdrantStore, Retriever
from opsverse_rag.embeddings import FastEmbedEmbedder
from opsverse_rag.rerank import CrossEncoderReranker


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db_sessionmaker() as session:
        yield session


async def get_arq_pool(request: Request) -> ArqRedis:
    """Lazily create the job-queue pool so API startup never requires Redis."""
    if request.app.state.arq_pool is None:
        try:
            request.app.state.arq_pool = await create_pool(
                RedisSettings.from_dsn(request.app.state.settings.redis_url)
            )
        except OSError as exc:
            raise HTTPException(status_code=503, detail="job queue unavailable") from exc
    return request.app.state.arq_pool


def get_object_store(request: Request) -> ObjectStore:
    return request.app.state.object_store


def get_retriever(request: Request) -> Retriever:
    """Built lazily: embedding/reranker models only load on first search."""
    if request.app.state.retriever is None:
        settings = request.app.state.settings
        embedder = FastEmbedEmbedder(
            settings.embedding_model, settings.sparse_model, settings.embedding_dim
        )
        store = QdrantStore(
            request.app.state.qdrant, settings.qdrant_collection, embedder.dense_dim
        )
        reranker = CrossEncoderReranker(settings.reranker_model)
        request.app.state.retriever = Retriever(store, embedder, reranker)
    return request.app.state.retriever
