from pathlib import Path

from opsverse_evals import RetrievalCase, RetrievalDataset, hit_at_k, mrr_at_k, ndcg_at_k
from opsverse_evals.generate_retrieval_set import parse_json_reply

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


def test_parse_json_reply():
    assert parse_json_reply('{"question": "q?", "answerable": true}') == {
        "question": "q?",
        "answerable": True,
    }
    fenced = 'Here you go:\n```json\n{"question": "q?", "answerable": false}\n```'
    assert parse_json_reply(fenced) == {"question": "q?", "answerable": False}
    assert parse_json_reply("no json here") is None
    assert parse_json_reply("{broken") is None
