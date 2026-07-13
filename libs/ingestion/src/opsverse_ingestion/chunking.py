"""Segment -> chunk conversion.

Code segments (yaml/hcl/dockerfile) are already structural units and pass
through whole (oversize ones are split on line boundaries). Prose segments are
packed into size-bounded windows with sentence-boundary overlap.
"""

import re

from opsverse_ingestion.schemas import ChunkDraft, ParsedDocument, Segment, estimate_tokens

TARGET_TOKENS = 350
MAX_TOKENS = 512
OVERLAP_TOKENS = 50

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_prose(text: str) -> list[str]:
    """Pack sentences into windows of ~TARGET_TOKENS with trailing overlap."""
    sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
    if not sentences:
        return []
    windows: list[str] = []
    current: list[str] = []
    size = 0
    for sentence in sentences:
        s_tokens = estimate_tokens(sentence)
        if current and size + s_tokens > TARGET_TOKENS:
            windows.append(" ".join(current))
            # carry sentences from the tail as overlap
            overlap: list[str] = []
            overlap_size = 0
            for prev in reversed(current):
                overlap_size += estimate_tokens(prev)
                if overlap_size > OVERLAP_TOKENS:
                    break
                overlap.insert(0, prev)
            current, size = overlap, sum(estimate_tokens(s) for s in overlap)
        current.append(sentence)
        size += s_tokens
    if current:
        windows.append(" ".join(current))
    return windows


def _split_code(text: str) -> list[str]:
    """Split oversize code on line boundaries; no overlap (units are structural)."""
    if estimate_tokens(text) <= MAX_TOKENS:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines():
        l_tokens = estimate_tokens(line)
        if current and size + l_tokens > TARGET_TOKENS:
            parts.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += l_tokens
    if current:
        parts.append("\n".join(current))
    return parts


def chunk_document(parsed: ParsedDocument) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for segment in parsed.segments:
        pieces = _split_segment(segment)
        for piece in pieces:
            drafts.append(
                ChunkDraft(
                    ord=len(drafts),
                    text=piece,
                    token_estimate=estimate_tokens(piece),
                    section=segment.section,
                    language=segment.language,
                )
            )
    return drafts


def _split_segment(segment: Segment) -> list[str]:
    text = segment.text.strip()
    if not text:
        return []
    if segment.language is not None:
        return _split_code(text)
    if estimate_tokens(text) <= MAX_TOKENS:
        return [text]
    return _split_prose(text)
