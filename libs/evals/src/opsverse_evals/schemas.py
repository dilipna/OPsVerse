from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class RetrievalCase(BaseModel):
    """One labeled retrieval query.

    The gold label is the chunk the question was generated from. Because the
    corpus contains near-duplicate content across documents, harnesses report
    both chunk-level and document-level credit (see run_ablation.py).
    """

    id: str  # stable: the gold chunk id
    question: str
    relevant_chunk_ids: list[str] = Field(min_length=1)
    relevant_document_ids: list[str] = Field(min_length=1)
    source: str
    tool: str | None = None
    doc_type: str | None = None
    section: str | None = None


class RetrievalDataset(BaseModel):
    name: str
    version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generator_model: str
    corpus_stats: dict[str, int] = {}
    cases: list[RetrievalCase] = []

    def save_jsonl(self, path: Path) -> None:
        """Header line with metadata, then one case per line (diff-friendly)."""
        lines = [self.model_dump_json(exclude={"cases"})]
        lines += [case.model_dump_json() for case in self.cases]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def load_jsonl(cls, path: Path) -> "RetrievalDataset":
        header, *rest = path.read_text(encoding="utf-8").splitlines()
        dataset = cls.model_validate_json(header)
        dataset.cases = [RetrievalCase.model_validate_json(line) for line in rest if line]
        return dataset
