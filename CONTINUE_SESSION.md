# OpsVerse AI — FINAL SESSION HANDOFF (demo 2026-07-27)

> **Read this whole top block before doing anything.** This is the **last working session**
> before the user's demo. Persistent memory:
> `C:\Users\Dilip\.claude\projects\c--Users-Dilip-OneDrive-Pictures-ftrag\memory\`.

## 🎯 The one thing that matters

**The user demos on 2026-07-27.** The project is in strong shape and **already
demo-worthy**. The docs are consistent, every claim is backed by committed data, and
**`docs/demo-runbook.md` has been rewritten inference-first** (2026-07-25) — it now
leads with the measured benchmark, has correct counts, marks every step that needs no
infrastructure `[no stack]`, and carries a "tough questions → honest answers" section.

**The remaining risk is purely operational: the runbook's live commands have never been
run end-to-end against a live stack.** That is this session's P0.

## Priority plan for this session — do strictly in order

### P0 — demo-critical (~60 min). Nothing else until these pass.

1. **Bring the stack up and walk the runbook top to bottom yourself**, verifying every
   command actually works (see "How to bring the local stack up" below):
   - `curl http://localhost:8100/health/ready` → 4× ok
   - `uv run python -m opsverse_evals.regression` → **15/15 PASS**
   - runbook step 4 (live chat in the web UI) → streams, cites, no degraded badges
   - runbook step 6 (`curl` cache hit) → prints `(cached)`, cost `0.0`, ~30ms
   - runbook step 7 (`opsverse_security.evaluate`) → TPR 1.0 / spec 1.0
   - runbook step 5 (Langfuse trace visible at :3002)
   **Fix the runbook wherever reality differs — reality wins.**
2. **Confirm `benchmarks/dashboard.html` opens correctly from disk** in the browser
   they'll present with. It's the `[no stack]` centerpiece and the whole fallback plan.
3. **Have the user rehearse once, end to end, out loud.** Mind the 20/day
   `gemini-3.5-flash` chat quota — at most two live-chat rehearsals.

### P1 — polish if P0 passes (~30 min)
4. Read the **"Tough questions"** section of the runbook with the user so the honest
   answers (especially "is the fine-tune actually better?") are natural, not read aloud.
5. Optional: deploy `benchmarks/dashboard.html` to GitHub Pages for a shareable link.

### P2 — STRETCH ONLY. Do not start unless P0+P1 are finished and there is real time left.
6. **Before/after eval** (base Qwen3-4B vs OpsLM-v1) — the one genuine content gap.
   Needs a **served OpsLM endpoint** (Colab vLLM + a tunnel) *and* the local stack:
   ```bash
   OPSVERSE_CHAT_MODEL=openai/OpsLM-v1 OPSVERSE_LLM_API_BASE=<tunnel-url>/v1 \
     uv run python -m opsverse_evals.rag_suite --n 20
   ```
   Then the frontier: `python benchmarks/report.py --results benchmarks/results
   --quality fp16=<score> --quality q4_k_m=<score> --out docs/reports/inference-benchmark-v1.md`.
   **Risk: HIGH** (3 Colab sessions were burned on GPU work on 2026-07-24/25).
   **Judgment: the demo does not need this.** "Trained and published; the measured
   before/after is the next serving session" is already an honest, strong answer.
   Burning demo-prep time here to chase it would be a bad trade — say so plainly.

## Where the project actually stands (2026-07-25, HEAD `25d9606`, pushed clean)

**Repositioned** to an "LLM inference & operations platform" (rationale:
`docs/migration-plan.md`; split serving: ADR-0016 — ephemeral Colab-T4 GPU for
measurement, always-on Oracle-ARM CPU for the demo). RAG is framed as the workload.

**Inference is MEASURED on a real T4** (the flagship gap, closed):
vLLM fp16 **13.4×** throughput scaling at **0.81×** latency; Ollama q4 **0.89× / 16×**;
prefix cache **47.8% on vs 0.0% off** (control); guided decoding vLLM **0→1.0**,
Ollama 0→0.0. → `docs/reports/inference-benchmark-v1.md`, raw JSON
`benchmarks/results/*.json`, visual `benchmarks/dashboard.html`.

