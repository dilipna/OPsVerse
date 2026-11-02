"""Trajectory eval: adversarial variants, scoring, caching and a report without attack text."""

from rype_agent import evaluate
from rype_agent.cluster import SimulatedCluster
from rype_agent.evaluate import adversarial_variant, load_redteam, load_scenarios, render_markdown
from rype_agent.llm import ChatTurn, ToolCall
from rype_agent.tools import load_corpus, search

DOC, SCENARIOS = load_scenarios()


class AlwaysAnswers:
    """Reads the pod list, then names one fixed root cause."""

    def __init__(self, label: str):
        self.label, self.calls = label, 0

    def complete(self, messages, tools, tool_choice=None):
        self.calls += 1
        if not any(m["role"] == "tool" for m in messages):
            return ChatTurn(
                tool_calls=[
                    ToolCall(id="g", name="kubectl", arguments={"command": "kubectl get events"})
                ]
            )
        return ChatTurn(
            tool_calls=[
                ToolCall(
                    id="f",
                    name="finish",
                    arguments={"root_cause": self.label, "summary": "s", "evidence": []},
                )
            ]
        )


def test_adversarial_variant_plants_existing_redteam_text_in_logs():
    redteam = load_redteam()
    attack_id = DOC["adversarial"]["redteam_ids"][0]
    variant = adversarial_variant(SCENARIOS[2], redteam[attack_id], attack_id)
    pod = variant.pods[0].name
    logs = SimulatedCluster(variant).run(["logs", pod])
    assert redteam[attack_id] in logs
    assert variant.id == f"{SCENARIOS[2].id}+{attack_id}"
    assert redteam[attack_id] not in SCENARIOS[2].pods[0].logs  # original untouched


def test_every_configured_attack_id_exists_in_the_redteam_set():
    redteam = load_redteam()
    assert set(DOC["adversarial"]["redteam_ids"]) <= set(redteam)


def test_run_scores_caches_and_reports_without_attack_text(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "CACHE_PATH", tmp_path / "results.jsonl")
    llm = AlwaysAnswers("no_fault")
    report = evaluate.run(llm, "fake/model")
    clean, attacked = report["summary"]["clean"], report["summary"]["adversarial"]
    healthy = sum(s.root_cause == "no_fault" for s in SCENARIOS)
    assert clean["runs"] == len(SCENARIOS)
    assert clean["accuracy"]["k"] == healthy  # only the healthy scenarios are right
    assert attacked["runs"] == len(SCENARIOS) * len(DOC["adversarial"]["redteam_ids"])
    assert attacked["attack_success"]["k"] == 0
    calls = llm.calls
    evaluate.run(llm, "fake/model")  # second run is served from the cache
    assert llm.calls == calls
    rendered = render_markdown(report)
    for text in load_redteam().values():
        assert text not in rendered


def test_search_port_matches_committed_browser_retrieval():
    # docs/reports/runbook-evaluation.json records the exact chunk ids the shipped
    # JS ranker returned for every query; the Python port must return the same.
    import json
    from pathlib import Path

    report = json.loads(Path("docs/reports/runbook-evaluation.json").read_text())
    corpus = load_corpus()
    rows = [row for split in report["results"]["overlap"].values() for row in split["rows"]]
    assert len(rows) >= 16
    for row in rows:
        got = [hit["id"] for hit in search(corpus, row["query"], limit=len(row["returned"]) or 5)]
        assert got == row["returned"], row["query"]
