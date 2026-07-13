# ADR-0004: Chat serving — thin LiteLLM SDK client, SSE events, pre-first-token fallback

Date: 2026-07-12 · Status: accepted

## Context

Phase 3 needs `/v1/chat`: retrieval-grounded, citation-bearing answers streamed
to clients, on free-tier LLM APIs (Gemini primary; Groq later as fallback). The
approved plan defers the full LiteLLM **proxy** (routing, budgets, caching) to
Phase 6. Decisions needed now: how to call providers, the wire protocol for
streaming, and what happens when a provider fails.

## Decision

1. **LiteLLM SDK directly (`litellm.acompletion`), not the proxy.**
   `opsverse_core.llm.LiteLLMClient` is a ~150-line wrapper that is already
   OpenAI-shaped, so the Phase 6 proxy swap is a config change (point at the
   proxy's base URL) rather than a rewrite. Running the proxy now would add a
   service to the compose stack with none of its value used yet.
   API keys are passed explicitly from `Settings` (pydantic-settings reads
   `.env` without exporting to `os.environ`, so relying on litellm's implicit
   env lookup would silently break under uvicorn).

2. **SSE with typed events, not a bare token stream.** `POST /v1/chat` emits
   `sources` (all retrieved chunks, numbered — sent *before* generation so the
   UI can render citations as `[n]` markers arrive), then `delta` events, then
   exactly one `done` (model, cited indices, tokens, cost, latency) or `error`.
   SSE over WebSocket for the base path: it works through proxies/curl, and
   the client→server direction isn't needed until image upload (which gets a
   WebSocket variant later, per plan).

3. **Provider fallback only before the first token.** The fallback chain
   (`chat_model` + `chat_fallback_models`) advances only while nothing has
   been streamed. After first delta, a provider failure surfaces as an `error`
   event: silently switching mid-answer would splice two models' outputs and
   corrupt citations.

4. **Degradation over failure for retrieval** (skip rerank → skip retrieval →
   error), with every step recorded on the events and in `request_ledger` —
   see `docs/latency-budget.md`.

5. **`request_ledger` starts now** (migration 0002), not in Phase 6: tokens,
   cost (litellm price table; free-tier rows still record what it *would*
   cost), latency, first-token latency, degradation markers. Phase 4's
   production metrics and Phase 6's cost panel read from it; starting it with
   the first LLM-touching endpoint means the cost story has data from day one.

6. **Model: `gemini/gemini-3.5-flash`, `reasoning_effort=minimal`.** The
   planned gemini-2.5-flash now 404s for new API keys ("no longer available
   to new users"), and gemini-2.0-flash has free-tier quota 0. 3.5-flash
   thinks by default (measured: 89 reasoning tokens for a one-word reply);
   `minimal` drops that to zero, which is the right default for grounded RAG
   synthesis where latency matters more than multi-step reasoning. Both are
   settings (`chat_model`, `chat_reasoning_effort`), and we pin a concrete
   model rather than the floating `gemini-flash-latest` alias so eval numbers
   stay attributable to a model version.
   **Quota reality (measured 2026-07-12):** the free tier caps 3.5-flash at
   **20 requests/day** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`).
   Consequences: `chat_fallback_models` defaults to `gemini-3.1-flash-lite`
   (separate, much larger quota) so interactive chat degrades from "best
   model" to "lite model" instead of erroring; bulk offline jobs (eval-set
   generation, judging) default to the lite model via `eval_generator_model`
   and must never point at the 20/day quality model.

## Consequences

- Phase 6 keeps `LiteLLMClient`'s interface and re-points it at the proxy;
  routing/caching/budget logic stays out of the API service.
- Non-streaming mode (`stream: false`) returns the same pipeline as one JSON
  document — the eval harnesses (retrieval eval, RAGAS) consume this instead
  of parsing SSE.
- Known limitation: gemini free tier is ~10–15 RPM; there is no rate limiting
  or caching until Phase 6, so bulk eval runs must batch and back off
  themselves (the Phase 4 harness does).
