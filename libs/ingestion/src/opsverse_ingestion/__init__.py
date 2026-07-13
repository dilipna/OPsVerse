"""Ingestion pipeline: parse -> chunk -> validate -> stats."""

from opsverse_ingestion.pipeline import PipelineResult, ingest_bytes

__all__ = ["PipelineResult", "ingest_bytes"]
