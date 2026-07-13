"""Binary-relevance IR metrics over a ranked list of retrieved ids."""

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
