"""A frozen, read-only Kubernetes cluster for agent evaluation.

Each scenario in `evalsets/agent-v1/scenarios.json` describes one namespace with a
single injected fault. `SimulatedCluster.run` answers the policy-approved kubectl
commands with output shaped like the real CLI, so an agent investigates the way it
would against a live cluster, but deterministically and with nothing to break.

Pod logs and events are where a compromised workload can write text the agent will
read, which is exactly the indirect prompt-injection path the adversarial variants
exercise (threat model T-01, T-08).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field


class Pod(BaseModel):
    name: str
    ready: str = "1/1"
    status: str = "Running"
    restarts: int = 0
    age: str = "10m"
    node: str = "node-1"
    labels: dict[str, str] = Field(default_factory=dict)
    describe: str = ""
    logs: str = ""
    previous_logs: str = ""


class Deployment(BaseModel):
    name: str
    ready: str = "1/1"
    up_to_date: int = 1
    available: int = 1
    age: str = "10m"
    describe: str = ""
    rollout_status: str = ""
    rollout_history: str = ""


class Service(BaseModel):
    name: str
    cluster_ip: str = "10.96.0.10"
    ports: str = "80/TCP"
    selector: dict[str, str] = Field(default_factory=dict)
    endpoints: str = "<none>"


class Scenario(BaseModel):
    id: str
    namespace: str
    symptom: str
    root_cause: str
    heldout: bool = False
    pods: list[Pod] = Field(default_factory=list)
    deployments: list[Deployment] = Field(default_factory=list)
    services: list[Service] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)


_KINDS = {
    "pod": "pods",
    "pods": "pods",
    "deployment": "deployments",
    "deployments": "deployments",
    "service": "services",
    "services": "services",
    "endpoint": "endpoints",
    "endpoints": "endpoints",
    "event": "events",
    "events": "events",
    "replicaset": "replicasets",
    "replicasets": "replicasets",
}


def _table(header: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(str(c)) for c in col) for col in zip(header, *rows, strict=False)]
    lines = [header, *rows]
    return "\n".join(
        "   ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=False)).rstrip() for r in lines
    )


class SimulatedCluster:
    def __init__(self, scenario: Scenario):
        self.s = scenario

    # ------------------------------------------------------------------ parsing

    def run(self, argv: list[str]) -> str:
        """Answer a policy-approved argv (without the leading `kubectl`)."""
        verb, rest = argv[0], argv[1:]
        sub = ""
        if verb == "rollout":
            sub, rest = rest[0], rest[1:]
        namespace, output, name, previous, tail = self.s.namespace, None, None, False, None
        target, options = rest[0], rest[1:]
        i = 0
        while i < len(options):
            token = options[i]
            if token in ("-n", "--namespace"):
                namespace, i = options[i + 1], i + 1
            elif token.startswith("--namespace="):
                namespace = token.split("=", 1)[1]
            elif token in ("-o", "--output"):
                output, i = options[i + 1], i + 1
            elif token == "--previous":
                previous = True
            elif token.startswith("--tail="):
                tail = int(token.split("=", 1)[1])
            else:
                name = token
            i += 1
        kind_part, _, slash_name = target.partition("/")
        name = slash_name or name
        if namespace != self.s.namespace:
            return f"No resources found in {namespace} namespace."
        if verb == "logs":
            return self._logs(slash_name or kind_part, previous, tail)
        kind = _KINDS[kind_part]
        if verb == "rollout":
            return self._rollout(sub, name)
        if verb == "describe":
            return self._describe(kind, name)
        return self._get(kind, name, output)

    # ------------------------------------------------------------------ verbs

    def _find(self, kind: str, name: str | None) -> list[Any]:
        items: list[Any] = {
            "pods": self.s.pods,
            "deployments": self.s.deployments,
            "services": self.s.services,
            "endpoints": self.s.services,
        }.get(kind, [])
        return [x for x in items if name is None or x.name == name]

    def _not_found(self, kind: str, name: str) -> str:
        return f'Error from server (NotFound): {kind} "{name}" not found'

    def _get(self, kind: str, name: str | None, output: str | None) -> str:
        if kind == "events":
            return (
                "\n".join(["LAST SEEN   TYPE      REASON   OBJECT   MESSAGE", *self.s.events])
                if self.s.events
                else "No events found."
            )
        if kind == "replicasets":
            return "No resources found."
        found = self._find(kind, name)
        if name and not found:
            return self._not_found(kind, name)
        if not found:
            return f"No resources found in {self.s.namespace} namespace."
        if output in ("json", "yaml"):
            return json.dumps(
                [x.model_dump(exclude={"describe", "logs", "previous_logs"}) for x in found],
                indent=1,
            )
        if kind == "pods":
            return _table(
                ["NAME", "READY", "STATUS", "RESTARTS", "AGE"],
                [[p.name, p.ready, p.status, str(p.restarts), p.age] for p in found],
            )
        if kind == "deployments":
            return _table(
                ["NAME", "READY", "UP-TO-DATE", "AVAILABLE", "AGE"],
                [[d.name, d.ready, str(d.up_to_date), str(d.available), d.age] for d in found],
            )
        if kind == "services":
            return _table(
                ["NAME", "TYPE", "CLUSTER-IP", "PORT(S)"],
                [[s.name, "ClusterIP", s.cluster_ip, s.ports] for s in found],
            )
        return _table(["NAME", "ENDPOINTS"], [[s.name, s.endpoints] for s in found])

    def _describe(self, kind: str, name: str | None) -> str:
        found = self._find(kind, name)
        if name and not found:
            return self._not_found(kind, name)
        if kind == "services":
            return "\n\n".join(
                f"Name: {s.name}\nNamespace: {self.s.namespace}\n"
                f"Selector: {','.join(f'{k}={v}' for k, v in s.selector.items())}\n"
                f"Port: {s.ports}\nEndpoints: {s.endpoints}"
                for s in found
            )
        return "\n\n".join(x.describe or f"Name: {x.name}" for x in found) or "No resources found."

    def _logs(self, name: str, previous: bool, tail: int | None) -> str:
        found = self._find("pods", name)
        if not found:
            return self._not_found("pods", name)
        text = found[0].previous_logs if previous else found[0].logs
        if previous and not text:
            return (
                f'Error from server (BadRequest): previous terminated container "{name}" not found'
            )
        lines = text.splitlines()
        return "\n".join(lines[-tail:] if tail else lines)

    def _rollout(self, sub: str, name: str | None) -> str:
        found = self._find("deployments", name)
        if not found:
            return self._not_found("deployments", name or "")
        d = found[0]
        if sub == "status":
            return d.rollout_status or f'deployment "{d.name}" successfully rolled out'
        return (
            d.rollout_history
            or f"deployment.apps/{d.name}\nREVISION  CHANGE-CAUSE\n1         <none>"
        )
