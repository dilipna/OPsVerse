"""Redis Streams ingestion: a continuous, at-least-once document intake path.

This complements the arq job queue (one-shot, API-submitted ingests) with a
consumer-group *stream* for live document feeds — webhooks, doc-change events,
a CI hook that fires on every merged PR. The semantics that make this genuinely
"streaming" rather than "another queue", all provided by Redis Streams:

  - **consumer groups** — N competing consumers share one stream; each entry is
    delivered to exactly one of them (`XREADGROUP`), so intake scales
    horizontally without double-processing.
  - **explicit acknowledgement** — an entry stays in the group's pending list
    until `XACK`; a consumer that crashes mid-document loses nothing
    (at-least-once delivery).
  - **reclaim of abandoned work** — `XAUTOCLAIM` hands entries left pending by a
    dead consumer (idle past a threshold) to a live one.
  - **dead-lettering** — an entry that fails `max_deliveries` times is moved to
    a DLQ stream and acked, so one poison document can never wedge the group.

The mechanics here are infrastructure only: a `StreamRedis` Protocol (so tests
inject a fake, exactly like `gateway.py`) and a `handler` callback that does the
real work. The DB + pipeline binding lives in `apps/api/stream_ingest.py`.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

DEFAULT_STREAM = "opsverse:ingest:stream"
DEFAULT_GROUP = "ingestors"
DEFAULT_DLQ = "opsverse:ingest:dlq"


class StreamEvent(BaseModel):
    """One document-intake event carried on the stream.

    `inline` events carry the document bytes directly (base64) — the natural
    shape for a push feed. `url` / `github_repo` events carry a reference the
    consumer fetches, reusing the same sources as the job-queue path.
    """

    source_type: str  # inline | url | github_repo
    uri: str = ""  # url or owner/repo; empty for inline
    filename: str = "event.txt"  # names the parser + citation source
    tool: str | None = None  # optional tool hint; else auto-detected
    content_b64: str | None = None  # inline document bytes
    origin: str | None = None  # free-form audit tag (feed name, webhook id)

    def to_fields(self) -> dict[str, str]:
        """Serialize to a single-field stream entry (one JSON blob is simplest
        to round-trip and keeps the entry schema stable as the model grows)."""
        return {"json": self.model_dump_json()}

    @classmethod
    def from_fields(cls, fields: dict[Any, Any]) -> StreamEvent:
        raw = fields.get("json", fields.get(b"json"))
        if isinstance(raw, bytes):
            raw = raw.decode()
        if raw is None:
            raise ValueError("stream entry missing 'json' field")
        return cls.model_validate_json(raw)


class StreamRedis(Protocol):
    """The subset of redis.asyncio stream ops used here (Protocol so tests inject
    a fake, matching the gateway's RedisLike pattern)."""

    async def xadd(
        self,
        name: str,
        fields: dict[str, Any],
        *,
        maxlen: int | None = ...,
        approximate: bool = ...,
    ) -> Any: ...
    async def xgroup_create(
        self, name: str, groupname: str, id: str = ..., mkstream: bool = ...
    ) -> Any: ...
    async def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int | None = ...,
        block: int | None = ...,
    ) -> Any: ...
    async def xack(self, name: str, groupname: str, *ids: str) -> Any: ...
    async def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str = ...,
        count: int | None = ...,
    ) -> Any: ...
    async def xpending_range(
        self, name: str, groupname: str, min: str, max: str, count: int
    ) -> Any: ...


# handler(event, entry_id) -> None; raising signals a processing failure.
Handler = Callable[[StreamEvent, str], Awaitable[None]]


@dataclass
class ConsumerStats:
    processed: int = 0
    failed: int = 0  # transient failures left for redelivery
    dead_lettered: int = 0
    reclaimed: int = 0
    malformed: int = 0


class StreamProducer:
    """Publishes intake events onto the stream. What a live feed calls."""

    def __init__(
        self, redis: StreamRedis, *, stream: str = DEFAULT_STREAM, maxlen: int | None = 100_000
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._maxlen = maxlen

    async def publish(self, event: StreamEvent) -> str:
        entry_id = await self._redis.xadd(
            self._stream, event.to_fields(), maxlen=self._maxlen, approximate=True
        )
        return entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)


