# Multi-turn retrieval eval v1 - does a follow-up break retrieval?

Generated 2026-09-03 by `opsverse_evals.multiturn_eval` against the live
`opsverse_kb` collection, hybrid mode (production default). **50 two-turn cases**, each built so turn 2 is elliptical/coreferential and only
resolves given turn 1.

## The gap

`stream_chat` (`libs/rag/chat.py`) sends only the current turn's raw text to the
retriever: `retrieval_query = query`. History reaches the generator's prompt, never
the retriever. Every eval set before this one was single-turn and could not see this.

## Two conditions

- **`turn2_only`** - what production does today: retrieve on the follow-up alone.
- **`concat_history`** - the cheapest plausible fix: retrieve on
  `f"{turn1} {turn2}"`. No architecture change, no query rewriting model.

## Results (mean, 95% bootstrap CI)

| condition | hit@10 | mrr@10 | ndcg@10 |
|---|---|---|---|
| `turn2_only` | 0.680 <sub>[0.540,0.820]</sub> | 0.483 <sub>[0.359,0.614]</sub> | 0.530 <sub>[0.407,0.656]</sub> |
| `concat_history` | 0.600 <sub>[0.460,0.740]</sub> | 0.413 <sub>[0.288,0.544]</sub> | 0.456 <sub>[0.331,0.587]</sub> |

## Does concatenating history actually help? (paired permutation test)

| metric | delta (concat - turn2_only) | 95% CI | p | verdict |
|---|---|---|---|---|
| hit@10 | -0.0800 | [-0.2400, +0.0800] | 0.4482 | not significant |
| mrr@10 | -0.0707 | [-0.2008, +0.0631] | 0.3015 | not significant |
| ndcg@10 | -0.0742 | [-0.1963, +0.0536] | 0.2471 | not significant |

**No significant effect either way at n=50.** The naive concatenation trends lower on average but the gap does not clear the noise floor — this sample size cannot distinguish 'no effect' from 'a small effect'. It does **not** support adopting concatenation as a fix.

## Honest limits

- **Constructed, not observed.** These are LLM-written conversations designed to be
  elliptical, not conversations sampled from real usage (none are logged). They test
  whether the failure mode exists and is measurable, not its frequency in the wild.
- **`concat_history` is a naive baseline**, not a proposed design — this eval tests
  whether the cheapest possible fix works, not what the actual fix should be. If it
  doesn't help, the honest next step is query rewriting (an LLM call that resolves the
  reference before retrieval) or a dedicated conversational encoder.
- Single golden chunk per case (matches `retrieval-v1/v2/v3`'s convention); the
  degeneracy documented in ADR-0018 applies here too — hit@k and mrr@k are what this
  set can say, not recall/precision.
