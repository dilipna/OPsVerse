"""OpsVerse evaluation library.

Phase 3: retrieval eval sets + IR metrics + mode-ablation harness.
Phase 4 adds RAGAS/DeepEval suites, the judge cache, and CI eval gates.
"""

from opsverse_evals.metrics import hit_at_k, mrr_at_k, ndcg_at_k
from opsverse_evals.schemas import RetrievalCase, RetrievalDataset

__all__ = [
    "RetrievalCase",
    "RetrievalDataset",
    "hit_at_k",
    "mrr_at_k",
    "ndcg_at_k",
]
