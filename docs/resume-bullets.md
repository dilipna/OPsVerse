# OpsVerse AI — resume bullets

Grounded only in what's measured and committed as of 2026-09-06 (HEAD after ADR-0022).
Numbers cross-checked against the repo, not recalled from memory. Pick 3-4 bullets per
application, matched to the variant below that fits the role.

---

## Variant A — LLM / AI Engineer (generalist, RAG + fine-tuning)

- Built an LLM engineering platform (hybrid RAG + fine-tuning + evaluation, 280 tests,
  22 ADRs) that fine-tuned Qwen3-4B into a DevOps assistant (**OpsLM-v1**, published on
  Hugging Face) served behind a citation-grounded, hybrid dense+sparse retrieval
  pipeline with streaming chat, degradation handling, and vision input.
- Designed and ran a **pooled, graded (TREC-style) golden evaluation set** — 100 queries,
  1,914 relevance judgements across 4 retrieval modes — with bootstrap confidence
  intervals and paired permutation significance testing; the analysis downgraded two of
  the project's own earlier "wins" to statistical ties, catching an evaluation artifact
  before it reached a conclusion.
- Measured LLM inference serving on a real GPU (Tesla T4): vLLM's continuous batching
  delivered **13.4× throughput scaling** with *falling* p95 latency at concurrency 16,
  versus Ollama's flat throughput and 16× latency inflation — then converted the
  benchmark into a **goodput-under-SLO** analysis showing 6.3× more usable throughput per
  dollar, exposing that the raw throughput number wasn't the actionable one.
- Built a Redis-backed LLM gateway (cache + daily budget kill-switch) and a red-team
  security classifier (TPR 1.0, specificity 1.0) with injection quarantine verified live
  against poisoned documents — both instrumented with Langfuse tracing end to end.

## Variant B — LLM Evaluation / Applied ML (eval-first, methodology emphasis)

- Implemented the standard RAG retrieval metrics (`precision@k`, `recall@k`, contextual
  precision) — then **proved three of them were mathematically degenerate** on the
  project's own single-gold-label eval sets (`recall@k ≡ hit@k` etc., verified to 1e-12
  across 300 cases), and published that finding as the reason to build better labels
  instead of reporting hollow metrics.
- Closed that gap by building a **pooled, graded, position-randomised golden set** from
  scratch (TREC pooling across 4 retrieval modes, 0–3 relevance grading, 100% seed
  recovery as a judge sanity check) and used it to run a from-first-principles
  significance analysis: bootstrap CIs on every mean, paired permutation tests on every
  comparison — the correct statistic given per-query difficulty dominates the variance.
