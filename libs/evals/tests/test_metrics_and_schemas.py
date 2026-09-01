from pathlib import Path

from opsverse_evals import (
    RetrievalCase,
    RetrievalDataset,
    contextual_precision_at_k,
    hit_at_k,
    mrr_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from opsverse_evals.judge import parse_json_reply

RANKED = ["a", "b", "c", "d"]


def test_hit_at_k():
    assert hit_at_k(RANKED, {"c"}, 3) == 1.0
    assert hit_at_k(RANKED, {"c"}, 2) == 0.0
    assert hit_at_k([], {"c"}, 5) == 0.0


def test_mrr_at_k():
    assert mrr_at_k(RANKED, {"a"}, 10) == 1.0
    assert mrr_at_k(RANKED, {"c"}, 10) == 1 / 3
    assert mrr_at_k(RANKED, {"z"}, 10) == 0.0
    # relevant item beyond k gets no credit
    assert mrr_at_k(RANKED, {"d"}, 3) == 0.0


def test_ndcg_at_k():
    # single relevant item at rank 1 -> perfect
    assert ndcg_at_k(RANKED, {"a"}, 10) == 1.0
    # at rank 2: dcg = 1/log2(3), idcg = 1/log2(2) = 1
    import math

    assert ndcg_at_k(RANKED, {"b"}, 10) == 1 / math.log2(3)
    assert ndcg_at_k(RANKED, {"z"}, 10) == 0.0
    assert ndcg_at_k([], set(), 10) == 0.0


def test_precision_at_k():
    assert precision_at_k(RANKED, {"a", "b"}, 2) == 1.0
    assert precision_at_k(RANKED, {"a"}, 4) == 0.25
    assert precision_at_k(RANKED, {"z"}, 4) == 0.0
    # denominator is k, not len(ranked): a short candidate list is not rewarded
    assert precision_at_k(["a"], {"a"}, 4) == 0.25
    assert precision_at_k(RANKED, {"a"}, 0) == 0.0


def test_recall_at_k():
    assert recall_at_k(RANKED, {"a", "b"}, 2) == 1.0
    assert recall_at_k(RANKED, {"a", "d"}, 2) == 0.5
    assert recall_at_k(RANKED, {"z"}, 10) == 0.0
    # no relevant items defined -> 0.0, never a ZeroDivisionError
    assert recall_at_k(RANKED, set(), 4) == 0.0


def test_contextual_precision_at_k_is_rank_aware():
    # same recall, different ranking -> the earlier ranking must score higher
    early = contextual_precision_at_k(["a", "b", "x", "y"], {"a", "b"}, 4)
    late = contextual_precision_at_k(["x", "y", "a", "b"], {"a", "b"}, 4)
    assert early == 1.0
    assert early > late
    # AP with hits at ranks 3,4 = ((1/3) + (2/4)) / 2
    assert late == ((1 / 3) + (2 / 4)) / 2
    assert contextual_precision_at_k(RANKED, set(), 4) == 0.0


def test_single_label_degeneracies_are_real():
    """Pin the identities documented in metrics.py.

    On the shipped eval sets every query has exactly one gold label, which makes
    three of these metrics restatements of ones already reported. These asserts
    exist so that fact stays visible instead of being rediscovered in an
    interview. See docs/adr/0018 and docs/reports/retrieval-metrics-audit-v1.md.
    """
    relevant = {"c"}  # exactly one gold label, as in retrieval-v1/v2/v3
    for k in (1, 3, 5, 10):
        assert recall_at_k(RANKED, relevant, k) == hit_at_k(RANKED, relevant, k)
        assert precision_at_k(RANKED, relevant, k) == hit_at_k(RANKED, relevant, k) / k
        assert contextual_precision_at_k(RANKED, relevant, k) == mrr_at_k(RANKED, relevant, k)

    # ...and they stop being identical the moment a query has two gold labels
    # that straddle the cutoff: "a" is inside k=3, "d" is not.
    multi = {"a", "d"}
    assert recall_at_k(RANKED, multi, 3) == 0.5  # found 1 of 2
    assert hit_at_k(RANKED, multi, 3) == 1.0  # "found anything?" says yes
    assert recall_at_k(RANKED, multi, 3) != hit_at_k(RANKED, multi, 3)
    assert contextual_precision_at_k(RANKED, multi, 3) == 0.5
    assert mrr_at_k(RANKED, multi, 3) == 1.0
    assert contextual_precision_at_k(RANKED, multi, 3) != mrr_at_k(RANKED, multi, 3)


def test_dataset_jsonl_roundtrip(tmp_path: Path):
    dataset = RetrievalDataset(
        name="retrieval-test",
        version="1",
        generator_model="gemini/test",
        corpus_stats={"documents": 2, "chunks": 5},
        cases=[
            RetrievalCase(
                id="c1",
                question="how do I healthcheck postgres?",
                relevant_chunk_ids=["c1"],
                relevant_document_ids=["d1"],
                source="github://x/compose.yaml",
                tool="docker",
                doc_type="yaml",
            )
        ],
    )
    path = tmp_path / "ds.jsonl"
    dataset.save_jsonl(path)
    loaded = RetrievalDataset.load_jsonl(path)
    assert loaded.name == "retrieval-test"
    assert loaded.corpus_stats == {"documents": 2, "chunks": 5}
    assert len(loaded.cases) == 1
    assert loaded.cases[0].question == "how do I healthcheck postgres?"


def test_faithfulness_score():
    from opsverse_evals.rag_suite import faithfulness_score

    score, n = faithfulness_score(
        {"claims": [{"claim": "a", "supported": True}, {"claim": "b", "supported": False}]}
    )
    assert score == 0.5
    assert n == 2
    # refusals / no claims: nothing asserted -> nothing unfaithful
    assert faithfulness_score({"claims": []}) == (1.0, 0)
    assert faithfulness_score({}) == (1.0, 0)


def test_parse_json_reply():
    assert parse_json_reply('{"question": "q?", "answerable": true}') == {
        "question": "q?",
        "answerable": True,
    }
    fenced = 'Here you go:\n```json\n{"question": "q?", "answerable": false}\n```'
    assert parse_json_reply(fenced) == {"question": "q?", "answerable": False}
    assert parse_json_reply("no json here") is None
    assert parse_json_reply("{broken") is None
