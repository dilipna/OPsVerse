# Retrieval metrics audit v1 - which metrics are independent?

Generated 2026-09-01 by `opsverse_evals.metrics_audit` from the committed
`retrieval-ablation-v*-raw.json`. No Qdrant, no network: reproducible from the repo.

## Why this exists

`precision@k`, `recall@k` and contextual precision are standard RAG-evaluation
metrics and they are now implemented in `opsverse_evals.metrics`. But adding them
to these eval sets would **not** have added information, and reporting them as if
it had would be the same mistake this project caught in ablation v2 - a number that
looks like evidence and isn't.

Every question in `retrieval-v1/v2/v3` is generated from exactly one chunk, so each
query has exactly **one** gold label. Under that condition:

```
recall@k               == hit@k       (1 relevant item: you find it or you don't)
precision@k            == hit@k / k   (at most one hit in the numerator)
contextual_precision@k == mrr@k       (AP over a single relevant item = 1/rank)
```

The tables below verify this **per case**, not on the aggregate - the aggregate could
hide compensating errors.

## `retrieval-v1` (v1) - 100 queries, k=10

Gold labels per query: **[1]** (single-label)

| mode | hit@10 | recall@10 | precision@10 | mrr@10 | ctx_precision@10 | max deviation |
|---|---|---|---|---|---|---|
| dense | 0.8600 | 0.8600 | 0.0860 | 0.6356 | 0.6356 | 0.00e+00 |
| sparse | 0.8400 | 0.8400 | 0.0840 | 0.6050 | 0.6050 | 0.00e+00 |
| hybrid | 0.8600 | 0.8600 | 0.0860 | 0.6432 | 0.6432 | 0.00e+00 |
| hybrid+rerank | 0.9000 | 0.9000 | 0.0900 | 0.6115 | 0.6115 | 0.00e+00 |

**Result: identities hold exactly across every case.**

## `retrieval-v2` (v2) - 100 queries, k=10

Gold labels per query: **[1]** (single-label)

| mode | hit@10 | recall@10 | precision@10 | mrr@10 | ctx_precision@10 | max deviation |
|---|---|---|---|---|---|---|
| dense | 0.8300 | 0.8300 | 0.0830 | 0.5535 | 0.5535 | 0.00e+00 |
| sparse | 0.9700 | 0.9700 | 0.0970 | 0.7594 | 0.7594 | 0.00e+00 |
| hybrid | 0.9700 | 0.9700 | 0.0970 | 0.7049 | 0.7049 | 0.00e+00 |
| hybrid+rerank | 0.9600 | 0.9600 | 0.0960 | 0.7450 | 0.7450 | 0.00e+00 |

**Result: identities hold exactly across every case.**

## `retrieval-v3` (v3) - 100 queries, k=10

Gold labels per query: **[1]** (single-label)

| mode | hit@10 | recall@10 | precision@10 | mrr@10 | ctx_precision@10 | max deviation |
|---|---|---|---|---|---|---|
| dense | 0.7700 | 0.7700 | 0.0770 | 0.5703 | 0.5703 | 0.00e+00 |
| sparse | 0.8800 | 0.8800 | 0.0880 | 0.6105 | 0.6105 | 0.00e+00 |
| hybrid | 0.9000 | 0.9000 | 0.0900 | 0.6555 | 0.6555 | 0.00e+00 |
| hybrid+rerank | 0.9000 | 0.9000 | 0.0900 | 0.6445 | 0.6445 | 0.00e+00 |

**Result: identities hold exactly across every case.**

## What this means

- `recall@10` and `hit@10` are the *same column twice*. `precision@10` is `hit@10/10`.
  Quoting all three as separate evidence would inflate an evaluation suite without
  strengthening it.
- The metrics are implemented, tested and correct **for the general multi-label case**
  (`libs/evals/tests/test_metrics_and_schemas.py` pins both the identities and the
  point at which they break). They are ready for an eval set that earns them.
- To make them independent, relevance judgements must be **graded over the retrieved
  candidates**, not inherited from the generating chunk - that is a labelling problem,
  not a metrics problem, and it is the honest next step.

## What was *not* done, and why

**Contextual recall was not implemented.** Its definition requires a ground-truth
answer to attribute claims against, and this project has no reference answers: the
faithfulness judge in `rag_suite.py` is deliberately *reference-free*, grading each
claim against the retrieved context. Adding contextual recall means first writing gold
answers - real work with a real cost, not a metric to switch on.
