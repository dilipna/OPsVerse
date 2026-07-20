"""Consumer-group semantics for the Redis-Streams ingestion path.

FakeStreamRedis models a Redis stream + one consumer group faithfully enough to
exercise delivery, ack, reclaim (XAUTOCLAIM), and dead-lettering — the same
approach as test_gateway's FakeRedis, so the tests need no live Redis.
"""

import base64

from opsverse_core.streaming import (
    DEFAULT_DLQ,
    DEFAULT_GROUP,
    DEFAULT_STREAM,
    StreamConsumer,
    StreamEvent,
    StreamProducer,
)


class FakeStreamRedis:
    def __init__(self) -> None:
        # stream name -> list[(id, fields)]
        self.streams: dict[str, list[tuple[str, dict]]] = {}
        # group name -> {"last": id, "pel": {id: {"consumer","count","deliver_ms"}}}
        self.groups: dict[str, dict] = {}
        self._seq = 0
        self.now_ms = 10_000  # controllable clock for idle-time tests

    def _next_id(self) -> str:
        self._seq += 1
        return f"{self._seq}-0"

    @staticmethod
    def _seqnum(entry_id: str) -> int:
        return int(entry_id.split("-")[0])

    async def xadd(self, name, fields, *, maxlen=None, approximate=True):
        entry_id = self._next_id()
        self.streams.setdefault(name, []).append((entry_id, dict(fields)))
        if maxlen is not None and len(self.streams[name]) > maxlen:
            self.streams[name] = self.streams[name][-maxlen:]
        return entry_id

    async def xgroup_create(self, name, groupname, id="0", mkstream=False):
        self.streams.setdefault(name, [])
        if groupname in self.groups:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        self.groups[groupname] = {"last": id if id != "$" else self._last_id(name), "pel": {}}

    def _last_id(self, name) -> str:
        entries = self.streams.get(name, [])
        return entries[-1][0] if entries else "0"

    async def xreadgroup(self, groupname, consumername, streams, count=None, block=None):
        name = next(iter(streams))
        group = self.groups[groupname]
        last_seq = self._seqnum(group["last"]) if group["last"] != "0" else 0
        out = []
        for entry_id, fields in self.streams.get(name, []):
            if self._seqnum(entry_id) > last_seq:
                out.append((entry_id, fields))
                group["pel"][entry_id] = {
                    "consumer": consumername,
                    "count": 1,
                    "deliver_ms": self.now_ms,
                }
                group["last"] = entry_id
                if count and len(out) >= count:
                    break
        return [[name, out]] if out else None

    async def xack(self, name, groupname, *ids):
        pel = self.groups[groupname]["pel"]
        return sum(pel.pop(i, None) is not None for i in ids)

    async def xautoclaim(
        self, name, groupname, consumername, min_idle_time, start_id="0-0", count=None
    ):
        pel = self.groups[groupname]["pel"]
        claimed = []
        for entry_id in sorted(pel, key=self._seqnum):
            if self.now_ms - pel[entry_id]["deliver_ms"] >= min_idle_time:
                pel[entry_id]["consumer"] = consumername
                pel[entry_id]["count"] += 1
                pel[entry_id]["deliver_ms"] = self.now_ms
                fields = next(f for i, f in self.streams[name] if i == entry_id)
                claimed.append((entry_id, fields))
                if count and len(claimed) >= count:
                    break
        return ("0-0", claimed, [])

    async def xpending_range(self, name, groupname, min, max, count):
        pel = self.groups[groupname]["pel"]
        lo, hi = self._seqnum(min), self._seqnum(max)
        return [
            {
                "message_id": entry_id,
                "consumer": info["consumer"],
                "time_since_delivered": self.now_ms - info["deliver_ms"],
                "times_delivered": info["count"],
            }
            for entry_id, info in sorted(pel.items(), key=lambda kv: self._seqnum(kv[0]))
            if lo <= self._seqnum(entry_id) <= hi
        ][:count]

    # --- test conveniences -------------------------------------------------
    def dlq(self) -> list[dict]:
        import json

        return [json.loads(f["json"]) for _id, f in self.streams.get(DEFAULT_DLQ, [])]

    def pending_count(self, group=DEFAULT_GROUP) -> int:
        return len(self.groups[group]["pel"])


