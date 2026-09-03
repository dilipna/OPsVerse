import json
from itertools import pairwise

import pytest

from opsverse_evals import golden_set
from opsverse_evals import judge_validation as jv
from opsverse_evals.schemas import (
    GradedRetrievalCase,
    GradedRetrievalDataset,
    HumanLabel,
    JudgeValidationKey,
)


def pair(human: int, judge: int, weight: float = 1.0, stratum: str = "a", **kw) -> jv.LabelPair:
    return jv.LabelPair(
        human=human,
        judge=judge,
        weight=weight,
        stratum=stratum,
        retrieved_by=kw.get("retrieved_by", ()),
        is_seed=kw.get("is_seed", False),
    )


def test_excerpt_window_matches_the_judges():
    """A human reading less text than the judge would measure the truncation."""
    assert jv.EXCERPT_CHARS == golden_set.EXCERPT_CHARS


def test_threshold_matches_the_dataset_default():
    dataset = GradedRetrievalDataset(name="x", version="1", judge_model="m")
    assert dataset.relevance_threshold == jv.THRESHOLD


# --------------------------------------------------------------------------
# agreement statistics
# --------------------------------------------------------------------------


def test_perfect_agreement_is_kappa_one():
    pairs = [pair(g, g) for g in (0, 1, 2, 3) for _ in range(5)]
    assert jv.tpr(pairs) == pytest.approx(1.0)
    assert jv.tnr(pairs) == pytest.approx(1.0)
    assert jv.cohen_kappa_binary(pairs) == pytest.approx(1.0)
    assert jv.quadratic_weighted_kappa(pairs) == pytest.approx(1.0)
    assert jv.exact_agreement(pairs) == pytest.approx(1.0)
    assert jv.mean_signed_error(pairs) == pytest.approx(0.0)


def test_degenerate_judge_scores_zero_kappa_despite_high_raw_agreement():
    """The reason kappa is the headline: a judge that rejects everything looks
    good on raw agreement when the pool is mostly non-relevant."""
    # 17 truly non-relevant, 3 truly relevant; the judge calls all 20 non-relevant
    pairs = [pair(0, 0) for _ in range(17)] + [pair(3, 0) for _ in range(3)]
    assert jv.exact_agreement(pairs) == pytest.approx(0.85)
    assert jv.cohen_kappa_binary(pairs) == pytest.approx(0.0)
    assert jv.tpr(pairs) == pytest.approx(0.0)
    assert jv.tnr(pairs) == pytest.approx(1.0)


def test_quadratic_kappa_penalises_distance_not_just_mismatch():
    near = [pair(3, 2) for _ in range(10)] + [pair(0, 0) for _ in range(10)]
    far = [pair(3, 0) for _ in range(10)] + [pair(0, 0) for _ in range(10)]
    # binary kappa cannot see the difference: 3-vs-2 is a hit, 3-vs-0 is a miss,
    # but on the graded scale the near miss must score strictly better
    assert jv.quadratic_weighted_kappa(near) > jv.quadratic_weighted_kappa(far)


def test_binary_counts_orientation():
    pairs = [pair(3, 3), pair(0, 2), pair(2, 1), pair(0, 0)]
    tp, fp, fn, tn = jv.binary_counts(pairs, weighted=False)
    assert (tp, fp, fn, tn) == (1.0, 1.0, 1.0, 1.0)
    assert jv.precision(pairs, weighted=False) == pytest.approx(0.5)
    assert jv.npv(pairs, weighted=False) == pytest.approx(0.5)


def test_confusion_rows_are_human_cols_are_judge():
    table = jv.confusion([pair(3, 0)], weighted=False)
    assert table[3][0] == 1.0
    assert table[0][3] == 0.0


def test_mean_signed_error_sign_convention():
    # judge grades below the human -> the judge is too strict -> positive
    assert jv.mean_signed_error([pair(3, 1)], weighted=False) == pytest.approx(2.0)
    assert jv.mean_signed_error([pair(1, 3)], weighted=False) == pytest.approx(-2.0)


