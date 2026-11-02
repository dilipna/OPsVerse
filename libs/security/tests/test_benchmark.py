"""Security benchmark: dataset pinning, statistics and the no-text report. Offline."""

import io
import json

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rype_security import benchmark
from rype_security.benchmark import (
    DatasetPinError,
    DatasetSpec,
    Row,
    evaluate,
    mcnemar_exact,
    parse_parquet,
    record_pin,
    render_markdown,
    sha256,
    wilson,
)

SPEC = DatasetSpec("tiny", "org/tiny", "test")


def parquet_bytes(texts, labels) -> bytes:
    sink = io.BytesIO()
    pq.write_table(pa.table({"text": texts, "label": labels}), sink)
    return sink.getvalue()


def test_wilson_interval_known_values():
    low, high = wilson(0, 10)
    assert low == 0.0 and 0.27 < high < 0.29  # 0/10 is not "0% with certainty"
    low, high = wilson(50, 100)
    assert 0.40 < low < 0.41 and 0.59 < high < 0.60
    assert wilson(0, 0) == (0.0, 1.0)


def test_mcnemar_exact_values():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(0, 5) == pytest.approx(0.0625)  # 2 * 0.5**5
    assert mcnemar_exact(3, 3) == 1.0


def test_evaluate_counts_errors_separately_and_reports_layering():
    rows = [
        Row(0, "attack caught by both", True),
        Row(1, "attack only the model sees", True),
        Row(2, "attack the model errors on", True),
        Row(3, "benign the model flags", False),
        Row(4, "benign text", False),
    ]
    regex_hits = {0}
    verdicts = {0: True, 1: True, 2: None, 3: True, 4: False}

    # Stand in for the regex detector by index, so the test needs no attack text.
    def fake_scan(text):
        class V:
            is_suspicious = int(text.split("#")[1]) in regex_hits

        return V()

    benchmark_rows = [Row(r.index, f"row#{r.index}", r.is_attack) for r in rows]
    original = benchmark.scan_injection
    benchmark.scan_injection = fake_scan
    try:
        result = evaluate(benchmark_rows, lambda t: verdicts[int(t.split("#")[1])])
    finally:
        benchmark.scan_injection = original

    assert result["regex"]["confusion"] == {"tp": 1, "fn": 2, "fp": 0, "tn": 2}
    llm = result["llm"]
    assert llm["confusion"] == {"tp": 2, "fn": 0, "fp": 1, "tn": 1}
    assert llm["errors"] == 1
    assert llm["fail_closed"]["tpr"] == 1.0  # the error counted as a flag
    assert llm["fail_open_tpr"] == round(2 / 3, 4)  # reported to 4 places
    combined = result["regex_or_llm"]
    assert combined["confusion"]["tp"] == 2 and combined["errors"] == 1
    assert result["layering"] == {
        "attacks_gained": 1,
        "attacks_gained_p": 1.0,
        "false_alarms_added": 1,
        "false_alarms_added_p": 1.0,
    }
    assert result["regex"]["missed_indices"] == [1, 2]


def test_parse_parquet_maps_labels_and_drops_empty_text():
    data = parquet_bytes(["a", "", "b", None], [1, 0, 0, 1])
    rows = parse_parquet(data, SPEC)
    assert [(r.index, r.text, r.is_attack) for r in rows] == [(0, "a", True), (2, "b", False)]


def hf_handler(data: bytes, files=("data/train-0001.parquet", "data/test-0001.parquet")):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/datasets/org/tiny":
            return httpx.Response(
                200,
                json={"sha": "c0ffee" * 6 + "abcd", "siblings": [{"rfilename": f} for f in files]},
            )
        if "/resolve/" in request.url.path:
            return httpx.Response(200, content=data)
        return httpx.Response(404)

    return handler


def test_record_pin_resolves_commit_file_and_hash():
    data = parquet_bytes(["a"], [1])
    with httpx.Client(transport=httpx.MockTransport(hf_handler(data))) as client:
        pin = record_pin(SPEC, client)
    assert pin["file"] == "data/test-0001.parquet"
    assert pin["revision"].startswith("c0ffee")
    assert pin["sha256"] == sha256(data)


def test_record_pin_refuses_ambiguous_files():
    handler = hf_handler(b"", files=("data/test-1.parquet", "data/test-2.parquet"))
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(DatasetPinError, match="expected one"),
    ):
        record_pin(SPEC, client)


def test_tampered_download_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, "CACHE_DIR", tmp_path)
    good = parquet_bytes(["a"], [1])
    pin = {
        "repo": "org/tiny",
        "revision": "abc",
        "file": "data/test-0001.parquet",
        "sha256": sha256(good),
    }
    tampered = parquet_bytes(["changed"], [0])
    with (
        httpx.Client(transport=httpx.MockTransport(hf_handler(tampered))) as client,
        pytest.raises(DatasetPinError, match="does not match"),
    ):
        benchmark.fetch_pinned(SPEC, pin, client)
    with httpx.Client(transport=httpx.MockTransport(hf_handler(good))) as client:
        assert benchmark.fetch_pinned(SPEC, pin, client) == good
    assert (tmp_path / f"{pin['sha256']}.parquet").exists()


def test_report_contains_no_sample_text():
    rows = [Row(0, "UNIQUE-SAMPLE-TEXT-123", True), Row(1, "OTHER-SAMPLE-456", False)]
    results = evaluate(rows, lambda t: True)
    report = {
        "title": "t",
        "date": "2026-11-02",
        "model": "m",
        "prompt_version": "v1",
        "datasets": {
            "tiny": {
                "meta": {"description": "d", "rows": 2, "attacks": 1, "benign": 1},
                "results": results,
            }
        },
    }
    rendered = render_markdown(report) + json.dumps(report)
    assert "UNIQUE-SAMPLE-TEXT-123" not in rendered
    assert "OTHER-SAMPLE-456" not in rendered
    assert "| `llm` |" in rendered