- Extended the same golden set to the **generator side**: wrote independent reference
  answers grounded in judge-verified relevant chunks (not any system's own output),
  decomposed them into 412 atomic claims, and measured **contextual recall** per
  retrieval mode — the one metric able to catch a system that retrieves too little and
  still "sounds" faithful, because the faithfulness judge alone is reference-free.
- Practiced eval-before-claims discipline throughout: the harness caught a real bug
  (grading against a 900-character excerpt window silently truncated 35% of the corpus's
  answers before the judge ever saw them) during validation, and a prior retrieval
  "win" for sparse search was later shown to be vocabulary leakage in the eval set
  itself — both documented rather than hidden.

- **Audited the LLM judge that produced those labels** — the check nobody runs on their own
  eval set. Blinded, stratified sample (n=190) with inverse-probability weighting back to
  population rates, TPR/TNR and quadratic-weighted kappa with a stratified bootstrap; found
  the judge **systematically strict** (signed error +0.327 [+0.226, +0.430], precision 0.968
  vs TPR 0.571). Reported both consequences: absolute recall reads low, but judge error is
  equal across retrieval modes, so the published comparisons survive. *(Second-model rater,
  not human — say so.)*
- Ran a **chunk-size ablation** by re-parsing the original source documents under 3 configs
  (not re-splitting existing chunks) and found the **shipped 350-token default was not the
  best-measured option** — 150-token chunks scored +0.044 nDCG_graded@10, p=0.0002 — and an
  **embedding-model ablation** showing the incumbent is statistically indistinguishable from
  a model 3.1× smaller (p=0.94), with indexing throughput reported next to quality so "no
  difference" becomes a cost decision.
- Built the project's first **multi-turn eval set**, identified a concrete production failure
  mode (retrieval ignores conversation history), floor-tested the obvious fix, and
  **published the null result** — concatenating history trends *worse*, not better
  (nDCG −0.074, p=0.25) — rather than shipping an untested intuition.

## Variant C — MLOps / Platform Engineering (infra, reliability, cost emphasis)

- Operated an LLM platform on strictly free-tier infrastructure: Docker Compose
  (Postgres, Redis, Qdrant, MinIO, Langfuse) locally, ephemeral Colab-T4 GPU for
  measurement, and a Vercel-deployed demo site — with a CI eval gate (15 pinned
  thresholds) blocking regressions on every push.
- Converted a raw inference benchmark into a **capacity-and-cost decision**: modeled
  goodput under a latency SLO (p95 TTFT ≤ 1s), found the flagship serving engine was
  **not saturated** at its highest tested concurrency (65% marginal efficiency) and that
  two identical runs varied by ±22% — publishing the noise floor next to the headline
  number instead of letting it imply more precision than it had.
- Built a request-scoped LLM gateway with an exact-match Redis cache (measured
  tens-of-milliseconds cache hits vs. multi-second cold calls, $0 marginal cost) and a
  daily spend kill-switch, keeping a multi-service platform inside a free-tier LLM
  quota under real usage.
- Instrumented the full request path (retrieval → generation → cost) with Langfuse
  tracing and shipped a CI security-scan stage (pip-audit + Trivy); when the scan
  silently no-op'd for 7 pushes due to an unresolvable action version, caught and fixed
  it, then documented the outage rather than quietly re-greening the badge.

---

## What NOT to claim yet (keep the resume honest)

- **No before/after number for the fine-tune.** Say, if asked: *"trained and published;
  the measured before/after against the base model is the next serving session."*
  (Runbook prepared for an AWS Spot T4 if you revisit it — currently deprioritized.)
- **The judge validation used a second MODEL, not a human.** Never write or say "validated
  against human labels". The correct phrasing is *"audited the judge against a blinded
  second-model rater; human labels are the open next step."* Model-model agreement is
  biased upward and an interviewer who knows evals will ask. Owning it first is the
  stronger move.
- **Live demo chat is canned/demo-mode**, not calling the fine-tuned model. The
  dashboard at the same URL is real and measured; don't conflate the two if asked to
  demo live.
- **The chunking ablation covered 100 of 594 candidate documents** (time-boxed). Quote the
  scope with the result, as the report does.
- **Peak serving throughput is un-measured** — vLLM was still scaling at c=16. Say "at
  least 13.4×", never "up to".

---

## Links to include on every application

- Repo: https://github.com/dilipna/OPsVerse
- **Start-here page** (the 8 overturns, one screen): `docs/evidence.md` in the repo
- Measured benchmark dashboard: https://ops-verse.vercel.app/dashboard.html
- Claim ledger, hosted: https://ops-verse.vercel.app/overturns.html
- Writing: https://dilipna.hashnode.dev — three posts, listed in the README

Anthropic's careers page says to put independent research and blog posts at the *top* of
a resume. These three are the closest thing this project has to that, so lead with them
rather than burying them under the repo link.

## The one-line version (for a LinkedIn headline or the top of a cover letter)

> Built an LLM inference + evaluation platform on free tiers, then used it to prove myself
> wrong eight times — including that the grader scoring everything else was miscalibrated —
> and published each with the significance test that caught it.

## The 30-second spoken version (phone screens)

> "It's an LLM inference and ops platform — fine-tuned model, hybrid RAG, benchmarked on a
> real T4. But the part I'd defend is the evaluation. I built the harness before the model,
> and it's overturned eight things: two shipped defaults, four of my own prior conclusions,
> and eventually the LLM judge producing the labels — which turned out to be systematically
> strict, precision 0.97 against TPR 0.57. That last one mattered because it told me my
> absolute recall numbers read low, but the bias was equal across retrieval modes, so the
> comparisons still held. Levels move, deltas don't."
