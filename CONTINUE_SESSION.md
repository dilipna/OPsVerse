# OpsVerse AI — Session Handoff

> Give this file to Claude at the start of the next session. Everything needed to continue is here.
> Full roadmap: `C:\Users\Dilip\.claude\plans\opsverse-ai-immutable-scroll.md` (approved 11-phase plan).
> Persistent memory also exists at `C:\Users\Dilip\.claude\projects\c--Users-Dilip-OneDrive-Pictures-ftrag\memory\`.

## What this is

Portfolio project #3 (of 3): a production-grade **LLM engineering platform** for the DevOps/MLOps
community. ProtoPro covers agents; FIFA2026MLOps covers MLOps; **OpsVerse covers LLM engineering**.

**Repo root = this folder** (`C:\Users\Dilip\OneDrive\Pictures\ftrag`). Local commits pre-approved
(commit at the end of each milestone without asking). **GitHub remote**: `origin` →
`https://github.com/dilipna/OPsVerse.git`; give a quick "pushing now" heads-up before each push.

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
- The permission classifier may block destructive DB scripts even on generated data — use
  AskUserQuestion when that happens (it worked for the localized-corpus purge).

## Status after 2026-07-13/14 session (all committed + pushed to origin/main 2026-07-14)

**70/70 tests; ruff + pyright clean; `next build` clean. Phases 1–3 COMPLETE, Phase 4 ~COMPLETE,
Phase 5 pipeline built + pilot-verified.** Everything below was verified live this session unless
marked otherwise. Commits tell the story — read `git log`.

- **Corpus (v3, clean): 1,241 docs / 7,383 chunks, all embedded (Qdrant points == chunks).**
  Big finding: 279/1,344 docs were *localized* kubernetes/website pages (content/bn, zh-cn, …) —
  invisible to the English-only embedder. Added a `non_english` ingestion quality gate
  (>30% non-ASCII letters), purged them (user-approved), re-ingested English
  `content/en/docs/concepts` (176 docs / 2,470 chunks, 0 failures). Tools: docker 442,
  mlflow 300, terraform 300, kubernetes 198, unknown 1.
- **The embed-sweep timeout fix (f58f0c0) is now verified end-to-end**: watched a 427s job stop at
  the soft deadline, self-re-enqueue (`embed-cont-…`), and the continuation drain to 0. Trustworthy.
- **DVC is real now**: `data/corpus` (v3) and `data/instructions` (41-pair pilot) are dvc-added and
  pushed to MinIO (`dvc status -c` = in sync). Note `.gitignore` no longer blankets `data/` — DVC
  writes `data/.gitignore`; pointer files are committed.
- **Phase 4 (evaluation platform) essentially complete:**
  - **RAG-quality smoke ran live** (run `c7c35138`, 20 retrieval-v1 cases via /v1/chat on
    3.5-flash, flash-lite judge): faithfulness **1.0**, answer_relevance **0.99**, citation_used
    **1.0**. Caveat (recorded in thresholds file): questions are generated from indexed chunks —
    this gates regressions, it does not prove general quality.
  - **Reports live in Postgres**: `eval_runs.summary` holds the renderable report;
    `/v1/evals/reports` merges Postgres over committed `docs/reports/*-summary.json` (Postgres
    wins). Serves 3 reports live: ablation v1+v2, rag-quality-smoke.
  - **Regression gate**: `uv run python -m opsverse_evals.regression` asserts 9 pinned thresholds
    (evalsets/regression-thresholds.json) — all green. Missing report/mode/metric = failure.
  - **CI eval gate (ADR-0005, option b)**: `eval-gate.yml` = regression CLI + live retrieval smoke
    on a committed 200-chunk fixture (`evalsets/ci/`) in a Qdrant service container; secret-free.
    **Verified on GitHub Actions 2026-07-14: both CI and Eval Gate passed on commit 172b82d.**
  - **Contamination policy** (docs/eval-contamination-policy.md) enforced by
    `opsverse_evals.contamination.ContaminationGuard` (normalized-hash + 5-gram shingle Jaccard
    ≥0.6). Frozen sets are hashed in the policy table.
- **Retrieval ablation v2** (evalsets/retrieval-v2.jsonl, frozen, 100 Qs on the clean corpus) —
  the story changed at scale, full analysis in `docs/reports/retrieval-ablation-v2.md`:
  chunk mrr@10: **sparse .759 > hybrid+rerank .745 > hybrid .705 > dense .553**.
  Decisions: chat stays hybrid (generator questions reuse chunk vocabulary → lexical bias;
  paraphrased evalset is the follow-up before switching); rerank flipped to quality-POSITIVE but
  stays default-off (6.9s/query CPU vs 300ms budget; revisit = GPU or distilled reranker).
- **Phase 5 started**: `libs/training` (opsverse-training) — InstructionPair/DatasetManifest
  schemas, quality filters (scaffold-leak regex, length bounds), Deduper, and
  `generate_instructions` (3 grounded formats qa/explain/diagnosis, resumable, decontaminated,
  manifest with drops_by_reason). **Pilot verified live: 41 pairs**, guard protecting all 200
  frozen questions, 0 contaminated. Spot-checked quality: good.
  Run it from the REPO ROOT (it refuses to run if ./evalsets is missing — that guard exists
  because a wrong-cwd run once produced an unguarded dataset).
- **Test-isolation bug fixed**: the WS chat test used to write fake ledger rows into the LIVE
  Postgres on every pytest run (TestClient runs the lifespan, which rebuilds
  app.state.db_sessionmaker from real settings). Now a RecordingLedger + assertions; 15 polluted
  rows deleted. If /v1/costs ever shows gemini-2.5-flash again, that's the regression signature.