def test_weights_recover_the_population_rate():
    """The point of the design: a balanced sample reweighted back to a skewed
    population must not report the balanced sample's rates."""
    # population: 10 relevant (judge agrees on all), 90 non-relevant (judge
    # wrongly calls 45 relevant). Sample 10 from each stratum.
    positives = [pair(3, 3, weight=1.0, stratum=jv.STRATUM_POS) for _ in range(10)]
    negatives = [pair(0, 0, weight=9.0, stratum=jv.STRATUM_NEG) for _ in range(10)]
    pairs = positives + negatives
    # unweighted, the two strata are equal-sized, so precision looks like 1.0 either
    # way; the informative contrast is prevalence-sensitive NPV weighting
    assert jv.tpr(pairs, weighted=True) == pytest.approx(1.0)
    unweighted_share = sum(1 for p in pairs if p.human_relevant) / len(pairs)
    weighted_share = sum(p.weight for p in pairs if p.human_relevant) / sum(p.weight for p in pairs)
    assert unweighted_share == pytest.approx(0.5)
    assert weighted_share == pytest.approx(0.1)


# --------------------------------------------------------------------------
# sampling and blinding
# --------------------------------------------------------------------------


def _golden(n_queries: int = 20) -> GradedRetrievalDataset:
    cases = []
    for q in range(n_queries):
        grades = {f"c{q}-{i}": (3 if i == 0 else (2 if i == 1 else i % 2)) for i in range(10)}
        cases.append(
            GradedRetrievalCase(
                id=f"q{q}",
                question=f"question {q}?",
                grades=grades,
                pool_size=len(grades),
                seed_chunk_id=f"c{q}-0",
                seed_grade=3,
            )
        )
    return GradedRetrievalDataset(name="t", version="1", judge_model="test-judge", cases=cases)


def _texts(golden: GradedRetrievalDataset) -> dict[str, str]:
    return {cid: f"text for {cid} " * 40 for case in golden.cases for cid in case.grades}


def test_draw_sample_is_balanced_and_weighted():
    golden = _golden()
    texts = _texts(golden)
    tasks, keys = draw = jv.draw_sample(golden, texts, {}, n_total=40, seed=7)
    assert len(tasks) == len(keys) == 40

    pos = [k for k in keys if k.stratum == jv.STRATUM_POS]
    neg = [k for k in keys if k.stratum == jv.STRATUM_NEG]
    assert len(pos) == len(neg) == 20

    # 2 relevant of 10 per query -> 40 positives, 160 negatives in the population
    assert pos[0].weight == pytest.approx(40 / 20)
    assert neg[0].weight == pytest.approx(160 / 20)
    assert all(k.judge_grade >= jv.THRESHOLD for k in pos)
    assert all(k.judge_grade < jv.THRESHOLD for k in neg)
    del draw


def test_draw_sample_splits_dev_and_test_within_stratum():
    golden = _golden()
    _, keys = jv.draw_sample(golden, _texts(golden), {}, n_total=40, seed=7)
    for stratum in (jv.STRATUM_POS, jv.STRATUM_NEG):
        splits = [k.split for k in keys if k.stratum == stratum]
        assert splits.count("dev") == splits.count("test") == 10


def test_draw_sample_is_deterministic():
    golden = _golden()
    texts = _texts(golden)
    a = jv.draw_sample(golden, texts, {}, n_total=40, seed=7)[1]
    b = jv.draw_sample(golden, texts, {}, n_total=40, seed=7)[1]
    assert [k.chunk_id for k in a] == [k.chunk_id for k in b]
    c = jv.draw_sample(golden, texts, {}, n_total=40, seed=8)[1]
    assert [k.chunk_id for k in a] != [k.chunk_id for k in c]


def test_tasks_are_blinded():
    """An annotator who can join back to the judge's grade is not independent."""
    golden = _golden()
    # text that deliberately does NOT embed the chunk id, so the assertion below
    # tests what draw_sample emits rather than the fixture
    texts = {cid: "opaque body text" for case in golden.cases for cid in case.grades}
    tasks, keys = jv.draw_sample(golden, texts, {}, n_total=20, seed=7)
    fields = set(tasks[0].model_dump())
    assert fields == {"task_id", "question", "chunk_text"}
    serialized = " ".join(t.model_dump_json() for t in tasks)
    for key in keys:
        assert key.chunk_id not in serialized
        assert key.case_id not in serialized


def test_tasks_are_shuffled_so_strata_are_not_blocked():
    golden = _golden(40)
    _, keys = jv.draw_sample(golden, _texts(golden), {}, n_total=80, seed=7)
    strata = [k.stratum for k in keys]
    runs = sum(1 for a, b in pairwise(strata) if a != b)
    # a blocked (sorted) order would have exactly 1 transition
    assert runs > 10


