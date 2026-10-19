"""A parser/chunker regression must fail the raw-input browser release chain."""

import pytest

from opsverse_evals.runbook_fixture import build


def test_real_raw_docs_are_attributed_and_chunked():
    corpus = build()
    assert len(corpus["manifest"]["documents"]) == 6
    assert len(corpus["chunks"]) > 50
    assert all(corpus["manifest"]["revision"] in c["source"] for c in corpus["chunks"])
    assert any("readiness" in c["text"] for c in corpus["chunks"])


def test_broken_chunker_cannot_pass_browser_fixture_generation(monkeypatch):
    monkeypatch.setattr("opsverse_ingestion.pipeline.chunk_document", lambda parsed: [])
    with pytest.raises(ValueError, match="no usable chunks"):
        build()
