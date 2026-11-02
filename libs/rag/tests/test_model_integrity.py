"""Model file pinning: verification, failure modes and fastembed wiring. Offline."""

import hashlib
from types import SimpleNamespace

import pytest

from rype_rag.embeddings import FastEmbedEmbedder
from rype_rag.model_integrity import (
    ModelIntegrityError,
    hash_model_dir,
    verify_loaded,
    verify_model_dir,
)


@pytest.fixture
def model_dir(tmp_path):
    root = tmp_path / "models--org--embed" / "snapshots" / "abc"
    (root / "onnx").mkdir(parents=True)
    (root / "onnx" / "model.onnx").write_bytes(b"weights-v1")
    (root / "tokenizer.json").write_text("{}")
    (root / ".cache").mkdir()
    (root / ".cache" / "download.json").write_text("bookkeeping")
    (root / "model.onnx.lock").write_text("")
    return root


def pins_for(model_dir, name="org/embed"):
    return {name: {"files": hash_model_dir(model_dir)}}


def test_hashes_cover_model_files_only(model_dir):
    hashes = hash_model_dir(model_dir)
    assert set(hashes) == {"onnx/model.onnx", "tokenizer.json"}
    assert hashes["onnx/model.onnx"] == hashlib.sha256(b"weights-v1").hexdigest()


def test_symlinked_blobs_are_hashed_by_content(tmp_path):
    blob = tmp_path / "blobs" / "deadbeef"
    blob.parent.mkdir()
    blob.write_bytes(b"real bytes")
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "model.onnx").symlink_to(blob)
    assert hash_model_dir(snap)["model.onnx"] == hashlib.sha256(b"real bytes").hexdigest()


def test_matching_files_pass(model_dir):
    verify_model_dir("org/embed", model_dir, "enforce", pins_for(model_dir))


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        (
            lambda d: (d / "onnx" / "model.onnx").write_bytes(b"weights-EVIL"),
            "changed onnx/model.onnx",
        ),
        (lambda d: (d / "extra.py").write_text("print(1)"), r"unexpected extra\.py"),
        (lambda d: (d / "tokenizer.json").unlink(), r"missing tokenizer\.json"),
    ],
)
@pytest.mark.parametrize("mode", ["enforce", "warn"])
def test_any_drift_fails_in_every_checking_mode(model_dir, tamper, expected, mode):
    pins = pins_for(model_dir)
    tamper(model_dir)
    with pytest.raises(ModelIntegrityError, match=expected):
        verify_model_dir("org/embed", model_dir, mode, pins)


def test_unpinned_model_depends_on_mode(model_dir, caplog):
    with pytest.raises(ModelIntegrityError, match="no pinned hashes"):
        verify_model_dir("org/other", model_dir, "enforce", {})
    verify_model_dir("org/other", model_dir, "warn", {})
    assert "no pinned hashes" in caplog.text
    verify_model_dir("org/other", model_dir / "missing", "off", {})  # off never touches disk


def test_verify_loaded_reads_fastembed_model_dir(model_dir):
    loaded = SimpleNamespace(model=SimpleNamespace(_model_dir=str(model_dir)))
    assert verify_loaded("org/embed", loaded, "enforce", pins_for(model_dir)) is loaded
    with pytest.raises(ModelIntegrityError, match="cannot locate"):
        verify_loaded("org/embed", SimpleNamespace(model=None), "enforce", {})


def test_embedder_refuses_a_tampered_model_before_embedding(model_dir, monkeypatch):
    import fastembed

    pins = pins_for(model_dir, "BAAI/bge-base-en-v1.5")
    (model_dir / "onnx" / "model.onnx").write_bytes(b"swapped")

    class FakeTextEmbedding:
        def __init__(self, model_name):
            self.model = SimpleNamespace(_model_dir=str(model_dir))

        def embed(self, texts):
            raise AssertionError("must not embed with an unverified model")

    monkeypatch.setattr(fastembed, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr("rype_rag.model_integrity.load_pins", lambda path=None: pins)
    embedder = FastEmbedEmbedder(pin_mode="enforce")
    with pytest.raises(ModelIntegrityError, match=r"changed onnx/model\.onnx"):
        embedder.embed_dense(["pods"])
