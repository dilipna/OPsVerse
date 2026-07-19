"""Guards the one GPU-free integration risk in train_opslm_qlora.py: that the
SFT `messages` shape feeds the chat template correctly. Runs `format_chat`
over the REAL generated SFT data (when present) with a stub tokenizer."""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "train_opslm", REPO / "training" / "scripts" / "train_opslm_qlora.py"
)
assert SPEC and SPEC.loader
train_opslm = importlib.util.module_from_spec(SPEC)
sys.modules["train_opslm"] = train_opslm
SPEC.loader.exec_module(train_opslm)


class StubTokenizer:
    """Mimics apply_chat_template: concatenates roles+contents like a template
    would, so we assert the messages reached it intact and in order."""

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        assert tokenize is False
        return "".join(f"<|{m['role']}|>{m['content']}" for m in messages)


def test_format_chat_renders_messages_in_order():
    batch = {
        "messages": [
            [
                {"role": "user", "content": "How do I scale an HPA?"},
                {"role": "assistant", "content": "Set target metrics."},
            ]
        ]
    }
    out = train_opslm.format_chat(StubTokenizer(), batch)
    assert out["text"] == ["<|user|>How do I scale an HPA?<|assistant|>Set target metrics."]


def test_format_chat_over_real_sft_data_if_present():
    train_file = REPO / "data" / "sft" / "train.jsonl"
    if not train_file.exists():
        return  # DVC content not pulled in this environment; unit test above covers logic
    lines = train_file.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line]
    batch = {"messages": [r["messages"] for r in rows[:32]]}
    out = train_opslm.format_chat(StubTokenizer(), batch)
    assert len(out["text"]) == len(batch["messages"])
    # every rendered example carries both turns
    assert all("<|user|>" in t and "<|assistant|>" in t for t in out["text"])
