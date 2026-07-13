import pytest

from opsverse_ingestion.parsers import UnsupportedDocumentError, detect_doc_type, parse_document
from opsverse_ingestion.parsers.common import DecodingError

MARKDOWN = b"""# Install

Intro paragraph.

## Linux

Use the package manager.

```bash
apt install thing
```

## Windows

Download the installer.
"""

K8S_YAML = b"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 2
---
apiVersion: v1
kind: Service
metadata:
  name: web-svc
"""

TERRAFORM = b"""provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "logs" {
  bucket = "my-logs"
  tags = {
    env = "prod"
  }
}
"""

DOCKERFILE = b"""FROM python:3.12 AS builder
RUN pip install uv

FROM python:3.12-slim
COPY --from=builder /app /app
"""

HTML = b"""<html><head><script>bad()</script></head><body>
<h1>Guide</h1><p>Welcome text.</p>
<h2>Setup</h2><p>Run the setup command.</p><ul><li>step one</li></ul>
</body></html>"""


def test_markdown_heading_paths():
    doc = parse_document(MARKDOWN, "guide.md")
    sections = [s.section for s in doc.segments]
    assert "Install" in sections
    assert "Install > Linux" in sections
    assert "Install > Windows" in sections
    linux = next(s for s in doc.segments if s.section == "Install > Linux")
    assert "apt install thing" in linux.text


def test_yaml_splits_per_k8s_resource():
    doc = parse_document(K8S_YAML, "deploy.yaml")
    assert [s.section for s in doc.segments] == ["Deployment/web", "Service/web-svc"]
    assert all(s.language == "yaml" for s in doc.segments)


def test_terraform_splits_per_block():
    doc = parse_document(TERRAFORM, "main.tf")
    assert len(doc.segments) == 2
    assert doc.segments[0].section == "provider aws"
    assert doc.segments[1].section == "resource aws_s3_bucket logs"
    assert doc.segments[1].text.rstrip().endswith("}")
    assert "tags" in doc.segments[1].text  # nested braces stay inside the block


def test_dockerfile_splits_per_stage():
    doc = parse_document(DOCKERFILE, "Dockerfile")
    assert len(doc.segments) == 2
    assert doc.segments[0].text.startswith("FROM python:3.12 AS builder")
    assert doc.segments[1].text.startswith("FROM python:3.12-slim")


def test_html_drops_script_and_sections_by_heading():
    doc = parse_document(HTML, "guide.html")
    all_text = " ".join(s.text for s in doc.segments)
    assert "bad()" not in all_text
    assert any(s.section == "Guide > Setup" for s in doc.segments)


def test_binary_rejected():
    with pytest.raises(DecodingError):
        parse_document(b"\x00\x01\x02", "weird.md")


def test_unknown_extension_rejected():
    with pytest.raises(UnsupportedDocumentError):
        detect_doc_type("photo.png")
