# OpsVerse AI — Demo Runbook

A tight **~10-minute** live walkthrough of an LLM **inference & operations platform**.
Rehearse once end-to-end before demo day.

> **Read this first — the resilience rule.** Steps marked **[no stack]** need nothing
> running: no Docker, no API, no network. They are `benchmarks/dashboard.html`, the
> committed reports, and the README. **If anything goes wrong live, retreat to those and
> you still deliver the whole story.** The strongest part of this demo — the measured
> inference result — is a `[no stack]` step by design.

---

## Pre-flight (10 min before you present)

```bash
# 1. Stack up (core + observability). Langfuse migrates on first boot (~40s).
docker compose -f infra/compose/docker-compose.yml --profile full up -d --wait

# 2. API (tracing on) + worker + web UI — three terminals
OPSVERSE_LANGFUSE_HOST=http://localhost:3002 \
  uv run uvicorn opsverse_api.main:app --port 8100     # terminal 1
uv run arq opsverse_api.worker.WorkerSettings          # terminal 2
(cd apps/web && npm run dev)                            # terminal 3 -> :3000

# 3. Sanity — do not present until these two pass
curl http://localhost:8100/health/ready                # expect 4x ok
uv run python -m opsverse_evals.regression             # expect 15/15 PASS
```

**Tabs to open, left to right (in demo order):**
1. `benchmarks/dashboard.html` (open the file directly — no server needed)
2. web UI http://localhost:3000
3. Langfuse http://localhost:3002 (`dev@opsverse.local` / `opsverse-dev-password`)
4. this runbook

