"""arq worker: run with `uv run arq opsverse_api.worker.WorkerSettings`."""

import hashlib
import io
import tarfile
import uuid
from functools import lru_cache, partial
from pathlib import PurePosixPath
from typing import Any, ClassVar

import anyio.to_thread
import httpx
from arq.connections import RedisSettings
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from opsverse_api.db.models import Chunk, Document, IngestJob, utcnow
from opsverse_api.db.session import build_sessionmaker
from opsverse_core.object_store import ObjectStore
from opsverse_core.settings import get_settings
from opsverse_ingestion import PipelineResult, ingest_bytes
from opsverse_ingestion.parsers import SUPPORTED_EXTENSIONS, UnsupportedDocumentError
from opsverse_ingestion.parsers.common import DecodingError
from opsverse_rag import ChunkPoint, QdrantStore
from opsverse_rag.embeddings import FastEmbedEmbedder

MAX_REPO_FILES = 300
MAX_REPO_MEMBER_BYTES = 2 * 1024 * 1024
# PDFs are excluded from repo walks: parsing them requires the optional
# docling extra and repo PDFs are rarely worth the cost.
REPO_EXTENSIONS = SUPPORTED_EXTENSIONS - {".pdf"}

EMBED_BATCH = 32


@lru_cache
def _get_embedder() -> FastEmbedEmbedder:
    settings = get_settings()
    return FastEmbedEmbedder(
        settings.embedding_model, settings.sparse_model, settings.embedding_dim
    )


async def _run_pipeline(raw: bytes, source: str, tool: str | None) -> PipelineResult:
    return await anyio.to_thread.run_sync(partial(ingest_bytes, raw, source, tool))


def _apply_result(session: AsyncSession, document: Document, result: PipelineResult) -> None:
    document.doc_type = result.doc_type.value
    document.tool = result.tool
    document.status = "ready"
    for draft in result.chunks:
        session.add(
            Chunk(
                document_id=document.id,
                ord=draft.ord,
                text=draft.text,
                token_count=draft.token_estimate,
                section=draft.section,
                language=draft.language,
            )
        )


def _merge_stats(total: dict[str, Any], result: PipelineResult) -> None:
    total["documents_created"] = total.get("documents_created", 0) + 1
    total["chunks_kept"] = total.get("chunks_kept", 0) + result.stats.chunks_kept
    total["chunks_rejected"] = total.get("chunks_rejected", 0) + result.stats.chunks_rejected
    total["duplicates_removed"] = (
        total.get("duplicates_removed", 0) + result.stats.duplicates_removed
    )


async def _ingest_upload(
    ctx: dict[str, Any], session: AsyncSession, job: IngestJob
) -> dict[str, Any]:
    document = await session.get(Document, uuid.UUID(job.payload["document_id"]))
    if document is None:
        raise ValueError("document not found for upload job")
    store: ObjectStore = ctx["store"]
    raw = await anyio.to_thread.run_sync(store.get_bytes, document.uri)
    try:
        result = await _run_pipeline(raw, job.payload["filename"], job.payload.get("tool"))
    except (UnsupportedDocumentError, DecodingError, ImportError) as exc:
        document.status = "failed"
        document.error = str(exc)[:500]
        raise
    _apply_result(session, document, result)
    stats: dict[str, Any] = {}
    _merge_stats(stats, result)
    stats["reject_reasons"] = result.stats.reject_reasons
    return stats


async def _ingest_url(ctx: dict[str, Any], session: AsyncSession, job: IngestJob) -> dict[str, Any]:
    uri: str = job.payload["uri"]
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(uri)
        response.raise_for_status()
    raw = response.content
    sha = hashlib.sha256(raw).hexdigest()
    name = PurePosixPath(httpx.URL(uri).path).name or "index.html"
    if "." not in name:
        name += ".html"
    key = f"raw/{sha}/{name}"
    store: ObjectStore = ctx["store"]
    await anyio.to_thread.run_sync(store.put_bytes, key, raw)

    document = Document(source_type="url", uri=uri, sha256=sha)
    session.add(document)
    await session.flush()
    result = await _run_pipeline(raw, name, job.payload.get("tool"))
    _apply_result(session, document, result)
    stats: dict[str, Any] = {"object_key": key}
    _merge_stats(stats, result)
    stats["reject_reasons"] = result.stats.reject_reasons
    return stats


def _repo_slug(uri: str) -> tuple[str, str]:
    path = uri.removeprefix("https://github.com/").removeprefix("github.com/").strip("/")
    owner, _, repo = path.partition("/")
    repo = repo.removesuffix(".git")
    if not owner or not repo or "/" in repo:
        raise ValueError(f"expected owner/repo, got: {uri}")
    return owner, repo


