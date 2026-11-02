"""Output guard: make model answers safe to render before they reach a browser.

Threat (threat model T-03, OWASP LLM05 improper output handling): a document
that slips past the ingest scan can steer the model into writing Markdown
such as an image whose URL carries conversation text in its query string.
A Markdown renderer fetches images automatically, so the data would leave
with no click at all. Links to unknown hosts are the same risk with one click.

Policy, applied to every answer:
- images (Markdown, reference-style or HTML `<img>`) are removed; an answer
  never needs to load a remote image;
- links and autolinks are kept only for allowlisted hosts (the hosts of the
  retrieved sources plus official documentation sites); others keep their
  text and lose the URL;
- non-http(s) link schemes (`javascript:`, `data:` ...) are removed;
- credential-shaped strings are redacted with the same patterns as ingest.

Limitation: rewriting is purely syntactic, so it also applies inside code
blocks, where Markdown would not render it. That trades a rare cosmetic
change for not having to parse Markdown correctly in a streaming setting.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from urllib.parse import urlsplit

from pydantic import BaseModel

from opsverse_security.redact import redact_secrets

DEFAULT_ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "kubernetes.io",
        "docs.docker.com",
        "developer.hashicorp.com",
        "mlflow.org",
        "github.com",
        "prometheus.io",
        "helm.sh",
    }
)

_TITLE = r'(?:\s+"[^"\n]*")?'
_MD_IMAGE = re.compile(r"!\[([^\]\n]*)\]\(\s*<?([^)\s>]*)>?" + _TITLE + r"\s*\)")
_REF_IMAGE = re.compile(r"!\[([^\]\n]*)\]\[[^\]\n]*\]")
_HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_MD_LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\(\s*<?([^)\s>]*)>?" + _TITLE + r"\s*\)")
_AUTOLINK = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.-]*:[^>\s]+)>")
_REF_DEFINITION = re.compile(r"^( {0,3}\[[^\]\n]+\]:[ \t]*)(\S+)(.*)$", re.MULTILINE)


class GuardResult(BaseModel):
    text: str
    findings: dict[str, int] = {}


def hosts_from_sources(sources: Iterable[str]) -> set[str]:
    """Hosts of retrieved source URIs; non-URL sources contribute nothing."""
    hosts: set[str] = set()
    for source in sources:
        parts = urlsplit(source)
        if parts.scheme in {"http", "https"} and parts.hostname:
            hosts.add(parts.hostname.lower())
    return hosts


class OutputGuard:
    def __init__(self, allowed_hosts: Iterable[str] = DEFAULT_ALLOWED_HOSTS):
        self._allowed = {h.lower().lstrip(".") for h in allowed_hosts}

    def _url_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"}:
            return False
        host = (parts.hostname or "").lower()
        return any(host == a or host.endswith("." + a) for a in self._allowed)

    def sanitize(self, text: str) -> GuardResult:
        found: Counter[str] = Counter()

        def drop_image(match: re.Match[str]) -> str:
            found["image_removed"] += 1
            alt = match.group(1).strip() if match.groups() else ""
            return f"[image removed{': ' + alt if alt else ''}]"

        def drop_html_image(match: re.Match[str]) -> str:
            found["image_removed"] += 1
            return "[image removed]"

        def check_link(match: re.Match[str]) -> str:
            label, url = match.group(1), match.group(2)
            if url.startswith("#") or self._url_allowed(url):
                return match.group(0)
            found["link_removed"] += 1
            return f"{label} [link removed]"

        def check_autolink(match: re.Match[str]) -> str:
            if self._url_allowed(match.group(1)):
                return match.group(0)
            found["link_removed"] += 1
            return "[link removed]"

        def check_definition(match: re.Match[str]) -> str:
            if self._url_allowed(match.group(2).strip("<>")):
                return match.group(0)
            found["link_removed"] += 1
            return f"{match.group(1)}#link-removed"

        text = _MD_IMAGE.sub(drop_image, text)
        text = _REF_IMAGE.sub(drop_image, text)
        text = _HTML_IMAGE.sub(drop_html_image, text)
        text = _MD_LINK.sub(check_link, text)
        text = _AUTOLINK.sub(check_autolink, text)
        text = _REF_DEFINITION.sub(check_definition, text)
        redaction = redact_secrets(text)
        for kind, count in redaction.findings.items():
            found[f"secret_redacted:{kind}"] += count
        return GuardResult(text=redaction.text, findings=dict(found))


class StreamingOutputGuard:
    """Apply `OutputGuard` to a token stream without splitting a construct.

    Text is released one complete line at a time: the patterns never span a
    newline, so a line is the smallest unit that can be checked safely. A
    line longer than `max_buffer` is released whole to bound latency.
    """

    def __init__(self, guard: OutputGuard, max_buffer: int = 4096):
        self._guard = guard
        self._buffer = ""
        self._max = max_buffer
        self.findings: Counter[str] = Counter()

    def _release(self, text: str) -> str:
        result = self._guard.sanitize(text)
        self.findings.update(result.findings)
        return result.text

    def feed(self, text: str) -> str:
        self._buffer += text
        cut = self._buffer.rfind("\n")
        if cut == -1:
            if len(self._buffer) < self._max:
                return ""
            cut = len(self._buffer) - 1
        ready, self._buffer = self._buffer[: cut + 1], self._buffer[cut + 1 :]
        return self._release(ready)

    def flush(self) -> str:
        ready, self._buffer = self._buffer, ""
        return self._release(ready) if ready else ""
