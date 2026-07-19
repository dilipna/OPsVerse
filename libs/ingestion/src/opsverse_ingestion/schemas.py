from enum import StrEnum

from pydantic import BaseModel, Field


class DocType(StrEnum):
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    YAML = "yaml"
    DOCKERFILE = "dockerfile"
    TERRAFORM = "terraform"
    TEXT = "text"


class Segment(BaseModel):
    """A logical unit produced by a parser: one heading section, one YAML
    document, one Terraform block, one Dockerfile stage."""

    text: str
    section: str | None = None  # e.g. "Install > Linux" or "resource aws_s3_bucket.logs"
    language: str | None = None  # set for code segments (yaml/hcl/dockerfile)


class ParsedDocument(BaseModel):
    doc_type: DocType
    source: str  # uri or filename
    segments: list[Segment]


class ChunkDraft(BaseModel):
    ord: int
    text: str
    token_estimate: int
    section: str | None = None
    language: str | None = None


class PipelineStats(BaseModel):
    segments: int = 0
    chunks_kept: int = 0
    chunks_rejected: int = 0
    duplicates_removed: int = 0
    reject_reasons: dict[str, int] = Field(default_factory=dict)
    secrets_redacted: int = 0
    quarantined: bool = False  # ingest-time injection scan flagged this document
    quarantine_reasons: list[str] = Field(default_factory=list)


def estimate_tokens(text: str) -> int:
    # chars/4 is a serviceable estimate for English + code; real token
    # counting arrives with the embedding pipeline in Phase 3.
    return max(1, len(text) // 4)
