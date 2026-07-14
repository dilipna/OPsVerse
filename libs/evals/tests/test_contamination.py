from pathlib import Path

from opsverse_evals.contamination import (
    ContaminationGuard,
    frozen_evalsets,
    jaccard,
    normalize_question,
    question_hash,
    shingles,
)
from opsverse_evals.schemas import RetrievalCase, RetrievalDataset


def test_normalize_question():
    assert normalize_question("  How do I   scale an HPA?! ") == "how do i scale an hpa"
    # normalization is punctuation/case/whitespace-insensitive, nothing more
    assert normalize_question("scale HPA") != normalize_question("scaling HPA")


def test_question_hash_stable_across_formatting():
    a = question_hash("How does a Kubernetes HPA scale on custom metrics?")
    b = question_hash("how does a kubernetes  hpa scale on custom metrics")
    assert a == b
    assert len(a) == 64


def test_shingles_and_jaccard():
    a = shingles("one two three four five six")
    assert ("one", "two", "three", "four", "five") in a
    assert jaccard(a, a) == 1.0
    assert jaccard(a, set()) == 0.0
    # short questions fall back to a single whole-question shingle
    assert shingles("just three words") == {("just", "three", "words")}


def test_guard_exact_and_near_duplicate():
    guard = ContaminationGuard(
        ["How does a Kubernetes HPA scale a deployment based on custom metrics?"]
    )
    # exact (modulo normalization)
    assert guard.is_contaminated(
        "how does a kubernetes hpa scale a deployment based on custom metrics"
    )
    # near-duplicate: one word substituted -> high shingle overlap
    assert guard.is_contaminated(
        "How does a Kubernetes HPA scale a deployment based on external metrics?"
    )
    # unrelated question passes
    assert not guard.is_contaminated("What is a Terraform state file and where is it stored?")


def test_guard_filter_splits():
    guard = ContaminationGuard(["what is a dockerfile healthcheck instruction for"])
    kept, dropped = guard.filter(
        [
            "What is a Dockerfile HEALTHCHECK instruction for?",
            "How do I configure MLflow tracking URIs?",
        ]
    )
    assert dropped == ["What is a Dockerfile HEALTHCHECK instruction for?"]
    assert kept == ["How do I configure MLflow tracking URIs?"]


def test_frozen_evalsets_excludes_partials(tmp_path: Path):
    dataset = RetrievalDataset(
        name="retrieval-test",
        version="1",
        generator_model="gemini/test",
        cases=[
            RetrievalCase(
                id="c1",
                question="how do I healthcheck postgres?",
                relevant_chunk_ids=["c1"],
                relevant_document_ids=["d1"],
                source="github://x/compose.yaml",
            )
        ],
    )
    dataset.save_jsonl(tmp_path / "retrieval-v9.jsonl")
    dataset.save_jsonl(tmp_path / "retrieval-v9.partial.jsonl")
    frozen = frozen_evalsets(tmp_path)
    assert [p.name for p in frozen] == ["retrieval-v9.jsonl"]

    guard = ContaminationGuard.from_evalsets_dir(tmp_path)
    assert guard.is_contaminated("How do I healthcheck Postgres?")
