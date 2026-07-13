# OpsVerse AI — Session Handoff

> Give this file to Claude at the start of the next session. Everything needed to continue is here.
> Full roadmap: `C:\Users\Dilip\.claude\plans\opsverse-ai-immutable-scroll.md` (approved 11-phase plan).
> Persistent memory also exists at `C:\Users\Dilip\.claude\projects\c--Users-Dilip-OneDrive-Pictures-ftrag\memory\`.

## What this is

Portfolio project #3 (of 3): a production-grade **LLM engineering platform** for the DevOps/MLOps
community. ProtoPro covers agents; FIFA2026MLOps covers MLOps; **OpsVerse covers LLM engineering**:
data pipeline → RAG → evaluation → fine-tuning (OpsLM) → gateway → inference lab → observability →
security → MCP server.

**Repo root = this folder** (`C:\Users\Dilip\OneDrive\Pictures\ftrag`). Git initialized.
**Commit regularly** (user instruction, 2026-07-12: no longer "ask first" — commit at the
end of each completed milestone/phase-slice, with a clear message, without asking).
**GitHub remote target: https://github.com/dilipna/OPsVerse** (user-provided 2026-07-12,
repo not yet wired up here) — ASK before running `git remote add` or any `git push`; local
commits are pre-approved, remote operations are not.

## Hard constraints (user-confirmed, do not revisit)

| Thing | Decision |
|---|---|
| GPU | Free tiers only (Colab T4 / Kaggle) — training happens OFF this machine |
| LLM APIs | Free tiers only (Gemini free tier, Groq) |
| Base model for fine-tuning | Qwen3-4B → "OpsLM" published to HF Hub |
| Timeline | ~20 working weeks from 2026-07-12, 10–15 hrs/wk |
| Deployment | Docker Compose primary; K8s manifests as docs only; HF Spaces live demo |
| Frontend | Minimal Next.js: chat + eval results + cost panel (not built yet) |
| Order | Evaluation platform (Phase 4) comes BEFORE fine-tuning (Phase 5) |

## User working rules (important)

- **Everything stays inside this folder.** User rejected two other locations; do NOT relocate.
- **Ask before**: deleting anything non-generated, starting/stopping apps (incl. Docker Desktop),
  committing, or acting outside this folder. Rebuilding `.venv`/caches is fine.
- Leftover empty dirs from earlier moves the user may delete themselves:
  `C:\Users\Dilip\projects`, `C:\sandbox`.

## Status: Phases 1–2 DONE (verified live), Phase 3 core DONE (verified live)

**30/30 tests pass; ruff + pyright clean** (`uv run pytest -q`, `uv run ruff check .`, `uv run pyright`).

- **Phase 1 (Foundation)**: uv workspace monorepo (Python 3.12 pinned via `.python-version`),
  FastAPI app (`apps/api`), settings lib (`libs/core`), compose stack, CI (`.github/workflows/ci.yml`),
  ADR-0001/0002, `/health/live` + `/health/ready` (per-dependency checks).
- **Phase 2 (Data pipeline)**: `libs/ingestion` — parsers (markdown w/ heading paths, HTML, k8s YAML
  per-resource, Terraform per-block, Dockerfile per-stage; PDF = optional `[pdf]` docling extra),
  structure-aware chunking (prose ~350tok windows w/ overlap; code kept whole), quality gates
  (min-length, printable-ratio, sha256 exact-dedup, 64-bit simhash near-dedup), Postgres models
  (`documents`/`chunks`/`ingest_jobs`) + Alembic migration 0001, MinIO ObjectStore (`libs/core`),
  `/v1/ingest` (url | github_repo | upload) + arq worker (`apps/api/src/opsverse_api/worker.py`).
  **Live-verified**: 156 docs / 421 chunks ingested (incl. `docker/awesome-compose` repo → 142 docs).
- **Phase 3 core (RAG)**: `libs/rag` — fastembed embedder (lazy-loading), QdrantStore (named
  dense+sparse vectors, server-side RRF hybrid, metadata filters), CrossEncoderReranker, Retriever.
  Embed sweep auto-chains after each successful ingest. `/v1/search` endpoint (mode/k/filters/rerank).
  **Live-verified**: all 421 chunks embedded; hybrid + filtered + reranked queries return correct hits.

## Environment gotchas (will bite you if forgotten)

1. **Port 8000 is TAKEN** by the user's FIFA2026MLOps "WC26 Model Serving" app. OpsVerse API runs on
   **8100**. Do not touch the WC26 app.
2. **fastembed 0.8 does NOT support** `BAAI/bge-m3` or `BAAI/bge-reranker-v2-m3`. Current models
   (see ADR-0003, all overridable via `OPSVERSE_*` settings): dense `BAAI/bge-base-en-v1.5` (768d),
   sparse `Qdrant/bm25` (IDF applied server-side by Qdrant), reranker `BAAI/bge-reranker-base`.
   Models are cached locally; no re-download needed.
3. PowerShell mangles inline JSON in `curl.exe -d` — write request bodies to files (`--data "@file"`).
4. Qdrant collection `opsverse_kb` exists with 768d dense + sparse; if `embedding_dim` ever changes,
   the collection must be deleted and chunks re-embedded (`UPDATE chunks SET embedding_status='pending'`).
5. arq quirk: chained embed jobs use unique `_job_id`s because arq keeps result keys ~1h (a reused
   id would silently not enqueue).
6. This folder is OneDrive-synced: if builds get slow/flaky, exclude `.venv`/`node_modules` from sync.

## How to bring everything up

```bash
docker compose -f infra/compose/docker-compose.yml up -d --wait   # ASK USER before starting Docker Desktop if daemon is down
uv sync --all-packages
(cd apps/api && uv run alembic upgrade head)
uv run uvicorn opsverse_api.main:app --port 8100      # API (background)
uv run arq opsverse_api.worker.WorkerSettings          # worker (background)
curl http://localhost:8100/health/ready                # expect 4x ok
```

Smoke test search: `POST http://localhost:8100/v1/search` body
`{"query": "how do I add a healthcheck to a postgres container?", "k": 3, "rerank": true}`.

