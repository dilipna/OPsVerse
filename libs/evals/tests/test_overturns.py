import copy
import json
from pathlib import Path

import pytest

from opsverse_evals import overturns as ov

REPORTS = Path("docs/reports")


@pytest.fixture(scope="module")
def summaries() -> ov.Summaries:
    return ov.load_summaries(REPORTS)


@pytest.fixture(scope="module")
def rows(summaries: ov.Summaries) -> list[dict]:
    return ov.build_rows(summaries)


def test_every_cited_summary_is_committed():
    """The ledger cites only reports that exist in the repo."""
    for name in ov.SOURCES:
        assert (REPORTS / f"{name}-summary.json").exists(), name


def test_load_summaries_fails_loudly_on_a_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError, match="claim ledger cites it"):
        ov.load_summaries(tmp_path)


def test_pluck_names_the_full_path_when_a_field_moves(summaries):
    with pytest.raises(KeyError, match="retrieval-golden-v1 -> modes -> nope"):
        ov.pluck(summaries, "retrieval-golden-v1", "modes", "nope", "hit@10")


def test_every_claim_resolves_to_real_prose(rows):
    assert len(rows) == len(ov.LEDGER) == 7
    for r in rows:
        assert r["belief"] and r["verdict"] and r["consequence"]
        assert len(r["detail"]) > 80, r["key"]
        assert r["reports"], r["key"]
        # a claim without a decision record is a claim nobody has to live with
        assert r["adr"], r["key"]


def test_claim_keys_are_unique():
    keys = [c.key for c in ov.LEDGER]
    assert len(keys) == len(set(keys))


def test_every_cited_report_and_adr_file_exists(rows):
    for r in rows:
        for name in r["reports"]:
            assert (REPORTS / f"{name}.md").exists(), name
        assert Path("docs/adr") / f"{r['adr']}.md", r["adr"]
        assert (Path("docs/adr") / f"{r['adr']}.md").exists(), r["adr"]


def test_numbers_are_plucked_from_json_not_typed_into_the_ledger(summaries):
    """The anti-drift guarantee, tested rather than asserted in a docstring.

    Perturb a source value and the rendered prose must move with it. If a number
    were hardcoded in the ledger this test would fail, which is the whole point:
    a page whose argument is 'these numbers are honest' must not be the one
    artifact in the repo that can silently go stale.
    """
    before = ov.build_rows(summaries)

    mutated = copy.deepcopy(summaries)
    mutated["judge-validation-v1"]["weighted"]["mean_signed_error"]["mean"] = -9.876
    mutated["chunking-ablation-v1"]["comparisons"]["small"]["ndcg_graded@10"]["delta"] = 0.4242

    after = ov.build_rows(mutated)
    detail = {r["key"]: r["detail"] for r in after}
    assert "-9.876" in detail["judge-calibration"]
    assert "+0.424" in detail["chunk-size"]

    # and the untouched rows are byte-identical, so nothing is being re-derived
    # from a global that a mutation elsewhere could disturb
    unchanged = {"sparse-vs-hybrid", "metric-degeneracy", "hit-at-10", "multiturn-fix"}
    for a, b in zip(before, after, strict=True):
        if a["key"] in unchanged:
            assert a["detail"] == b["detail"], a["key"]


def test_judge_row_states_the_rater_kind_from_the_summary(summaries, rows):
    """A model rater must never be silently presented as human validation."""
    kind = ov.pluck(summaries, "judge-validation-v1", "rater_kind")
    detail = next(r["detail"] for r in rows if r["key"] == "judge-calibration")
    if kind == "model":
        assert "not a person" in detail
        assert "optimistic ceiling" in detail
        assert "human labels remain open" in detail


def test_markdown_carries_every_claim_and_the_disclaimers(rows):
    md = ov.render_markdown(rows, "2026-09-06")
    for r in rows:
        assert r["verdict"] in md
    assert "does *not* claim" in md
    for claim, _ in ov.NOT_CLAIMED:
        assert claim in md


def test_html_is_self_contained(rows):
    html = ov.render_html(rows, "2026-09-06", "https://example.test/repo")
    # no network: the page must render with the machine offline
    for loader in ("<script", "<link ", "@import", "src=", "fetch("):
        assert loader not in html
    assert html.count('<article class="card"') == len(rows)
    assert html.count("<html") == html.count("</html>") == 1
    # theme-aware in both directions
    assert "prefers-color-scheme" in html
    assert '[data-theme="dark"]' in html


def test_html_escapes_markup_in_claim_text():
    """Claim prose is authored, but it still must not be able to break the page."""
    rows = [
        {
            "key": "x",
            "belief": "a <script>alert(1)</script> & b",
            "verdict": "<b>bad</b>",
            "detail": "uses `code` and <tags>",
            "consequence": "fixed & shipped",
            "reports": ["retrieval-golden-v1"],
            "adr": None,
            "tags": [],
        }
    ]
    html = ov.render_html(rows, "2026-09-06", "https://example.test/repo")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<code>code</code>" in html  # backticks still become real markup


def test_generated_files_on_disk_are_current(rows):
    """`docs/evidence.md` is generated -- catch a hand-edit or a stale commit."""
    generated = Path("docs/evidence.md")
    if not generated.exists():
        pytest.skip("evidence.md not generated yet")
    on_disk = generated.read_text(encoding="utf-8")
    for r in rows:
        assert r["verdict"] in on_disk, (
            f"{r['key']} is stale in docs/evidence.md -- "
            "rerun `uv run python -m opsverse_evals.overturns`"
        )


def test_summary_files_are_valid_json():
    for name in ov.SOURCES:
        json.loads((REPORTS / f"{name}-summary.json").read_text(encoding="utf-8"))
