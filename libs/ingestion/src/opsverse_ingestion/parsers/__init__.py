from pathlib import PurePosixPath

from opsverse_ingestion.parsers.code import parse_dockerfile, parse_terraform, parse_yaml
from opsverse_ingestion.parsers.html import parse_html
from opsverse_ingestion.parsers.markdown import parse_markdown
from opsverse_ingestion.parsers.text import parse_text
from opsverse_ingestion.schemas import DocType, ParsedDocument

_BY_EXTENSION = {
    ".md": (DocType.MARKDOWN, parse_markdown),
    ".markdown": (DocType.MARKDOWN, parse_markdown),
    ".html": (DocType.HTML, parse_html),
    ".htm": (DocType.HTML, parse_html),
    ".yaml": (DocType.YAML, parse_yaml),
    ".yml": (DocType.YAML, parse_yaml),
    ".tf": (DocType.TERRAFORM, parse_terraform),
    ".txt": (DocType.TEXT, parse_text),
}


class UnsupportedDocumentError(ValueError):
    pass


def detect_doc_type(source: str) -> DocType:
    name = PurePosixPath(source.replace("\\", "/")).name.lower()
    if name == "dockerfile" or name.startswith("dockerfile."):
        return DocType.DOCKERFILE
    suffix = PurePosixPath(name).suffix
    if suffix == ".pdf":
        return DocType.PDF
    if suffix in _BY_EXTENSION:
        return _BY_EXTENSION[suffix][0]
    raise UnsupportedDocumentError(f"unsupported document type: {source}")


def parse_document(raw: bytes, source: str) -> ParsedDocument:
    """Route raw bytes to the right parser based on the source name."""
    doc_type = detect_doc_type(source)
    if doc_type is DocType.DOCKERFILE:
        return parse_dockerfile(raw, source)
    if doc_type is DocType.PDF:
        from opsverse_ingestion.parsers.pdf import parse_pdf  # optional heavy dep

        return parse_pdf(raw, source)
    for ext_type, parser in _BY_EXTENSION.values():
        if ext_type is doc_type:
            return parser(raw, source)
    raise UnsupportedDocumentError(f"no parser for {doc_type}")  # pragma: no cover


SUPPORTED_EXTENSIONS = set(_BY_EXTENSION) | {".pdf"}
