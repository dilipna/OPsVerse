# OpsVerse AI — Demo Runbook

A tight **~12-minute** live walkthrough of an LLM **inference & operations platform**.
Rehearse once end-to-end before demo day.

> **If you only get 6 minutes:** steps 1, 2, 3 — and nothing else. All three are
> **[no stack]**, so they need no Docker, no API and no network. Steps 4–8 are the
> platform breadth; they are cuttable. Steps 2 and 3 are the demo.

> ✅ **Every live command in this runbook was executed end-to-end on 2026-07-26** against a
> real local stack on the presenting machine. Steps 3, 5, 6, 7 and the pre-flight are
> verified; the commands and expected outputs below are what actually happened, not what
> was intended. Shell-specific fixes from that run are folded in — **the original bash
> one-liners failed in PowerShell.**

> **Read this first — the resilience rule.** Steps marked **[no stack]** need nothing
> running: no Docker, no API, no network. They are `benchmarks/dashboard.html`, the
> committed reports, and the README. **If anything goes wrong live, retreat to those and
> you still deliver the whole story.** The strongest part of this demo — the measured
> inference result — is a `[no stack]` step by design.

---

## Pre-flight (10 min before you present)

> **Shell matters.** These were verified in **PowerShell** on the presenting machine
> (2026-07-26). In PowerShell `curl` is an alias for `Invoke-WebRequest` and **`&&` is a
> parse error** — the bash forms below will fail. Use the PowerShell column.

**PowerShell (the presenting shell):**
```powershell
# 1. Stack up (core + observability). Langfuse migrates on first boot (~40s).
docker compose -f infra/compose/docker-compose.yml --profile full up -d --wait

# 2. API (tracing on) + worker + web UI — three terminals
$env:OPSVERSE_LANGFUSE_HOST='http://localhost:3002'
uv run uvicorn opsverse_api.main:app --port 8100        # terminal 1
uv run arq opsverse_api.worker.WorkerSettings           # terminal 2
cd apps/web; npm run dev                                # terminal 3 -> :3000  (cd back after!)

# 3. Sanity — do not present until these two pass
curl.exe -s http://localhost:8100/health/ready          # expect 4x ok  (curl.exe, NOT curl)
uv run python -m opsverse_evals.regression              # expect 15/15 PASS

# 4. Clear the gateway cache — REQUIRED, see the warning below
docker exec opsverse-redis-1 redis-cli --scan --pattern 'gw:cache:*' | ForEach-Object { docker exec opsverse-redis-1 redis-cli DEL $_ }
```

> 🚨 **Flush the cache or step 4 dies.** Cache entries live **24 h**. If you rehearsed —
> or if anyone ran that question in the last day — step 4's question is already cached, so
> it returns **instantly at `cost=0` with no streaming and no fresh trace**. You lose the
> live-answer moment, step 5 has no new trace to open, and step 6's reveal is spoiled
> because the cache was already warm. The command above deletes only `gw:cache:*` keys —
> it leaves the arq queue and budget counters alone, so it is safe to run right before you
> present. Verify it worked: the scan should return nothing.

<details><summary>bash / WSL equivalents</summary>

```bash
docker compose -f infra/compose/docker-compose.yml --profile full up -d --wait
OPSVERSE_LANGFUSE_HOST=http://localhost:3002 \
  uv run uvicorn opsverse_api.main:app --port 8100
uv run arq opsverse_api.worker.WorkerSettings
(cd apps/web && npm run dev)
curl http://localhost:8100/health/ready
uv run python -m opsverse_evals.regression
```
</details>

**Tabs to open, left to right (in demo order):**
1. `benchmarks/dashboard.html` (open the file directly — no server needed)
2. `docs/overturns.html` (same — self-contained, no server, no network)
3. web UI http://localhost:3000
4. Langfuse http://localhost:3002 (`dev@opsverse.local` / `opsverse-dev-password`)
5. this runbook

> **Regenerate the two static pages before you present** so they match the repo:
> ```powershell
> uv run python -m opsverse_evals.overturns          # -> docs/overturns.html + docs/evidence.md
> python benchmarks/report.py --out docs/reports/inference-benchmark-v1.md
> ```
> Tabs 1 and 2 are the whole `[no stack]` retreat path. If Docker dies mid-demo, those two
> files plus the committed reports still carry the entire story.

