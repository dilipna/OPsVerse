"""OpsVerse evaluation library.

Phase 3: retrieval eval sets + IR metrics + mode-ablation harness.
Phase 4 adds RAGAS/DeepEval suites, the judge cache, and CI eval gates.
"""

from opsverse_evals.metrics import (
    contextual_precision_at_k,
    hit_at_k,
    mrr_at_k,
    ndcg_at_k,
    ndcg_at_k_graded,
    precision_at_k,
    recall_at_k,
)
from opsverse_evals.schemas import (
    GradedRetrievalCase,
    GradedRetrievalDataset,
    RetrievalCase,
    RetrievalDataset,
)

__all__ = [
    "GradedRetrievalCase",
    "GradedRetrievalDataset",
    "RetrievalCase",
    "RetrievalDataset",
    "contextual_precision_at_k",
    "hit_at_k",
    "mrr_at_k",
    "ndcg_at_k",
    "ndcg_at_k_graded",
    "precision_at_k",
    "recall_at_k",
]
