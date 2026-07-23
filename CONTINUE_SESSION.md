# OpsVerse AI — Session Handoff

> Give this file to Claude at the start of the next session. Everything needed to continue is here.
> Full roadmap: `C:\Users\Dilip\.claude\plans\opsverse-ai-immutable-scroll.md` (approved 11-phase plan).
> Persistent memory: `C:\Users\Dilip\.claude\projects\c--Users-Dilip-OneDrive-Pictures-ftrag\memory\`.
> Demo script: `docs/demo-runbook.md` (rehearsal-ready, ~8 min).

## What this is

Portfolio project #3 (of 3): a production-grade **LLM engineering platform** for DevOps/MLOps.
ProtoPro covers agents; FIFA2026MLOps covers MLOps; **OpsVerse covers LLM engineering**.
**Repo root = this folder** (`C:\Users\Dilip\OneDrive\Pictures\ftrag`).
GitHub: `origin` = `https://github.com/dilipna/OPsVerse.git` — everything pushed, working tree clean.

**CONTEXT THAT MATTERS: the user demos this at an international conference (week of 2026-07-21)
and it may lead to a job — target roles: AI Engineer / LLM Engineer / LLM Inference Engineer at
top companies.** Treat every decision with "would a hiring panel see production judgment here."
Depth > breadth; honest numbers always; a claim without a measured number is a liability.

## Hard constraints (user-confirmed, do not revisit)

| Thing | Decision |
|---|---|
| GPU | Free tiers only — training happens OFF this machine (Colab T4; Kaggle blocked, see below) |
| LLM APIs | Free tiers only (Gemini; Groq key never provided) |
| Base model | Qwen3-4B → "OpsLM" — **TRAINED + published at `dhf1234/OpsLM-v1`** |
| Deployment | Docker Compose local; K8s manifests as docs; **demo site live on Vercel**; always-on model serving = Oracle Cloud Free Tier (HF Spaces now PRO-only) |
| Order | Evaluation platform BEFORE fine-tuning (done — this ordering is a talking point) |

## User working rules

- Everything stays inside this folder. **Ask before**: starting/stopping apps (incl. Docker
  Desktop), deleting non-generated things, acting outside this folder.
- Local commits at each milestone WITHOUT asking; quick "pushing now" heads-up before each `git push`.
- The user wants simple, numbered, non-technical steps for anything they must do themselves
  (Colab/Vercel/Oracle console). Give screen-by-screen when they're in an unfamiliar UI.
- The permission classifier may block destructive-looking DB scripts even on regenerable data —
  use AskUserQuestion when that happens.

## Current status (2026-07-22, all committed + pushed, HEAD = 3f4679a)

**132 tests · ruff check + format clean · pyright clean · 15 ADRs · CI + Eval Gate green.**
ALL 11 phases have committed artifacts; **OpsLM is trained and live on the Hub.**

| Phase | State |
|---|---|
| 1–2 Foundation / Ingestion | ✅ 1,243 docs / 7,386 chunks embedded; **+ Redis-Streams intake path (ADR-0013), verified live** |
| 3 Hybrid RAG serving | ✅ SSE/WS chat, citations, degradation ladder, vision input |
| 4 Evaluation platform | ✅ ablations v1/v2/v3, RAG-quality (1.0/0.99/1.0), structured-output eval, regression gate **15 thresholds**, CI eval-gate, contamination policy |
| 5 OpsLM fine-tune | ✅ **TRAINED on Colab T4 → `dhf1234/OpsLM-v1`**: merged 16-bit + LoRA adapter + **GGUF Q4_K_M** (`qwen3-4b-base.Q4_K_M.gguf`), all verified on the Hub. **+ DPO pipeline for v2 (ADR-0015).** Before/after eval still pending a serving session. |
| 6 LLM gateway | ✅ Redis cache (hit = 184× faster, $0) + daily budget kill-switch (ADR-0008) |
| 7 Inference lab | 🟡 harness + **5 inference-opt techniques** written & unit-tested (ADR-0011, ADR-0014) — **GPU/served-model numbers NOT yet produced** |
| 8 Observability | ✅ Langfuse v2 self-host (:3002) + tracing facade; live trace verified + screenshot in README (ADR-0010) |
| 9 Security | ✅ red-team classifier TPR 1.0 / spec 1.0; **injection quarantine verified live** (poisoned → 0 chunks) on both ingest paths; secret redaction (ADR-0007) |
| 10 MCP server | ✅ 5 tools verified live over stdio; Claude Desktop/Cursor config in `apps/mcp-server/README.md` |
| 11 Packaging | ✅ flagship README, architecture doc, K8s manifests, demo runbook, **2 blog posts**, **live Vercel demo site** |

