# OpsVerse AI — Session Handoff

> Give this file to Claude at the start of the next session. Everything needed to continue is here.
> Full roadmap: `C:\Users\Dilip\.claude\plans\opsverse-ai-immutable-scroll.md` (approved 11-phase plan).
> Persistent memory also exists at `C:\Users\Dilip\.claude\projects\c--Users-Dilip-OneDrive-Pictures-ftrag\memory\`.

## What this is

Portfolio project #3 (of 3): a production-grade **LLM engineering platform** for the DevOps/MLOps
community. ProtoPro covers agents; FIFA2026MLOps covers MLOps; **OpsVerse covers LLM engineering**.

**Repo root = this folder** (`C:\Users\Dilip\OneDrive\Pictures\ftrag`). Git initialized, local
commits pre-approved (commit at the end of each milestone without asking).
**GitHub remote is wired up and pushed**: `origin` → `https://github.com/dilipna/OPsVerse.git`
(added + pushed 2026-07-13 on explicit user request). Future pushes still deserve a quick
"pushing now" mention, but the remote itself no longer needs to be (re-)added.

## Hard constraints (user-confirmed, do not revisit)

| Thing | Decision |
|---|---|
| GPU | Free tiers only (Colab T4 / Kaggle) — training happens OFF this machine |
| LLM APIs | Free tiers only (Gemini free tier; Groq key still not provided) |
| Base model for fine-tuning | Qwen3-4B → "OpsLM" published to HF Hub |
| Deployment | Docker Compose primary; K8s manifests as docs only; HF Spaces live demo |
| Order | Evaluation platform (Phase 4) BEFORE fine-tuning (Phase 5) |

## User working rules

- Everything stays inside this folder. Ask before: deleting non-generated things, starting/stopping
  apps (incl. Docker Desktop), remote git operations, acting outside this folder.

## Status after 2026-07-12/13 session (all committed + pushed to origin/main)

**52/52 tests; ruff + pyright clean; `next build` clean.** Phases 1–3 COMPLETE (live-verified).
Phase 4 core scaffold DONE (code merged; the actual smoke run is NOT done — see Next steps #1).
Commits tell the story — read `git log`.

**IMPORTANT — verify live state before trusting anything below marked "live-verified corpus
stats": this session ended with Docker Desktop down** (container state lost — Postgres/Qdrant
contents are still on disk in Docker volumes and will come back once `docker compose up` runs
again, but nothing was queryable at session end to confirm the embed sweep finished). Treat the
document/chunk counts below as "as of the last successful query", not as confirmed-current.

- **Phase 1–2** (foundation, ingestion): as before, plus `/v1/ingest` github_repo now takes
  `path_prefix` to target doc subtrees of big repos.
- **Phase 3 COMPLETE**:
  - `/v1/chat` SSE (events: sources/delta/done/error), citation-grounded, degradation ladder
    (skip rerank → skip retrieval → error), thin LiteLLM client (ADR-0004), request_ledger
    (migration 0002) recording model/tokens/cost/latency per request.
  - `WS /v1/chat/stream`: multi-turn + image upload → Gemini vision description feeds retrieval
    + prompt (live-verified with a terminal-screenshot PNG).
  - Provider fallback chain live-verified: 3.5-flash → 3.1-flash-lite on 429.
  - **Retrieval eval**: `evalsets/retrieval-v1.jsonl` (100 labeled Qs, frozen, corpus-pinned to
    the ORIGINAL 156-doc corpus) + `docs/reports/retrieval-ablation-v1.md`. Hybrid wins
    (MRR@10 .643); **rerank measured quality-NEGATIVE + ~9s/query CPU → chat rerank now
    opt-in via OPSVERSE_CHAT_RERANK (default off)**.
  - **Minimal web UI** (`apps/web`, Next 16 + Tailwind 4 + react-markdown): / chat (streaming,
    citations, image attach, degraded badges, stats), /evals, /costs. Custom SSE client, no
    AI-SDK dep. API has CORS for :3000.
- **Corpus expanded (ingest jobs all reported `succeeded`)**: kubernetes/website (concepts),
  docker/docs (manuals), hashicorp/terraform (website/docs), mlflow/mlflow (docs) → last
  confirmed count **1,344 docs**; chunk count was still climbing (last confirmed: 1,581
  embedded / 4,292 pending, i.e. **5,873 chunks total**, most NOT yet embedded into Qdrant).
  **The embed sweep did not finish this session** — see gotcha #9 and Next steps #1.