def _inline_event(
    text: str = "# Title\n\nSome ops content about docker.", name: str = "doc.md"
) -> StreamEvent:
    return StreamEvent(
        source_type="inline",
        filename=name,
        content_b64=base64.b64encode(text.encode()).decode(),
        origin="test",
    )


def test_event_round_trips_through_fields():
    event = _inline_event()
    restored = StreamEvent.from_fields(event.to_fields())
    assert restored.source_type == "inline"
    assert restored.filename == "doc.md"
    assert restored.content_b64 == event.content_b64


async def test_publish_then_consume_acks_and_processes():
    redis = FakeStreamRedis()
    seen = []

    async def handler(event: StreamEvent, entry_id: str) -> None:
        seen.append((event.filename, entry_id))

    consumer = StreamConsumer(redis, handler)
    await consumer.ensure_group()
    await StreamProducer(redis).publish(_inline_event(name="a.md"))

    handled = await consumer.run_once()
    assert handled == 1
    assert seen and seen[0][0] == "a.md"
    assert consumer.stats.processed == 1
    assert redis.pending_count() == 0  # acked, nothing left pending


async def test_ensure_group_is_idempotent():
    async def noop(event: StreamEvent, entry_id: str) -> None:
        return None

    redis = FakeStreamRedis()
    consumer = StreamConsumer(redis, noop)
    await consumer.ensure_group()
    await consumer.ensure_group()  # BUSYGROUP swallowed, no raise
    assert DEFAULT_GROUP in redis.groups


async def test_malformed_entry_is_dead_lettered_immediately():
    redis = FakeStreamRedis()

    async def handler(event, entry_id):  # should never be called
        raise AssertionError("handler ran on malformed entry")

    consumer = StreamConsumer(redis, handler)
    await consumer.ensure_group()
    await redis.xadd(DEFAULT_STREAM, {"json": "{not valid json"})

    await consumer.run_once()
    assert consumer.stats.malformed == 1
    assert redis.pending_count() == 0  # acked
    assert redis.dlq() and "malformed" in redis.dlq()[0]["reason"]


async def test_transient_failure_is_retried_then_dead_lettered():
    redis = FakeStreamRedis()
    calls = {"n": 0}

    async def flaky(event, entry_id):
        calls["n"] += 1
        raise RuntimeError("boom")

    consumer = StreamConsumer(redis, flaky, max_deliveries=2, claim_min_idle_ms=1_000)
    await consumer.ensure_group()
    await StreamProducer(redis).publish(_inline_event())

    # Delivery 1: fails, left pending (not yet at max).
    await consumer.run_once()
    assert consumer.stats.failed == 1
    assert redis.pending_count() == 1
    assert not redis.dlq()

    # Advance past the idle threshold so XAUTOCLAIM reclaims it.
    redis.now_ms += 5_000
    await consumer.run_once()  # reclaim -> delivery 2 -> hits max -> DLQ
    assert calls["n"] == 2
    assert consumer.stats.reclaimed == 1
    assert consumer.stats.dead_lettered == 1
    assert redis.pending_count() == 0
    assert redis.dlq() and "RuntimeError" in redis.dlq()[0]["reason"]


async def test_reclaim_then_success_acks_without_dlq():
    redis = FakeStreamRedis()
    calls = {"n": 0}

    async def recover_on_retry(event, entry_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        # second delivery succeeds

    consumer = StreamConsumer(redis, recover_on_retry, max_deliveries=5, claim_min_idle_ms=1_000)
    await consumer.ensure_group()
    await StreamProducer(redis).publish(_inline_event())

    await consumer.run_once()  # fails, pending
    assert redis.pending_count() == 1
    redis.now_ms += 5_000
    await consumer.run_once()  # reclaimed, succeeds, acked

    assert calls["n"] == 2
    assert consumer.stats.processed == 1
    assert consumer.stats.dead_lettered == 0
    assert redis.pending_count() == 0
    assert not redis.dlq()