Key eval story (the demo's backbone): v1 hybrid wins → v2 sparse "wins" (corpus 15×) → v3
paraphrase set proves the sparse win was vocabulary leakage; hybrid vindicated. Rerank measured
twice, off by default. Numbers in `docs/reports/`; narrative in
`docs/blog/01-eval-first-changed-my-retrieval-twice.md`.

## What shipped this session (2026-07-22)

- **OpsLM TRAINED** on Colab T4 (after fixing 3 version-drift bugs — see gotchas). Live at
  `dhf1234/OpsLM-v1` (merged 16-bit + adapter + GGUF Q4_K_M).
- **Instruction dataset scaled 593 → 838 pairs** (`generate_instructions --n 900`); DVC-pushed.
- **Streaming ingestion** (ADR-0013): `libs/core/streaming.py` + `apps/api/stream_ingest.py`, 6 tests, verified live.
- **Inference-optimization lab** (ADR-0014): `benchmarks/techniques/` — speculative decoding
  (lossless + acceptance meter), guided/structured decoding (schema FSM), quant Pareto frontier;
  harness TPOT + prefix-cache probe. 16 tests.
- **DPO pipeline** (ADR-0015): `libs/training/preferences.py` (+6 tests), `generate_preferences.py`,
  `training/scripts/train_opslm_dpo.py`, `training/notebooks/opslm_dpo_colab.ipynb`.
- **Demo site DEPLOYED**: `opslm-demo/` (Next.js, black/red terminal aesthetic) → live at
  **https://ops-verse.vercel.app** (public, no login wall). Chat is in **○ demo mode** (canned,
  labelled answers) until a model endpoint is wired.
- **Always-on free serving** scaffolded: `infra/oracle-opslm/` (Oracle Cloud Free ARM VM +
  Ollama + token-gated Caddy). `infra/hf-space-opslm/` kept but **HF now requires PRO** for
  Docker/Gradio Spaces — noted in its README.

## LEFTOVER WORK — prioritized

### 1. Take the demo chat LIVE (always-on, free) — `infra/oracle-opslm/`
User chose always-on. Path: Oracle Cloud "Always Free" A1 ARM VM (4 cores/24 GB) → run
`setup.sh` (installs Ollama, loads OpsLM GGUF, token-gated Caddy on :8080) → set Vercel env
`OPSLM_ENDPOINT` / `OPSLM_MODEL=opslm` / `OPSLM_API_KEY` → redeploy → console flips to `● model
online`. Full guide in `infra/oracle-opslm/README.md`. **Caveat:** Oracle free A1 often returns
"Out of host capacity" — retry different AD/time. User may want screen-by-screen help.

### 2. Before/after eval + Phase-7 inference numbers (needs OpsLM SERVED on a GPU/endpoint)
Both env-vars-only against a served OpsLM. Baseline (Gemini) already recorded.
```bash
OPSVERSE_CHAT_MODEL=ollama/opslm uv run python -m opsverse_evals.rag_suite --n 20
OPSVERSE_CHAT_MODEL=ollama/opslm uv run python -m opsverse_evals.structured_eval --n 12
# inference bench + technique numbers (vLLM/Ollama serving OpsLM):
python benchmarks/harness.py --base-url <engine>/v1 --model opslm --concurrency 1,4,16 --requests 32 --out benchmarks/results/<engine>.json
```
Write reports into `docs/reports/` (same shape → `/evals` renders them). Fill in the 5 technique
payoffs: speculative acceptance rate + tokens/s, guided-decoding json_parse_rate→1.0, quant
frontier (FP16/Q8/Q4), prefix-cache TTFT drop, multi-LoRA. Serve flags + what-proves-what in
`benchmarks/README.md`. **This is the LLM-inference-engineer story.** NOTE: rag_suite chat calls
burn the 20/day gemini-3.5-flash quota — budget around demo rehearsal.

