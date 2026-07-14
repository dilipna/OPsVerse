"""Deterministic quality filters for generated instruction pairs.

Every drop returns a reason string so the dataset manifest can report
drops_by_reason — "we filtered X for Y" is part of the dataset's story.
"""

import re

from opsverse_evals.contamination import jaccard, question_hash, shingles

MIN_USER_CHARS = 15
MAX_USER_CHARS = 2_000
MIN_ASSISTANT_CHARS = 80
MAX_ASSISTANT_CHARS = 8_000
NEAR_DUP_JACCARD = 0.6

# generation-scaffold phrases that must never leak into training data: the
# fine-tuned model would learn to talk about context it won't have
_SCAFFOLD = re.compile(
    r"the (provided|given|above) (excerpt|context|document|text)"
    r"|based on the (excerpt|context|provided)"
    r"|in the excerpt"
    r"|as an ai\b",
    re.IGNORECASE,
)


def quality_drop_reason(user: str, assistant: str) -> str | None:
    if len(user.strip()) < MIN_USER_CHARS:
        return "user_too_short"
    if len(user) > MAX_USER_CHARS:
        return "user_too_long"
    if len(assistant.strip()) < MIN_ASSISTANT_CHARS:
        return "assistant_too_short"
    if len(assistant) > MAX_ASSISTANT_CHARS:
        return "assistant_too_long"
    if _SCAFFOLD.search(user) or _SCAFFOLD.search(assistant):
        return "scaffold_leak"
    if question_hash(user) == question_hash(assistant):
        return "user_equals_assistant"
    return None


class Deduper:
    """Exact (normalized hash) + near-duplicate (shingle Jaccard) dedup of
    user prompts within a dataset."""

    def __init__(self) -> None:
        self._hashes: set[str] = set()
        self._shingles: list[set[tuple[str, ...]]] = []

    def is_duplicate(self, user: str) -> bool:
        if question_hash(user) in self._hashes:
            return True
        cand = shingles(user)
        return any(jaccard(cand, seen) >= NEAR_DUP_JACCARD for seen in self._shingles)

    def add(self, user: str) -> None:
        self._hashes.add(question_hash(user))
        self._shingles.append(shingles(user))
