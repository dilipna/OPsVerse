"""Structure-aware parsing for infra-as-code formats.

Chunk boundaries follow the format's own structure: one Kubernetes resource,
one Terraform block, one Dockerfile stage — never a mid-resource size split.
"""

import re
from itertools import pairwise

import yaml

from opsverse_ingestion.parsers.common import decode
from opsverse_ingestion.schemas import DocType, ParsedDocument, Segment

_YAML_DOC_SPLIT = re.compile(r"^---\s*$", re.MULTILINE)
_TF_BLOCK = re.compile(
    r"^(resource|module|data|provider|variable|output|locals|terraform)\b[^\n{]*\{",
    re.MULTILINE,
)
_FROM = re.compile(r"^\s*FROM\b", re.IGNORECASE | re.MULTILINE)


def _k8s_label(doc_text: str) -> str | None:
    try:
        data = yaml.safe_load(doc_text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or "kind" not in data or "apiVersion" not in data:
        return None
    name = data.get("metadata", {}).get("name") if isinstance(data.get("metadata"), dict) else None
    return f"{data['kind']}/{name}" if name else str(data["kind"])


def parse_yaml(raw: bytes, source: str) -> ParsedDocument:
    """One segment per YAML document; Kubernetes manifests get a Kind/name label."""
    text = decode(raw, source)
    segments = []
    for doc_text in _YAML_DOC_SPLIT.split(text):
        doc_text = doc_text.strip()
        if not doc_text:
            continue
        segments.append(Segment(text=doc_text, section=_k8s_label(doc_text), language="yaml"))
    return ParsedDocument(doc_type=DocType.YAML, source=source, segments=segments)


def parse_dockerfile(raw: bytes, source: str) -> ParsedDocument:
    """One segment per build stage (FROM ... FROM boundaries)."""
    text = decode(raw, source).strip()
    starts = [m.start() for m in _FROM.finditer(text)]
    if not starts:
        spans = [text] if text else []
    else:
        bounds = [0, *starts[1:], len(text)] if starts[0] == 0 else [0, *starts, len(text)]
        spans = [text[a:b].strip() for a, b in pairwise(bounds)]
    segments = [
        Segment(text=span, section=f"stage {i}", language="dockerfile")
        for i, span in enumerate(s for s in spans if s)
    ]
    return ParsedDocument(doc_type=DocType.DOCKERFILE, source=source, segments=segments)


def parse_terraform(raw: bytes, source: str) -> ParsedDocument:
    """One segment per top-level HCL block, found by brace matching."""
    text = decode(raw, source)
    segments: list[Segment] = []
    for match in _TF_BLOCK.finditer(text):
        depth, end = 0, len(text)
        for i in range(match.end() - 1, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        header = " ".join(text[match.start() : match.end() - 1].replace('"', "").split())
        segments.append(Segment(text=text[match.start() : end], section=header, language="hcl"))
    return ParsedDocument(doc_type=DocType.TERRAFORM, source=source, segments=segments)
