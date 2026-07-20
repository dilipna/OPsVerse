# OpsVerse AI — Session Handoff

> Give this file to Claude at the start of the next session. Everything needed to continue is here.
> Full roadmap: `C:\Users\Dilip\.claude\plans\opsverse-ai-immutable-scroll.md` (approved 11-phase plan).
> Persistent memory: `C:\Users\Dilip\.claude\projects\c--Users-Dilip-OneDrive-Pictures-ftrag\memory\`.
> Demo script: `docs/demo-runbook.md` (rehearsal-ready, ~8 min).

## What this is

Portfolio project #3 (of 3): a production-grade **LLM engineering platform** for DevOps/MLOps.
ProtoPro covers agents; FIFA2026MLOps covers MLOps; **OpsVerse covers LLM engineering**.
**Repo root = this folder** (`C:\Users\Dilip\OneDrive\Pictures\ftrag`).
GitHub: `origin` = `https://github.com/dilipna/OPsVerse.git` — everything is pushed, working tree clean.

**CONTEXT THAT MATTERS: the user demos this at an international conference the week of
2026-07-21 and it may lead to a job.** Treat every decision with "would a hiring panel see
production judgment here." Depth > breadth; honest numbers always.

## Hard constraints (user-confirmed, do not revisit)

| Thing | Decision |
|---|---|
| GPU | Free tiers only (Colab T4 / Kaggle) — training/benchmarks happen OFF this machine |
| LLM APIs | Free tiers only (Gemini; Groq key never provided) |
| Base model | Qwen3-4B → "OpsLM" published to HF Hub |
| Deployment | Docker Compose primary; K8s manifests as docs only; HF Spaces live demo later |
| Order | Evaluation platform BEFORE fine-tuning (done — this ordering is a talking point) |

## User working rules

- Everything stays inside this folder. **Ask before**: starting/stopping apps (incl. Docker
  Desktop), deleting non-generated things, acting outside this folder.
- Local commits at each milestone WITHOUT asking; quick "pushing now" heads-up before each `git push`.
- The permission classifier may block destructive-looking DB scripts even on regenerable data —
  use AskUserQuestion when that happens.

## Current status (2026-07-20, all committed + pushed, HEAD = 7876f16)

**110 tests · ruff + pyright clean · 13 ADRs · CI + Eval Gate green on GitHub Actions.**
ALL 11 phases have committed artifacts. Everything below marked ✅ was **verified live** against
the running stack, not just written.

**NEW 2026-07-20 — Streaming ingestion (ADR-0013), verified live.** A Redis-Streams intake path
alongside the arq job queue: `libs/core/streaming.py` (StreamProducer/StreamConsumer behind a
StreamRedis Protocol — consumer group, at-least-once XACK, XAUTOCLAIM reclaim, DLQ) + concrete
DB/pipeline binding in `apps/api/stream_ingest.py` (reuses `ingest_bytes` incl. ADR-0007
quarantine/redaction, and the `embed_pending_chunks` sweep). 6 unit tests vs an in-memory
FakeStreamRedis. **Live proof today:** published a clean K8s doc → 3 chunks ready + embedded;
published a poisoned doc → quarantined, 0 chunks. Run consumer: `uv run python -m
opsverse_api.stream_ingest`; publish a file: `... --publish <path> [--tool k8s]`.

| Phase | State |
|---|---|
| 1–2 Foundation / Ingestion | ✅ 1,241 docs / 7,383 chunks, all embedded (Qdrant = chunk count); **+ streaming intake path (ADR-0013)** |
| 3 Hybrid RAG serving | ✅ SSE/WS chat, citations, degradation ladder, vision input |
| 4 Evaluation platform | ✅ ablations v1/v2/v3, RAG-quality (1.0/0.99/1.0), structured-output eval, regression gate **15 thresholds**, CI eval-gate, contamination policy |
| 5 OpsLM fine-tune | 🟡 pipeline DONE+tested (593-pair dataset, SFT split, Colab notebook, before/after wiring) — **training run itself NOT executed** |
| 6 LLM gateway | ✅ Redis cache (hit = 184× faster, $0) + daily budget kill-switch (ADR-0008) |
| 7 Inference lab | 🟡 harness written, math unit-tested (ADR-0011) — **GPU run NOT executed** |
| 8 Observability | ✅ Langfuse v2 self-host (`full` profile, :3002) + tracing facade; live trace verified via API (ADR-0010) |
| 9 Security | ✅ red-team classifier TPR 1.0 / spec 1.0; **injection quarantine verified end-to-end live** (poisoned upload → 0 chunks); secret redaction at ingest (ADR-0007) |
| 10 MCP server | ✅ 5 tools verified live over stdio; Claude Desktop/Cursor config in `apps/mcp-server/README.md` |
| 11 Packaging | ✅ flagship README, architecture doc, K8s manifests (YAML validated), demo runbook, blog post |

