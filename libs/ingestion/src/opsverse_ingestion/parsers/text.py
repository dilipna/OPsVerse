from opsverse_ingestion.parsers.common import decode
from opsverse_ingestion.schemas import DocType, ParsedDocument, Segment


def parse_text(raw: bytes, source: str) -> ParsedDocument:
    """One segment per blank-line-separated paragraph block."""
    text = decode(raw, source)
    segments = [Segment(text=block.strip()) for block in text.split("\n\n") if block.strip()]
    return ParsedDocument(doc_type=DocType.TEXT, source=source, segments=segments)
