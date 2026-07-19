# OpsVerse AI — Session Handoff

> Give this file to Claude at the start of the next session. Everything needed to continue is here.
> Full roadmap: `C:\Users\Dilip\.claude\plans\opsverse-ai-immutable-scroll.md` (approved 11-phase plan).
> Persistent memory also exists at `C:\Users\Dilip\.claude\projects\c--Users-Dilip-OneDrive-Pictures-ftrag\memory\`.

## What this is

Portfolio project #3 (of 3): a production-grade **LLM engineering platform** for DevOps/MLOps.
**Repo root = this folder.** GitHub remote `origin` = `https://github.com/dilipna/OPsVerse.git`,
pushed. Commit at each milestone without asking; quick "pushing now" heads-up before each push.

**The user has an international-conference demo NEXT WEEK** and may get a job from it — treat every
decision with "would a hiring panel see production judgment here." See `docs/demo-runbook.md` for the
live walkthrough script.

## Hard constraints (do not revisit)

Free GPU only (Colab T4, training OFF this machine) · free LLM APIs only (Gemini free tier; no Groq
key) · base model Qwen3-4B → "OpsLM" on HF Hub · Docker Compose primary, K8s as docs · evaluation
before fine-tuning.

## Status after 2026-07-16/17/18 session — MAJOR PROGRESS (all pushed to origin/main)

**90 tests green · ruff + pyright clean · CI + eval-gate green on Actions · 10 ADRs.**
Phases 1–6 + 8–11 substantially DONE and live-verified. Only Phase 7 (inference lab, needs GPU) and
the actual OpsLM training run (Colab, off-machine) remain, plus polish.

**This session added, in order (each committed + pushed, live-verified unless noted):**
- **Phase 4 finish** — paraphrased retrieval-v3 evalset (proved hybrid > sparse; sparse's v2 win was
  vocabulary leakage), ADR-0006 (promptfoo declined). All 3 ablations + RAG-quality in the regression
  gate (13 thresholds).
- **Corpus/dataset** — 593-pair instruction dataset (qa/explain/diagnosis, decontaminated, 1 pair
  dropped live by the guard), DVC-pushed. SFT prep splits 534/59.
- **Phase 9 Security** (`libs/security`, ADR-0007) — injection quarantine + secret redaction wired
  into ingest & chat; red-team classifier TPR 1.0 / specificity 1.0 on adversarial-benign DevOps text.
- **Phase 10 MCP** (`apps/mcp-server`) — 5 tools, **verified live over stdio** (real search + reports).
- **Phase 6 Gateway** (`libs/core/gateway.py`, ADR-0008) — Redis response cache + daily budget
  kill-switch. **Verified live: cache hit 184× faster, $0** (cost panel shows the `(cached)` row).
- **Phase 5 training scaffold** (`training/`, ADR-0009) — `prepare_sft.py` (runs) + resumable Colab
  QLoRA script + honest README. Training run itself NOT done (needs Colab + HF token).
- **Phase 11 Packaging** — flagship README (measured capability table), `docs/architecture.md`,
  `infra/k8s/` documented manifests (probes match real `/health/ready`+`/health/live`; YAML validated).
- **Phase 8 Observability** (`libs/core/tracing.py`, ADR-0010) — Langfuse v2 self-host in the compose
  **`full` profile** (port 3002, headless-init keys). Facade design: NullTracer default, so the core
  stack & all tests run with zero Langfuse. **Verified live**: a `/v1/chat` produced a `chat` trace
  with `retrieval` (chunk ids+scores) and `generation` (model, $0.0038, 1976 tokens, cited [1,2,3,4],
  cache flag) spans, queried back through the Langfuse API.
- **Phase 7 Inference lab** (`benchmarks/`, ADR-0011) — engine-agnostic OpenAI-compatible harness
  (Ollama/vLLM/SGLang), TTFT + throughput across a concurrency sweep; measurement math unit-tested.
  Committed-and-tested scaffolding; the GPU run is pending OpsLM (same honest pattern as Phase 5).
- `docs/demo-runbook.md` — the 8-minute conference walkthrough.
- **94 tests green; 11 ADRs; CI + eval-gate green on every push.** All 11 phases now have committed
  artifacts (Phases 5 training-run and 7 GPU-run are the only pending executions, both off-machine).

## Demo-polish added at end of session (committed)

- `apps/mcp-server/README.md` — Claude Desktop + Cursor config (demo step 7 turnkey). MCP re-verified
  live after the gateway/tracing changes: 5 tools, real search, 5 reports.
- `training/notebooks/opslm_qlora_colab.ipynb` — turnkey Colab training (set HF token, upload SFT,
  run). Valid nbformat.
- `docs/blog/01-eval-first-changed-my-retrieval-twice.md` — the rerank-off + sparse-leakage story;
  every number cross-checked against the committed reports.
- **Web UI verified**: `/`, `/evals`, `/costs` all compile + serve 200; their data endpoints return
  content (5 reports; cost rows incl. the `(cached)` row). A browser *render* screenshot is still nice
  to grab, but the surface is confirmed working.
