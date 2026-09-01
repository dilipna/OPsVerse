import json
from pathlib import Path

import pytest

from opsverse_evals.golden_eval import degeneracy_still_holds
from opsverse_evals.golden_set import build_pools, load_chunk_text
from opsverse_evals.metrics import ndcg_at_k_graded
from opsverse_evals.schemas import GradedRetrievalCase, GradedRetrievalDataset


def test_build_pools_unions_modes_and_preserves_first_seen_order(tmp_path: Path):
    raw = {
        "k": 10,
        "results": {
            "dense": [{"case_id": "q1", "retrieved_chunk_ids": ["a", "b"]}],
            "sparse": [{"case_id": "q1", "retrieved_chunk_ids": ["b", "c"]}],
            "hybrid": [{"case_id": "q1", "retrieved_chunk_ids": ["c", "d"]}],
        },
    }
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    pools, contributors = build_pools(path)
    # union, deduplicated -- this is the point of pooling
    assert pools["q1"] == ["a", "b", "c", "d"]
    assert contributors["q1"] == ["dense", "sparse", "hybrid"]


def test_build_pools_is_larger_than_any_single_mode(tmp_path: Path):
    raw = {
        "k": 10,
        "results": {
            "dense": [{"case_id": "q1", "retrieved_chunk_ids": ["a", "b"]}],
            "sparse": [{"case_id": "q1", "retrieved_chunk_ids": ["x", "y"]}],
        },
    }
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    pools, _ = build_pools(path)
    assert len(pools["q1"]) == 4 > 2


def test_load_chunk_text(tmp_path: Path):
    corpus = tmp_path / "chunks.jsonl"
    corpus.write_text(
        '{"id": "a", "text": "alpha"}\n\n{"id": "b", "text": "beta"}\n',
        encoding="utf-8",
    )
    assert load_chunk_text(corpus) == {"a": "alpha", "b": "beta"}


def test_relevant_ids_respects_threshold():
    case = GradedRetrievalCase(id="q1", question="q", grades={"a": 3, "b": 2, "c": 1, "d": 0})
    assert case.relevant_ids(2) == {"a", "b"}
    assert case.relevant_ids(3) == {"a"}
    assert case.relevant_ids(1) == {"a", "b", "c"}


def test_graded_ndcg_separates_full_answer_from_on_topic():
    grades = {"full": 3, "partial": 2, "ontopic": 1, "junk": 0}
    best = ndcg_at_k_graded(["full", "partial", "ontopic", "junk"], grades, 4)
    worst = ndcg_at_k_graded(["junk", "ontopic", "partial", "full"], grades, 4)
    assert best == pytest.approx(1.0)
    assert worst < best
    # binary relevance would score these two orderings identically at k=4;
    # graded gain is exactly what breaks the tie
    assert best - worst > 0.2


def test_degeneracy_check_reports_independence():
    """The golden-set check must FAIL the identity that single-label sets satisfy."""
    degenerate = {
        "m": {
            "recall@10": [1.0, 0.0],
            "hit@10": [1.0, 0.0],
            "ctx_precision@10": [0.5, 0.0],
            "mrr@10": [0.5, 0.0],
        }
    }
    assert degeneracy_still_holds(degenerate)["still_degenerate"] is True

    independent = {
        "m": {
            "recall@10": [0.5, 0.0],  # found 1 of 2 relevant -> differs from hit
            "hit@10": [1.0, 0.0],
            "ctx_precision@10": [0.5, 0.0],
            "mrr@10": [1.0, 0.0],
        }
    }
    result = degeneracy_still_holds(independent)
    assert result["still_degenerate"] is False
    assert result["recall_vs_hit_max_gap"] == pytest.approx(0.5)


def test_graded_dataset_jsonl_roundtrip(tmp_path: Path):
    ds = GradedRetrievalDataset(
        name="retrieval-golden-test",
        version="1",
        judge_model="gemini/test",
        cases=[
            GradedRetrievalCase(
                id="q1",
                question="how do I scale pods?",
                grades={"a": 3, "b": 0},
                pool_size=2,
                pool_contributors=["dense", "sparse"],
                seed_chunk_id="a",
                seed_grade=3,
            )
        ],
    )
    path = tmp_path / "golden.jsonl"
    ds.save_jsonl(path)
    loaded = GradedRetrievalDataset.load_jsonl(path)
    assert loaded.name == ds.name
    assert loaded.judge_model == "gemini/test"
    assert len(loaded.cases) == 1
    assert loaded.cases[0].grades == {"a": 3, "b": 0}
    assert loaded.cases[0].seed_grade == 3
    assert loaded.cases[0].relevant_ids() == {"a"}