- **Phase 4 core (code only, not yet run end-to-end)**: migration 0003 (`judge_cache`,
  `eval_runs`, `eval_results`) applied; `CachedJudge` (Postgres prompt-hash cache);
  `opsverse_evals.rag_suite` (faithfulness = claim-level judging, answer_relevance,
  citation_used) written and unit-tested, but **never actually invoked against a live
  API** — `docs/reports/rag-quality-smoke-summary.json` does NOT exist yet, no `eval_runs`
  row exists. `/v1/evals/reports` + `/v1/costs/summary` APIs are live-verified (return
  correctly, just have no rag-quality data yet — only the retrieval-ablation-v1 report shows).
- **DVC**: `dvc init` done, remote configured (`s3://opsverse-dvc` on MinIO, creds in
  gitignored `.dvc/config.local`: opsverse / opsverse-secret) and committed
  (`.dvc/config`, `.dvc/.gitignore`, `.dvcignore` are in git). **Nothing has been exported or
  pushed to it yet** — `uv run python -m opsverse_api.export_corpus` was never run, `data/`
  does not exist, no `dvc add` / `dvc push` has happened. This is real remaining work, not
  just "re-verify."

## Environment gotchas (will bite you)

1. **Port 8000 TAKEN** (user's WC26 app). OpsVerse API = **8100**; web dev = 3000.
2. **Gemini free-tier quotas (measured 2026-07-12)**: `gemini-3.5-flash` = **20 requests/DAY**
   (`...PerDayPerProjectPerModel-FreeTier`, quotaValue 20). `gemini-2.5-flash` 404s for new keys;
   `gemini-2.0-flash` free quota is 0. `gemini-3.1-flash-lite` has a separate much larger quota —
   it is the default fallback (`chat_fallback_models`) AND the bulk-job model
   (`eval_generator_model`). Never point bulk jobs at 3.5-flash.
3. Gemini 3.5-flash **thinks by default** — `chat_reasoning_effort=minimal` disables (measured
   89→0 reasoning tokens). litellm warns temperature is deprecated for Gemini 3+.
4. **litellm must stay <1.92** (1.92+ needs a Rust/MSVC build that fails on this machine).
5. fastembed 0.8: models per ADR-0003 (bge-base-en-v1.5 dense 768d, Qdrant/bm25 sparse,
   bge-reranker-base). Qdrant collection `opsverse_kb`.
6. PowerShell mangles inline JSON in curl -d AND non-ASCII in `-replace` file rewrites (em-dash
   mojibake) — write request bodies to files; use the Edit tool for file changes.
7. arq: chained embed jobs need unique `_job_id`s. OneDrive: exclude .venv/node_modules if slow.
8. Windows: no `link.exe`/MSVC; `Docker Desktop.exe` not at the standard path but daemon comes up.
9. **`embed_pending_chunks` used to be able to hit arq's 600s `job_timeout` on large sweeps**
   (happened 3x on the expanded corpus — each kill wasted the in-flight batch but did NOT lose
   already-committed progress, since it commits per 32-chunk batch). Fixed in commit
   `f58f0c0` (2026-07-13): the sweep now stops at a 420s soft deadline and self-re-enqueues a
   fresh job (`embed-cont-<uuid>`) until no chunks are pending. **This fix has NOT yet been
   exercised against real data** — restart the worker and watch at least one full drain before
   trusting it.

## How to bring everything up

```bash
docker compose -f infra/compose/docker-compose.yml up -d --wait   # ASK before starting Docker Desktop if daemon down
uv sync --all-packages
(cd apps/api && uv run alembic upgrade head)                      # head = 0003
uv run uvicorn opsverse_api.main:app --port 8100                  # API (background)
uv run arq opsverse_api.worker.WorkerSettings                     # worker (background)
(cd apps/web && npm run dev)                                      # web UI on :3000 (optional)
curl http://localhost:8100/health/ready                           # expect 4x ok
```

## Next steps, in order (start here — this is a clean checklist, not a recap)

0. **Bring the stack up first** (per "How to bring everything up" below). Docker Desktop was
   down at end of session — ask before starting it, then `docker compose up -d --wait`,
   `alembic upgrade head` (should be a no-op, already at 0003), start API + worker.

1. **Finish the embed sweep for the expanded corpus** (never completed this session):
   - Check state: `docker exec opsverse-postgres-1 psql -U opsverse -d opsverse -c
     "SELECT embedding_status, count(*) FROM chunks GROUP BY 1;"`
   - If any `pending` remain, the restarted worker (with the timeout fix from commit
     `f58f0c0`) should already be chaining sweeps automatically once one is enqueued — trigger
     one if none is running: any new `/v1/ingest` call chains a sweep, or enqueue
     `embed_pending_chunks` directly. Watch it actually reach 0 pending — this exact fix has
     never been observed working end-to-end.

2. **Export + version the corpus with DVC** (nothing done yet, this is from scratch):
   ```
   uv run python -m opsverse_api.export_corpus     # writes data/corpus/{documents,chunks}.jsonl + manifest.json
   uv run dvc add data/corpus
   uv run dvc push                                  # needs MinIO up; creds already in .dvc/config.local
   git add data/corpus.dvc .gitignore && git commit -m "Version corpus v2 snapshot with DVC"
   ```

3. **Run the Phase 4 RAG-quality smoke live** (code exists, never executed):
   ```
   uv run python -m opsverse_evals.rag_suite --n 20   # API must be running on :8100
   ```
   Judges on `gemini-3.1-flash-lite` (protects the 20/day quota on 3.5-flash), resumable via
   `--run-id <id>` if it stalls. Confirm `docs/reports/rag-quality-smoke-summary.json` appears
   and `/evals` in the web UI renders it, then commit.

4. **Retrieval ablation v2** on the expanded corpus: generate `evalsets/retrieval-v2.jsonl`
   (the v1 set only covers the original 156-doc corpus; keep v1 frozen for comparability),
   rerun `run_ablation`, compare v1↔v2 in the report; revisit the rerank-off verdict at the
   new scale (bigger/more diverse corpus could change the answer).
5. **Phase 4 completion**: DeepEval-style regression assertions pinned to frozen evalsets;
   promptfoo prompt-variant testing; **CI eval gate** — open decision: needs a DVC remote +
   secrets reachable from GitHub Actions (local MinIO isn't); options: (a) GDrive DVC remote,
   (b) commit a trimmed CI corpus fixture, (c) nightly-only gate on a self-hosted runner.
   Also: eval dashboard page already renders eval_runs summaries via /v1/evals/reports —
   move reports fully into Postgres (`eval_runs.summary` exists; endpoint currently reads
   *-summary.json files).
6. **Contamination policy doc** (evalsets never enter training data, enforced by hash) —
   quick doc, belongs to Phase 4/5 boundary.
7. **Phase 5**: synthetic instruction dataset from the corpus (use flash-lite; 20/day cap makes
   3.5-flash useless for bulk), Unsloth QLoRA on Colab — plan file has the full task list.
8. Langfuse (Phase 8) can be started early if evals stall on quota.

## GitHub remote

`origin` = `https://github.com/dilipna/OPsVerse.git`, wired up and pushed 2026-07-13 on
explicit user request. Local commits remain pre-approved (commit without asking); a `git push`
after that point should still get a quick heads-up before running, per the user's general
"confirm risky/shared-state actions" preference — the blanket "ask before remote git ops" rule
from earlier sessions is superseded only for the one explicit push already done, not as a
standing "always push freely" grant.

## Repo map (quick)

```
apps/api        FastAPI: routers/{health,ingest,search,chat,costs,evals}.py, worker.py,
                export_corpus.py, deps.py, db/, alembic/ (0001..0003)
apps/web        Next 16 UI: src/app/{page,evals/page,costs/page}.tsx, src/lib/api.ts (SSE client)
libs/core       settings.py (OPSVERSE_*), llm.py (LiteLLM client + fallback), object_store.py
libs/ingestion  parsers/, chunking.py, quality.py, pipeline.py
libs/rag        embeddings.py, store.py, rerank.py, retriever.py, chat.py (ChatService + events)
libs/evals      metrics.py (hit/MRR/nDCG), schemas.py, generate_retrieval_set.py,
                run_ablation.py, judge.py (CachedJudge), rag_suite.py
evalsets/       retrieval-v1.jsonl (frozen, 100 cases, original corpus)
docs/adr        0001 monorepo · 0002 qdrant · 0003 fastembed swap · 0004 chat serving/LiteLLM/SSE
docs/reports    retrieval-ablation-v1.{md,json} · rag-quality-smoke-summary.json (after step 1)
docs/latency-budget.md   budget vs measured + degradation ladder
infra/compose   docker-compose.yml (postgres/redis/qdrant/minio; api profile "app", port 8100)
```
