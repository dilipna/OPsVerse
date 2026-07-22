"""Grammar-constrained (schema-guided) decoding via token masking.

Structured-output serving guarantees valid JSON by *masking* the vocabulary at
each decode step to only the tokens a grammar can still accept — the model
never even sees structurally-invalid tokens, so it cannot emit them. This is
how vLLM/SGLang guided decoding (XGrammar, Outlines, lm-format-enforcer) makes
`json_parse_rate` 1.0 by construction rather than by hoping the model behaves.

This module implements that masking for a **flat JSON object schema** (ordered
string / boolean fields) at the character level — a character *is* the token in
this toy vocabulary, which keeps the FSM legible and fully unit-testable. The
load-bearing property, verified in tests: whatever the model *wants* (even an
adversarial scorer that prefers structural garbage), the constrained output is
always schema-valid JSON. On a served model the identical idea runs as a
logits-processor, and its payoff is measured directly by the committed
structured-output evalset (ADR-0012): parse/field-accuracy under guided decoding.

Integer/float/nested-object fields are a deliberate, documented extension point
(see ADR-0014) — string+boolean already demonstrates the masking mechanism
without dragging in number-delimiter edge cases.
"""

from __future__ import annotations

from collections.abc import Callable

# A scorer models the LM: given the text emitted so far, return candidate chars
# in the model's preferred order. Constrained decoding picks its top *allowed* one.
Scorer = Callable[[str], list[str]]

_STRING_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789 -_/.:")


class _Literal:
    """A fixed structural span (braces, quoted keys, colons, commas)."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._i = 0

    def allowed(self) -> set[str]:
        return {self._text[self._i]} if self._i < len(self._text) else set()

    def feed(self, ch: str) -> bool:
        if self._i < len(self._text) and ch == self._text[self._i]:
            self._i += 1
            return True
        return False

    def done(self) -> bool:
        return self._i >= len(self._text)


class _StringVal:
    """A JSON string value: opening quote, content chars, closing quote."""

    def __init__(self) -> None:
        self._state = "open"  # open -> body -> closed

    def allowed(self) -> set[str]:
        if self._state == "open":
            return {'"'}
        if self._state == "body":
            return set(_STRING_CHARS) | {'"'}  # any content char, or close
        return set()

    def feed(self, ch: str) -> bool:
        if self._state == "open" and ch == '"':
            self._state = "body"
            return True
        if self._state == "body":
            if ch == '"':
                self._state = "closed"
                return True
            if ch in _STRING_CHARS:
                return True
        return False

    def done(self) -> bool:
        return self._state == "closed"


class _BoolVal:
    """A JSON boolean: the model chooses `true` or `false`, then it's forced."""

    def __init__(self) -> None:
        self._remaining = ""  # forced literal tail once the first char is chosen
        self._started = False
        self._done = False

    def allowed(self) -> set[str]:
        if self._done:
            return set()
        if not self._started:
            return {"t", "f"}
        return {self._remaining[0]}

    def feed(self, ch: str) -> bool:
        if self._done:
            return False
        if not self._started:
            if ch == "t":
                self._remaining, self._started = "rue", True
                return True
            if ch == "f":
                self._remaining, self._started = "alse", True
                return True
            return False
        if ch == self._remaining[0]:
            self._remaining = self._remaining[1:]
            if not self._remaining:
                self._done = True
            return True
        return False

    def done(self) -> bool:
        return self._done


def _matcher_for(field_type: str):
    if field_type == "string":
        return _StringVal()
    if field_type == "boolean":
        return _BoolVal()
    raise ValueError(f"unsupported field type: {field_type!r} (string|boolean)")


class SchemaFSM:
    """FSM for a flat JSON object with ordered (key, type) fields.

    `allowed()` returns exactly the set of characters that keep the output on a
    path to a valid document — the mask a guided decoder applies each step.
    """

    def __init__(self, fields: list[tuple[str, str]]) -> None:
        if not fields:
            raise ValueError("schema needs at least one field")
        program: list = [_Literal("{")]
        for idx, (key, ftype) in enumerate(fields):
            if idx > 0:
                program.append(_Literal(","))
            program.append(_Literal(f'"{key}":'))
            program.append(_matcher_for(ftype))
        program.append(_Literal("}"))
        self._program = program

    def _current(self):
        for matcher in self._program:
            if not matcher.done():
                return matcher
        return None

    def allowed(self) -> set[str]:
        current = self._current()
        return current.allowed() if current is not None else set()

    def feed(self, ch: str) -> bool:
        current = self._current()
        return current is not None and current.feed(ch)

    def done(self) -> bool:
        return self._current() is None


def constrained_decode(scorer: Scorer, fsm: SchemaFSM, max_steps: int = 512) -> str:
    """Greedy decode under the FSM mask: at each step emit the scorer's most
    preferred character that the grammar still allows. Guaranteed to yield a
    schema-valid JSON string (or raise if the scorer/grammar cannot progress,
    which for these schemas only happens if max_steps is set pathologically low).
    """
    out: list[str] = []
    for _ in range(max_steps):
        if fsm.done():
            return "".join(out)
        allowed = fsm.allowed()
        ranked = scorer("".join(out))
        choice = next((c for c in ranked if c in allowed), None)
        if choice is None:
            # Model expressed no valid preference; fall back deterministically to
            # the lexicographically-first legal char so decoding always advances.
            choice = min(allowed)
        assert fsm.feed(choice)  # choice came from `allowed`, so this holds
        out.append(choice)
    if not fsm.done():
        raise RuntimeError("constrained_decode hit max_steps before completing the schema")
    return "".join(out)
