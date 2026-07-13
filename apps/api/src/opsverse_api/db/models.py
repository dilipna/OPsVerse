import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB on Postgres, plain JSON elsewhere (sqlite in tests)
JSONVariant = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(sa.String(32))  # upload | url | github_repo
    uri: Mapped[str] = mapped_column(sa.Text)
    sha256: Mapped[str] = mapped_column(sa.String(64), index=True)
    status: Mapped[str] = mapped_column(sa.String(16), default="pending")  # pending|ready|failed
    doc_type: Mapped[str | None] = mapped_column(sa.String(32), default=None)
    tool: Mapped[str | None] = mapped_column(sa.String(32), default=None)
    error: Mapped[str | None] = mapped_column(sa.Text, default=None)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (sa.UniqueConstraint("document_id", "ord"),)

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ord: Mapped[int] = mapped_column(sa.Integer)
    text: Mapped[str] = mapped_column(sa.Text)
    token_count: Mapped[int] = mapped_column(sa.Integer)
    section: Mapped[str | None] = mapped_column(sa.Text, default=None)
    language: Mapped[str | None] = mapped_column(sa.String(16), default=None)
    # pending -> embedded (Phase 3 flips this and fills qdrant_point_id)
    embedding_status: Mapped[str] = mapped_column(sa.String(16), default="pending")
    qdrant_point_id: Mapped[str | None] = mapped_column(sa.String(64), default=None)

    document: Mapped[Document] = relationship(back_populates="chunks")


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(sa.String(16))  # upload | url | github_repo
    status: Mapped[str] = mapped_column(sa.String(16), default="queued")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, default=None)
    error: Mapped[str | None] = mapped_column(sa.Text, default=None)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
