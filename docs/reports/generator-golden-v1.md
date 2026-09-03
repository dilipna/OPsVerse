# Generator golden eval v1 - contextual recall

Generated 2026-09-03 by `opsverse_evals.generator_eval` (judge: `gemini/gemini-3.1-flash-lite`).
**100 queries, 412 atomic claims** (mean 4.12/query) from `evalsets/golden-answers-v1.jsonl`.

## What this measures, that nothing else did

`contextual_recall` = share of the reference answer's atomic claims that a mode's
retrieved context actually **supports**. It answers *"was what we retrieved enough to
produce the right answer?"*

- `hit@10` asks only whether the seed chunk was found, and is **saturated** at
  0.97-0.99 on this corpus ([ADR-0019](../adr/0019-golden-set-pooled-graded-relevance.md)).
- `faithfulness` (in `rag_suite`) is **reference-free**: it asks whether the answer
  matches the retrieved context, so a system that retrieves little and answers
  narrowly scores *well*. Contextual recall is what catches that.

## Results (mean with 95% bootstrap CI)

| mode | contextual recall |
|---|---|
| dense | **0.839** <sub>[0.777, 0.900]</sub> (n=100) |
| sparse | **0.899** <sub>[0.852, 0.940]</sub> (n=100) |
| hybrid | **0.902** <sub>[0.853, 0.944]</sub> (n=100) |
| hybrid+rerank | **0.921** <sub>[0.879, 0.960]</sub> (n=100) |

## Is any gap real? (paired permutation test vs `hybrid`)

| comparison | delta | 95% CI | p | verdict |
|---|---|---|---|---|
| dense_vs_hybrid | -0.0626 | [-0.1211, -0.0006] | 0.0484 | **significant** |
| sparse_vs_hybrid | -0.0027 | [-0.0410, +0.0396] | 0.9022 | not significant |
| hybrid+rerank_vs_hybrid | +0.0195 | [-0.0321, +0.0750] | 0.4651 | not significant |

## Honest limits

- **The reference answers are LLM-written, not human-authored.** They are independent
  of every retrieval mode (grounded in the pooled *judged-relevant* chunks, not in any
  system's output), which is what makes the comparison fair - but that is not the same
  as human ground truth. A human-authored reference set is the next step and is not
  claimed here.
- **The claim-support judge is the same model family that wrote the claims.** Shared
  blind spots are possible. A different judge model would be a cheap, worthwhile check.
- Claims are graded against the **top-10** retrieved context only, matching what the
  generator would actually see.
- n = 100 queries. Gaps inside the CIs are not resolvable at this size.