def test_sample_excerpt_is_truncated_to_the_judges_window():
    golden = _golden(2)
    texts = {cid: "x" * 9000 for case in golden.cases for cid in case.grades}
    tasks, _ = jv.draw_sample(golden, texts, {}, n_total=4, seed=7)
    assert all(len(t.chunk_text) == jv.EXCERPT_CHARS for t in tasks)


def test_draw_sample_skips_chunks_missing_from_the_corpus():
    golden = _golden(4)
    texts = _texts(golden)
    for cid in list(texts)[:20]:
        del texts[cid]
    _, keys = jv.draw_sample(golden, texts, {}, n_total=10, seed=7)
    assert all(k.chunk_id in texts for k in keys)


def test_retrieval_map_reads_committed_raw_json(tmp_path):
    raw = tmp_path / "raw.json"
    raw.write_text(
        json.dumps(
            {
                "k": 10,
                "results": {
                    "dense": [{"case_id": "q1", "retrieved_chunk_ids": ["a", "b"]}],
                    "sparse": [{"case_id": "q1", "retrieved_chunk_ids": ["b"]}],
                },
            }
        ),
        encoding="utf-8",
    )
    modes = jv.retrieval_map(raw)
    assert modes[("q1", "a")] == ["dense"]
    assert sorted(modes[("q1", "b")]) == ["dense", "sparse"]


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def _keys(n: int, grades: list[int]) -> list[JudgeValidationKey]:
    return [
        JudgeValidationKey(
            task_id=f"t{i:04d}",
            case_id=f"q{i}",
            chunk_id=f"c{i}",
            judge_grade=grades[i],
            stratum=jv.STRATUM_POS if grades[i] >= 2 else jv.STRATUM_NEG,
            weight=2.0 if grades[i] >= 2 else 8.0,
            split="dev" if i % 2 == 0 else "test",
            retrieved_by=["hybrid"] if i % 2 == 0 else ["dense"],
        )
        for i in range(n)
    ]


def test_build_pairs_drops_unlabelled_tasks():
    keys = _keys(4, [3, 0, 2, 1])
    labels = [
        HumanLabel(task_id="t0000", human_grade=3),
        HumanLabel(task_id="t0002", human_grade=1),
    ]
    pairs = jv.build_pairs(keys, labels)
    assert len(pairs) == 2
    assert [(p.human, p.judge) for p in pairs] == [(3, 3), (1, 2)]


def test_build_pairs_clamps_out_of_range_human_grades():
    pairs = jv.build_pairs(_keys(1, [3]), [HumanLabel(task_id="t0000", human_grade=9)])
    assert pairs[0].human == jv.MAX_GRADE


def test_score_reports_intervals_and_raises_without_labels():
    grades = [3, 2, 1, 0] * 10
    keys = _keys(40, grades)
    labels = [HumanLabel(task_id=k.task_id, human_grade=k.judge_grade) for k in keys]
    report = jv.score(keys, labels)
    assert report["n_labelled"] == 40
    assert report["weighted"]["tpr"]["mean"] == pytest.approx(1.0)
    assert report["weighted"]["cohen_kappa_binary"]["mean"] == pytest.approx(1.0)
    assert set(report["by_split"]) == {"dev", "test"}
    assert report["per_mode_signed_error"]["hybrid"]["mean"] == pytest.approx(0.0)

    with pytest.raises(ValueError, match="no labelled tasks"):
        jv.score(keys, [])


def test_render_produces_a_report_with_the_headline_numbers():
    grades = [3, 2, 1, 0] * 10
    keys = _keys(40, grades)
    labels = [HumanLabel(task_id=k.task_id, human_grade=k.judge_grade) for k in keys]
    text = jv.render(jv.score(keys, labels), "gemini/test", "2026-09-03")
    assert "Judge validation v1" in text
    assert "Cohen's kappa" in text
    assert "Quadratic-weighted kappa" in text
    assert "One human rater" in text  # the limits section must survive rendering


def test_labeler_page_is_self_contained_and_escapes_script_tags():
    golden = _golden(2)
    texts = {cid: "</script><b>x</b>" for case in golden.cases for cid in case.grades}
    tasks, _ = jv.draw_sample(golden, texts, {}, n_total=4, seed=7)
    html = jv.render_labeler(tasks, "T")
    # exactly one opening and one closing script tag: the payload must not break out
    assert html.count("</script>") == 1
    # "self-contained" means the *markup* pulls in nothing, which is not the same
    # as "the string http never appears" -- corpus excerpts are full of URLs
    for loader in ("<script src", "<link ", "<img ", "@import", "fetch(", "XMLHttpRequest"):
        assert loader not in html
    assert "localStorage" in html
