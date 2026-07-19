# ADR-0010: Observability via a Langfuse facade, default-off

**Status:** accepted (2026-07-18) — traces verified live end-to-end

## Context

Phase 8 needs end-to-end request tracing: query → retrieval (chunks + scores)
→ generation (tokens + cost) → the whole story in one trace. The plan picked
**Langfuse** (LLM-native, self-hostable, cost/token aware). Two things had to
be decided: which Langfuse, and how to instrument without coupling the RAG
library to it or making the core stack depend on it.

## Decision

**Self-host Langfuse v2** (single app container + its own Postgres) in the
compose **`full` profile**, and instrument the pipeline through a **thin
in-house facade** (`opsverse_core.tracing`) rather than the Langfuse SDK
directly.

- **Langfuse v2, not v3.** v3 self-host requires ClickHouse + Redis + S3 +
  two app containers — heavy and fragile on this Windows dev box. v2 needs
  only Postgres, boots in under a minute, and its project API keys are
  bootstrapped **headlessly** via `LANGFUSE_INIT_*` env vars, so there is no
  manual UI click to get keys. That reproducibility matters more here than
  v3's scale features.
- **Facade, not direct SDK calls.** `Tracer`/`Trace`/`Span` are small
  protocols; `NullTracer` is the default and every method is a no-op. libs/rag
  depends on the facade, never on `langfuse`. Consequences:
  - The **core stack and every test run with zero Langfuse** — tracing is
    active only when `OPSVERSE_LANGFUSE_HOST` is set (the `full` profile).
  - **Tracing can never break a request:** every SDK call is wrapped in
    `suppress(Exception)`; a broken/absent Langfuse degrades to no-op.
  - Swapping backends later (OTel/Phoenix/Langfuse Cloud) is one class, not a
    pipeline change.
- **Custom spans over the LiteLLM callback.** The generation span is emitted
  by our pipeline (not litellm's Langfuse callback) so it carries *our*
  attributes — cited indices, cache-hit flag, degradation, first-token
  latency — alongside model/tokens/cost. The retrieval span carries chunk
  ids + scores. That is the debuggable story; the raw provider call is not.

## Verified

A live `/v1/chat` call produced a `chat` trace with a `retrieval` span
(n_chunks, degraded state) and a `generation` span (model
`gemini-3.5-flash`, cost $0.0038, 1976 prompt tokens, cited [1,2,3,4],
`cached: false`, first-token latency) — queried back through the Langfuse
public API.

## Consequences

- One screenshot in the README tells the whole request story (the plan's P8
  deliverable).
- Online quality sampling and OTel FastAPI auto-instrumentation are deferred;
  the facade is where they'd attach. Revisit when there is production traffic
  to sample.
- The gateway cache is visible in the trace (`cached` flag on the generation
  span) — observability and the Phase-6 cache reinforce each other.
