"""Heuristic prompt-injection detection, treated as a classifier with an eval.

Scores a text for instruction-override content. Used two ways:
- ingest-time (the serious threat for RAG): documents carrying instructions
  aimed at the assistant get quarantined before they can enter retrieval;
- query-time (defense-in-depth): suspicious user queries are flagged in the
  request ledger, not blocked — the platform is read-only RAG, and DevOps
  vocabulary ("override", "ignore files", "system:masters") makes blocking
  on heuristics an FPR trap. See ADR-0007.

Measured TPR/specificity against evalsets/security-redteam-v1.jsonl via
`python -m rype_security.evaluate`; thresholds pinned in the regression
gate. This is a heuristic layer — it catches the commodity attacks, and the
eval says exactly how much.
"""

import re
import unicodedata

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

# Latin look-alikes from Cyrillic and Greek. A single substituted letter is
# enough to defeat a regex written against ASCII words, so text is folded to
# Latin before matching. Deliberately small: the letters that render
# identically to Latin in common fonts, not the full Unicode confusables table.
_CONFUSABLES = str.maketrans(
    "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u0458\u0455\u0501\u04cf"
    "\u04bb\u051b\u051d\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421"
    "\u0422\u0425\u0406\u0408\u0405\u03bf\u03b1\u03b5\u03b9\u03ba\u03bd\u03c1"
    "\u03c4\u03c5\u03c7\u039f\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c"
    "\u039d\u03a1\u03a4\u03a5\u03a7",
    "aeopcyxijsdlhqwABEKMHOPCTXIJSoaeikvptuxOABEZHIKMNPTYX",
)
_LATIN = re.compile(r"[A-Za-z]")
_LOOKALIKE = re.compile(r"[\u0370-\u03ff\u0400-\u04ff\u0500-\u052f]")
_WORD = re.compile(r"\S+")
_WHITESPACE = re.compile(r"\s+")


def _strip_invisible(text: str) -> tuple[str, int]:
    """Drop format characters (zero-width, bidi controls, soft hyphen...)."""
    kept = [ch for ch in text if unicodedata.category(ch) != "Cf"]
    return "".join(kept), len(text) - len(kept)


def _mixed_script_words(text: str) -> int:
    return sum(1 for w in _WORD.findall(text) if _LATIN.search(w) and _LOOKALIKE.search(w))


def normalize_for_scan(text: str) -> str:
    """The text a reader sees: compatibility forms folded (NFKC turns
    full-width letters into ASCII), invisible characters removed, look-alike
    letters mapped to Latin."""
    text, _ = _strip_invisible(unicodedata.normalize("NFKC", text))
    return text.translate(_CONFUSABLES)


class InjectionVerdict(BaseModel):
    score: float
    matched: list[str] = []

    @property
    def is_suspicious(self) -> bool:
        return self.score >= SUSPICION_THRESHOLD


# Obfuscation on its own is weak evidence (non-English text mixes scripts;
# copied terminal output can carry zero-width spaces), so it adds weight but
# can never cross the threshold alone.
OBFUSCATION_WEIGHT = 0.5


def scan_injection(text: str, *, normalize: bool = True) -> InjectionVerdict:
    """Score `text` for instructions aimed at the assistant.

    With `normalize` (the default) every signal is matched against two views
    of the normalized text: line structure kept (for line-anchored signals)
    and all whitespace collapsed (so splitting a phrase across lines does not
    hide it). `normalize=False` is the raw-regex baseline the robustness
    report compares against.
    """
    score = 0.0
    matched: list[str] = []
    views = [text]
    if normalize:
        normalized = normalize_for_scan(text)
        views = [normalized, _WHITESPACE.sub(" ", normalized)]
    for name, weight, pattern in _SIGNALS:
        if any(pattern.search(view) for view in views):
            score += weight
            matched.append(name)
    if normalize:
        _, invisible = _strip_invisible(text)
        if invisible or _mixed_script_words(unicodedata.normalize("NFKC", text)):
            score += OBFUSCATION_WEIGHT
            matched.append("obfuscation")
    return InjectionVerdict(score=score, matched=matched)