- Ruff now excludes `*.ipynb` (Colab magics) — CI stayed green.

## NOT verified / honest gaps

- Langfuse **trace screenshot** for the README not captured (traces verified via API; need a browser).
- **OpsLM is not trained** — the pipeline is committed and the SFT data is ready; the Colab run + the
  before/after (base vs OpsLM) eval are the remaining flagship deliverable.
- rag-quality thresholds are n=20 (noisy — fine as a gate, don't quote as proof).
- Langfuse trace attributes are on spans as metadata (verified via API); the *screenshot* for the
  README hasn't been captured yet.

## Environment gotchas (will bite you)

1. **Docker Desktop shuts down between sessions** — ASK before starting it, then
   `Start-Process "shell:AppsFolder\Docker.DockerForWindows.Settings"`, wait for the daemon.
2. **Ports**: API 8100, web 3000, Langfuse 3002 (3001 was taken), 8000 is the user's other app.
3. **Gemini**: `gemini-3.5-flash` = 20 chat calls/DAY; `gemini-3.1-flash-lite` = large quota, used for
   ALL bulk jobs (eval gen, judging, instruction gen). Never point bulk at 3.5-flash.
4. **litellm < 1.92** (MSVC build fails). **langfuse SDK pinned `>=2.50,<3.0`** (pairs with v2 server).
5. **PowerShell**: no heredocs; parens/quotes in `git commit -m` break parsing — **write commit
   messages to a scratchpad file and `git commit -F <file>`**. Set `$env:PYTHONUTF8='1'` for any
   long-running Python that prints LLM output (cp1252 console dies on non-ASCII). PowerShell cwd
   persists between tool calls.
6. `git push` prints its banner to stderr — PowerShell shows it as a red "error" but the
   `old..new main -> main` line means success. Non-fatal.
7. Bash tool blocks `Start-Sleep`-then-read chains; use Monitor with an until-loop, or a background task.

## How to bring everything up

```bash
docker compose -f infra/compose/docker-compose.yml --profile full up -d --wait   # ASK before Docker Desktop
uv sync --all-packages
(cd apps/api && uv run alembic upgrade head)                      # head = 0003
OPSVERSE_LANGFUSE_HOST=http://localhost:3002 uv run uvicorn opsverse_api.main:app --port 8100
uv run arq opsverse_api.worker.WorkerSettings
(cd apps/web && npm run dev)                                      # :3000
curl http://localhost:8100/health/ready                          # 4x ok
```

## Next steps, in priority order (demo is next week)

1. **Eyeball the web UI** (`/`, `/evals`, `/costs`) in a browser — the only unverified demo surface.
   Capture a **Langfuse trace screenshot** for the README (the P8 money shot).
2. **Run OpsLM training on Colab** (the flagship gap): push `data/sft/` to an HF dataset repo, run
   `training/scripts/train_opslm_qlora.py` on a T4, then the before/after eval (base Qwen3-4B vs
   OpsLM-v1) through `opsverse_evals`. Needs an HF token from the user. Everything else is ready.
3. **Phase 7 Inference lab** (Colab GPU): Ollama vs vLLM vs SGLang on OpsLM-GGUF — TTFT/throughput +
   a quality-vs-quant curve via the Phase-4 harness. Reproducible notebooks, raw CSVs.
4. **HF Spaces live demo** (trimmed corpus, rate-limited) — a public URL for the talk.
5. Polish: demo video, 1–2 blog posts (eval-first dev; the sparse→hybrid v2/v3 story is a great one).

## Repo map (quick)

```
apps/api        FastAPI (routers, worker, gateway wiring, tracer wiring), alembic 0001..0003
apps/web        Next.js UI (chat/evals/costs)
apps/mcp-server MCP stdio server (5 tools) — opsverse-mcp
libs/core       settings, llm (LiteLLM client), gateway (cache/budget), tracing (Langfuse facade), object_store
libs/ingestion  parse/chunk/quality (dedup, non_english, security redaction+quarantine)
libs/rag        hybrid retrieval, rerank, citation chat + degradation ladder + trace spans
libs/evals      metrics, ablation, judge(cached), rag_suite, regression gate, CI smoke, contamination, paraphrase
libs/security   injection heuristic + secret redaction + red-team evaluator
libs/training   instruction dataset pipeline (generate/quality/decontaminate)
training/       Colab QLoRA scripts (prepare_sft, train_opslm_qlora) + README
evalsets/       retrieval-v1/v2/v3 (frozen, hashed), ci/, security-redteam-v1, regression-thresholds.json
docs/adr        0001..0010    docs/reports  ablations v1/v2/v3, rag-quality, security   docs/demo-runbook.md
infra/compose   core + `full` profile (Langfuse)   infra/k8s  documented manifests
data/           DVC pointers: corpus.dvc, instructions.dvc (content in MinIO s3://opsverse-dvc)
```
