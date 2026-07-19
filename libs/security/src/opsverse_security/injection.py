"""Heuristic prompt-injection detection, treated as a classifier with an eval.

Scores a text for instruction-override content. Used two ways:
- ingest-time (the serious threat for RAG): documents carrying instructions
  aimed at the assistant get quarantined before they can enter retrieval;
- query-time (defense-in-depth): suspicious user queries are flagged in the
  request ledger, not blocked — the platform is read-only RAG, and DevOps
  vocabulary ("override", "ignore files", "system:masters") makes blocking
  on heuristics an FPR trap. See ADR-0007.

Measured TPR/specificity against evalsets/security-redteam-v1.jsonl via
`python -m opsverse_security.evaluate`; thresholds pinned in the regression
gate. This is a heuristic layer — it catches the commodity attacks, and the
eval says exactly how much.
"""

import re

from pydantic import BaseModel

# Weighted signals. Each pattern is written against *imperatives aimed at an
# AI assistant*, not DevOps prose that shares surface words.
_SIGNALS: list[tuple[str, float, re.Pattern[str]]] = [
    # direct instruction override
    (
        "override_instructions",
        2.0,
        re.compile(
            r"(?i)\b(ignore|disregard|forget|override)\b[^.\n]{0,40}"
            r"\b(previous|prior|above|earlier|all|your)\b[^.\n]{0,40}"
            r"\b(instruction|prompt|rule|guideline|direction|context)s?\b"
        ),
    ),
    # persona hijack
    (
        "persona_hijack",
        1.5,
        re.compile(
            r"(?i)\b(you are now|act as|pretend to be|roleplay as|from now on you)\b"
            r"[^.\n]{0,60}\b(unrestricted|jailbroken|DAN|no (?:rules|filter|restriction)s?|"
            r"different (?:AI|assistant|persona))\b"
        ),
    ),
    # system-prompt / instruction exfiltration
    (
        "prompt_exfiltration",
        2.0,
        re.compile(
            r"(?i)\b(reveal|show|print|repeat|output|tell me)\b[^.\n]{0,40}"
            r"\b(system prompt|your (?:instructions|prompt|rules)|initial prompt|"
            r"hidden (?:instructions|prompt))\b"
        ),
    ),
    # addressed-to-the-model imperatives embedded in documents
    (
        "assistant_directive",
        1.5,
        re.compile(
            r"(?i)^\s*(?:SYSTEM|ASSISTANT|AI|IMPORTANT INSTRUCTION)S?\s*[:>\]]"
            r"[^\n]{0,120}\b(you must|always|never|do not tell|without telling)\b",
            re.MULTILINE,
        ),
    ),
    # exfiltration-of-context demands
    (
        "context_exfiltration",
        1.5,
        re.compile(
            r"(?i)\b(send|post|forward|exfiltrate|transmit)\b[^.\n]{0,50}"
            r"\b(conversation|chat history|context|these documents|user data)\b"
            r"[^.\n]{0,50}\bhttps?://"
        ),
    ),
    # refusal-suppression framing
    (
        "refusal_suppression",
        1.0,
        re.compile(
            r"(?i)\b(do not|don't|never)\b[^.\n]{0,30}\b(refuse|decline|say no|"
            r"mention (?:policy|rules|guidelines))\b"
        ),
    ),
    # concealment: asking the model to hide its behavior from the user
    (
        "conceal_from_user",
        1.5,
        re.compile(
            r"(?i)\b(do not|don't|without|never)\b[^.\n]{0,20}"
            r"\b(tell|telling|inform|informing|notify|alert|mention to)\b"
            r"[^.\n]{0,20}\b(the )?(user|anyone|them|him|her)\b"
        ),
    ),
]

SUSPICION_THRESHOLD = 1.5


class InjectionVerdict(BaseModel):
    score: float
    matched: list[str] = []

    @property
    def is_suspicious(self) -> bool:
        return self.score >= SUSPICION_THRESHOLD


def scan_injection(text: str) -> InjectionVerdict:
    score = 0.0
    matched: list[str] = []
    for name, weight, pattern in _SIGNALS:
        if pattern.search(text):
            score += weight
            matched.append(name)
    return InjectionVerdict(score=score, matched=matched)
