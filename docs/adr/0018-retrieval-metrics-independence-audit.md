# ADR-0018: Implement precision/recall/contextual-precision, but report only what is independent

**Status:** accepted (2026-08-31)

## Context

`precision@k`, `recall@k`, "contextual precision" and "contextual recall" are the
metrics most RAG-evaluation writing (and most RAGAS/DeepEval tutorials) puts at the
centre. This project reports `hit@k`, `mrr@k` and `ndcg@k` for retrieval, and a
judged faithfulness / answer-relevance / citation-use triple for generation. The
obvious move was to add the missing names to `opsverse_evals.metrics` and put them
in the ablation reports — broader coverage, more standard vocabulary.

Before doing that, the arithmetic was checked against the actual eval sets.

**Every question in `retrieval-v1/v2/v3` is generated from exactly one chunk**
(`generate_retrieval_set.py`), so every query carries exactly **one** gold label.
Verified: all 300 cases across the three sets have `len(relevant_chunk_ids) == 1`.

Under that condition three of the four candidates are not new measurements:

```
recall@k               == hit@k        one relevant item: it is found or it is not
precision@k            == hit@k / k    at most one hit can appear in the numerator
contextual_precision@k == mrr@k        average precision over one item = 1/rank
```

This is the same failure mode the v2→v3 paraphrase work caught
([ablation v3](../reports/retrieval-ablation-v3.md)): a number that *looks* like
independent evidence but is an artefact of how the eval set was built. There, sparse
retrieval "won" because LLM-written questions reused the gold chunk's vocabulary; here,
three metrics would "agree" because they are the same quantity rescaled. Reporting a five-metric
table where three columns are deterministic functions of a fourth would inflate the
apparent rigour of the suite while adding nothing, and it would not survive the
question *"what did recall@10 tell you that hit@10 didn't?"*

## Decision

**Implement the metrics; do not report the degenerate ones as findings.**

1. `precision_at_k`, `recall_at_k` and `contextual_precision_at_k` are implemented in
   `opsverse_evals.metrics`, correct for the **general multi-label case**, and unit
   tested. They are not wrong and not unused — they are ready for an eval set that
   earns them.
2. The degeneracy is pinned as **executable assertions**
   (`test_single_label_degeneracies_are_real`), which also assert the point at which
   the identities break (two gold labels straddling the cut-off). The property cannot
   silently rot.
3. A dedicated audit, `opsverse_evals.metrics_audit`, recomputes all five metrics
   per case from the committed `retrieval-ablation-v*-raw.json` and verifies the
   identities to a `1e-12` tolerance. Output:
   [`docs/reports/retrieval-metrics-audit-v1.md`](../reports/retrieval-metrics-audit-v1.md).
   Measured deviation across all 300 cases × 4 modes × 4 values of k: **exactly 0.0**.
   The audit needs no Qdrant, no API and no network — it is reproducible from a
   clone.
4. The ablation reports keep reporting `hit@k` / `mrr@k` / `ndcg@k`. No column is
   added that a reader could mistake for independent evidence.

**Contextual recall is deliberately not implemented.** Its definition requires a
ground-truth answer to attribute claims against. This project has none: the
faithfulness judge in `rag_suite.py` is *reference-free* by design, grading each
claim against the retrieved context rather than a reference. Implementing contextual
recall means first authoring gold answers — a labelling cost, not a metric toggle.
Claiming the metric without that work would be the same error in the generation half
of the pipeline.

This is consistent with [ADR-0006](0006-prompt-variant-testing-without-promptfoo.md):
the objection was never to RAGAS's *metrics*, it was to importing a framework whose
numbers you cannot interrogate. Implementing the metric and then proving what it does
and does not measure on your own data is the position that ADR implies.

## Consequences

- The evaluation suite gains three correct, tested metric implementations and **zero**
  new reported numbers. That asymmetry is the point.
- There is now a written, reproducible answer to "why doesn't your RAG eval report
  precision/recall?" — with a report backing it — instead of the absence looking like
  an oversight.
- The path to making them independent is identified and costed: relevance must be
  **graded over the retrieved candidates** (judge-labelled, multi-label), not
  inherited from the chunk the question was generated from. That is a labelling
  problem and the honest next step.
- Risk accepted: a reader skimming for metric names will not find `recall@k` in the
  ablation tables. The audit report exists so that skim resolves to a decision rather
  than a gap.
