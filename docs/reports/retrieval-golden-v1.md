# Golden retrieval set v1 - pooled, graded, with uncertainty

Generated 2026-09-01 by `opsverse_evals.golden_eval`. Labels from `evalsets/retrieval-golden-v1.jsonl` (judge: `gemini/gemini-3.1-flash-lite`); ranked lists re-scored from the committed ablation raw JSON, so this compares *labels*, not runs.

## What changed versus the shipped eval sets

`retrieval-v1/v2/v3` give each question one gold label - the chunk it was generated
from. [ADR-0018](../adr/0018-retrieval-metrics-independence-audit.md) showed that
makes `recall@k` = `hit@k`, `precision@k` = `hit@k/k` and contextual precision =
`mrr@k`. This set replaces those labels with **pooled, graded** judgements:

- **Pooling (TREC-style):** candidates pooled from dense + sparse + hybrid +
  hybrid+rerank, deduplicated - **mean pool 19.14 candidates/query**
  versus 10 if only one system were judged. No mode is scored solely on what it
  itself retrieved.
- **Graded 0-3** (TREC convention), so nDCG can separate a full answer from an
  on-topic near-miss.
- **Position-randomised**: candidate order shuffled per query with a deterministic
  seed, so the judge cannot inherit any system's ranking.

## The labels

- **100 queries**, relevance threshold **grade >= 2**
- Relevant chunks per query: mean **3.03**, range 1-13
- **70/100** queries have more than one relevant
  chunk (the whole point); 0 have none
- Grade histogram (all judgements): `{0: 773, 1: 838, 2: 122, 3: 181}`
- **Seed recovery 100%** - share of originating chunks the judge independently graded >=2. A judge-sanity check: the question was written *from* that chunk, so a low rate would mean the judge, not the retriever, is the problem.

## Did the degeneracy actually break?

Re-running the ADR-0018 identity check against these labels - here a **failure is the
desired result**, because it means the metrics now measure different things:

- `max |recall@10 - hit@10|` = **0.8750**
- `max |ctx_precision@10 - mrr@10|` = **0.7571**

**Still degenerate: False** -- the metrics are now independent.

## Results (mean with 95% bootstrap CI, 2000 resamples)

| mode | hit@10 | recall@10 | precision@10 | mrr@10 | ctx_prec@10 | nDCG_graded@10 |
|---|---|---|---|---|---|---|
| dense | 0.970 <sub>[0.940,1.000]</sub> | 0.783 <sub>[0.723,0.843]</sub> | 0.207 <sub>[0.179,0.236]</sub> | 0.739 <sub>[0.669,0.807]</sub> | 0.597 <sub>[0.527,0.666]</sub> | 0.703 <sub>[0.653,0.755]</sub> |
| sparse | 0.990 <sub>[0.970,1.000]</sub> | 0.868 <sub>[0.824,0.910]</sub> | 0.231 <sub>[0.203,0.263]</sub> | 0.867 <sub>[0.817,0.917]</sub> | 0.712 <sub>[0.659,0.768]</sub> | 0.831 <sub>[0.797,0.866]</sub> |
| hybrid | 0.990 <sub>[0.970,1.000]</sub> | 0.887 <sub>[0.848,0.925]</sub> | 0.241 <sub>[0.214,0.269]</sub> | 0.853 <sub>[0.801,0.908]</sub> | 0.712 <sub>[0.659,0.769]</sub> | 0.824 <sub>[0.788,0.860]</sub> |
| hybrid+rerank | 0.990 <sub>[0.970,1.000]</sub> | 0.869 <sub>[0.825,0.911]</sub> | 0.236 <sub>[0.206,0.268]</sub> | 0.900 <sub>[0.849,0.945]</sub> | 0.723 <sub>[0.667,0.781]</sub> | 0.831 <sub>[0.794,0.867]</sub> |

## Is any gap real? (paired permutation test vs `hybrid`, 10k permutations)

Paired by query, because per-query difficulty dominates the variance. `p < 0.05`
two-sided is called significant; anything else is reported as **not** distinguishable
at this sample size rather than quietly ranked.

| comparison | metric | delta | 95% CI | p | verdict |
|---|---|---|---|---|---|
| dense_vs_hybrid | ctx_precision@10 | -0.1144 | [-0.1592, -0.0741] | 0.0001 | **significant** |
| dense_vs_hybrid | hit@10 | -0.0200 | [-0.0500, +0.0000] | 0.5000 | not significant |
| dense_vs_hybrid | mrr@10 | -0.1138 | [-0.1648, -0.0656] | 0.0001 | **significant** |
| dense_vs_hybrid | ndcg_graded@10 | -0.1202 | [-0.1584, -0.0846] | 0.0001 | **significant** |
| dense_vs_hybrid | precision@10 | -0.0340 | [-0.0520, -0.0150] | 0.0004 | **significant** |
| dense_vs_hybrid | recall@10 | -0.1039 | [-0.1529, -0.0572] | 0.0001 | **significant** |
| sparse_vs_hybrid | ctx_precision@10 | +0.0009 | [-0.0388, +0.0402] | 0.9692 | not significant |
| sparse_vs_hybrid | hit@10 | +0.0000 | [-0.0300, +0.0300] | 1.0000 | not significant |
| sparse_vs_hybrid | mrr@10 | +0.0137 | [-0.0287, +0.0539] | 0.5019 | not significant |
| sparse_vs_hybrid | ndcg_graded@10 | +0.0076 | [-0.0182, +0.0340] | 0.5731 | not significant |
| sparse_vs_hybrid | precision@10 | -0.0100 | [-0.0290, +0.0090] | 0.3626 | not significant |
| sparse_vs_hybrid | recall@10 | -0.0191 | [-0.0631, +0.0270] | 0.3982 | not significant |
| hybrid+rerank_vs_hybrid | ctx_precision@10 | +0.0119 | [-0.0430, +0.0664] | 0.6789 | not significant |
| hybrid+rerank_vs_hybrid | hit@10 | +0.0000 | [-0.0300, +0.0300] | 1.0000 | not significant |
| hybrid+rerank_vs_hybrid | mrr@10 | +0.0466 | [-0.0185, +0.1068] | 0.1529 | not significant |
| hybrid+rerank_vs_hybrid | ndcg_graded@10 | +0.0071 | [-0.0351, +0.0482] | 0.7505 | not significant |
| hybrid+rerank_vs_hybrid | precision@10 | -0.0050 | [-0.0240, +0.0140] | 0.6816 | not significant |
| hybrid+rerank_vs_hybrid | recall@10 | -0.0176 | [-0.0624, +0.0255] | 0.4488 | not significant |

## Honest limits

- **The judge is a single LLM.** These are LLM-graded relevance labels, not human
  ones. Seed recovery is a sanity check on the judge, not a substitute for human
  agreement; a second-annotator study is the next step, not a claim made here.
- **The pool is bounded by what the four modes retrieved.** A chunk no mode surfaced
  in its top-10 is unjudged and counts as irrelevant. That is the standard pooling
  assumption and it inflates recall for every system equally.
- **n = 100 queries.** The CIs are the honest width of that; several gaps
  below are not resolvable at this n, and are labelled so.
- Re-scored from committed ranked lists, so this isolates the effect of *labels*.
  It is not a fresh retrieval run.