### 3. DPO → OpsLM-v2 (optional depth; pipeline ready)
`uv run python -m opsverse_training.generate_preferences` (bulk quota; reads committed
`data/sft/`, writes `data/dpo/{train,val}.jsonl`) → `dvc add data/dpo && dvc push` → run
`training/notebooks/opslm_dpo_colab.ipynb` (Colab T4, ~1–2h) → OpsLM-v2. Then before/after v1-vs-v2.

### 4. USER TASKS (not code)
- **Rehearse `docs/demo-runbook.md`** once end-to-end (mind the 20/day quota).
- **Rotate 3 tokens** (all passed through chat): HF write token + both Kaggle `KGAT_` tokens.

### 5. Possible next upskill (researched 2026-07-22, user asked about it)
Top-2026 signal says the biggest remaining gap vs the market is **agents + agent/trace-based
evaluation** (OpsVerse has RAG+fine-tune+MCP; agents is the missing 4th pattern). Highest-leverage
future addition: an agentic layer over the existing MCP tools with step-level tool-use/task-completion
evals gated in CI. Only if the user wants it — it crosses the "OpsVerse ≠ agents" scope line.

## Honest gaps (do not overclaim)

- **OpsLM exists** (v1, SFT) — but the **before/after eval numbers don't exist yet** (needs serving).
  Say "trained and published; the measured before/after is the next serving session."
- Phase 7 inference techniques are **implemented + unit-tested**, but the **served numbers are pending**.
- Demo-site chat is **demo mode** until the Oracle endpoint is wired — describe it as such, don't
  claim it's live-calling the fine-tune yet.
- rag-quality thresholds n=20, structured-output n=12 — regression gates, not proof points.

## Environment gotchas (WILL bite you)

1. **Docker Desktop shuts down between sessions.** ASK the user first, then:
   `Start-Process "shell:AppsFolder\Docker.DockerForWindows.Settings"` and poll `docker info`.
   Only OpsVerse's own containers matter (the `wc26-mlops-*` ones belong to the user's other app).
2. **Ports**: API **8100** (8000 taken by WC26 app), web 3000, Langfuse **3002**.
3. **Gemini quotas**: `gemini-3.5-flash` = **20 req/DAY** (chat only). ALL bulk jobs use
   `gemini-3.1-flash-lite` — never point bulk at 3.5.
4. **Pins**: `litellm >=1.60,<1.92`; `langfuse >=2.50,<3.0`. fastembed cache: `FASTEMBED_CACHE_PATH`.
5. **PowerShell**: no heredocs; write commit messages to a scratchpad file + `git commit -F`, or
   use the Bash tool with `git commit -m` heredoc. `$env:PYTHONUTF8='1'` for any Python printing
   LLM output. cwd persists between tool calls.
6. `git push` prints its banner to stderr — PowerShell shows red "NativeCommandError" but
   `old..new main -> main` = success.
7. **CI runs BOTH `ruff check` AND `ruff format --check`.** Always run `uv run ruff format --check .`
   before committing — lint-clean is not format-clean (this bit us once, went red).
8. **Colab/Kaggle version drift** (fixed in the training scripts, keep in mind for new ones):
   T4 (Turing) has **no bf16** → use `is_bfloat16_supported()` to pick fp16; TRL ≥0.13 renamed
   `SFTTrainer(tokenizer=)` → `processing_class=`; import `unsloth` BEFORE trl/transformers.
