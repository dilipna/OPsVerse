from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

Format = Literal["qa", "explain", "diagnosis"]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class InstructionPair(BaseModel):
    """One SFT example in chat format (TRL-ready: a `messages` column)."""

    id: str  # "<chunk_id>:<format>" — stable, makes generation resumable
    format: Format
    messages: list[Message] = Field(min_length=2, max_length=2)
    source_chunk_ids: list[str]
    tool: str | None = None
    doc_type: str | None = None
    generator_model: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def user_text(self) -> str:
        return self.messages[0].content

    @property
    def assistant_text(self) -> str:
        return self.messages[1].content


class DatasetManifest(BaseModel):
    """Sidecar for every generated dataset version.

    Per docs/eval-contamination-policy.md a dataset without a
    `decontamination` entry does not get trained on.
    """

    name: str
    version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generator_model: str
    git_rev: str | None = None
    corpus: dict[str, int] = {}
    examples: int = 0
    by_format: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    drops_by_reason: dict[str, int] = {}
    decontamination: dict[str, object] = {}