async def _ingest_github(
    ctx: dict[str, Any], session: AsyncSession, job: IngestJob
) -> dict[str, Any]:
    owner, repo = _repo_slug(job.payload["uri"])
    tarball_url = f"https://codeload.github.com/{owner}/{repo}/tar.gz/HEAD"
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        response = await client.get(tarball_url)
        response.raise_for_status()

    sha = hashlib.sha256(response.content).hexdigest()
    store: ObjectStore = ctx["store"]
    tar_key = f"raw/github/{owner}-{repo}-{sha[:12]}.tar.gz"
    await anyio.to_thread.run_sync(store.put_bytes, tar_key, response.content)

    stats: dict[str, Any] = {"object_key": tar_key, "files_skipped": 0, "files_failed": 0}
    tool = job.payload.get("tool")
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
        processed = 0
        for member in tar.getmembers():
            if processed >= MAX_REPO_FILES:
                break
            if not member.isfile() or member.size > MAX_REPO_MEMBER_BYTES:
                continue
            relpath = PurePosixPath(*PurePosixPath(member.name).parts[1:])  # drop tar root dir
            name = relpath.name.lower()
            is_dockerfile = name == "dockerfile" or name.startswith("dockerfile.")
            if not is_dockerfile and relpath.suffix.lower() not in REPO_EXTENSIONS:
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            raw = extracted.read()
            try:
                result = await _run_pipeline(raw, str(relpath), tool)
            except (UnsupportedDocumentError, DecodingError):
                stats["files_failed"] += 1
                continue
            if not result.chunks:
                stats["files_skipped"] += 1
                continue
            document = Document(
                source_type="github_repo",
                uri=f"github://{owner}/{repo}/{relpath}",
                sha256=hashlib.sha256(raw).hexdigest(),
            )
            session.add(document)
            await session.flush()
            _apply_result(session, document, result)
            _merge_stats(stats, result)
            processed += 1
    return stats


_DISPATCH = {"upload": _ingest_upload, "url": _ingest_url, "github_repo": _ingest_github}


async def run_ingest_job(ctx: dict[str, Any], job_id: str) -> None:
    async with ctx["sessionmaker"]() as session:
        job = await session.get(IngestJob, uuid.UUID(job_id))
        if job is None:
            return
        job.status = "running"
        await session.commit()
        try:
            job.stats = await _DISPATCH[job.kind](ctx, session, job)
            job.status = "succeeded"
        except Exception as exc:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"[:500]
        job.finished_at = utcnow()
        await session.commit()

    # Chain an embedding sweep after every successful ingest. Concurrent
    # sweeps are safe: re-upserting the same point id is idempotent.
    if job.status == "succeeded" and (redis := ctx.get("redis")) is not None:
        await redis.enqueue_job("embed_pending_chunks", _job_id=f"embed-after-{job_id}")


async def embed_pending_chunks(ctx: dict[str, Any]) -> int:
    """Embed all pending chunks (dense BGE-M3 + sparse BM25) into Qdrant."""
    settings = get_settings()
    embedder = _get_embedder()
    store = QdrantStore(ctx["qdrant"], settings.qdrant_collection, embedder.dense_dim)
    await store.ensure_collection()
    total = 0
    while True:
        async with ctx["sessionmaker"]() as session:
            rows = (
                await session.execute(
                    select(Chunk, Document)
                    .join(Document, Chunk.document_id == Document.id)
                    .where(Chunk.embedding_status == "pending")
                    .limit(EMBED_BATCH)
                )
            ).all()
            if not rows:
                return total
            texts = [chunk.text for chunk, _ in rows]
            dense = await anyio.to_thread.run_sync(embedder.embed_dense, texts)
            sparse = await anyio.to_thread.run_sync(embedder.embed_sparse, texts)
            points = [
                ChunkPoint(
                    id=str(chunk.id),
                    dense=d,
                    sparse=s,
                    payload={
                        "text": chunk.text,
                        "section": chunk.section,
                        "language": chunk.language,
                        "ord": chunk.ord,
                        "document_id": str(document.id),
                        "source": document.uri,
                        "tool": document.tool,
                        "doc_type": document.doc_type,
                    },
                )
                for (chunk, document), d, s in zip(rows, dense, sparse, strict=True)
            ]
            await store.upsert(points)
            for chunk, _ in rows:
                chunk.embedding_status = "embedded"
                chunk.qdrant_point_id = str(chunk.id)
            await session.commit()
            total += len(rows)


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    ctx["engine"] = create_async_engine(settings.database_url)
    ctx["sessionmaker"] = build_sessionmaker(ctx["engine"])
    ctx["store"] = ObjectStore(settings)
    ctx["qdrant"] = AsyncQdrantClient(url=settings.qdrant_url)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["qdrant"].close()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions: ClassVar = [run_ingest_job, embed_pending_chunks]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = 3
    job_timeout = 600
