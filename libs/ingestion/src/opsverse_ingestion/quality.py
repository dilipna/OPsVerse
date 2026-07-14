"""Quality gates: every chunk must pass all checks; near-duplicates are
removed via 64-bit simhash over word trigrams (Hamming distance <= 3)."""

import hashlib
import re
from collections import Counter

from opsverse_ingestion.schemas import ChunkDraft, PipelineStats

MIN_TOKENS = 8
MAX_HAMMING = 3
# The embedding stack is English-only (bge-base-en, ADR-0003). Doc sites ship
# localized trees (kubernetes/website content/<locale>/...) that otherwise
# pass every gate and pollute retrieval — measured 279/1344 docs before this
# gate existed. Letters, not chars: code/config chunks stay ASCII-heavy and
# accented names in English prose stay far below the threshold.
MAX_NON_ASCII_LETTER_RATIO = 0.3

_WORD = re.compile(r"\w+")


def _hash64(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")


def simhash(text: str) -> int:
    words = _WORD.findall(text.lower())
    shingles = [" ".join(words[i : i + 3]) for i in range(max(1, len(words) - 2))]
    weights = Counter(shingles)
    vector = [0] * 64
    for shingle, weight in weights.items():
        h = _hash64(shingle)
        for bit in range(64):
            vector[bit] += weight if (h >> bit) & 1 else -weight
    result = 0
    for bit in range(64):
        if vector[bit] > 0:
            result |= 1 << bit
    return result


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _reject_reason(chunk: ChunkDraft) -> str | None:
    if chunk.token_estimate < MIN_TOKENS:
        return "too_short"
    printable = sum(c.isprintable() or c in "\n\t" for c in chunk.text)
    if printable / len(chunk.text) < 0.95:
        return "non_printable"
    letters = [c for c in chunk.text if c.isalpha()]
    if letters:
        non_ascii = sum(1 for c in letters if ord(c) > 127)
        if non_ascii / len(letters) > MAX_NON_ASCII_LETTER_RATIO:
            return "non_english"
    return None


def apply_quality_gates(chunks: list[ChunkDraft]) -> tuple[list[ChunkDraft], PipelineStats]:
    """Filter chunks; returns survivors (re-numbered) and the stats delta."""
    stats = PipelineStats()
    kept: list[ChunkDraft] = []
    seen_exact: set[str] = set()
    seen_hashes: list[int] = []

    for chunk in chunks:
        reason = _reject_reason(chunk)
        if reason:
            stats.chunks_rejected += 1
            stats.reject_reasons[reason] = stats.reject_reasons.get(reason, 0) + 1
            continue

        exact = hashlib.sha256(chunk.text.encode()).hexdigest()
        if exact in seen_exact:
            stats.duplicates_removed += 1
            continue
        sh = simhash(chunk.text)
        if any(hamming(sh, prior) <= MAX_HAMMING for prior in seen_hashes):
            stats.duplicates_removed += 1
            continue

        seen_exact.add(exact)
        seen_hashes.append(sh)
        chunk.ord = len(kept)
        kept.append(chunk)

    stats.chunks_kept = len(kept)
    return kept, stats
