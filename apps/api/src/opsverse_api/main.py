from contextlib import asynccontextmanager
from typing import cast

import httpx
from arq.connections import ArqRedis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from opsverse_api.db.session import build_sessionmaker
from opsverse_api.routers import chat, costs, evals, health, ingest, search
from opsverse_core.object_store import ObjectStore
from opsverse_core.settings import get_settings
from opsverse_core.tracing import build_tracer


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    # Clients are lazy: nothing connects until first use, so startup
    # succeeds even when the compose stack is down (readiness reports it).
    app.state.db_engine = create_async_engine(settings.database_url)
    app.state.db_sessionmaker = build_sessionmaker(app.state.db_engine)
    app.state.redis = Redis.from_url(settings.redis_url)
    app.state.qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    app.state.http = httpx.AsyncClient(timeout=5.0)
    app.state.object_store = ObjectStore(settings)
    app.state.arq_pool = None  # created lazily on first enqueue (see deps.py)
    app.state.retriever = None  # created lazily on first search (see deps.py)
    app.state.chat_service = None  # created lazily on first chat (see deps.py)
    app.state.gateway = None  # LLM gateway, created with the chat service
    # Tracer is built once: NullTracer unless OPSVERSE_LANGFUSE_HOST is set.
    app.state.tracer = build_tracer(
        settings.langfuse_host, settings.langfuse_public_key, settings.langfuse_secret_key
    )
    try:
        yield
    finally:
        arq_pool = cast("ArqRedis | None", app.state.arq_pool)
        if arq_pool is not None:
            await arq_pool.aclose()
        await app.state.http.aclose()
        await app.state.qdrant.close()
        await app.state.redis.aclose()
        await app.state.db_engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="OpsVerse API",
        version="0.1.0",
        description="LLM engineering platform for the DevOps/MLOps/LLMOps community.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(ingest.router, prefix="/v1")
    app.include_router(search.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")
    app.include_router(costs.router, prefix="/v1")
    app.include_router(evals.router, prefix="/v1")
    return app


app = create_app()
