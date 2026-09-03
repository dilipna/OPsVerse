# ADR-0021: Embedding-model ablation — the incumbent's size isn't earning its cost

**Status:** accepted (2026-09-03)

## Context

The project has used `BAAI/bge-base-en-v1.5` (768-dim, 0.21 GB) since Phase 3 and never
compared it to anything else — "why that embedding model?" had no measured answer, the
same gap ADR-0020 closed for chunk size.

## Decision

Ablate embedding model choice as a **cost/quality question**, not a leaderboard: candidates
span a deliberate size ladder (`bge-small-en-v1.5` 384-dim/0.067 GB → `bge-base-en-v1.5`
768-dim/0.21 GB, the incumbent → `bge-large-en-v1.5` 1024-dim/1.2 GB, ~18x range). Same
chunk text and ids throughout, **dense-only retrieval** (sparse BM25 is identical across
runs and would dilute the variable being measured), scored against the pooled graded
golden set so `recall@10` and `nDCG_graded@10` carry real information (ADR-0018).
Indexing throughput recorded alongside quality — a model that wins by 0.01 nDCG and costs
4x the embedding time is not obviously the right default.

**`bge-large` was dropped from today's run.** At measured throughput on this machine
(~0.7 chunks/s) it would have added ~35 minutes to an already time-boxed sweep, on a day
where two long single-shot jobs had already crashed to session restarts. Scope reduced to
`bge-small` vs `bge-base`; `bge-large` remains a documented next step, not silently
dropped.

## Result

Full report: [embedding-ablation-v1.md](../reports/embedding-ablation-v1.md). 100 golden
queries, 1,500-chunk index (all 1,447 judged chunks + distractors, per the same
bounded-pool convention as ADR-0019).

**No significant difference on any metric.** `bge-small` vs `bge-base`:
`nDCG_graded@10` delta -0.0014 (p=0.94), `recall@10` delta -0.0018 (p=0.93), `mrr@10`
delta +0.047 (p=0.17) — none clear significance.

`bge-small` is **3.1× smaller** than the incumbent and statistically indistinguishable
from it on this corpus. The incumbent's extra size is not measurably buying retrieval
quality here — a real cost/quality finding, not a shrug-worthy null result.

## Consequences

- A second embedding model is now a defensible, cheaper default candidate for this
  domain — not yet switched to (see below), but the case for staying on `bge-base` "by
  default" is now weaker than the case for at least re-evaluating.
- **Not switching yet.** Dense-only, one corpus, n=100 — the honest threshold for a
  production default change is higher than one ablation clears. This is evidence to
  weigh, not a shipped decision.
- `bge-large` is the natural next step once time allows: does the top of the size ladder
  actually buy something the bottom two don't, or does the null result extend all the way
  up?
- Throughput numbers in the report are flagged as measured under non-equivalent load
  (one run contended with a concurrent job, one did not) — stated explicitly rather than
  presented as a clean speed comparison.
