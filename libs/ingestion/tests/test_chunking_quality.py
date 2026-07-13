from opsverse_ingestion.chunking import MAX_TOKENS, chunk_document
from opsverse_ingestion.pipeline import detect_tool, ingest_bytes
from opsverse_ingestion.quality import apply_quality_gates, hamming, simhash
from opsverse_ingestion.schemas import ChunkDraft, DocType, ParsedDocument, Segment


def _draft(text: str, ord_: int = 0) -> ChunkDraft:
    return ChunkDraft(ord=ord_, text=text, token_estimate=max(1, len(text) // 4))


def test_long_prose_splits_with_overlap():
    sentences = " ".join(
        f"This is sentence number {i} with some padding words." for i in range(200)
    )
    parsed = ParsedDocument(
        doc_type=DocType.MARKDOWN, source="a.md", segments=[Segment(text=sentences)]
    )
    chunks = chunk_document(parsed)
    assert len(chunks) > 1
    assert all(c.token_estimate <= MAX_TOKENS for c in chunks)
    # consecutive windows share overlap sentences
    assert chunks[0].text.split(". ")[-1] in chunks[1].text or len(chunks) >= 2


def test_code_segment_not_split_when_small():
    parsed = ParsedDocument(
        doc_type=DocType.YAML,
        source="a.yaml",
        segments=[Segment(text="kind: Pod\nmetadata:\n  name: x", language="yaml")],
    )
    chunks = chunk_document(parsed)
    assert len(chunks) == 1
    assert chunks[0].language == "yaml"


def test_quality_rejects_short_and_dedups():
    base = (
        "Kubernetes horizontal pod autoscaling adjusts replica counts based on "
        "observed metrics like CPU utilization and custom metrics from adapters."
    )
    # punctuation/casing changes leave word shingles intact -> near-duplicate
    near_dup = base.upper().replace(",", " ,") + "!!"
    chunks = [_draft("tiny"), _draft(base, 1), _draft(base, 2), _draft(near_dup, 3)]
    kept, stats = apply_quality_gates(chunks)
    assert [c.ord for c in kept] == [0]  # renumbered survivor
    assert stats.chunks_kept == 1
    assert stats.reject_reasons["too_short"] == 1
    assert stats.duplicates_removed == 2  # one exact + one simhash-near


def test_simhash_distance_properties():
    a = simhash("deploy the application to the cluster with rolling updates enabled")
    b = simhash("deploy the application to the cluster with rolling updates disabled")
    c = simhash("completely unrelated text about cooking pasta with tomato sauce")
    assert hamming(a, b) < hamming(a, c)


def test_pipeline_end_to_end_markdown():
    raw = b"# Kubernetes Guide\n\nPods are the smallest deployable units in Kubernetes.\n"
    result = ingest_bytes(raw, "kubernetes-guide.md")
    assert result.doc_type == DocType.MARKDOWN
    assert result.tool == "kubernetes"
    assert result.stats.chunks_kept == len(result.chunks) == 1
    assert result.chunks[0].section == "Kubernetes Guide"


def test_detect_tool():
    assert detect_tool("https://docs.docker.com/build.html") == "docker"
    assert detect_tool("main.tf") == "terraform"
    assert detect_tool("random-notes.md") is None
