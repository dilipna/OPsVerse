from collections.abc import Callable

from pydantic import BaseModel

from rype_ingestion.chunking import chunk_document
from rype_ingestion.parsers import parse_document
from rype_ingestion.quality import apply_quality_gates
from rype_ingestion.schemas import ChunkDraft, DocType, PipelineStats
from rype_security import redact_secrets, scan_injection

_TOOL_HINTS = {
    "kubernetes": ("kubernetes", "k8s", "kubectl", "helm"),
    "docker": ("docker", "dockerfile", "compose"),
    "terraform": ("terraform", ".tf", "hashicorp"),
    "mlflow": ("mlflow",),
    "aws": ("aws", "amazon"),
}


def detect_tool(source: str) -> str | None:
    lowered = source.lower()
    for tool, hints in _TOOL_HINTS.items():
        if any(hint in lowered for hint in hints):
            return tool
    return None


class PipelineResult(BaseModel):
    doc_type: DocType
    tool: str | None
    chunks: list[ChunkDraft]
    stats: PipelineStats


# Second injection layer: chunk text -> True (injection), False (clean) or None
# (the classifier failed). Kept as a plain callable so this library does no I/O.
InjectionClassifier = Callable[[str], bool | None]


def ingest_bytes(
    raw: bytes,
    source: str,
    tool: str | None = None,
    *,
    llm_classifier: InjectionClassifier | None = None,
    llm_fail_closed: bool = True,
) -> PipelineResult:
    """Full pipeline for one document: parse -> chunk -> quality gates.

    Raises UnsupportedDocumentError / DecodingError for input the pipeline
    cannot represent honestly; callers record those as failed documents.
    """
    parsed = parse_document(raw, source)
    drafts = chunk_document(parsed)
    kept, stats = apply_quality_gates(drafts)
    stats.segments = len(parsed.segments)

    # Security (Phase 9, ADR-0007): redact credential-shaped strings from every
    # surviving chunk, and scan the assembled document for injection content
    # aimed at the assistant. A flagged document is quarantined (no chunks
    # enter retrieval) rather than silently indexed — indirect prompt injection
    # via poisoned docs is the primary RAG threat.
    for draft in kept:
        result = redact_secrets(draft.text)
        if result.redacted:
            draft.text = result.text
            stats.secrets_redacted += result.redacted
    verdict = scan_injection("\n".join(draft.text for draft in kept))
    if verdict.is_suspicious:
        stats.quarantined = True
        stats.quarantine_reasons = verdict.matched
    elif llm_classifier is not None:
        # Second layer (security-classifier-v1): on external data the regexes
        # catch ~7% of injections; adding this layer raised recall to ~59% with
        # no added false alarms. Checked per chunk, the unit closest to the short
        # texts it was benchmarked on; stops at the first flag. An error fails
        # closed by default, so an outage cannot wave documents through.
        for draft in kept:
            stats.llm_checked_chunks += 1
            flagged = llm_classifier(draft.text)
            if flagged or (flagged is None and llm_fail_closed):
                stats.quarantined = True
                stats.quarantine_reasons = ["llm_classifier" if flagged else "llm_classifier_error"]
                break
    if stats.quarantined:
        stats.chunks_kept = 0
        kept = []

    return PipelineResult(
        doc_type=parsed.doc_type,
        tool=tool or detect_tool(source),
        chunks=kept,
        stats=stats,
    )
