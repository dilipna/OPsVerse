"""Binary-relevance IR metrics over a ranked list of retrieved ids.

**Read this before quoting these metrics.** Several of them carry information
only when a query has more than one relevant item. On a single-gold-label set
(one question generated from one chunk — `retrieval-v1/v2/v3`) they degenerate:

| metric | with `len(relevant) == 1` |
|---|---|
| `recall_at_k`              | identical to `hit_at_k` |
| `precision_at_k`           | `hit_at_k / k` |
| `contextual_precision_at_k`| identical to `mrr_at_k` |

Reporting all of them on such a set looks like breadth but is arithmetic
restatement of `hit_at_k`. `tests/test_metrics.py` pins these identities as
executable assertions so the degeneracy cannot be quietly forgotten. Use the
multi-label set (`relevance_at_k` graded labels) when you want these to mean
something independent.
"""

import math
from collections.abc import Sequence


def hit_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    return 1.0 if any(rid in relevant for rid in ranked[:k]) else 0.0


def mrr_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    for pos, rid in enumerate(ranked[:k], 1):
        if rid in relevant:
            return 1.0 / pos
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(pos + 1) for pos, rid in enumerate(ranked[:k], 1) if rid in relevant)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(pos + 1) for pos in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of the top-k that is relevant.

    Denominator is `k`, not `len(ranked[:k])`: a retriever that returns fewer
    than k candidates is not rewarded for its own short list.
    """
    if k <= 0:
        return 0.0
    return sum(1 for rid in ranked[:k] if rid in relevant) / k


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of all relevant items recovered in the top-k."""
    if not relevant:
        return 0.0
    return sum(1 for rid in ranked[:k] if rid in relevant) / len(relevant)


def contextual_precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Average precision @k — rank-aware: relevant items ranked higher score more.

    This is the metric RAGAS calls "contextual precision". It answers "are the
    relevant chunks near the top?" rather than "are they present at all", which
    matters for RAG because the generator attends to early context most.

    Normalized by `min(len(relevant), k)` so a perfect ranking scores 1.0 even
    when there are more relevant items than slots.
    """
    if not relevant or k <= 0:
        return 0.0
    hits = 0
    running = 0.0
    for pos, rid in enumerate(ranked[:k], 1):
        if rid in relevant:
            hits += 1
            running += hits / pos
    denom = min(len(relevant), k)
    return running / denom if denom else 0.0


def dcg_graded(ranked: Sequence[str], grades: dict[str, int], k: int) -> float:
    """Exponential-gain DCG: gain = 2**grade - 1, discount = 1/log2(rank+1)."""
    return sum(
        (2 ** grades.get(rid, 0) - 1) / math.log2(pos + 1) for pos, rid in enumerate(ranked[:k], 1)
    )


def ndcg_at_k_graded(ranked: Sequence[str], grades: dict[str, int], k: int) -> float:
    """nDCG over *graded* relevance (0..3), not binary.

    Binary `ndcg_at_k` cannot distinguish "retrieved the perfect chunk" from
    "retrieved a marginally on-topic one". With graded labels the exponential
    gain makes a grade-3 hit worth 7 and a grade-1 hit worth 1, so ranking a
    partial answer above a full one is penalised.

    The ideal ranking is taken over the *judged pool*, so a system is measured
    against the best achievable ordering of what was actually labelled.
    """
    if k <= 0 or not grades:
        return 0.0
    dcg = dcg_graded(ranked, grades, k)
    ideal = sorted(grades.values(), reverse=True)[:k]
    idcg = sum((2**g - 1) / math.log2(pos + 1) for pos, g in enumerate(ideal, 1))
    return dcg / idcg if idcg > 0 else 0.0