> **Quota:** `gemini-3.5-flash` = **20 chat calls/day**. Rehearse the live chat at most
> twice; the gateway cache makes repeats free anyway (that's step 6).

---

## The walkthrough

### 1. The pitch (30s, no terminal) **[no stack]**

> "OpsVerse is an **LLM inference and operations platform**. I fine-tuned a model for
> DevOps, served it on real GPU hardware, and **measured** what production serving
> actually buys you — continuous batching, KV-cache reuse, guided decoding. Everything
> here is a measured number with its raw data committed: **16 ADRs, 176 tests**, CI and
> an eval gate green on every push."

### 2. The measured inference result — **the money shot** (2.5 min) **[no stack]**

Open **`benchmarks/dashboard.html`**.

> "Same model, same Tesla T4, same harness — the only variable is the serving engine.
> At one request at a time, **Ollama wins**: 3.6 seconds versus vLLM's 13. If I'd stopped
> there I'd have written that Ollama is 3.6× faster.
>
> Then I swept concurrency to 16 and the ranking **inverted**. vLLM scaled throughput
> **13.4×** — 17 to 233 tokens/sec — while its p95 latency actually *dropped*. Ollama's
> throughput went **flat**, and its latency inflated **16×**.
>
> That's **continuous batching**. vLLM interleaves many requests' decode steps into shared
> forward passes on top of PagedAttention, so concurrent requests ride the same GPU passes.
> Ollama serializes them, so everyone queues — its TTFT went from 0.4s to 65s.
>
> So 'which engine is faster' has no answer. **'Which is faster at what load'** does — and
> that's the actual engineering decision."

Then point at the **prefix-cache** rows:

> "Prefix caching measured a 47.8% TTFT reduction. On its own that number is worthless —
> a warm server is faster for lots of reasons. So I re-ran the identical probe with the
> cache **off**: **0.0%**. The gap between those two runs *is* the cache. A measurement
> without its control is an anecdote."

**If asked "how do I know these are real?"** → the raw JSON is committed in
`benchmarks/results/`, stamped with GPU, engine version, and timestamp; the report is
generated from those files by `benchmarks/report.py`.

### 3. Evaluation-first — the result that falsified itself (90s)

```bash
uv run python -m opsverse_evals.regression         # 15 pinned thresholds, all green
```
Then open **`/evals`** in the web UI.

> "The eval harness existed **before** the model, so 'better than base' is provable rather
> than asserted. It has contradicted me twice. The best one: after growing the corpus 15×,
> sparse BM25 beat hybrid — 0.759 vs 0.705 MRR. Tempting result. But my eval questions were
> LLM-written from the gold chunk, which reuses its vocabulary and flatters exact-term
> matching. So I built a **third eval set that paraphrases every question**. Sparse dropped
> **0.149**; hybrid only 0.049. The sparse win *was* vocabulary leakage — I'd have shipped
> the wrong default. That gate is now in CI."

### 4. A grounded answer, live (90s) — web UI

Ask: *"How does a Kubernetes HPA scale on custom metrics?"*

> "Streaming tokens, **inline citations**, a sources panel with retrieval scores, and
> degradation badges — none here, so this is full-quality retrieval. Every answer is
> grounded in retrieved docs and cites them."

### 5. The trace (60s) — Langfuse tab

Refresh → open the newest `chat` trace.

> "The span waterfall: retrieval with chunk IDs and scores, then generation with model,
> token counts, **cost in dollars**, and first-token latency. This is how you debug
> 'answers got worse yesterday' in production."

### 6. The gateway cache (45s) — terminal

Ask the **same** question again:
```bash
curl -s -X POST http://localhost:8100/v1/chat -H "Content-Type: application/json" \
  -d '{"query":"How does a Kubernetes HPA scale on custom metrics?","stream":false}' \
  | python -c "import sys,json;d=json.load(sys.stdin)['done'];print(d['model'],d['cost_usd'],d['latency_ms'])"
```
> "Tagged `(cached)`, **cost $0**, ~30ms instead of ~6 seconds — **184× faster**. A Redis
> exact-match cache plus a daily budget kill-switch. Free-tier survival by design."

### 7. Security (45s) — terminal

```bash
uv run python -m opsverse_security.evaluate        # TPR 1.0, specificity 1.0
```
> "Injection detection is a **measured classifier**, not a vibe — tested against benign
> DevOps text that shares the attack vocabulary, like `override entrypoint` and
> `system:masters`. Poisoned documents are quarantined at ingest: 0 chunks enter retrieval."

### 8. The model and its registry (45s) **[no stack]**

Open **`docs/model-registry.md`**.

> "**OpsLM-v1**: a QLoRA fine-tune of Qwen3-4B on 838 synthetic DevOps instructions,
> decontaminated against the eval sets by hash. It's trained and **published on the Hub** —
> merged 16-bit, the LoRA adapter, and a GGUF Q4. The registry tracks each variant's quant,
> serving engine, and deployment status, and it pulls latency and throughput straight from
> the benchmark JSON, so a number here can't drift from the file that produced it."

### 9. Close (20s) **[no stack]**

> "Free tiers end to end, measured everywhere, and an ADR for every hard call — including
> the ones where the measurement proved me wrong. That's the project."

Point at the README's inference table, or `docs/inference-design.md` for the deep dive.

---

## Tough questions — the honest answers

Have these ready. **Answering a gap cleanly is a stronger signal than not being asked.**

**"Is the fine-tuned model actually better than the base model?"**
> "I don't have that number yet, and I won't claim it. OpsLM is trained and published, and
> the eval harness that would grade it existed first — deliberately. The measured
> before/after is the next serving session. What I *have* measured is the serving layer."

**"Why only a T4? Can this scale?"**
> "A single free T4 can't demonstrate tensor parallelism or multi-node, so I don't claim it —
> it's written up as a limitation in the design doc. Everything a single device *can*
> show — continuous batching, KV-cache reuse, prefix caching, guided decoding — I measured."

**"Which quantization should you serve?"**
> "The frontier is deliberately empty right now. I have latency for FP16 and Q4, but a
> speed-only frontier always recommends the smallest quant by construction — that's the exact
> mistake it exists to prevent. It stays empty until each config has a quality score."

**"Why not RAGAS / DeepEval / Promptfoo?"**
> "I evaluated promptfoo and wrote up why I didn't use it (ADR-0006). The bespoke harness
> gives me frozen eval sets, a contamination guard, and pinned CI thresholds — and it caught
> two wrong decisions. Three imported frameworks wouldn't have."

**"What went wrong building it?"**
> "Plenty, and it's all documented. AWQ quantization: AutoAWQ is unmaintained past torch 2.6
> and threw cascading conflicts, so I dropped it and recorded why. Ollama silently ran 80% on
> CPU because vLLM still held the GPU — those numbers would have been mislabeled, so the
> notebook now asserts full GPU offload before benchmarking. And Colab recycled a runtime and
> wiped my results — which is why every run now prints its JSON immediately."

---

## If something fails live

| Failure | Fallback |
|---|---|
| **Docker won't start / stack down** | Go **all `[no stack]`**: dashboard → reports → registry → README. You lose steps 4–7 and keep the best 60%. |
| **Chat errors or quota exhausted** | The cache still serves prior questions. Otherwise skip to `/evals` and the dashboard — neither needs an LLM call. |
| **Langfuse down** | Tracing is default-off and never blocks chat. Skip step 5; show the trace screenshot in the README instead. |
| **Web UI won't build** | Use the `curl` in step 6 to show a grounded answer with citations from the API directly. |
| **Projector/network dies** | `benchmarks/dashboard.html` is a single self-contained file — it works offline from disk. |
