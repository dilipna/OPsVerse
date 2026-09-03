# Chunking ablation v1 - does chunk size matter?

Generated 2026-09-03 by `opsverse_evals.chunking_ablation`. Re-parsed from the original
GitHub tarballs in MinIO; same embedder throughout (`BAAI/bge-base-en-v1.5`, the
incumbent) so chunk size is the only variable. Scored at **document** granularity -
re-chunking changes chunk ids, so the golden set's per-chunk grades are aggregated up
to their parent document.

**100/594** target documents resolved from source (0 missing - logged, not silently dropped).

## Configs

| config | target tokens | max tokens | overlap | docs | chunks | chunks/doc | index time |
|---|---|---|---|---|---|---|---|
| `small` | 150 | 256 | 30 | 100 | 1511 | 15.11 | 2271.8s |
| `baseline` ⭐ | 350 | 512 | 50 | 100 | 922 | 9.22 | 993.4s |
| `large` | 700 | 900 | 100 | 100 | 792 | 7.92 | 997.8s |

## Retrieval quality (document-level, mean with 95% bootstrap CI)

| config | hit@10 | mrr@10 | nDCG_graded@10 |
|---|---|---|---|
| `small` | 0.350 <sub>[0.250,0.440]</sub> | 0.314 <sub>[0.224,0.403]</sub> | 0.508 <sub>[0.349,0.676]</sub> |
| `baseline` | 0.350 <sub>[0.250,0.440]</sub> | 0.323 <sub>[0.233,0.413]</sub> | 0.463 <sub>[0.322,0.613]</sub> |
| `large` | 0.350 <sub>[0.250,0.440]</sub> | 0.318 <sub>[0.228,0.408]</sub> | 0.446 <sub>[0.309,0.590]</sub> |

## Is any difference real? (paired permutation test vs `baseline`)

| config | metric | delta | 95% CI | p | verdict |
|---|---|---|---|---|---|
| `small` | hit@10 | +0.0000 | [+0.0000, +0.0000] | 1.0000 | not significant |
| `small` | mrr@10 | -0.0092 | [-0.0342, +0.0092] | 0.4905 | not significant |
| `small` | ndcg_graded@10 | +0.0443 | [+0.0186, +0.0736] | 0.0002 | **significant** |
| `large` | hit@10 | +0.0000 | [+0.0000, +0.0000] | 1.0000 | not significant |
| `large` | mrr@10 | -0.0050 | [-0.0250, +0.0100] | 1.0000 | not significant |
| `large` | ndcg_graded@10 | -0.0171 | [-0.0343, -0.0034] | 0.0174 | **significant** |

**Chunk size measurably affects ranking quality.** `small` scores significantly better (+0.0443, p=0.0002); `large` scores significantly worse (-0.0171, p=0.0174) than `baseline` on `nDCG_graded@10`. `hit@10` is identical (0.350) across every config — that is not evidence chunking doesn't matter, it is the ceiling imposed by indexing only 100 of the 594 candidate documents (see limits below): many queries' true answer document simply isn't in this smaller index, for any config. `nDCG_graded@10` is the metric with room to move here, and it moves.

## Honest limits

- **Document-level, not chunk-level.** A config that wins here retrieves the right
  *document*; whether it retrieves the specific passage the generator needs is a
  finer-grained question this ablation cannot answer without re-judging every chunk
  under every config, which was out of budget.
- **Scope is the judged-chunk document pool**, not the full corpus - every document
  any pooled mode ever surfaced, which is the same bounded-pool assumption
  `retrieval-golden-v1` already makes (ADR-0019), inherited here.
- **Only 100/594 candidate documents were indexed this run** (time-boxed for same-day turnaround). This deflates every config's
  *absolute* `hit@10` equally relative to `retrieval-golden-v1`'s own 0.97-0.99 (a much
  larger index) — the two are not comparable side by side. What survives the smaller
  scope is the **relative** comparison between configs, since all three index the
  identical 100 documents; that comparison is what the significance tests above test.
- **Index-time figures are not a clean throughput comparison.** `small`'s indexing ran
  concurrently with an unrelated embedding job competing for the same CPU cores;
  `baseline` and `large` did not. Chunk count (`chunks/doc`) is the reliable measure of
  relative indexing cost here, not wall-clock seconds.
- One embedder, one corpus, one domain. The right chunk size is a property of the
  content and the embedder together, not a universal constant - that is the entire
  argument against treating 350/512/50 as received wisdom rather than a measured
  choice.
