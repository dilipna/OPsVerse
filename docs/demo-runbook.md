# OpsVerse AI — Demo Runbook

A tight, ~8-minute live walkthrough that hits every headline capability, with
the exact commands and the one-line story to tell at each step. Rehearse once;
everything below is verified to work against the local stack.

## Pre-flight (before you present)

```bash
# 1. Stack up (core + observability profile) — do this 5 min early; Langfuse
#    runs DB migrations on first boot (~40s).
docker compose -f infra/compose/docker-compose.yml --profile full up -d --wait

# 2. API (with tracing on) + worker + web UI
OPSVERSE_LANGFUSE_HOST=http://localhost:3002 \
  uv run uvicorn opsverse_api.main:app --port 8100     # terminal 1
uv run arq opsverse_api.worker.WorkerSettings          # terminal 2
(cd apps/web && npm run dev)                            # terminal 3 -> :3000

# 3. Sanity
curl http://localhost:8100/health/ready                # expect 4x ok
```

Open tabs: **web UI** http://localhost:3000 · **Langfuse** http://localhost:3002
(login dev@opsverse.local / opsverse-dev-password) · this runbook.

> Gemini free tier: `gemini-3.5-flash` = **20 chat calls/day**. Don't rehearse
> the live chat more than a couple times on demo day; the cache (step 4) makes
> repeats free anyway.

## The walkthrough

### 1. The pitch (30s, no terminal)
"OpsVerse is a production LLM platform for DevOps knowledge — built
evaluation-first, on free tiers, with an ADR for every decision. Nine ADRs,
90 tests, CI + an eval gate green on every push."

### 2. Ask it something real (90s) — web UI
Type: *"How does a Kubernetes HPA scale on custom metrics?"*
- Point out: **streaming tokens**, **inline citations [1][2]**, the **sources
  panel** with scores, the **degraded badges** (none here = full quality).
- Story: "Every answer is grounded in retrieved docs and cites them — no
  free-floating LLM claims."

### 3. The trace — the money shot (90s) — Langfuse tab
Refresh Langfuse → open the newest `chat` trace.
- Show the **span waterfall**: `retrieval` (chunk ids + scores) → `generation`
  (model, prompt tokens, **cost in $**, cited indices, first-token latency).
- Story: "One screenshot tells the whole request story — this is how you debug
  'answers got worse yesterday' in production."

### 4. The gateway cache (45s) — terminal
Ask the **same** question again via the API:
```bash
curl -s -X POST http://localhost:8100/v1/chat -H "Content-Type: application/json" \
  -d '{"query":"How does a Kubernetes HPA scale on custom metrics?","stream":false}' \
  | python -c "import sys,json;d=json.load(sys.stdin)['done'];print(d['model'],d['cost_usd'],d['latency_ms'])"
```
- Show: model tagged `(cached)`, **cost 0.0**, latency ~30ms vs ~6000ms.
- Story: "Redis exact-match cache + a daily budget kill-switch — the gateway is
  a library, not another proxy to run. Free-tier survival by design."

### 5. Evaluation-first (60s) — terminal
```bash
uv run python -m opsverse_evals.regression         # 13 pinned thresholds, all green
```
- Then open `/evals` in the web UI: ablation v1/v2/v3 + RAG-quality + security.
- Story: "The eval harness existed **before** the model. v3 is the paraphrased
  set that proved hybrid beats sparse under real reworded queries — sparse's
  earlier win was vocabulary leakage. Honest numbers, including the ones that
  changed my mind."

### 6. Security (45s) — terminal
```bash
uv run python -m opsverse_security.evaluate        # TPR 1.0, specificity 1.0
```
- Story: "Injection detection is a **measured classifier**, not a vibe — tested
  against benign DevOps text that shares the attack vocabulary (`override
  entrypoint`, `system:masters`). Poisoned docs are quarantined at ingest."

### 7. MCP — inside Claude/Cursor (60s)
Show `apps/mcp-server` and (if wired to Claude Desktop) call `search_docs` live.
```bash
uv run opsverse-mcp    # stdio server; 5 tools
```
- Story: "The whole platform is also an MCP server — search, chat, evals, and
  costs as tools inside Claude Desktop or Cursor."

### 8. The model story (30s) — no terminal
Open `training/README.md`.
- Story: "OpsLM: a QLoRA fine-tune of Qwen3-4B on a 593-example instruction set
  synthesized from the corpus — decontaminated against the eval sets by hash.
  The pipeline is committed and resumable; the training run is a Colab session
  away, and it has to clear the eval gate that already exists."

## Close (20s)
"Free tiers, local-first, evaluation-first — every hard call is an ADR you can
read. That's the project." → point at the README capability table.

## If something fails live
- **Chat errors / quota**: the cache still serves prior questions; fall back to
  the `/evals` and Langfuse tabs (no LLM needed).
- **Langfuse down**: tracing is default-off and never blocks chat — just skip
  step 3; the stack is unaffected.
- **Docker cold**: `docker compose ... --profile full up -d --wait` and give
  Langfuse ~40s to migrate before opening its tab.