## NOT yet verified / honest gaps

- **eval-gate.yml has never run on GitHub Actions** (written + locally verified only: both its
  commands pass locally). Check the Actions tab after pushing.
- **/evals web page renders the 2 new reports**: API endpoint verified live + `next build` clean +
  the page's generic fallback table is unit-typed, but nobody has *looked* at the page in a
  browser this session (chat UI itself was live-verified in a prior session).
- rag-quality thresholds are pinned at n=20 — noisy; fine as a gate, don't quote as "proof".

## Environment gotchas (will bite you)

1. **Port 8000 TAKEN** (user's WC26 app). OpsVerse API = **8100**; web dev = 3000.
2. **Gemini free-tier quotas**: `gemini-3.5-flash` = **20 requests/DAY** (the smoke run consumes
   ~20 — budget it). `gemini-3.1-flash-lite` = separate much larger quota; it is the fallback AND
   all bulk jobs (`eval_generator_model`). Never point bulk jobs at 3.5-flash.
3. Gemini 3.5-flash thinks by default — `chat_reasoning_effort=minimal` disables. litellm warns
   temperature is deprecated for Gemini 3+.
4. **litellm must stay <1.92** (1.92+ needs a Rust/MSVC build that fails on this machine).
5. fastembed 0.8: bge-base-en-v1.5 dense 768d, Qdrant/bm25 sparse, bge-reranker-base (ADR-0003).
   Qdrant collection `opsverse_kb`. fastembed cache env: `FASTEMBED_CACHE_PATH`.
6. PowerShell mangles inline JSON in curl -d AND non-ASCII in `-replace` — write request bodies to
   files; use the Edit tool for file changes. **PowerShell cwd persists between tool calls** — a
   stray `cd apps/web` once sent a whole pipeline run to the wrong directory.
7. **Windows console is cp1252** — long-running Python that prints LLM output needs
   `$env:PYTHONUTF8='1'` or it dies on the first non-Latin character (happened once).
8. arq: chained embed jobs need unique `_job_id`s. Docker Desktop launches via
   `Start-Process "shell:AppsFolder\Docker.DockerForWindows.Settings"` (exe not at standard path).
9. `uv run pytest` is safe for the live DB now (see test-isolation fix), but stay suspicious of
   any test that touches `app.state` after a lifespan runs.

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

## Next steps, in order

1. **Verify CI on GitHub**: after push, confirm `ci.yml` AND the new `eval-gate.yml` both pass on
   Actions (eval-gate needs ~3-4 min; fastembed model download is cached on uv.lock).
2. **Phase 5 main run — scale the instruction dataset**: the pipeline is verified; now generate
   in flash-lite-quota-sized batches over several sessions toward ~8–15k pairs
   (`uv run python -m opsverse_training.generate_instructions --n 300` per sitting; resumable;
   re-dvc-push `data/instructions` after each batch). Watch `drops_by_reason` — if
   `skipped_by_generator` climbs, the doc sampling is hitting boilerplate.
   Consider adding the 4th format (tradeoff/X-vs-Y, needs cross-document chunk pairing) once
   volume exists.
3. **Paraphrased retrieval evalset** (retrieval-v3): rephrase v2 questions with the LLM
   (paraphrase-only prompt, keep gold labels) to remove the lexical bias that flatters BM25 —
   this decides whether chat's default stays hybrid. Cheap: 100 flash-lite calls.
4. **Phase 4 leftovers (small)**: promptfoo prompt-variant testing was deferred — decide
   deliberately whether to add it or record "regression gate + judged smoke covers it" in an ADR.
5. **Phase 5 training side**: `training/` Colab notebooks (Unsloth QLoRA on Qwen3-4B), preference
   pairs for DPO, HF Hub model cards — plan §Phase 5 has the full task list. Needs the dataset
   from step 2 first.
6. **Langfuse (Phase 8) can start early** if quota stalls eval/dataset work.

## Repo map (quick)

```
apps/api        FastAPI: routers/{health,ingest,search,chat,costs,evals}.py, worker.py,
                export_corpus.py, deps.py, db/, alembic/ (0001..0003)
apps/web        Next 16 UI: src/app/{page,evals/page,costs/page}.tsx, src/lib/api.ts (SSE client)
libs/core       settings.py (OPSVERSE_*), llm.py (LiteLLM client + fallback), object_store.py
libs/ingestion  parsers/, chunking.py, quality.py (incl. non_english gate), pipeline.py
libs/rag        embeddings.py, store.py, rerank.py, retriever.py, chat.py
libs/evals      metrics.py, schemas.py, generate_retrieval_set.py, run_ablation.py,
                judge.py (CachedJudge), rag_suite.py, contamination.py (guard), reporting.py,
                regression.py (threshold gate), build_ci_fixture.py, ci_retrieval_smoke.py
libs/training   schemas.py (InstructionPair/Manifest), quality.py, generate_instructions.py
evalsets/       retrieval-v1.jsonl + retrieval-v2.jsonl (frozen, hashed in policy),
                regression-thresholds.json, ci/ (fixture: ci-corpus.jsonl + retrieval-ci.jsonl)
data/           DVC pointers only: corpus.dvc, instructions.dvc (content in MinIO s3://opsverse-dvc)
docs/adr        0001 monorepo · 0002 qdrant · 0003 fastembed · 0004 chat serving · 0005 CI eval gate
docs/reports    retrieval-ablation-v1 + v2 (md/json/raw) · rag-quality-smoke-summary.json
docs/eval-contamination-policy.md   frozen-set registry + guard mechanics
.github/workflows  ci.yml · eval-gate.yml
infra/compose   docker-compose.yml (postgres/redis/qdrant/minio; api profile "app", port 8100)
```
