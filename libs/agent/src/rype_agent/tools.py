"""Tools the agent can call, and the documentation search behind one of them.

`search_docs` is a line-for-line port of the browser's evaluated term-overlap
ranker (`opslm-demo/lib/runbooks.mjs::search`, mode "overlap") over the same
pinned corpus (`opslm-demo/public/runbooks.json`), so the agent's documentation
evidence comes from the retrieval that `docs/reports/runbook-evaluation.json` scored.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CORPUS_PATH = Path("opslm-demo/public/runbooks.json")
# Same stopwords, in the same order, as opslm-demo/lib/runbooks.mjs.
_STOPWORDS = (
    "a an and are as at be by can do does for from how i if in is it me my of on or should "
    "that the this to was what when where which why will with you your"
)
_STOP = frozenset(_STOPWORDS.split())
_TERM = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")


def terms(text: str) -> list[str]:
    return [t for t in _TERM.findall(text.lower()) if len(t) > 1 and t not in _STOP]


def search(corpus: dict[str, Any], query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Term-overlap ranking, identical in behaviour to the browser implementation."""
    if len(query) > 500:
        raise ValueError("Use a question of 500 characters or fewer.")
    q = list(dict.fromkeys(terms(query)))
    if not q:
        return []
    chunks = corpus["chunks"]
    docs = [terms(c["text"]) for c in chunks]
    min_match = min(2, len(q))
    scored = []
    for chunk, d in zip(chunks, docs, strict=True):
        matched = sum(1 for t in q if t in d)
        if matched >= min_match:
            scored.append({**chunk, "score": matched, "matched": matched})
    scored.sort(key=lambda c: (-c["score"], c["id"]))
    return scored[:limit]


def load_corpus(path: Path = CORPUS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "kubectl",
            "description": (
                "Run one read-only kubectl command against the cluster and return its output. "
                "Allowed: get, describe, logs, rollout status|history on pods, deployments, "
                "services, endpoints, events, replicasets. Anything else is refused."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "e.g. kubectl get pods -n shop"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search the official Kubernetes documentation snapshot; returns short passages."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Submit the diagnosis. Call exactly once, when done investigating.",
            "parameters": {
                "type": "object",
                "properties": {
                    "root_cause": {
                        "type": "string",
                        "description": "One label from the allowed list.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Two to four sentences for the on-call engineer.",
                    },
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Short verbatim quotes from tool outputs supporting the diagnosis."
                        ),
                    },
                    "next_commands": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional read-only kubectl commands to suggest. Never executed."
                        ),
                    },
                },
                "required": ["root_cause", "summary", "evidence"],
            },
        },
    },
]
