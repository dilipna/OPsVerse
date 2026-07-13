from opsverse_ingestion.schemas import DocType, ParsedDocument, Segment


def parse_pdf(raw: bytes, source: str) -> ParsedDocument:
    """PDF parsing via Docling. Optional because Docling pulls in PyTorch;
    install with: uv add "opsverse-ingestion[pdf]" --package opsverse-ingestion
    """
    try:
        from docling.document_converter import (  # pyright: ignore[reportMissingImports]
            DocumentConverter,
        )
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "PDF support requires the optional 'pdf' extra: opsverse-ingestion[pdf]"
        ) from exc

    import io

    from docling.datamodel.base_models import (  # pyright: ignore[reportMissingImports]
        DocumentStream,
    )

    converter = DocumentConverter()
    result = converter.convert(DocumentStream(name=source, stream=io.BytesIO(raw)))
    markdown = result.document.export_to_markdown()

    from opsverse_ingestion.parsers.markdown import parse_markdown

    parsed = parse_markdown(markdown.encode("utf-8"), source)
    return ParsedDocument(
        doc_type=DocType.PDF,
        source=source,
        segments=parsed.segments or [Segment(text=markdown)],
    )
