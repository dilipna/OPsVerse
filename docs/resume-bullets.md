# OpsVerse AI — resume bullets

Grounded only in what's measured and committed as of 2026-09-01 (HEAD after ADR-0019).
Numbers cross-checked against the repo, not recalled from memory. Pick 3-4 bullets per
application, matched to the variant below that fits the role.

---

## Variant A — LLM / AI Engineer (generalist, RAG + fine-tuning)

- Built an LLM engineering platform (hybrid RAG + fine-tuning + evaluation, 215 tests,
  19 ADRs) that fine-tuned Qwen3-4B into a DevOps assistant (**OpsLM-v1**, published on
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
- **Embedding-model, chunking, and multi-turn ablations were in progress as of this
  draft** — do not cite specific numbers for these until `docs/reports/embedding-ablation-v1.md`,
  `chunking-ablation-v1.md`, and `multiturn-v1.md` exist and are committed. Placeholder
  bullets below, fill in once real:
  - *"Ran a chunk-size ablation (re-parsing the source corpus under 3 configs) and an
    embedding-model ablation (384→1024-dim, ~18× size range) against the golden set,
    with cost (indexing throughput) reported alongside quality rather than quality
    alone."*
  - *"Measured a concrete multi-turn retrieval failure mode — the retriever ignores
    conversation history — and tested the cheapest mitigation with a paired
    significance test."*
- **Live demo chat is canned/demo-mode**, not calling the fine-tuned model. The
  dashboard at the same URL is real and measured; don't conflate the two if asked to
  demo live.
