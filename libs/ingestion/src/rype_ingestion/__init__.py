"""Ingestion pipeline: parse -> chunk -> validate -> stats."""

from rype_ingestion.pipeline import PipelineResult, ingest_bytes

__all__ = ["PipelineResult", "ingest_bytes"]
