# Embedding-model ablation v1 - is a bigger encoder worth it?

Generated 2026-09-03 by `opsverse_evals.embedding_ablation`, scored against the pooled
graded golden set (`retrieval-golden-v1`). **Dense-only retrieval**: BM25 is identical
across runs, so including it would dilute the difference being measured.

Incumbent: **`BAAI/bge-base-en-v1.5`**. Chunk text and ids are unchanged, so this isolates
the embedding function and nothing else.

## Quality and cost together

| model | dim | size | index throughput | nDCG_graded@10 | recall@10 | mrr@10 |
|---|---|---|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | 384 | 0.067 GB | 2 chunks/s | 0.702 <sub>[0.658,0.748]</sub> | 0.781 <sub>[0.728,0.835]</sub> | 0.787 <sub>[0.725,0.850]</sub> |
| `BAAI/bge-base-en-v1.5` ⭐ | 768 | 0.21 GB | 1 chunks/s | 0.703 <sub>[0.653,0.755]</sub> | 0.783 <sub>[0.723,0.843]</sub> | 0.739 <sub>[0.669,0.807]</sub> |

## Is any difference real? (paired permutation test vs `BAAI/bge-base-en-v1.5`)

| model | metric | delta | 95% CI | p | verdict |
|---|---|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | ndcg_graded@10 | -0.0014 | [-0.0379, +0.0363] | 0.9427 | not significant |
| `BAAI/bge-small-en-v1.5` | recall@10 | -0.0018 | [-0.0389, +0.0358] | 0.9289 | not significant |
| `BAAI/bge-small-en-v1.5` | mrr@10 | +0.0472 | [-0.0168, +0.1128] | 0.1736 | not significant |

**No significant difference on any metric.** `BAAI/bge-small-en-v1.5` is 3.1x smaller than the incumbent and statistically indistinguishable from it on this corpus - the extra size is not measurably buying retrieval quality here. That is a real cost/quality finding, not a null result to shrug off: it means the incumbent's size was never actually earning its cost on this domain.

## Honest limits

- **Dense-only.** The shipped system runs hybrid; these numbers are not the
  end-to-end quality of the product, they are the contribution of the encoder.
- **One corpus, one domain.** DevOps/MLOps documentation. Nothing here generalises
  to a different corpus, and MTEB rankings are not a substitute for measuring on
  your own data - which is the entire point of running this.
- **Indexing throughput is CPU-bound on this machine** and will differ on other
  hardware; treat it as a relative cost signal, not an absolute.
- **The two throughput numbers above were not measured under equivalent load** — one
  model's run overlapped an unrelated concurrent job competing for the same CPU cores,
  the other ran alone. The gap between them is not a clean speed comparison; what does
  hold directionally is the expected relationship (more dimensions costs more compute
  per chunk), consistent with both runs despite the confound.
- n = 100 queries; gaps inside the CIs are not resolvable at this size.
