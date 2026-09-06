# Evidence index — how to read this repository

Generated 2026-09-06 by `opsverse_evals.overturns` from the committed
`docs/reports/*-summary.json`. Every number below is plucked from those files, so
this page cannot drift away from the reports it summarises. No network, no stack.

> **The short version.** The stack here — hybrid RAG, a QLoRA fine-tune, a served
> model, an eval harness — is not unusual. What is unusual is the record below:
> **seven claims this project believed, tested, and had to withdraw**, each
> published with the statistic that overturned it. Four of them were the project's
> own prior conclusions; two were shipped defaults; one was the grader itself.

---

## The overturns

### 1. Sparse retrieval beats hybrid — the v2 ablation measured it.

**Wrong twice, in two different ways.**

v2 raw set: sparse MRR@10 0.759 vs hybrid 0.705. v3 reworded queries: sparse falls to 0.611 (-0.149) while hybrid holds at 0.655 (-0.049) -- the 'win' was vocabulary leakage. Pooled graded labels: nDCG +0.008, p=0.573 -- a statistical tie.

*What changed:* Three chapters on one claim: a measured win, shown to be an artifact of the eval set, then shown to be no difference at all. Hybrid stayed the default for the robustness reason, not the original one.

Evidence: [retrieval-ablation-v2](reports/retrieval-ablation-v2.md) · [retrieval-ablation-v3](reports/retrieval-ablation-v3.md) · [retrieval-golden-v1](reports/retrieval-golden-v1.md) · [ADR-0019](adr/0019-golden-set-pooled-graded-relevance.md)

### 2. Adding `precision@k`, `recall@k` and contextual precision makes the eval suite more rigorous.

**Three of them were the same column twice.**

On single-gold-label sets `recall@k` == `hit@k`, `precision@k` == `hit@k/k`, and contextual precision == `mrr@k`. Verified per case across 3 datasets / 300 cases: the identities hold exactly, to the last bit of floating point (max deviation 0, against a 1e-12 tolerance). Three of the five new metrics carried no independent information, so they were not reported.

*What changed:* Implemented, tested, proven degenerate — and then *not reported*. The fix was better labels, not more metrics, which is what motivated the golden set.

Evidence: [retrieval-metrics-audit-v1](reports/retrieval-metrics-audit-v1.md) · [ADR-0018](adr/0018-retrieval-metrics-independence-audit.md)

### 3. `hit@10` is a meaningful headline metric for this corpus.

**Saturated. It cannot separate anything.**

All four retrieval modes score 0.97-0.99 on `hit@10`, and no pairwise difference is significant (worst p=1.000). The metric most prominent in the project's own earlier reports had no remaining power to separate anything.

*What changed:* Demoted from the headline. `nDCG_graded@10` and `recall@10` do the discriminating; `hit@10` is reported only to show it is exhausted.

Evidence: [retrieval-golden-v1](reports/retrieval-golden-v1.md) · [ADR-0019](adr/0019-golden-set-pooled-graded-relevance.md)

### 4. The shipped 350-token chunk size is the right default.

**It is not the best-measured option.**

Re-parsing the real source documents under three chunk sizes: 150-token chunks beat the shipped 350-token default by nDCG +0.044 [+0.019, +0.074], p<0.001. Scope: 100/594 candidate documents (time-boxed, and said so).

*What changed:* A shipped default was contradicted by a measurement of the system's own corpus. Reported at document granularity, with the time-boxed scope stated.

Evidence: [chunking-ablation-v1](reports/chunking-ablation-v1.md) · [ADR-0020](adr/0020-chunking-and-multiturn-ablations.md)

### 5. The larger embedding model earns its cost.

**No measurable difference against one 3.1x smaller.**

The incumbent (768-dim, 0.21 GB) is indistinguishable from a model 3.1x smaller (384-dim, 0.07 GB): nDCG -0.001 (p=0.943), recall -0.002 (p=0.929). The extra size was not earning its cost on this corpus.

