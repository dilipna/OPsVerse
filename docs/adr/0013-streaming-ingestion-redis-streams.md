# ADR-0013: Streaming ingestion on Redis Streams, not Kafka

**Status:** accepted (2026-07-20)

## Context

Ingestion so far is **job-based**: an API call (`POST /ingest`, `/ingest/upload`)
writes an `IngestJob` row and enqueues one arq task; the worker parses, chunks,
quality-gates, and hands off to the embed sweep. That is the right shape for
operator-driven, one-shot ingests of a knowledge corpus that changes
occasionally.

It does **not** model a *continuous feed*: a webhook that fires on every merged
docs PR, a change-data stream off a wiki, a fan-out of N workers sharing a
firehose of documents. A reviewer asking "does this handle streaming data?"
is really asking whether the design knows the difference between a queue and a
stream — competing consumers, at-least-once delivery with explicit
acknowledgement, and recovery of work abandoned by a crashed consumer.

## Decision

Add a **Redis Streams** intake path alongside the job queue — not replacing it.

- **Producer** (`opsverse_core.streaming.StreamProducer`) `XADD`s a `StreamEvent`
  (inline base64 bytes, or a `url`/`github_repo` reference) onto
  `opsverse:ingest:stream`, length-capped to bound memory.
- **Consumer** (`StreamConsumer`) reads as a **consumer group** (`XREADGROUP`),
  so N replicas share the stream with each entry delivered once. Every entry is
  explicitly `XACK`ed only after the handler succeeds — **at-least-once**
  delivery, so a consumer that dies mid-document loses nothing.
- **Reclaim**: each cycle first `XAUTOCLAIM`s entries left pending by a dead
  consumer past an idle threshold, so stuck work is picked up by a live replica
  rather than stranded.
- **Dead-letter**: an entry that fails `max_deliveries` times (or is malformed
  and can never parse) is moved to `opsverse:ingest:dlq` and acked — one poison
  document can never wedge the group.
- **Reuse, not fork**: the handler (`apps/api/stream_ingest.py`) runs the exact
  same `ingest_bytes` pipeline (parse → chunk → quality → **secret redaction +
  injection quarantine**, ADR-0007) and enqueues the same
  `embed_pending_chunks` sweep as the worker. Streamed docs land in the same
  `documents`/`chunks` tables and write an `IngestJob` audit row, so they show
  up on `/costs` and in retrieval identically. The stream adds an *intake* mode,
  not a second pipeline.

### Why Redis Streams and not Kafka

- **Zero new infrastructure.** Redis is already in the stack (arq queue, gateway
  cache, budget counter). Redis Streams gives consumer groups, PEL, `XAUTOCLAIM`,
  and DLQ semantics — the streaming primitives that matter here — with no new
  container, and stays inside the project's free-tier / minimal-surface rule
  (same reasoning as ADR-0008's "library, not a proxy binary").
- **Kafka/Redpanda would be resume-driven, not requirement-driven.** They win at
  multi-TB retention, partition-level ordering, and a broker ecosystem this
  single-node demo has no use for. Adding a broker to say "Kafka" on the diagram
  is the kind of over-engineering the eval-first work (ADR-0005) exists to
  resist. Revisit trigger: multi-node throughput or cross-service replay needs.

### Mechanics separated from binding (testability)

The stream logic lives in `libs/core` behind a `StreamRedis` Protocol and a
`handler` callback — no DB, no pipeline imports — exactly like `gateway.py`'s
`RedisLike`. Consumer-group behaviour (delivery, ack, `XAUTOCLAIM` reclaim,
retry-then-DLQ, malformed→DLQ) is unit-tested against an in-memory
`FakeStreamRedis`, so the semantics are covered without a live Redis. The
concrete DB/pipeline handler is the only part that needs the stack.

## Consequences

- A live producer can push documents continuously; multiple `stream_ingest`
  consumers scale intake horizontally with no double-processing.
- Delivery is at-least-once, so the handler must tolerate a re-run: it does —
  re-embedding a chunk id is idempotent (upsert), and a duplicate document is
  caught by the existing content dedup / `sha256`.
- Failure is bounded and auditable: transient errors retry via reclaim, terminal
  ones dead-letter with a reason, and nothing blocks the group.
- Not built (deferred, no current need): exactly-once semantics, per-partition
  ordering, a schema registry, and consumer-lag dashboards. Revisit with a
  real high-throughput feed.
- The security posture is unchanged by construction: streamed documents pass
  through the same quarantine/redaction gates, so ADR-0007's "the document is
  the attack surface" guarantee holds on this path too.
