from pathlib import Path

import pytest

from opsverse_evals.generator_eval import render, summarise
from opsverse_evals.schemas import GoldenAnswer, GoldenAnswerSet


def _answers(n: int = 3) -> GoldenAnswerSet:
    return GoldenAnswerSet(
        name="golden-answers-test",
        version="1",
        generator_model="gemini/test",
        answers=[
            GoldenAnswer(
                id=f"q{i}",
                question=f"question {i}?",
                reference_answer=f"answer {i}",
                claims=[f"claim {i}a", f"claim {i}b"],
                source_chunk_ids=[f"c{i}"],
            )
            for i in range(n)
        ],
    )


def test_golden_answer_roundtrip(tmp_path: Path):
    ds = _answers(2)
    path = tmp_path / "answers.jsonl"
    ds.save_jsonl(path)
    loaded = GoldenAnswerSet.load_jsonl(path)
    assert loaded.generator_model == "gemini/test"
    assert len(loaded.answers) == 2
    assert loaded.answers[0].claims == ["claim 0a", "claim 0b"]
    assert loaded.answers[1].source_chunk_ids == ["c1"]


def test_summarise_computes_per_mode_recall():
    answers = _answers(3)
    results = {
        ("hybrid", "q0"): 1.0,
        ("hybrid", "q1"): 0.5,
        ("hybrid", "q2"): 0.0,
        ("dense", "q0"): 0.0,
        ("dense", "q1"): 0.0,
        ("dense", "q2"): 0.0,
    }
    s = summarise(results, answers, "gemini/test", ["hybrid", "dense"])
    assert s["queries"] == 3
    assert s["total_claims"] == 6
    assert s["mean_claims_per_query"] == 2.0
    assert s["modes"]["hybrid"]["mean"] == pytest.approx(0.5)
    assert s["modes"]["dense"]["mean"] == pytest.approx(0.0)
    # dense is uniformly worse -> a comparison against the hybrid baseline exists
    assert "dense_vs_hybrid" in s["comparisons"]
    assert s["comparisons"]["dense_vs_hybrid"]["delta"] == pytest.approx(-0.5)


def test_summarise_skips_baseline_self_comparison():
    answers = _answers(2)
    results = {("hybrid", "q0"): 1.0, ("hybrid", "q1"): 1.0}
    s = summarise(results, answers, "gemini/test", ["hybrid"])
    assert s["comparisons"] == {}


def test_summarise_handles_missing_verdicts():
    """A mode with no completed judgements must not appear, not crash."""
    answers = _answers(2)
    results = {("hybrid", "q0"): 1.0, ("hybrid", "q1"): 0.0}
    s = summarise(results, answers, "gemini/test", ["hybrid", "sparse"])
    assert "hybrid" in s["modes"]
    assert "sparse" not in s["modes"]


def test_render_includes_limits_and_numbers():
    answers = _answers(2)
    results = {("hybrid", "q0"): 1.0, ("hybrid", "q1"): 0.5}
    s = summarise(results, answers, "gemini/test", ["hybrid"])
    text = render(s, "2026-08-31")
    assert "contextual recall" in text.lower()
    assert "0.750" in text  # the mean
    # the honest-limits section must survive any future edit of the renderer
    assert "LLM-written, not human-authored" in text
    assert "saturated" in text