> **Quota:** `gemini-3.5-flash` = **20 chat calls/day**. Rehearse the live chat at most
> twice; the gateway cache makes repeats free anyway (that's step 6).

---

## The walkthrough

### 1. The pitch (40s, no terminal) **[no stack]**

> "OpsVerse is an **LLM inference and operations platform**. I fine-tuned a model for
> DevOps, served it on real GPU hardware, and **measured** what production serving
> actually buys you — continuous batching, KV-cache reuse, guided decoding. Everything
> here is a measured number with its raw data committed: **22 ADRs, 258 tests**, CI and
> an eval gate green on every push.
>
> But the part I'd actually defend isn't the stack — hybrid RAG and a QLoRA fine-tune
> aren't rare. It's that **this project has been wrong seven times and published every
> one of them with the statistic that caught it.** Four were my own prior conclusions,
> two were defaults I'd already shipped, and one was the grader I was scoring everything
> else with. That's what I want to show you."

That last sentence sets up step 3 and reframes everything before it. If the room is
non-technical or you are short on time, cut the second paragraph and keep step 2 — but
**do not cut step 3 to save step 2**. Step 2 is the impressive one; step 3 is the rare one.

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

**If the room is technical, land this closer to step 2** (it is the sentence that separates
you from a benchmark screenshot):

> "Throughput isn't capacity, though. Hold both engines to the same latency contract —
> p95 time-to-first-token under a second, p95 end-to-end under thirty — and Ollama's
> serviceable concurrency is **one**. It fails the SLO at 4 and at 16. So the honest
> advantage isn't 13.4×, it's **6.3× goodput**, which is throughput that actually met the
> contract — about **42 cents versus $2.61 per million tokens** on a T4. And I'll flag the
> limitation myself: vLLM was still scaling at 16, so I never found its ceiling."

**It's already on screen** — scroll to the **"Capacity under an SLO"** panel on the dashboard.
Two rows, green/red chips per concurrency level: vLLM passes c=1/4/16, Ollama passes only c=1.
You do not have to leave the dashboard to make this point.

For the full version — every `n`, the saturation verdict, the noise floor — open
**`docs/reports/capacity-and-slo-v1.md`** ([ADR-0017](adr/0017-slo-constrained-goodput-as-the-capacity-metric.md)).
Generated by `benchmarks/capacity.py` from the same JSON as the benchmark, so the two can't drift.

### 3. Evaluation-first — the seven things I was wrong about (3.5 min) **[no stack]**

**This is the section that differentiates you.** Everything before it proves you can
measure; this proves you can be *wrong in public and correct it*, which is much rarer.

Open **`docs/overturns.html`** (self-contained — double-click it, no server, no network).
It is generated from the committed `*-summary.json` files, so every number on it is
plucked from source rather than typed.

> "The eval harness existed **before** the model, so 'better than base' is provable rather
> than asserted. And it has contradicted me seven times. Here they are on one screen."

**Tell three of them. Not all seven** — pick by room, and leave the rest on screen for
them to scan.

**(a) The one with three chapters — vocabulary leakage.** *Always tell this one.*

> "After growing the corpus 17× (421 → 7,383 chunks), sparse BM25 beat hybrid — 0.759 vs
> 0.705 MRR. Tempting result. But my eval questions were LLM-written *from* the gold chunk,
> which reuses its vocabulary and flatters exact-term matching. So I built a third eval set
> that **paraphrases every question**. Sparse dropped **0.149**; hybrid only 0.049. The win
> was leakage — I'd have shipped the wrong default.
>
> Then chapter three. I rebuilt the labels properly — pooled across all four retrieval
> modes, TREC-style, graded 0–3, 1,914 judgements — and ran a paired permutation test.
> Sparse versus hybrid: **+0.008 nDCG, p=0.57.** Not a win, not a loss. **A tie.** So the
> honest summary was never 'sparse wins' *or* 'hybrid wins'. It's 'these are
> indistinguishable here, and dense is genuinely worse.'"

**(b) The one where I deleted my own metrics.** *Best for an eval-focused room.*

> "I implemented `precision@k`, `recall@k` and contextual precision — the standard RAG
> metric set. Then I checked whether they carried independent information on my eval sets.
> They didn't: with exactly one gold label per query, `recall@k` **is** `hit@k`,
> `precision@k` is `hit@k/k`, and contextual precision is `mrr@k`. Verified per case
> across 3 datasets and 300 cases — the identities hold exactly.
>
> So I didn't report three of them. A five-metric table would have looked more rigorous
> than a two-metric one and contained exactly the same information. The fix was better
> labels, not more columns."

**(c) The grader itself.** *The freshest one, and the strongest for a research-adjacent room.*

> "Last thing. Every retrieval conclusion I just gave you rests on labels from **one LLM
> judge**. My only check on it was seed recovery — the chunk each question was written from
> should be graded relevant, and 100% were. That's a sanity check, not a validation: it asks
> one easy question per query and says nothing about the other eighteen candidates.
>
> So I audited it. Blinded sample, stratified on the judge's own call because only 16% of
> the pool is relevant, inverse-weighted back to population rates. **The judge is
> systematically strict** — precision 0.97, but TPR **0.57**. It misses a lot of what a
> second rater counts as relevant.
>
> Which means my absolute recall numbers read **low**. But the bias is near-equal across
> all four retrieval modes, and a shared bias cancels in a paired comparison — so the
> comparisons I just showed you still stand. **The levels move; the deltas don't.**
>
> And the honest caveat: my second rater was another model, not a human. Model-model
> agreement is biased upward, so that's an optimistic ceiling, not ground truth. Human
> labels are the open item."

**Then the CI gate, to land that none of this is theatre:**

```bash
uv run python -m opsverse_evals.regression         # 15 pinned thresholds, all green
```
Then open **`/evals`** in the web UI.

> "And these aren't retrospective write-ups — the thresholds are pinned in CI, so a
> regression fails the build on every push."

**If asked "isn't finding seven mistakes bad?"** — the answer to have ready:

> "Seven found is seven fixed. The question isn't whether a system has wrong assumptions
> in it — it's whether the process surfaces them before a user does. Every one of these was
> caught by a test I built, not by someone complaining."

### 4. A grounded answer, live (90s) — web UI

Ask: *"How does a Kubernetes HPA scale on custom metrics?"*

> ⚠️ **Expect a silent pause before the first token — measured 4.0 s and 13.3 s on
> 2026-07-26.** That is free-tier Gemini, not your stack. Don't stand there in silence and
> don't apologise; **talk over it** — this is the moment to say what's happening under the
> hood: *"while that's going — it's embedding the question, running hybrid retrieval over
> 7,386 chunks, and reranking before a token comes back."* By the time you finish that
> sentence it's usually streaming.

> "Streaming tokens, **inline citations**, a sources panel with retrieval scores, and
> degradation badges — none here, so this is full-quality retrieval. Every answer is
> grounded in retrieved docs and cites them."

Verified live 2026-07-26: `degraded: []`, `cited: [3, 2]`, 2,111 prompt / 141 completion
tokens, $0.0044. A second question (*"What is a Kubernetes readiness probe?"*) also
returned clean with 5 citations — a good spare if the first one misbehaves.

### 5. The trace (60s) — Langfuse tab

Refresh → open the newest `chat` trace. Two spans: `retrieval`, then `generation`.

> **Click the `generation` span, then its `Metadata` tab.** Verified 2026-07-26: the model,
> cost, and token counts live in span **metadata**, *not* in the waterfall header — these
> are `SPAN`-typed observations, so Langfuse's native cost column stays blank. Know this
> before you click; hunting for the number on stage looks like the feature is missing.
>
> `retrieval` span → input is the query, output is the ranked chunk IDs **with scores and
> source paths**, metadata has `n_chunks` and `degraded`.
> `generation` span → metadata has `model`, `cached`, `cost_usd`, `prompt_tokens`,
> `completion_tokens`, `first_token_ms`, `cited`, `grounded`.

> "The span waterfall: retrieval with chunk IDs and scores, then generation with model,
> token counts, **cost in dollars**, and first-token latency. This is how you debug
> 'answers got worse yesterday' in production."

⚠️ **Show the trace from your live step-4 question, not a repeat.** A cached call traces
with `cost_usd: 0` and `first_token_ms: ~33` — true, but it undercuts step 6's reveal and
looks like the cost tracking is broken.

### 6. The gateway cache (45s) — terminal

Ask the **same** question again.

**PowerShell** (verified 2026-07-26 — the bash `curl … | python` one-liner **fails** here):
```powershell
$body = '{"query":"How does a Kubernetes HPA scale on custom metrics?","stream":false}'
$r = Invoke-RestMethod -Uri http://localhost:8100/v1/chat -Method Post `
       -ContentType 'application/json' -Body $body
"{0}  cost={1}  latency_ms={2}" -f $r.done.model, $r.done.cost_usd, [math]::Round($r.done.latency_ms,1)
```
Expected: `gemini/gemini-3.5-flash (cached)  cost=0.0  latency_ms=` **anywhere from ~25 to ~140**
(mean 53.8 ms over n=13). The *number* moves run to run; `(cached)` and `cost=0.0` do not —
**those two are the point**, so lead with them and treat the latency as "tens of milliseconds".

<details><summary>bash equivalent</summary>

```bash
curl -s -X POST http://localhost:8100/v1/chat -H "Content-Type: application/json" \
  -d '{"query":"How does a Kubernetes HPA scale on custom metrics?","stream":false}' \
  | python -c "import sys,json;d=json.load(sys.stdin)['done'];print(d['model'],d['cost_usd'],d['latency_ms'])"
```
</details>

> "Tagged `(cached)`, **cost $0**, tens of milliseconds instead of seconds. A Redis
> exact-match cache plus a daily budget kill-switch. Free-tier survival by design."

**Say the multiplier only if you quote the range.** Measured over two independent rounds on
2026-07-26: cache hit **25–137 ms** (mean **53.8 ms**, n=13) versus a cold call of
**5.3 s–21.1 s** (n=2) — so the speedup spans **~40×–840×** depending on how the free-tier
upstream is behaving that minute. The safe line is *"tens of milliseconds and zero dollars,
versus seconds"*.

Do **not** quote a bare "184×" — it was the best case and had no recorded source.
Note the first round measured 25–33 ms and looked tight; a second round the same afternoon
ran up to 137 ms. **If asked why you don't give one number:** *"because it depends on an
upstream I don't control — the range is the honest answer, and the part that never moves is
`cost=0`."* That answer is stronger than a clean multiplier would have been.

### 7. Security (45s) — terminal

```bash
uv run python -m opsverse_security.evaluate        # TPR 1.0, specificity 1.0
```
> "Injection detection is a **measured classifier**, not a vibe — tested against benign
> DevOps text that shares the attack vocabulary, like `override entrypoint` and
> `system:masters`. Poisoned documents are quarantined at ingest: 0 chunks enter retrieval."

### 8. The model and its registry (45s) **[no stack]**

Open **`docs/model-registry.md`**.

> "**OpsLM-v1**: a QLoRA fine-tune of Qwen3-4B on **534 training examples** — a 593-pair
> split, decontaminated against the eval sets by hash. It's trained and **published on the Hub** —
> merged 16-bit, the LoRA adapter, and a GGUF Q4. The registry tracks each variant's quant,
> serving engine, and deployment status, and it pulls latency and throughput straight from
> the benchmark JSON, so a number here can't drift from the file that produced it."

⚠️ **The registry says `benchmarked; no live endpoint` — say that out loud, don't skip past it.**
It is the honest status: the GGUF is published and benchmarked, but nothing is serving it
always-on (Oracle ARM is scaffolded, not provisioned), so the public site runs in labelled
demo mode. Verified 2026-07-26: `ops-verse.vercel.app/api/chat` → `{"live":false}`.

> **If asked "so is it deployed?"** — *"It's published and benchmarked, not served. The
> always-on host is scaffolded but I haven't provisioned it, and the demo site says 'demo mode'
> on its face rather than pretending. I'd rather show you the measured serving numbers from the
> T4 than a box I can't prove is running."*

**The generated-vs-written point — worth making here.** This registry is generated from
`registry/models.json` plus the benchmark JSON. When I audited the docs the day before this
demo, the hand-written README had drifted on the dataset size and the registry had not —
because the registry can't drift, by construction. That's the argument for generating docs
from data, and it's on screen right now.

### 9. Close (25s) **[no stack]**

> "Free tiers end to end, measured everywhere, and an ADR for every hard call — including
> the seven where the measurement proved me wrong. Every number you saw has its raw JSON
> committed next to it, and the things I *can't* claim are written down too: no before/after
> for the fine-tune yet, no human labels on the judge, and a serving ceiling I never found
> because the sweep ran out before the GPU did. That's the project."

Point at **`docs/evidence.md`** — the one-page index of claim → report → raw JSON → the `n`
behind it, ending with a "what this project does not claim" section. It is the single
best link to leave someone with, and it is generated from the committed summaries.

Fallbacks: the README's inference table, or `docs/inference-design.md` for the deep dive.

---

## Tough questions — the honest answers

Have these ready. **Answering a gap cleanly is a stronger signal than not being asked.**

**"Is the fine-tuned model actually better than the base model?"**
> "I don't have that number yet, and I won't claim it. OpsLM is trained and published, and
> the eval harness that would grade it existed first — deliberately. The measured
> before/after is the next serving session. What I *have* measured is the serving layer."

**"How much data did you fine-tune on?"** ← *know this cold; the number is checkable in the repo*
> "534 training examples — a 593-pair split, 534 train / 59 val. The generator produced 838
> examples, but I scaled it two days *after* I built the split and never re-ran the prep step,
> so those extra examples never reached training. I caught that auditing my own claims the day
> before this demo — the docs had been saying 838. I fixed the claim rather than the data,
> because `data/sft/` is the provenance of the published checkpoint; regenerating it would make
> the committed data stop matching the weights on the Hub. It's written up in ADR-0009."

*Why this answer lands:* it is a small dataset and they know it. What you are demonstrating
is that you audit your own numbers, that you understand data provenance, and that you would
rather be correct than impressive. **Do not volunteer it unprompted** — but if dataset size
comes up, this is a better story than "838" ever was.

**"Isn't 534 examples too small to matter?"**
> "For a general model, yes. This is a narrow domain adapter — QLoRA r=16, ~0.5% of parameters,
> on one document domain. And I deliberately won't tell you it made the model better, because I
> haven't measured that yet. That's exactly why the eval harness came first."

**"What's your n on the prefix-cache number?"** ← *the sharpest question you will get; know it cold*
> "Four warm requests against one cold baseline. That's small, and I won't defend the exact
> 47.8% — I'd want n≥30 before I put an error bar on it. What I do defend is the **sign and
> the control**: the identical probe with caching disabled gave 0.0%, so the effect is real
> even though the magnitude has wide bars. I also measured my own noise floor — two vLLM runs
> at the same concurrency differed by 22% — so I don't read any single-run delta smaller than
> that as signal. All of it, with every `n`, is in the capacity report."

*Why this wins:* the questioner is testing whether you know your own measurement's weakness.
Naming n=4 **before they extract it**, then showing you quantified your noise floor, converts
the weakest number in the deck into evidence of rigour. Never say "about 48%" and stop.

**"How many users can one GPU serve? What does it cost?"**
> "Under a p95 TTFT ≤ 1s / p95 ≤ 30s contract: vLLM holds 16 concurrent, Ollama holds one.
> That's 233 vs 37 tokens/sec of goodput — roughly 42¢ versus $2.61 per million tokens at
> T4 on-demand pricing. The rate is an assumption and it's labelled as one in the report;
> everything else is measured."

**"Did you find the maximum throughput?"**
> "No, and the report says so. vLLM was still returning 65% marginal efficiency at
> concurrency 16, so the ceiling is above my last data point, not at it. Reporting 233 as a
> peak would be the single easiest way to be wrong on stage."

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
