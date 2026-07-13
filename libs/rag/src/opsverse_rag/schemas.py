from enum import StrEnum

from pydantic import BaseModel


class SearchMode(StrEnum):
    DENSE = "dense"
    SPARSE = "sparse"
    HYBRID = "hybrid"


class SparseVec(BaseModel):
    indices: list[int]
    values: list[float]


class SearchFilters(BaseModel):
    tool: str | None = None
    doc_type: str | None = None
    language: str | None = None


class RetrievedChunk(BaseModel):
    id: str
    score: float
    rerank_score: float | None = None
    text: str
    section: str | None = None
    source: str
    tool: str | None = None
    doc_type: str | None = None
    language: str | None = None
    document_id: str