*What changed:* Quality reported alongside indexing throughput, so 'no difference' becomes a cost decision rather than a shrug.

Evidence: [embedding-ablation-v1](reports/embedding-ablation-v1.md) · [ADR-0021](adr/0021-embedding-model-ablation.md)

### 6. Concatenating conversation history will fix multi-turn retrieval.

**It does not. It trends worse.**

Production retrieval ignores conversation history. The obvious fix -- concatenating the previous turn -- does not help: nDCG -0.074 (p=0.247), MRR -0.071 (p=0.301) across 50 two-turn conversations. It trends *worse*, not better. Published as a null result rather than assumed to work.

*What changed:* The intuitive fix was floor-tested before being shipped, and the null result was published with its significance test instead of being quietly dropped.

Evidence: [multiturn-v1](reports/multiturn-v1.md) · [ADR-0020](adr/0020-chunking-and-multiturn-ablations.md)

### 7. The relevance judge is sound — it recovered 100% of seed chunks.

**Systematically strict. Seed recovery was the easy question.**

Audited on a blinded, stratified sample (n=190): the judge is systematically strict. Signed error +0.327 [+0.226, +0.430] on the 0-3 scale, precision 0.968 against TPR 0.571, quadratic kappa 0.717. Reference rater is `claude-opus-5` -- a **model**, not a person, so this is an optimistic ceiling and human labels remain open.

*What changed:* Absolute recall/nDCG on the golden set read low. But the bias is near-equal across all four retrieval modes, so the published comparisons stand: the levels move, the deltas do not.

Evidence: [judge-validation-v1](reports/judge-validation-v1.md) · [ADR-0022](adr/0022-judge-validation-against-a-second-rater.md)

---

## Where everything else lives

**1. The overturns** — `docs/evidence.md`  
This page. Seven claims the project tested and had to withdraw.

**2. The measured inference result** — `docs/reports/inference-benchmark-v1.md`  
vLLM vs Ollama on one Tesla T4, one harness. Raw JSON in `benchmarks/results/`; visual dashboard in `benchmarks/dashboard.html` (self-contained).

**3. Throughput turned into a decision** — `docs/reports/capacity-and-slo-v1.md`  
Goodput under a latency SLO, cost per 1M tokens, and the two things the analysis reports against itself: the sweep never saturated the device, and two identical runs differed by 22%.

**4. How the labels were built** — `docs/reports/retrieval-golden-v1.md`  
Pooled TREC-style, graded 0-3, position-randomised, 1,914 judgements, with bootstrap CIs and paired permutation tests on every comparison.

**5. Whether the grader is trustworthy** — `docs/reports/judge-validation-v1.md`  
The golden set's own judge, audited against a blinded second rater.

**6. The decisions, with their tradeoffs** — `docs/adr/`  
22 ADRs. Each states what was rejected and why, not just what was chosen.

---

## What this project does *not* claim

Every result above has a boundary. These are the ones worth stating out loud,
because a portfolio that only lists wins is not reporting, it is advertising.

- **No before/after number for the fine-tune.** OpsLM-v1 is trained and published, but it has not been evaluated against base Qwen3-4B on a served endpoint. The runbook for that comparison is written (`docs/opslm-before-after-aws-runbook.md`); the run is deliberately not done.
- **The judge validation used a second model, not a human.** It narrows the 'one rater's opinion' limitation; it does not close it. Model-model agreement is biased upward. Human labels remain open.
- **Peak serving throughput is un-measured.** vLLM was still scaling at the top of the concurrency sweep (65% marginal efficiency at c=16), so the maximum was never found and is not reported as if it had been.
- **A single T4 cannot show tensor parallelism or multi-node serving.** Stated as a hardware limitation rather than simulated.
- **The public demo chat is canned.** `ops-verse.vercel.app` runs in labelled demo mode and does not call the fine-tuned model. The dashboard at the same site is real and measured.
- **The chunking ablation is time-boxed.** 100 of 594 candidate documents. The scope is printed next to the result.
