# Evidence index — how to read this repository

Generated 2026-09-07 by `opsverse_evals.overturns` from the committed
`docs/reports/*-summary.json`. Every number below is plucked from those files, so
this page cannot drift away from the reports it summarises. No network, no stack.

> **The short version.** The stack here — hybrid RAG, a QLoRA fine-tune, a served
> model, an eval harness — is not unusual. What is unusual is the record below:
> **eight claims this project believed, tested, and had to withdraw**, each
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

**It misses about half the relevant material. Seed recovery was the easy question.**

Audited on a blinded, stratified sample. Against a second *model* rater (n=190) the judge looked systematically strict: signed error +0.327 [+0.226, +0.430], precision 0.968 against TPR 0.571. A **human** rater then labelled 40 of the same tasks and reproduced the direction and the capability number -- TPR 0.556 -- but not the magnitude: signed error +0.226 [-0.076, +0.571], which **spans zero**. Head to head the human grades 0.28 of a grade lower than the model (-0.279, excluding zero): the model rater was the lenient one, and its leniency inflated the offset.

*What changed:* Absolute recall/nDCG on the golden set read low, and the bias is near-equal across all four retrieval modes, so the published comparisons stand — the levels move, the deltas do not. Then the human labels overturned part of the overturn: the second-model rater had exaggerated the size of the offset, so the direction survives and the magnitude is back to being an open question.

Evidence: [judge-validation-v1](reports/judge-validation-v1.md) · [judge-validation-v2](reports/judge-validation-v2.md) · [ADR-0022](adr/0022-judge-validation-against-a-second-rater.md)

### 8. A low `recall@10` on the golden set means retrieval is failing.

**Most of what the metric flags is not a defect at all.**

An over-inclusive signal flagged 28 of 100 queries as retrieval failures. Reading every one of them: **23 are not defects** (82%) and only **5** are -- 5% of queries, not the 28% the flag rate implied. The largest category (18 cases) is queries where a grade-3 answer sits at rank 1-3 and `recall@10` still scores them down because the corpus offers many acceptable answers per question. Coded by `claude-opus-5`, a language model, not a person.

*What changed:* The fix list changed completely. Nothing on it is motivated by raising `recall@10`, because most of what would raise that number would not help a user. What the aggregate had been hiding was its own composition: corpus redundancy and a metric penalising queries that were answered at rank 1.

Evidence: [failure-taxonomy-v1](reports/failure-taxonomy-v1.md) · [ADR-0020](adr/0020-chunking-and-multiturn-ablations.md)

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

**7. The write-ups** — `https://dilipna.hashnode.dev`  
Three published posts: the eval harness that stopped two wrong decisions, RAG security measured like a classifier, and continuous batching on a free T4. Source copies in `docs/blog/`.

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
