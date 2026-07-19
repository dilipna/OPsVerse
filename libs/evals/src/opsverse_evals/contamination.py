"""Eval-set contamination guard.

Frozen eval sets must never leak into training data (SFT/DPO pairs generated
in Phase 5). This module is the single enforcement point: every dataset
pipeline calls `filter_contaminated` with the hashes of all frozen eval sets
before writing training examples.

Two layers, per docs/eval-contamination-policy.md:
- exact: sha256 over a normalized question -> O(1) lookup.
- near-duplicate: 5-gram token shingles, Jaccard >= 0.6 vs any eval question
  (catches paraphrases produced by the same generator model).
"""

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

from opsverse_evals.schemas import RetrievalDataset

SHINGLE_N = 5
JACCARD_THRESHOLD = 0.6

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def normalize_question(text: str) -> str:
    """Casefold, strip punctuation, collapse whitespace.

    The exact normalization is part of the policy: changing it invalidates
    every stored hash, so version any change via a new policy revision.
    """
    return _WS.sub(" ", _PUNCT.sub("", text.casefold())).strip()


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_question(text).encode("utf-8")).hexdigest()


def shingles(text: str, n: int = SHINGLE_N) -> set[tuple[str, ...]]:
    tokens = normalize_question(text).split()
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def jaccard(a: set[tuple[str, ...]], b: set[tuple[str, ...]]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def frozen_evalsets(root: Path) -> list[Path]:
    """Frozen *retrieval* eval sets under `root` (evalsets/), recursively.

    Retrieval question sets are the ones whose questions must be kept out of
    training data. Other frozen sets live under evalsets/ too (e.g. the
    security red-team set has a different schema); those are matched out by
    the retrieval-* naming convention. Partials are working files, not frozen.
    """
    return sorted(p for p in root.rglob("retrieval-*.jsonl") if ".partial" not in p.name)


def load_eval_questions(paths: Iterable[Path]) -> list[str]:
    questions: list[str] = []
    for path in paths:
        dataset = RetrievalDataset.load_jsonl(path)
        questions += [case.question for case in dataset.cases]
    return questions


class ContaminationGuard:
    """Precomputed hashes + shingles for every frozen eval question."""

    def __init__(self, eval_questions: Iterable[str]) -> None:
        self.hashes = {question_hash(q) for q in eval_questions}
        self.eval_shingles = [shingles(q) for q in eval_questions]

    @classmethod
    def from_evalsets_dir(cls, root: Path) -> "ContaminationGuard":
        return cls(load_eval_questions(frozen_evalsets(root)))

    def is_contaminated(self, candidate: str) -> bool:
        if question_hash(candidate) in self.hashes:
            return True
        cand = shingles(candidate)
        return any(jaccard(cand, ev) >= JACCARD_THRESHOLD for ev in self.eval_shingles)

    def filter(self, candidates: Iterable[str]) -> tuple[list[str], list[str]]:
        """Split candidates into (kept, dropped)."""
        kept: list[str] = []
        dropped: list[str] = []
        for candidate in candidates:
            (dropped if self.is_contaminated(candidate) else kept).append(candidate)
        return kept, dropped
