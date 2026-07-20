"""Redis-Streams ingestion consumer, bound to the DB + ingestion pipeline.

Run the consumer:  uv run python -m opsverse_api.stream_ingest
Publish a test event:  uv run python -m opsverse_api.stream_ingest --publish path/to/doc.md

This is the streaming twin of the arq `run_ingest_job` worker: instead of a
one-shot job per API call, a long-lived consumer turns each stream event into
persisted, embeddable chunks and enqueues the same `embed_pending_chunks`
sweep. The stream mechanics (consumer group, ack, reclaim, DLQ) live in
`opsverse_core.streaming`; this module is the concrete handler.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hashlib
import signal
import sys
from functools import partial
from pathlib import PurePosixPath
from typing import Any, cast

import anyio.to_thread
import httpx
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from opsverse_api.db.models import Chunk, Document, IngestJob, utcnow
from opsverse_api.db.session import build_sessionmaker
from opsverse_core.settings import get_settings
from opsverse_core.streaming import StreamConsumer, StreamEvent, StreamProducer, StreamRedis
from opsverse_ingestion import PipelineResult, ingest_bytes
from opsverse_ingestion.parsers import UnsupportedDocumentError
from opsverse_ingestion.parsers.common import DecodingError

MAX_STREAM_DOC_BYTES = 10 * 1024 * 1024


class DbStreamHandler:
    """Turns one StreamEvent into a persisted Document + Chunks and queues embed.

    Mirrors the worker's `_apply_result`: quarantined docs keep their metadata
    for audit but contribute zero chunks. An `IngestJob` row is written per
    event so streamed ingests show up in the same audit surface as queued ones.
    """

    def __init__(
        self, sessionmaker: async_sessionmaker[Any], arq_pool: ArqRedis | None = None
    ) -> None:
        self._sessionmaker = sessionmaker
        self._arq_pool = arq_pool

    async def _fetch_bytes(self, event: StreamEvent) -> bytes:
        if event.source_type == "inline":
            if not event.content_b64:
                raise ValueError("inline event has no content_b64")
            return base64.b64decode(event.content_b64)
        if event.source_type == "url":
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(event.uri)
                response.raise_for_status()
            return response.content
        raise ValueError(f"unsupported stream source_type: {event.source_type}")

    async def __call__(self, event: StreamEvent, entry_id: str) -> None:
        raw = await self._fetch_bytes(event)
        if len(raw) > MAX_STREAM_DOC_BYTES:
            raise ValueError(f"document exceeds {MAX_STREAM_DOC_BYTES}B stream limit")
        filename = event.filename or PurePosixPath(event.uri).name or "event.txt"
        try:
            result: PipelineResult = await anyio.to_thread.run_sync(
                partial(ingest_bytes, raw, filename, event.tool)
            )
        except (UnsupportedDocumentError, DecodingError, ImportError):
            # Non-retryable: the bytes will never parse. Raise so the consumer
            # counts a failure; repeated delivery dead-letters it.
            raise

        sha = hashlib.sha256(raw).hexdigest()
        async with self._sessionmaker() as session:
            document = Document(
                source_type=f"stream:{event.source_type}"[:32],
                uri=event.uri or f"stream://{filename}",
                sha256=sha,
                doc_type=result.doc_type.value,
                tool=result.tool,
                status="quarantined" if result.stats.quarantined else "ready",
            )
            session.add(document)
            await session.flush()
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
            session.add(
                IngestJob(
                    kind="stream",
                    status="succeeded",
                    payload={
                        "entry_id": entry_id,
                        "source_type": event.source_type,
                        "origin": event.origin,
                        "filename": filename,
                        "document_id": str(document.id),
                    },
                    stats={
                        "chunks_kept": result.stats.chunks_kept,
                        "quarantined": result.stats.quarantined,
                        "secrets_redacted": result.stats.secrets_redacted,
                    },
                    finished_at=utcnow(),
                )
            )
            await session.commit()

        # Reuse the worker's embed sweep. Unique job id per entry so arq's ~1h
        # result cache doesn't silently drop a re-enqueue.
        if self._arq_pool is not None:
            await self._arq_pool.enqueue_job(
                "embed_pending_chunks", _job_id=f"embed-stream-{entry_id}"
            )


async def run_stream_consumer() -> None:
    settings = get_settings()
    redis: Redis = Redis.from_url(settings.redis_url)
    engine = None
    arq_pool: ArqRedis | None = None
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(settings.database_url)
        sessionmaker = build_sessionmaker(engine)
        arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        handler = DbStreamHandler(sessionmaker, arq_pool)
        consumer = StreamConsumer(cast("StreamRedis", redis), handler)

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        # SIGINT/SIGTERM: finish the in-flight cycle, then exit cleanly.
        # Windows has no add_signal_handler, hence the suppress.
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)
        print(f"stream consumer up: group={consumer._group} stream={consumer._stream}")
        await consumer.run_forever(should_stop=stop.is_set)
        print(f"stream consumer stopped: {consumer.stats}")
    finally:
        await redis.aclose()
        if arq_pool is not None:
            await arq_pool.aclose()
        if engine is not None:
            await engine.dispose()


async def publish_file(path: str, tool: str | None = None) -> None:
    """Dev helper: push a local file onto the stream as an inline event."""
    settings = get_settings()
    redis: Redis = Redis.from_url(settings.redis_url)
    try:
        raw = open(path, "rb").read()  # noqa: SIM115 - one-shot CLI helper
        event = StreamEvent(
            source_type="inline",
            filename=PurePosixPath(path).name,
            tool=tool,
            content_b64=base64.b64encode(raw).decode(),
            origin="cli",
        )
        entry_id = await StreamProducer(cast("StreamRedis", redis)).publish(event)
        print(f"published {path} as entry {entry_id}")
    finally:
        await redis.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="OpsVerse Redis-Streams ingestion")
    parser.add_argument("--publish", metavar="FILE", help="publish a file then exit")
    parser.add_argument("--tool", default=None, help="tool hint for --publish")
    args = parser.parse_args()
    if args.publish:
        asyncio.run(publish_file(args.publish, args.tool))
    else:
        try:
            asyncio.run(run_stream_consumer())
        except KeyboardInterrupt:
            sys.exit(0)


if __name__ == "__main__":
    main()