9. **Kaggle:** free GPU needs **phone verification, which the user CANNOT do** (number already used)
   → Colab is the training path. Kaggle API token is the new `KGAT_` kind (auth via
   `KAGGLE_API_TOKEN` env var, not kaggle.json). `training/kaggle/` exists but is unusable without
   phone verification.
10. **Vercel:** the repo root is a Python monorepo, so a Vercel project MUST set **Root Directory =
    `opslm-demo`** or it tries to build Python and fails. Turn OFF Deployment Protection for a public link.
11. Long background jobs are resumable by design; on session start check `*.partial.jsonl` before
    assuming loss. `uv run pytest` is safe for the live DB. pyright scope excludes training/+notebooks.

## How to bring the local stack up

```bash
docker compose -f infra/compose/docker-compose.yml --profile full up -d --wait   # ASK before Docker Desktop; `full` = +Langfuse
uv sync --all-packages
(cd apps/api && uv run alembic upgrade head)              # no-op, head = 0003
$env:OPSVERSE_LANGFUSE_HOST='http://localhost:3002'; uv run uvicorn opsverse_api.main:app --port 8100   # background
uv run arq opsverse_api.worker.WorkerSettings             # background
(cd apps/web && npm run dev)                              # :3000 (cwd persists — cd back!)
curl http://localhost:8100/health/ready                   # expect 4x ok
uv run python -m opsverse_evals.regression                # expect 15/15 PASS
```

## Repo map (quick)

```
apps/api          FastAPI: routers/{health,ingest,search,chat,costs,evals}, worker, stream_ingest, alembic 0001..0003
apps/web          Next.js internal UI: / (chat), /evals, /costs   (localhost only)
apps/mcp-server   MCP stdio server, 5 tools + Claude Desktop/Cursor README
libs/core         settings, llm.py, gateway.py (cache/budget), tracing.py, streaming.py (Redis Streams), object_store
libs/ingestion    parsers, chunking, quality.py, pipeline
libs/rag          embeddings, store, rerank, retriever, chat.py
libs/evals        metrics, ablation, judge, rag_suite, regression, ci_retrieval_smoke, contamination, structured_eval, reporting
libs/security     injection.py, redact.py, evaluate.py
libs/training     schemas, quality, generate_instructions, preferences.py (DPO), generate_preferences.py
training/         scripts/{prepare_sft,train_opslm_qlora,train_opslm_dpo}.py, notebooks/{opslm_qlora,opslm_dpo}_colab.ipynb, kaggle/ (unusable)
benchmarks/       harness.py + techniques/{speculative,constrained,frontier}.py + tests   (ADR-0011, ADR-0014)
opslm-demo/       Next.js Vercel demo site (LIVE: ops-verse.vercel.app); app/api/chat = edge proxy to OPSLM_ENDPOINT
infra/oracle-opslm    always-on free serving: setup.sh + Caddy + README   (the live-model backend path)
infra/hf-space-opslm  llama.cpp OpenAI server (HF Spaces now PRO — kept as reusable app.py)
infra/compose     core + `full` profile (langfuse)   infra/k8s   documented manifests
docs/adr          0001..0015        docs/reports   6 live reports        docs/blog  2 posts
data/             corpus.dvc + instructions.dvc (content in MinIO); data/sft/{train,val}.jsonl committed to git
```

## Session-start checklist for next Claude

1. Read this file. 2. Working tree is clean at `3f4679a`; no rebuild needed unless changing code.
3. Ask the user what they want this session. Most likely: (a) Oracle setup to take the chat live
   (item 1), (b) a GPU serving session for the before/after eval + inference numbers (item 2), or
   (c) DPO → v2 (item 3). Items 1 and 3 need the user's HF/Oracle accounts; walk them screen-by-screen.
4. If touching local code: bring the stack up, verify `/health/ready` + `regression` 15/15.
5. Commit per milestone, `ruff check` + `ruff format --check` before every commit, heads-up before
   pushes, update this file at session end.
