# ADR-0019: A pooled, graded golden set — and testing whether retrieval gaps are real

**Status:** accepted (2026-08-31)

## Context

[ADR-0018](0018-retrieval-metrics-independence-audit.md) established that on
`retrieval-v1/v2/v3` the metrics `recall@k`, `precision@k` and contextual precision
were algebraic restatements of `hit@k` and `mrr@k`, because every question carries
exactly one gold label — the chunk it was generated from. It costed the fix:
relevance must be **judged over a pooled candidate set**, not inherited from the
generating chunk.

A second, independent weakness was visible in every prior ablation report: the
numbers had **no uncertainty and no significance test**. `sparse 0.759` versus
`hybrid 0.705` was reported as a result, but nothing established the gap was larger
than run-to-run noise. The inference side had already learned this lesson —
[ADR-0017](0017-slo-constrained-goodput-as-the-capacity-metric.md) measured a ±22%
spread between two identical vLLM runs — and the retrieval side had not applied it.

## Decision

Build `retrieval-golden-v1` and report retrieval with uncertainty.

**1. Pooling (TREC-style).** Candidates are pooled from all four modes (dense,
sparse, hybrid, hybrid+rerank), deduplicated, and judged together — mean **19.1
candidates/query** versus 10 if a single system were judged. Judging one system's
top-k only ever labels what that system already found, which flatters its recall and
makes every other system look worse by construction.

**2. Graded relevance, 0–3.** TREC convention (3 fully answers / 2 substantially
relevant / 1 on-topic / 0 irrelevant). Binary labels cannot distinguish "retrieved
the chunk that fully answers" from "retrieved something on the right topic";
`ndcg_at_k_graded` with exponential gain can.

**3. Position-randomised judging.** Candidate order is shuffled per query with a
deterministic seed before being shown to the judge, so no system's ranking leaks
into the labels and the run stays reproducible.

**4. Uncertainty and significance are mandatory.** Every mean carries a 95%
percentile bootstrap CI (2000 resamples). Every mode-vs-baseline gap carries a
**paired permutation test** (10k permutations), paired by query because per-query
difficulty is the dominant variance component. `stats.paired_permutation_test`
raises on unequal-length inputs so an unpaired comparison cannot happen by accident.

**5. Seed recovery as a judge sanity check.** Each question was written *from* a
specific chunk, so that chunk should grade ≥2. Measured: **100/100 (100%)**. A low
rate would have meant the judge, not the retriever, was the problem.

## What it found

Full report: [`retrieval-golden-v1.md`](../reports/retrieval-golden-v1.md).
100 queries, 1,914 judgements, mean 3.03 relevant chunks/query, **70/100 queries
multi-label**, 0 queries left with no relevant chunk.

**The degeneracy broke, as intended.** Re-running the ADR-0018 identity check
against these labels: `max |recall@10 − hit@10| = 0.875`,
`max |ctx_precision@10 − mrr@10| = 0.757`. The metrics now measure different things.

**`hit@10` is saturated and can no longer discriminate.** All four modes score
0.97–0.99, and *no* pairwise `hit@10` difference is significant (p = 0.50–1.00).
The metric most prominent in the earlier ablation reports has no remaining power on
this corpus; `ndcg_graded@10` and `recall@10` separate the modes, `hit@10` does not.

**Dense is genuinely worse than hybrid** — significant on five of six metrics
(nDCG −0.120, recall −0.104, mrr −0.114, all p ≈ 0.0001), and *not* significant on
the one saturated metric. A consistent, believable result.

**Sparse versus hybrid is not distinguishable at n=100.** No metric reaches
significance (nDCG +0.008, p = 0.57; recall −0.019, p = 0.40). This is the third and
final chapter of a story the project has been telling since ablation v2: sparse
"won" on the raw v2 set (0.759 vs 0.705 MRR), v3 showed that win was vocabulary
leakage from LLM-written questions, and now — with pooled, graded labels and a
significance test — the two are statistically tied. The honest summary is not
"hybrid wins" but **"hybrid and sparse are indistinguishable here, and dense is
worse."**

**The reranker does not measurably help.** `hybrid+rerank` vs `hybrid` is not
significant on any metric (best case mrr +0.047, p = 0.15). Rerank was already off
by default on cost grounds; that default now has a significance test behind it
rather than a single measured delta.

## Consequences

- Retrieval reporting gains real metrics (`recall`, `precision`, graded nDCG) that
  say something `hit@k`/`mrr@k` did not, plus intervals and p-values.
- Two previously-reported "wins" are downgraded to ties. That is the intended
  behaviour of adding a significance test, and it is the second time this project's
  own evaluation has contradicted its earlier conclusion.
- **The judge is a single LLM, not a human panel.** Seed recovery is a sanity check,
  not inter-annotator agreement. A second-annotator study is the next step and is
  *not* claimed here.
- **The pool is bounded by what the four modes retrieved.** A chunk no mode surfaced
  is unjudged and counts as irrelevant — the standard pooling assumption, which
  inflates recall equally for all systems.
- n=100. Several gaps are simply not resolvable at that size, and are reported as
  such rather than ranked anyway.
- The old ablation reports are **not** rewritten. They remain accurate for the
  labels they used; this ADR and the golden report record what changed and why.
