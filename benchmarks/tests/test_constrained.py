"""Schema-guided decoding: the mask makes invalid JSON unreachable."""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "constrained", REPO / "benchmarks" / "techniques" / "constrained.py"
)
assert SPEC and SPEC.loader
constrained = importlib.util.module_from_spec(SPEC)
sys.modules["constrained"] = constrained
SPEC.loader.exec_module(constrained)

SchemaFSM = constrained.SchemaFSM
constrained_decode = constrained.constrained_decode

SCHEMA = [("severity", "string"), ("urgent", "boolean")]


def test_fsm_masks_to_only_valid_openers():
    fsm = SchemaFSM(SCHEMA)
    assert fsm.allowed() == {"{"}  # a document can only begin with '{'
    assert fsm.feed("{")
    assert fsm.allowed() == {'"'}  # then the first key's opening quote


def test_adversarial_scorer_still_yields_schema_valid_json():
    # This "model" always wants characters the grammar can never accept next
    # (uppercase, stray braces, symbols outside string content) and only reaches
    # '"' / letters far down its ranking — so every emission is forced by the mask.
    garbage = ["}", "{", "Z", "X", "!", "?", "@", "*"]
    preferred = [*garbage, '"', *list("truefalse abcdefghijklmnopqrstuvwxyz")]

    def scorer(_prefix: str) -> list[str]:
        return preferred

    out = constrained_decode(scorer, SchemaFSM(SCHEMA))
    parsed = json.loads(out)  # must parse
    assert set(parsed) == {"severity", "urgent"}
    assert isinstance(parsed["severity"], str)
    assert isinstance(parsed["urgent"], bool)


def test_cooperative_scorer_emits_intended_content():
    # A model that spells "high" then closes, and prefers 'true'.
    plan = {
        "": ["h"], "h": ["i"], "hi": ["g"], "hig": ["h"], "high": ['"'],
    }

    def scorer(prefix_out: str) -> list[str]:
        # `prefix_out` is the whole emitted string; key off the string content.
        content = prefix_out.split('"severity":"', 1)[-1]
        if content in plan:
            return plan[content]
        return ['"', "t", *list("truefalse abcdefghijklmnopqrstuvwxyz")]

    out = constrained_decode(scorer, SchemaFSM(SCHEMA))
    parsed = json.loads(out)
    assert parsed["severity"] == "high"
    assert parsed["urgent"] is True


def test_boolean_false_branch():
    def scorer(_prefix: str) -> list[str]:
        # close the string immediately, then prefer 'f' for the boolean
        return ['"', "f", *list("alse")]

    out = constrained_decode(scorer, SchemaFSM(SCHEMA))
    assert json.loads(out) == {"severity": "", "urgent": False}


def test_three_field_schema_roundtrips():
    schema = [("component", "string"), ("severity", "string"), ("paged", "boolean")]

    def scorer(_prefix: str) -> list[str]:
        return ['"', "t", *list("abcdefghijklmnopqrstuvwxyz")]

    out = constrained_decode(scorer, SchemaFSM(schema))
    parsed = json.loads(out)
    assert list(parsed) == ["component", "severity", "paged"]
    assert parsed["paged"] is True
