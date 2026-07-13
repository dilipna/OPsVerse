from collections.abc import AsyncIterator

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import HTTPException, Request, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from opsverse_core.llm import LiteLLMClient
from opsverse_core.object_store import ObjectStore
from opsverse_rag import ChatService, QdrantStore, Retriever
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


def _build_retriever(app) -> Retriever:
    """Built lazily: embedding/reranker models only load on first search."""
    if app.state.retriever is None:
        settings = app.state.settings
        embedder = FastEmbedEmbedder(
            settings.embedding_model, settings.sparse_model, settings.embedding_dim
        )
        store = QdrantStore(app.state.qdrant, settings.qdrant_collection, embedder.dense_dim)
        reranker = CrossEncoderReranker(settings.reranker_model)
        app.state.retriever = Retriever(store, embedder, reranker)
    return app.state.retriever


def get_retriever(request: Request) -> Retriever:
    return _build_retriever(request.app)


def _build_chat_service(app) -> ChatService:
    if app.state.chat_service is None:
        settings = app.state.settings
        llm = LiteLLMClient(
            [settings.chat_model, *settings.chat_fallback_models],
            {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key},
            timeout_s=settings.chat_llm_timeout_s,
            max_tokens=settings.chat_max_tokens,
            temperature=settings.chat_temperature,
            reasoning_effort=settings.chat_reasoning_effort,
        )
        app.state.chat_service = ChatService(
            _build_retriever(app),
            llm,
            context_k=settings.chat_context_k,
            retrieval_timeout_s=settings.chat_retrieval_timeout_s,
            rerank=settings.chat_rerank,
        )
    return app.state.chat_service


def get_chat_service(request: Request) -> ChatService:
    return _build_chat_service(request.app)


def get_chat_service_ws(websocket: WebSocket) -> ChatService:
    return _build_chat_service(websocket.app)
