from bs4 import BeautifulSoup
from bs4.element import Tag

from opsverse_ingestion.parsers.common import decode
from opsverse_ingestion.schemas import DocType, ParsedDocument, Segment

_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_CONTENT = {"p", "li", "pre", "td", "th", "dd", "dt", "blockquote"}


def parse_html(raw: bytes, source: str) -> ParsedDocument:
    """Heading-sectioned text extraction; script/style/nav chrome is dropped."""
    soup = BeautifulSoup(decode(raw, source), "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    segments: list[Segment] = []
    heading_stack: list[tuple[int, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        buffer.clear()
        if body:
            section = " > ".join(title for _, title in heading_stack) or None
            segments.append(Segment(text=body, section=section))

    for el in soup.find_all(list(_HEADINGS) + sorted(_CONTENT)):
        if not isinstance(el, Tag):
            continue
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name in _HEADINGS:
            flush()
            level = _HEADINGS[el.name]
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, text))
        elif el.find(sorted(_CONTENT)) is None:  # skip containers; keep leaves only
            buffer.append(text)
    flush()
    return ParsedDocument(doc_type=DocType.HTML, source=source, segments=segments)
