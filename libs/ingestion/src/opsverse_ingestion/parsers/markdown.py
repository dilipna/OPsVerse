import re

from opsverse_ingestion.parsers.common import decode
from opsverse_ingestion.schemas import DocType, ParsedDocument, Segment

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def parse_markdown(raw: bytes, source: str) -> ParsedDocument:
    """One segment per heading section; the section label is the heading path
    (e.g. "Install > Linux"). Fenced code blocks stay inside their section."""
    text = decode(raw, source)
    segments: list[Segment] = []
    heading_stack: list[tuple[int, str]] = []
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        body = "\n".join(buffer).strip()
        buffer.clear()
        if body:
            section = " > ".join(title for _, title in heading_stack) or None
            segments.append(Segment(text=body, section=section))

    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            buffer.append(line)
            continue
        match = None if in_fence else _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, match.group(2)))
        else:
            buffer.append(line)
    flush()
    return ParsedDocument(doc_type=DocType.MARKDOWN, source=source, segments=segments)