Key eval story (the demo's backbone): v1 hybrid wins → v2 sparse "wins" (corpus 15×) → v3
paraphrase set proves the sparse win was vocabulary leakage; hybrid vindicated. Rerank measured
twice, off by default. All numbers in `docs/reports/`, narrative in
`docs/blog/01-eval-first-changed-my-retrieval-twice.md`.

## LEFTOVER WORK — prioritized for the next session(s)

### 1. OpsLM training run — USER CHOSE THE KAGGLE PATH (planned 2026-07-20)
The user's HF token is verified: **HF user = `dhf1234`**, fine-grained with `repo.write`
(it was pasted into the 2026-07-19 chat — after the run, remind them to revoke/rotate it).
The Colab laptop-free alternative is fully prepped in `training/kaggle/` (kernel-metadata.json,
notebook with `HF_USER = "dhf1234"` already set, README with all driving commands):
1. User does one-time Kaggle setup: phone-verify account, download `kaggle.json`
   (Settings → API → Create New Token), add `HF_TOKEN` secret in the notebook editor.
2. Claude: edit `KAGGLE_USERNAME` in kernel-metadata.json, `kaggle kernels push -p training/kaggle`,
   poll `kaggle kernels status`. First push fails fast until the secret is attached — expected.
3. ~3–4 h on T4; resumable (set `RESUME = True`, push again). Output: `dhf1234/OpsLM-v1`
   (merged 16-bit + GGUF Q4_K_M). Colab notebook remains as fallback.

### 2. Before/after eval (once OpsLM exists; env-vars-only, no code changes)
```bash
# baseline (Gemini path) — already recorded; rerun if wanted:
uv run python -m opsverse_evals.rag_suite --n 20
uv run python -m opsverse_evals.structured_eval --n 12
# OpsLM via Ollama (from the GGUF):
OPSVERSE_CHAT_MODEL=ollama/opslm uv run python -m opsverse_evals.rag_suite --n 20
OPSVERSE_CHAT_MODEL=ollama/opslm uv run python -m opsverse_evals.structured_eval --n 12
# OpsLM via vLLM/SGLang (OpenAI-compatible):
OPSVERSE_CHAT_MODEL=openai/OpsLM-v1 OPSVERSE_CHAT_API_BASE=http://localhost:8000/v1 uv run ...
```
Write the before/after report into `docs/reports/` (same shape as the others so `/evals` renders
it), pin thresholds, commit. The structured-output eval is the "did SFT break tool-calling?" check.
NOTE: rag_suite's chat calls burn the 20/day 3.5-flash quota — budget demo rehearsal around it.

### 3. Phase 7 GPU benchmark run (Colab; after OpsLM exists)
Serve OpsLM with each engine, then per engine:
`python benchmarks/harness.py --base-url <engine>/v1 --model opslm --concurrency 1,4,16 --requests 32 --out benchmarks/results/<engine>.json`
Then write `docs/reports/inference-benchmark-v1.md` from the JSONs (+ quality-vs-quant via the
Phase-4 harness per ADR-0011). Commit raw JSONs.

### 4. Demo-day polish — DONE 2026-07-19 except the human rehearsal
- ✅ Langfuse trace screenshot captured headlessly (Playwright in scratchpad), committed at
  `docs/assets/langfuse-trace.png`, embedded in README. Retrieval 0.90s / generation 15.08s spans.
- ✅ `/`, `/evals`, `/costs` visually inspected via headless screenshots — all render correctly;
  `/evals` shows all **6 reports** incl. structured-output-v1. README test count fixed 85→104.
- ⬜ Rehearse `docs/demo-runbook.md` once end-to-end (user task; mind the 20/day quota).

### 5. Nice-to-have (only if time)
- HF Spaces live demo (trimmed corpus, rate-limited) — public URL for the talk.
- ✅ Second blog post DONE 2026-07-19: `docs/blog/02-the-document-is-the-attack-surface.md`
  (security quarantine story), linked from README. Demo video still open.
- Instruction dataset scale to 900 (`generate_instructions --n 900`): **partial at 749/900** in
  `data/instructions/instructions-v1.partial.jsonl` (background job was stopped by process
  teardown). Resume by re-running the same command — it picks up from the partial. When it hits
  900, finalize: `dvc add data/instructions && dvc push`, commit the .dvc + manifest.

## Honest gaps (do not overclaim in the demo)

- OpsLM does not exist yet — say "the pipeline is committed and gated; the run is a Colab session".
- Phase 7 has no numbers yet — the harness is tested, the comparison is pending.
- rag-quality thresholds are n=20, structured-output n=12 — regression gates, not proof points.

## Environment gotchas (WILL bite you)

1. **Docker Desktop shuts down between sessions.** ASK the user first, then:
   `Start-Process "shell:AppsFolder\Docker.DockerForWindows.Settings"` and poll `docker info`.
2. **Ports**: API **8100** (8000 taken by user's WC26 app), web 3000, Langfuse **3002**.
3. **Gemini quotas**: `gemini-3.5-flash` = **20 req/DAY** (chat only). ALL bulk jobs (eval gen,
   judging, instruction gen, structured eval) use `gemini-3.1-flash-lite` — never point bulk at 3.5.
4. **Pins**: `litellm >=1.60,<1.92` (MSVC build fails ≥1.92); `langfuse >=2.50,<3.0` (pairs with
   the v2 server). fastembed cache env: `FASTEMBED_CACHE_PATH`.
5. **PowerShell**: no heredocs; parens/quotes in `git commit -m` break parsing — **write commit
   messages to a scratchpad file, `git commit -F <file>`**. `$env:PYTHONUTF8='1'` for any Python
   printing LLM output (cp1252 console). cwd persists between tool calls (a stray `cd` once sent a
   pipeline's output to the wrong dir — generators refuse to run without `./evalsets` for this).
6. `git push` prints its banner to stderr — PowerShell shows red "NativeCommandError" but
   `old..new main -> main` = success.
7. Bash tool blocks sleep-then-check chains: use Monitor with an until-loop, or `run_in_background`.
8. Long background jobs (instruction gen etc.) die if the Claude process exits — they are
   resumable by design; on session start check partial files (`*.partial.jsonl`) before assuming loss.
9. `uv run pytest` is safe for the live DB (WS-test leak fixed); pyright scope is bare
   `uv run pyright` (training/ + notebooks excluded on purpose — unsloth/trl aren't installed here).

## How to bring everything up

```bash
docker compose -f infra/compose/docker-compose.yml --profile full up -d --wait   # ASK before Docker Desktop; `full` = +Langfuse
uv sync --all-packages
(cd apps/api && uv run alembic upgrade head)              # no-op, head = 0003
$env:OPSVERSE_LANGFUSE_HOST='http://localhost:3002'; uv run uvicorn opsverse_api.main:app --port 8100   # background
uv run arq opsverse_api.worker.WorkerSettings             # background
(cd apps/web && npm run dev)                              # :3000 (remember: cwd persists — cd back!)
curl http://localhost:8100/health/ready                   # expect 4x ok
uv run python -m opsverse_evals.regression                # expect 15/15 PASS
```

## Repo map (quick)

```
apps/api          FastAPI: routers/{health,ingest,search,chat,costs,evals}, worker, deps (gateway+tracer wiring), alembic 0001..0003
apps/web          Next.js UI: / (chat), /evals, /costs
apps/mcp-server   MCP stdio server, 5 tools (opsverse-mcp) + Claude Desktop/Cursor README
libs/core         settings, llm.py (LiteLLM client, api_base), gateway.py (cache/budget), tracing.py (Langfuse facade), object_store
libs/ingestion    parsers, chunking, quality.py (dedup+non_english+security wiring), pipeline
libs/rag          embeddings, store, rerank, retriever, chat.py (ChatService + trace spans)
libs/evals        metrics, ablation, judge (CachedJudge), rag_suite, regression (gate), ci_retrieval_smoke,
                  contamination (guard), paraphrase_evalset, structured_eval, reporting, build_ci_fixture
libs/security     injection.py, redact.py, evaluate.py (red-team TPR/FPR)
libs/training     schemas, quality, generate_instructions (resumable, decontaminated)
training/         scripts/{prepare_sft,train_opslm_qlora}.py, notebooks/opslm_qlora_colab.ipynb, README
benchmarks/       harness.py (tested) + README + tests/    evalsets/  retrieval-v1/v2/v3, ci/, security-redteam-v1,
                  structured-output-v1, regression-thresholds.json (15, hashed sets in the contamination policy)
docs/adr          0001..0012        docs/reports   6 live reports        docs/blog  eval-first post
docs/demo-runbook.md · docs/architecture.md · docs/eval-contamination-policy.md · docs/latency-budget.md
infra/compose     core + `full` profile (langfuse, langfuse-db)   infra/k8s   documented manifests
data/             corpus.dvc + instructions.dvc (DVC pointers; content in MinIO s3://opsverse-dvc)
                  data/sft/{train,val}.jsonl + manifest ARE committed to git (small; Colab clone gets them)
```

## Session-start checklist for next Claude

1. Read this file. 2. Ask before starting Docker Desktop, bring the stack up, verify
`/health/ready` + `regression` 15/15. 3. The session IS leftover item 1: the Kaggle training run
(see item 1 for exactly what the user must hand over — `kaggle.json` + `HF_TOKEN` secret attached).
While it trains (~3–4 h, poll via `kaggle kernels status`), do the remaining item-5 bits and prep
item 2's before/after eval. 4. Commit per milestone, heads-up before pushes, update this file at
session end.
