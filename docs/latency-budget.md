# Chat Latency Budget & Degradation Ladder

Applies to `POST /v1/chat` (SSE). Budgets are targets on the dev stack
(CPU-only embeddings/reranker, Gemini free tier); measured numbers live in the
`request_ledger` table (`latency_ms`, `first_token_ms`) and, later, Langfuse
(Phase 8).

## Budget vs. measured (2026-07-12, dev stack, warm process)

| Stage | Target | Measured | Enforced by |
|---|---|---|---|
| Retrieval total: embed + hybrid search, no rerank (default since ablation v1) | ≤ 300 ms warm | ~60 ms | `chat_retrieval_timeout_s` (10 s hard cap) |
| Retrieval with rerank (opt-in, `OPSVERSE_CHAT_RERANK`) | — | ~2.7 s @ k=6, ~9 s @ k=10 (CPU cross-encoder; measured quality-negative — see retrieval-ablation-v1) | same |
| LLM first token (Gemini 3.5-flash **free tier**) | provider-bound | 7–19 s, grows with prompt size | `chat_llm_timeout_s` |
| First streamed token, end to end | < 2 s (paid/local serving) | ~18–23 s on free tier | measured (`first_token_ms` in ledger) |
| Full answer | ≤ 45 s hard cap | ~19–24 s | `chat_llm_timeout_s` |

Honest reading: the < 2 s first-token target is **not achievable on the free
tier** — the provider queue alone exceeds it — so it is stated as the target
for paid or local (OpsLM/Ollama, Phase 5–7) serving, and the free-tier numbers
are recorded as measured baselines in `request_ledger`. Our own stack's share
is the ~2.7 s warm retrieval (CPU rerank ~2.5 s of it; GPU or a smaller
reranker are the Phase 7 levers), plus a one-off ~10 s cold start to load
embedding + reranker models on the first request after boot.

## Degradation ladder

Failures degrade quality; they do not 500. Each step down is recorded in the
`degraded` list on the `sources` and `done` SSE events, and in
`request_ledger.status` / `meta.degraded`.

| Step | Condition | Behaviour | `degraded` marker |
|---|---|---|---|
| 1 | happy path | hybrid retrieval + rerank → grounded, cited answer | — |
| 2 | rerank fails or retrieval times out | retry hybrid retrieval without rerank | `rerank_skipped` |
| 3 | retrieval fails entirely (Qdrant down, embedder broken) | answer from the LLM alone; the system prompt forces a visible "answering from general knowledge" disclaimer and no citations are emitted | `retrieval_skipped` |
| 4 | LLM fails (all models in the fallback chain, or mid-stream) | `error` SSE event; ledger row with `status=error` | — |

Provider fallback (`chat_fallback_models`, e.g. Groq) happens inside step 4's
"all models" clause: the next model is tried only if the current one produced
no tokens yet — once tokens have streamed, switching providers would splice
two answers, so we fail instead (see ADR-0004).
