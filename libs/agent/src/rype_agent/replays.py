"""Agent replays for the public /agent page, rebuilt from committed evidence.

`docs/reports/agent-v1-trajectories.json` records, for a few clean runs of the
agent-v1 evaluation, what the agent did: each tool call, the policy decision and
the final answer. It holds no tool output and no red-team text. This module
regenerates every tool output deterministically from the frozen scenarios (the
same `SimulatedCluster` and `search_docs` the agent used) and writes
`opslm-demo/public/agent-replays.json`; `--check` fails if that file drifts.

`--record` refreshes the trajectory file from the local evaluation cache
(gitignored), so only that step needs the original run.

Usage:
    uv run python -m rype_agent.replays --record   # after an evaluation run
    uv run python -m rype_agent.replays            # rebuild page data
    uv run python -m rype_agent.replays --check    # CI
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rype_agent.cluster import SimulatedCluster
from rype_agent.evaluate import CACHE_PATH, HARNESS_VERSION, load_scenarios
from rype_agent.policy import check_kubectl
from rype_agent.tools import load_corpus, search

TRAJECTORIES_PATH = Path("docs/reports/agent-v1-trajectories.json")
REPLAYS_PATH = Path("opslm-demo/public/agent-replays.json")
# A fast correct run, two held-out runs (one with a refused Secrets read) and the
# clean-pass miss, shown on purpose.
REPLAY_IDS = ["a07", "h01", "h04", "a10"]
MAX_OUTPUT_CHARS = 1500


def record() -> None:
    rows = [
        json.loads(line) for line in CACHE_PATH.read_text(encoding="utf-8").splitlines() if line
    ]
    model = None
    runs = {}
    for row in rows:
        model_name, harness, scenario_id = row["key"].split("|")
        if harness == HARNESS_VERSION and scenario_id in REPLAY_IDS:
            model = model_name
            r = row["result"]
            runs[scenario_id] = {
                "steps": [
                    {k: s[k] for k in ("tool", "arguments", "allowed", "denial_reason")}
                    for s in r["steps"]
                ],
                "root_cause": r["root_cause"],
                "summary": r["summary"],
                "evidence": r["evidence"],
                "forced_finish": r.get("forced_finish", False),
                "canary_leaked": r["canary_leaked"],
            }
    missing = set(REPLAY_IDS) - set(runs)
    if missing:
        raise SystemExit(f"no cached {HARNESS_VERSION} runs for {sorted(missing)}")
    doc = {
        "report": "agent-v1",
        "model": model,
        "harness": HARNESS_VERSION,
        "note": "Clean runs only; tool outputs are not stored and are rebuilt from the scenarios.",
        "runs": {sid: runs[sid] for sid in REPLAY_IDS},
    }
    TRAJECTORIES_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"recorded {len(runs)} trajectories -> {TRAJECTORIES_PATH}")


def _output(step: dict[str, Any], cluster: SimulatedCluster, corpus: dict[str, Any]) -> str:
    args = step["arguments"]
    if step["tool"] == "kubectl":
        command = args.get("command")
        if isinstance(command, str) and not command.strip().startswith("kubectl"):
            command = f"kubectl {command.strip()}"
        decision = check_kubectl(command)
        if not decision.allowed:
            return f"REFUSED by policy: {decision.reason}."
        return cluster.run(decision.argv)
    if step["tool"] == "search_docs":
        hits = search(corpus, str(args.get("query", ""))[:500])
        return "\n\n".join(f"[{h['id']}] {h['text'][:300]}" for h in hits) or "No passages found."
    return f"Unknown tool {step['tool']!r}."


def build() -> dict[str, Any]:
    trajectories = json.loads(TRAJECTORIES_PATH.read_text(encoding="utf-8"))
    doc, scenarios = load_scenarios()
    by_id = {s.id: s for s in scenarios}
    corpus = load_corpus()
    replays = []
    for sid, run in trajectories["runs"].items():
        scenario = by_id[sid]
        cluster = SimulatedCluster(scenario)
        steps = []
        for step in run["steps"]:
            output = _output(step, cluster, corpus)
            steps.append(
                {
                    "tool": step["tool"],
                    "input": step["arguments"].get("command") or step["arguments"].get("query"),
                    "allowed": step["allowed"],
                    "denial_reason": step["denial_reason"],
                    "output": output[:MAX_OUTPUT_CHARS],
                    "truncated": len(output) > MAX_OUTPUT_CHARS,
                }
            )
        replays.append(
            {
                "id": sid,
                "heldout": scenario.heldout,
                "symptom": scenario.symptom,
                "truth": scenario.root_cause,
                "predicted": run["root_cause"],
                "correct": run["root_cause"] == scenario.root_cause,
                "summary": run["summary"],
                "evidence": run["evidence"],
                "forced_finish": run["forced_finish"],
                "canary_leaked": run["canary_leaked"],
                "steps": steps,
            }
        )
    return {
        "schema": 1,
        "generated_by": "python -m rype_agent.replays",
        "model": trajectories["model"],
        "harness": trajectories["harness"],
        "labels": doc["root_cause_definitions"],
        "replays": replays,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.record:
        record()
    rendered = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    if args.check:
        current = REPLAYS_PATH.read_text(encoding="utf-8") if REPLAYS_PATH.exists() else ""
        if current != rendered:
            raise SystemExit("agent replays are stale: run python -m rype_agent.replays")
        print("agent replays match the committed trajectories and scenarios")
        return
    REPLAYS_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {REPLAYS_PATH}")


if __name__ == "__main__":
    main()
