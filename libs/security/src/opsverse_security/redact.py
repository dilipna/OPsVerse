"""Secret redaction for ingested documents and generated answers.

Deliberately scoped to *credential-shaped* strings with distinctive formats
(low false-positive risk). Things we do NOT redact, on purpose:
- IPv4/hostnames/ports — legitimate, load-bearing content in DevOps docs.
- Generic "password:" values in tutorial YAML — example creds ARE the docs
  (a compose tutorial with `POSTGRES_PASSWORD: example` must stay usable).
The rationale and the Presidio deferral live in ADR-0007.
"""

import re

from pydantic import BaseModel

# name -> compiled pattern. Each format is distinctive enough that a match is
# near-certainly a real credential shape, not prose.
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key_id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
    "github_pat_fine": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,255}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,250}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,100}\b"),
    "private_key_block": re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]{0,4000}?"
        r"-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    ),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    # assignment-style: api_key=..., secret_key: '...' with a long opaque value
    "assigned_secret": re.compile(
        r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\b"
        r"\s*[:=]\s*['\"]?(?!\{\{)[A-Za-z0-9_/+.-]{20,}['\"]?"
    ),
}


class RedactionResult(BaseModel):
    text: str
    findings: dict[str, int] = {}  # pattern name -> count

    @property
    def redacted(self) -> int:
        return sum(self.findings.values())


def redact_secrets(text: str) -> RedactionResult:
    """Replace credential-shaped strings with [REDACTED:<kind>] markers."""
    findings: dict[str, int] = {}
    for name, pattern in SECRET_PATTERNS.items():
        text, count = pattern.subn(f"[REDACTED:{name}]", text)
        if count:
            findings[name] = count
    return RedactionResult(text=text, findings=findings)