class StreamConsumer:
    """Reads the stream as a consumer group, runs the handler, acks or DLQs.

    Degrades honestly: a handler exception leaves the entry pending (redelivered
    later) until it has failed `max_deliveries` times, at which point it is
    dead-lettered and acked. Malformed entries are dead-lettered immediately —
    redelivering them would never succeed.
    """

    def __init__(
        self,
        redis: StreamRedis,
        handler: Handler,
        *,
        stream: str = DEFAULT_STREAM,
        group: str = DEFAULT_GROUP,
        consumer: str = "consumer-1",
        dlq: str = DEFAULT_DLQ,
        max_deliveries: int = 5,
        claim_min_idle_ms: int = 60_000,
        block_ms: int = 5_000,
        batch: int = 10,
    ) -> None:
        self._redis = redis
        self._handler = handler
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._dlq = dlq
        self._max_deliveries = max_deliveries
        self._claim_min_idle_ms = claim_min_idle_ms
        self._block_ms = block_ms
        self._batch = batch
        self.stats = ConsumerStats()

    async def ensure_group(self) -> None:
        """Create the group + stream if absent; idempotent across restarts."""
        try:
            await self._redis.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    def _decode(value: Any) -> str:
        return value.decode() if isinstance(value, bytes) else str(value)

    async def _delivery_count(self, entry_id: str) -> int:
        pending = await self._redis.xpending_range(
            self._stream, self._group, entry_id, entry_id, 1
        )
        if not pending:
            return 1
        item = pending[0]
        # redis-py returns dicts; a bare list/tuple is [id, consumer, idle, times].
        if isinstance(item, dict):
            return int(item["times_delivered"])
        return int(item[3])

    async def _dead_letter(self, entry_id: str, fields: dict[Any, Any], reason: str) -> None:
        payload = {"orig_id": entry_id, "reason": reason[:500]}
        raw = fields.get("json", fields.get(b"json"))
        if raw is not None:
            payload["json"] = self._decode(raw)
        await self._redis.xadd(self._dlq, {"json": json.dumps(payload)})
        await self._redis.xack(self._stream, self._group, entry_id)

    async def _process_one(self, entry_id: str, fields: dict[Any, Any]) -> None:
        try:
            event = StreamEvent.from_fields(fields)
        except Exception as exc:
            self.stats.malformed += 1
            await self._dead_letter(entry_id, fields, f"malformed: {exc}")
            return
        try:
            await self._handler(event, entry_id)
        except Exception as exc:
            if await self._delivery_count(entry_id) >= self._max_deliveries:
                self.stats.dead_lettered += 1
                await self._dead_letter(entry_id, fields, f"{type(exc).__name__}: {exc}")
            else:
                self.stats.failed += 1  # leave unacked -> redelivered via XAUTOCLAIM
            return
        await self._redis.xack(self._stream, self._group, entry_id)
        self.stats.processed += 1

    async def _reclaim(self) -> None:
        """Take over entries abandoned by a crashed consumer."""
        result = await self._redis.xautoclaim(
            self._stream,
            self._group,
            self._consumer,
            self._claim_min_idle_ms,
            start_id="0-0",
            count=self._batch,
        )
        # redis-py returns (next_cursor, claimed_entries[, deleted_ids]).
        claimed = result[1] if isinstance(result, (list, tuple)) and len(result) >= 2 else []
        for entry_id, entry_fields in claimed:
            self.stats.reclaimed += 1
            await self._process_one(self._decode(entry_id), entry_fields)

    async def run_once(self) -> int:
        """One reclaim + read + process cycle. Returns entries handled (testable)."""
        await self._reclaim()
        response = await self._redis.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=self._batch,
            block=self._block_ms,
        )
        if not response:
            return 0
        handled = 0
        for _stream_name, entries in response:
            for entry_id, entry_fields in entries:
                await self._process_one(self._decode(entry_id), entry_fields)
                handled += 1
        return handled

    async def run_forever(self, should_stop: Callable[[], bool] | None = None) -> None:
        await self.ensure_group()
        while should_stop is None or not should_stop():
            await self.run_once()
