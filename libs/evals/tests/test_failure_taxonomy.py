import json
from pathlib import Path

import pytest

from opsverse_evals import failure_taxonomy as ft

GOLDEN = Path("evalsets/retrieval-golden-v1.jsonl")
RAW = Path("docs/reports/retrieval-ablation-v2-raw.json")
CODES = Path("evalsets/failure-taxonomy-v1-codes.jsonl")


@pytest.fixture(scope="module")
def flagged():
    golden = ft.load_golden(GOLDEN)
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    return golden, ft.extract_candidates(golden, raw, "hybrid")


def test_every_flagged_case_is_coded(flagged):
    """An uncoded case is a silent hole in the counts, so it must be impossible."""
    golden, cases = flagged
    report = ft.build(cases, ft.load_codes(CODES), total_queries=len(golden))
    assert report["uncoded"] == []
    assert report["coded"] == report["flagged"] == len(cases)


def test_codes_file_only_uses_declared_categories():
    for line in CODES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            assert row["code"] in ft.BY_CODE, row["code"]
            # a code without a note is an opinion, not error analysis
            assert len(row["note"]) > 30, row["case_id"]


def test_load_codes_rejects_an_unknown_category(tmp_path):
    bad = tmp_path / "codes.jsonl"
    bad.write_text('{"case_id":"x","code":"made_up","note":"n"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown code"):
        ft.load_codes(bad)


def test_categories_are_split_between_defects_and_artifacts():
    """The whole point of the taxonomy is this distinction, so both sides must exist."""
    real = [c for c in ft.CATEGORIES if c.real_defect]
    artifact = [c for c in ft.CATEGORIES if not c.real_defect]
    assert real and artifact
    assert len({c.code for c in ft.CATEGORIES}) == len(ft.CATEGORIES)
    for c in ft.CATEGORIES:
        assert c.what and c.fix and c.title


def test_extract_candidates_flags_each_signal_shape():
    golden = {
        "hit": {"question": "q", "grades": {"a": 3, "b": 2, "c": 0}},
        "miss": {"question": "q", "grades": {"a": 3, "b": 0}},
        "buried": {"question": "q", "grades": {"z": 3, "b": 0}},
    }
    raw = {
        "results": {
            "hybrid": [
                # every relevant chunk retrieved at the top -> not flagged
                {"case_id": "hit", "retrieved_chunk_ids": ["a", "b", "c"]},
                # relevant exists in pool but none retrieved
                {"case_id": "miss", "retrieved_chunk_ids": ["b"] * 10},
                # first relevant at rank 7
                {"case_id": "buried", "retrieved_chunk_ids": ["b"] * 6 + ["z"]},
            ]
        }
    }
    got = {c["case_id"]: c["signal"] for c in ft.extract_candidates(golden, raw, "hybrid")}
    assert got["miss"] == "no_relevant_in_top_k"
    assert got["buried"] == "first_relevant_buried"
    assert "hit" not in got


def test_extract_candidates_ignores_queries_with_no_relevant_chunk():
    golden = {"x": {"question": "q", "grades": {"a": 1, "b": 0}}}
    raw = {"results": {"hybrid": [{"case_id": "x", "retrieved_chunk_ids": ["a", "b"]}]}}
    assert ft.extract_candidates(golden, raw, "hybrid") == []


def test_build_separates_real_defects_from_artifacts(flagged):
    golden, cases = flagged
    report = ft.build(cases, ft.load_codes(CODES), total_queries=len(golden))
    assert report["real_defects"] + report["not_defects"] == report["coded"]
    # the headline claim of the report: most flagged failures are not defects
    assert report["not_defects"] > report["real_defects"]
    recomputed = sum(n for code, n in report["counts"].items() if ft.BY_CODE[code].real_defect)
    assert recomputed == report["real_defects"]


def test_render_names_the_coder_and_never_claims_a_human_did_it(flagged):
    golden, cases = flagged
    report = ft.build(cases, ft.load_codes(CODES), total_queries=len(golden))
    text = ft.render(report, "2026-09-07", "claude-opus-5", "language model")
    assert "claude-opus-5" in text
    assert "not a person" in text
    assert "No second coder" in text
    # the flag rate must never be presented as a failure rate
    assert "not a failure" in text or "not quoted as one" in text


def test_render_lists_only_real_defects_in_the_fix_list(flagged):
    golden, cases = flagged
    report = ft.build(cases, ft.load_codes(CODES), total_queries=len(golden))
    text = ft.render(report, "2026-09-07", "c", "language model")
    fixes = text.split("## What to fix next")[1].split("## Limits")[0]
    for cat in ft.CATEGORIES:
        if cat.code in report["counts"] and not cat.real_defect:
            assert cat.title not in fixes, cat.code


def test_generated_report_on_disk_is_current(flagged):
    out = Path("docs/reports/failure-taxonomy-v1.md")
    if not out.exists():
        pytest.skip("not generated yet")
    golden, cases = flagged
    report = ft.build(cases, ft.load_codes(CODES), total_queries=len(golden))
    on_disk = out.read_text(encoding="utf-8")
    assert f"**{report['real_defects']}**" in on_disk, (
        "failure-taxonomy-v1.md is stale -- rerun "
        "`uv run python -m opsverse_evals.failure_taxonomy`"
    )