## Next steps, in order (Phase 3 remainder → Phase 4)

1. **FIRST: initial git commit** — the working tree holds 3 verified phases uncommitted;
   commit it (no need to ask, per the commit-regularly instruction above), then keep
   committing after each subsequent milestone rather than batching everything at the end.
2. **`/v1/chat`**: retrieval → prompt with numbered context → Gemini free tier → SSE-streamed,
   citation-grounded answer. **UNBLOCKED 2026-07-12: `GEMINI_API_KEY` is in `.env`, live-verified
   against `generativelanguage.googleapis.com` (HTTP 200, model list incl. gemini-2.5-flash).**
   Note: the key format is `AQ....` not the classic `AIzaSy...` — confirmed working via a real API
   call, not a formatting assumption, so don't "fix" it. `GROQ_API_KEY` still not provided (optional
   fallback provider, not a blocker). Use a thin LiteLLM client (the full gateway/proxy is Phase 6).
   Latency-budget doc + graceful degradation ladder (skip rerank → skip retrieval → error).
3. **Retrieval eval**: ~100 Q/A pairs w/ labeled relevant chunks over the ingested corpus →
   hit-rate/MRR/nDCG harness → **ablation report** (dense vs sparse vs hybrid vs hybrid+rerank) in
   `docs/reports/`. This justifies ADR-0003's model choice and starts Phase 4's eval story.
4. Seed corpus expansion (K8s/Docker/Terraform/MLflow official docs) + DVC versioning of the corpus.
5. WebSocket variant of chat + image-upload path (Gemini vision), then minimal Next.js UI (`apps/web`).
6. Phase 4 eval platform per the plan file (RAGAS + DeepEval + judge cache + CI eval gate).

## Repo map (quick)

```
apps/api        FastAPI: routers/{health,ingest,search}.py, worker.py, deps.py, db/, alembic/
libs/core       settings.py (all OPSVERSE_* env), object_store.py (MinIO)
libs/ingestion  parsers/, chunking.py, quality.py, pipeline.py
libs/rag        embeddings.py, store.py, rerank.py, retriever.py
infra/compose   docker-compose.yml (postgres/redis/qdrant/minio healthchecked; api profile "app", host port 8100)
docs/adr        0001 monorepo · 0002 qdrant · 0003 fastembed/bge-base swap
```
