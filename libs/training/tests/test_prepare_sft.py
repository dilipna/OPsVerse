"""Tests for the SFT prep script (training/scripts/prepare_sft.py).

The script lives outside the package tree, so load it by path.
"""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "prepare_sft", REPO / "training" / "scripts" / "prepare_sft.py"
)
assert SPEC and SPEC.loader
prepare_sft = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_sft)


def _pair_line(uid: str, user: str, assistant: str) -> str:
    return json.dumps(
        {
            "id": uid,
            "format": "qa",
            "messages": [
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ],
            "source_chunk_ids": ["c1"],
            "tool": "docker",
            "generator_model": "gemini/test",
        }
    )


def test_prepare_splits_and_writes_chat_format(tmp_path: Path, monkeypatch):
    inp = tmp_path / "instructions.jsonl"
    inp.write_text(
        "\n".join(
            _pair_line(f"c{i}:qa", f"How do I do docker thing {i}?", f"Do it like {i}.")
            for i in range(20)
        ),
        encoding="utf-8",
    )
    # a frozen eval set so the guard is non-empty
    evalsets = tmp_path / "evalsets"
    evalsets.mkdir()
    (evalsets / "retrieval-v1.jsonl").write_text(
        json.dumps({"name": "retrieval-v1", "version": "1", "generator_model": "g"})
        + "\n"
        + json.dumps(
            {
                "id": "x",
                "question": "totally unrelated question about kubernetes services",
                "relevant_chunk_ids": ["x"],
                "relevant_document_ids": ["d"],
                "source": "s",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "sft"
    monkeypatch.setattr(
        "sys.argv",
        ["prepare_sft.py", "--in", str(inp), "--out", str(out), "--evalsets", str(evalsets)],
    )
    prepare_sft.main()

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["total_pairs"] == 20
    assert manifest["train"] + manifest["val"] == 20
    assert manifest["val"] >= 1
    # TRL-ready chat rows
    first = json.loads((out / "train.jsonl").read_text().splitlines()[0])
    assert set(first) == {"messages"}
    assert first["messages"][0]["role"] == "user"


def test_prepare_drops_eval_contaminated_pairs(tmp_path: Path, monkeypatch):
    leaked_q = "How does a Kubernetes HPA scale on custom metrics exactly?"
    inp = tmp_path / "instructions.jsonl"
    inp.write_text(
        _pair_line("c1:qa", leaked_q, "It uses a metrics adapter.")
        + "\n"
        + _pair_line("c2:qa", "How do I write a Dockerfile HEALTHCHECK?", "Use HEALTHCHECK."),
        encoding="utf-8",
    )
    evalsets = tmp_path / "evalsets"
    evalsets.mkdir()
    (evalsets / "retrieval-v1.jsonl").write_text(
        json.dumps({"name": "retrieval-v1", "version": "1", "generator_model": "g"})
        + "\n"
        + json.dumps(
            {
                "id": "x",
                "question": leaked_q,
                "relevant_chunk_ids": ["x"],
                "relevant_document_ids": ["d"],
                "source": "s",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "sft"
    monkeypatch.setattr(
        "sys.argv",
        ["prepare_sft.py", "--in", str(inp), "--out", str(out), "--evalsets", str(evalsets)],
    )
    prepare_sft.main()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["contaminated_dropped"] == 1
    assert manifest["train"] + manifest["val"] == 1
