# OpsVerse AI — Architecture

OpsVerse is a monorepo LLM platform: a FastAPI service over Postgres / Redis /
Qdrant / MinIO, a Next.js UI, and an MCP server, with an offline training track
(Colab) for the OpsLM model. This document is the map; the [ADRs](adr/) hold
the *why* for each decision.

## Request lifecycle (a chat query)

```
client ─POST /v1/chat─► API
   │  1. security: scan_injection(query) → flag in request_ledger (not blocked)
   │  2. retrieval: embed query (BGE dense + BM25 sparse) → Qdrant RRF fusion → top-k
   │       degradation ladder: hybrid+rerank → hybrid → no-retrieval → error
   │  3. prompt: numbered context blocks + grounded system prompt
   │  4. gateway: exact-match Redis cache? → hit: replay (free) │ miss: budget check
   │  5. generate: LiteLLM client → Gemini (fallback chain on 429) → stream tokens (SSE)
   │  6. citations: extract [n] refs the answer used
   │  7. ledger: model, tokens, cost_usd, latency, degraded[], injection_flags
   └────► SSE events: sources → delta* → done
```

Every stage is observable in the response (`sources`/`done` events carry
`degraded` and citation info) and in Postgres (`request_ledger`), which feeds
the `/v1/costs/summary` panel.

## Components

- **apps/api** — routers per domain (ingest, search, chat, evals, costs,
  health); an arq worker for async ingest + embedding. Lazy clients: the API
  starts even when the stack is down, and `/health/ready` reports the truth.
- **libs/ingestion** — Docling/markup parsers → source-aware chunking (prose
  vs YAML/HCL/Dockerfile boundaries) → quality gates (simhash dedup,
  language, min-length) → **security** (secret redaction + injection
  quarantine). Emits validated chunks; the worker embeds them.
- **libs/rag** — hybrid retrieval (dense + sparse named vectors in one Qdrant
  collection, RRF fusion), optional cross-encoder rerank (measured, default
  off), citation-grounded chat with a 4-rung degradation ladder.
- **libs/evals** — IR metrics (hit/MRR/nDCG), ablation harness, cached LLM
  judge (Postgres, keyed by prompt hash + model), regression gate (pinned
  thresholds), CI retrieval smoke on a committed fixture, contamination guard.
- **libs/security** — injection heuristic (weighted signals, measured as a
  classifier), secret redaction, red-team evaluator.
- **libs/core** — settings, the thin LiteLLM client (fallback + cost), and the
  **LLM gateway** (Redis response cache + daily budget kill-switch).
- **libs/training** + **training/** — synthetic instruction dataset pipeline
  and the Colab QLoRA scripts for OpsLM (Qwen3-4B).
- **apps/mcp-server** — FastMCP stdio server exposing search/chat/evals/costs
  as tools; wraps the running API over HTTP so an MCP session sees exactly
  what the UI sees.

## Data stores

| Store | Holds | Notes |
|---|---|---|
| Postgres | documents, chunks, ingest_jobs, eval_runs/results, judge_cache, request_ledger | JSONB for flexible eval/ledger payloads; Alembic-migrated |
| Qdrant | `opsverse_kb` — named vectors {dense 768d, sparse BM25} + payload | one collection, metadata-partitioned (ADR-0002) |
| Redis | response cache, arq queue, gateway budget counters | all reconstructible/transient |
| MinIO | raw ingested docs (S3-compatible) | swap to real S3 via one env var |

## Cross-cutting

- **Evaluation-first**: the eval harness and CI gate existed before any model
  claim. Deterministic tests for code, statistical gates for model behavior.
- **Free-tier-aware**: batched, cached, resumable everywhere the LLM is used
  (judge cache in Postgres, response cache in Redis, budget kill-switch, and
  a 20/day quota model kept off bulk jobs).
- **Honest degradation**: retrieval, rerank, and vision each fail *soft* and
  say so in `degraded[]`; only a generation failure is a hard error.
- **Versioning**: corpus and instruction datasets are DVC-tracked (MinIO
  remote); eval sets are frozen and hash-registered against training leakage.

## Deployment

- **Runtime**: Docker Compose (`infra/compose`). The API image is opt-in
  behind the `app` profile; datastores always up.
- **Kubernetes**: `infra/k8s` — documented manifests (stateless API + HPA,
  StatefulSet datastores, arq worker, ingress) as a portfolio artifact, not
  the operated runtime. See `infra/k8s/README.md`.
