from pydantic import BaseModel

from opsverse_ingestion.chunking import chunk_document
from opsverse_ingestion.parsers import parse_document
from opsverse_ingestion.quality import apply_quality_gates
from opsverse_ingestion.schemas import ChunkDraft, DocType, PipelineStats
from opsverse_security import redact_secrets, scan_injection

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


def ingest_bytes(raw: bytes, source: str, tool: str | None = None) -> PipelineResult:
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
        stats.chunks_kept = 0
        kept = []

    return PipelineResult(
        doc_type=parsed.doc_type,
        tool=tool or detect_tool(source),
        chunks=kept,
        stats=stats,
    )
