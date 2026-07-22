"""Preference-pair schema + TRL DPO format (the parts that must be exact)."""

import pytest

from opsverse_training.preferences import (
    PreferenceError,
    PreferencePair,
    build_preference_pair,
    build_reject_messages,
)

SFT_ROW = {
    "id": "chunk123:qa",
    "messages": [
        {"role": "user", "content": "How do I check why a pod was OOMKilled?"},
        {
            "role": "assistant",
            "content": "Run `kubectl describe pod <name>` and read Last State: Reason=OOMKilled.",
        },
    ],
}


def test_to_trl_is_conversational_dpo_format():
    pair = PreferencePair(
        id="x:dpo", prompt="q?", chosen="good", rejected="bad", generator_model="m"
    )
    trl = pair.to_trl()
    assert trl == {
        "prompt": [{"role": "user", "content": "q?"}],
        "chosen": [{"role": "assistant", "content": "good"}],
        "rejected": [{"role": "assistant", "content": "bad"}],
    }


def test_build_from_sft_row_uses_grounded_answer_as_chosen():
    pair = build_preference_pair(
        SFT_ROW,
        reject_fn=lambda q: "Just run `kubectl oom --fix`, it always works.",
        generator_model="gemini/flash-lite",
    )
    assert pair.prompt.startswith("How do I check")
    assert "OOMKilled" in pair.chosen  # chosen is the grounded SFT answer
    assert pair.rejected.startswith("Just run")
    assert pair.id == "chunk123:qa:dpo"
    assert pair.source_id == "chunk123:qa"


def test_identical_sides_are_rejected():
    same = "Run `kubectl describe pod <name>` and read Last State: Reason=OOMKilled."
    with pytest.raises(PreferenceError):
        build_preference_pair(SFT_ROW, reject_fn=lambda q: same)


def test_empty_rejected_is_rejected():
    with pytest.raises(PreferenceError):
        build_preference_pair(SFT_ROW, reject_fn=lambda q: "   ")


def test_malformed_row_is_rejected():
    with pytest.raises(PreferenceError):
        build_preference_pair({"messages": []}, reject_fn=lambda q: "x")


def test_reject_prompt_carries_question_and_system():
    msgs = build_reject_messages("why is my ingress 502?")
    assert msgs[0]["role"] == "system" and "DISPREFERRED" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "why is my ingress 502?"}
