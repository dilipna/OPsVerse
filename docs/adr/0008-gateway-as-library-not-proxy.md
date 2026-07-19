# ADR-0008: LLM gateway as a library layer, not a proxy binary

**Status:** accepted (2026-07-18)

## Context

Phase 6 calls for a LiteLLM **proxy** as the single entry point: routing,
fallback, caching, rate limiting, per-key budgets, cost ledger. Two of those
already exist in the thin `LiteLLMClient` (ADR-0004): **fallback chains** and
**per-call cost accounting written to `request_ledger`**. What was missing:
a response **cache**, and **budget enforcement**.

Running the actual `litellm --proxy` binary was evaluated and rejected:
- It adds a container and a second configuration surface (providers, keys,
  routing) that duplicates `libs/core` settings — the exact drift ADR-0004's
  thin client was created to avoid.
- The machine pins `litellm < 1.92` (1.92+ needs an MSVC/Rust build that
  fails here); the proxy server extra pulls a heavier dependency set that has
  not been validated under that pin.
- Its headline feature over our client — provider routing — is not yet
  needed: there is one live provider (Gemini free tier) with a fallback
  model. OpsLM routing arrives with Phase 5's served model, and is a
  one-line change to the model chain when it does.

## Decision

Implement the missing gateway concerns as a **library layer**,
`opsverse_core.gateway.LLMGateway`, that wraps any `complete`/`stream` client
and is dropped in where the chat service used the raw client:

1. **Exact-match response cache (Redis).** Keyed by
   `sha256(model_chain + messages)`. A hit returns the stored answer with
   `cost_usd = 0` and a `… (cached)` model tag, so the ledger and cost panel
   show cache hits as free — visible, not hidden. Streaming hits replay the
   stored text as a single delta then a zero-cost result, preserving the
   event shape the caller already handles.
2. **Daily budget kill-switch.** A Redis counter per UTC day
   (`gw:spend:<date>`) accumulates real spend; when it reaches
   `OPSVERSE_GATEWAY_DAILY_BUDGET_USD` the next call raises
   `BudgetExceededError` (surfaced as a chat error event, not a crash). The
   default ceiling is $1/day — the point is to prove the control exists on a
   free-tier stack, not to authorize spend.

**Graceful degradation is a hard requirement:** every Redis operation is
wrapped so that a cache miss, a broken counter, or Redis being down entirely
falls back to a direct provider call. The gateway can slow the platform (one
Redis round-trip) but can never take it down.

## Consequences

- Repeated identical questions are instant and free; the cost panel shows a
  `gemini/… (cached)` row at $0 next to the paid rows — a concrete demo of
  the cache working.
- Free-tier quota is protected twice over: judged evals already cache in
  Postgres (CachedJudge), and now the chat path caches in Redis.
- Semantic (embedding-similarity) caching and per-API-key rate limiting are
  deferred: single-user demo has no key tenancy, and exact-match caching
  captures the repeated-query win without a similarity threshold to tune.
  Revisit trigger: multi-tenant deployment (keys) or measured near-duplicate
  query volume (semantic cache).
- When OpsLM is served (Phase 5/7), domain routing (ops → OpsLM, general →
  Gemini) is added to the model chain the gateway already wraps — no
  architectural change.