**Shipped over 2026-07-23→25:** measurement suite (`benchmarks/run_suite.py`,
`report.py`) · model registry (`registry/` → `docs/model-registry.md`) · hardened
Colab notebook · inference TDD (`docs/inference-design.md`) · inference-first README ·
inference dashboard · CI security-scan stage (pip-audit + Trivy, advisory) ·
blog #3 (`docs/blog/03-measuring-continuous-batching-on-a-free-t4.md`).
**176 tests · ruff + format + pyright clean · 16 ADRs · CI + eval gate green.**

**Honest gaps — do not overclaim in the demo:**
- **Before/after eval (base vs OpsLM) does not exist.** Say "trained and published;
  the measured before/after is the next serving session."
- Quantization→quality **frontier is empty** (needs that eval); the report says so itself.
- No tensor-parallel / multi-GPU numbers — a single T4 can't; stated as a limitation.
- Demo-site chat is in **demo mode** unless the Oracle endpoint is wired.
- rag-quality n=20, structured-output n=12 — regression gates, not proof points.

**Colab lessons (baked into the notebook — don't rediscover):** install vLLM via
`uv pip install --system vllm --torch-backend=auto` → restart → set `LD_LIBRARY_PATH`
+ ctypes-preload `libcudart.so.13`; **AWQ dropped** (AutoAWQ unmaintained past torch
2.6); **stop vLLM before starting Ollama** (else Ollama silently runs 80% on CPU —
verify `ollama ps` shows 100% GPU); harness uses `include_usage` for token counts;
**Colab recycles the whole runtime**, so each run cats its JSON to stdout.

---

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

## Phase status (historical, as of 2026-07-22 — superseded by the top block)

> Counts here are stale (132 tests / 15 ADRs). **Current: 176 tests, 16 ADRs, HEAD `25d9606`.**
> Phase 7 is now DONE and measured. Kept for the per-phase detail only.

| Phase | State |
|---|---|
| 1–2 Foundation / Ingestion | ✅ 1,243 docs / 7,386 chunks embedded; **+ Redis-Streams intake path (ADR-0013), verified live** |
| 3 Hybrid RAG serving | ✅ SSE/WS chat, citations, degradation ladder, vision input |
| 4 Evaluation platform | ✅ ablations v1/v2/v3, RAG-quality (1.0/0.99/1.0), structured-output eval, regression gate **15 thresholds**, CI eval-gate, contamination policy |
| 5 OpsLM fine-tune | ✅ **TRAINED on Colab T4 → `dhf1234/OpsLM-v1`**: merged 16-bit + LoRA adapter + **GGUF Q4_K_M** (`qwen3-4b-base.Q4_K_M.gguf`), all verified on the Hub. **+ DPO pipeline for v2 (ADR-0015).** Before/after eval still pending a serving session. |
| 6 LLM gateway | ✅ Redis cache (hit = 184× faster, $0) + daily budget kill-switch (ADR-0008) |
| 7 Inference lab | ✅ **MEASURED 2026-07-25** on a Colab T4 — vLLM vs Ollama, batching 13.4× vs 0.89×, prefix cache 47.8% vs 0.0% control, guided decoding 0→1.0 (ADR-0011, ADR-0014, ADR-0016) |
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

## LEFTOVER WORK (2026-07-22 list — ⚠️ SUPERSEDED by the priority plan at the top)

> Item 2's "Phase-7 inference numbers" is **DONE** (measured 2026-07-25). The rest are
> post-demo ideas, not final-session work. **Follow the top block's P0→P1→P2 instead.**

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

## Session-start checklist for the FINAL session

1. **Read the top block.** The demo is 2026-07-27; **P0 is rewriting `docs/demo-runbook.md`
   inference-first** — it currently tells the old story with wrong counts.
2. Working tree is clean at `25d9606`; no rebuild needed unless changing code.
3. Do P0 → P1 → (only if time) P2, in that order. **Resist starting the before/after eval
   first** — it is the most seductive and the least demo-critical item, and GPU work has
   burned three sessions already.
4. If touching local code: bring the stack up, verify `/health/ready` (4× ok) + `regression`
   15/15. `uv run ruff check .` **and** `uv run ruff format --check .` before every commit.
5. Commit per milestone without asking; quick "pushing now" heads-up before each push.
6. **End of session:** tell the user plainly what is demo-ready and what is not, and give
   them the one-paragraph honest answer for each gap (see "Honest gaps" above) so nothing
   gets overclaimed on stage.
