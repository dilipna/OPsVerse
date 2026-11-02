"""Tool policy: the only commands the agent may run (threat model T-08, excessive agency).

Started as a port of the allowlist the public workspace ships for commands it
*suggests to people* (`opslm-demo/lib/troubleshoot.mjs::readOnlyCommand`), and still
agrees with it on that list's own test cases. The first live agent run showed that
list is too narrow for an investigator: 16 refused calls, every one a harmless read
(nodes, configmaps, quotas, ingresses, `svc`). So the agent policy is a documented
superset: more read-only kinds and the standard short names. Secrets, exec, port-
forward, raw API access, credential flags, shell syntax and every mutating verb are
still refused, and the tests pin that.

The policy is the security boundary, not the prompt: every tool call is checked here
before anything runs, and a refusal is shown to the model as a tool error.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

MAX_COMMAND_CHARS = 240
VERBS = ("get", "describe", "logs", "rollout")
ROLLOUT_SUBCOMMANDS = ("status", "history")
OUTPUT_FORMATS = ("wide", "json", "yaml")

_SAFE_CHARS = re.compile(r"^[a-zA-Z0-9_./=:\s-]*$")
_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
_NAMESPACE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_LOGS_TARGET = re.compile(r"^(?:pods?/)?[a-z0-9][a-z0-9.-]*$")
_ROLLOUT_TARGET = re.compile(r"^(deployments?|deploy)(/[a-z0-9][a-z0-9.-]*)?$")
# Read-only kinds an investigator needs, with kubectl's standard short names.
# Secrets are deliberately absent.
READ_KINDS = {
    "pod": "pods", "pods": "pods", "po": "pods",
    "deployment": "deployments", "deployments": "deployments", "deploy": "deployments",
    "service": "services", "services": "services", "svc": "services",
    "endpoint": "endpoints", "endpoints": "endpoints", "ep": "endpoints",
    "event": "events", "events": "events", "ev": "events",
    "replicaset": "replicasets", "replicasets": "replicasets", "rs": "replicasets",
    "node": "nodes", "nodes": "nodes", "no": "nodes",
    "configmap": "configmaps", "configmaps": "configmaps", "cm": "configmaps",
    "resourcequota": "resourcequotas", "resourcequotas": "resourcequotas",
    "quota": "resourcequotas",
    "limitrange": "limitranges", "limitranges": "limitranges", "limits": "limitranges",
    "ingress": "ingresses", "ingresses": "ingresses", "ing": "ingresses",
    "namespace": "namespaces", "namespaces": "namespaces", "ns": "namespaces",
}  # fmt: skip
_RESOURCE = re.compile(r"^([a-z]+)(/[a-z0-9][a-z0-9.-]*)?$")


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str = "allowed"
    argv: list[str] = []


def _deny(reason: str) -> PolicyDecision:
    return PolicyDecision(allowed=False, reason=reason)


def _allowed_flag(verb: str, token: str) -> bool:
    if re.match(r"^--namespace=[a-z0-9][a-z0-9-]*$", token):
        return True
    return verb == "logs" and (token == "--previous" or bool(re.match(r"^--tail=\d{1,4}$", token)))


def check_kubectl(command: object) -> PolicyDecision:
    """Decide whether `command` is a permitted read-only kubectl invocation."""
    if not isinstance(command, str):
        return _deny("command must be a string")
    if len(command) > MAX_COMMAND_CHARS:
        return _deny("command too long")
    if not _SAFE_CHARS.match(command):
        return _deny("characters outside the allowed set (no shell syntax)")
    tokens = command.split()
    if not tokens or tokens[0] != "kubectl":
        return _deny("only kubectl is available")
    argv = tokens[1:]
    if not argv or argv[0] not in VERBS:
        return _deny(f"verb not allowed: {argv[0] if argv else '(none)'}")
    verb, rest = argv[0], argv[1:]
    if verb == "rollout":
        if not rest or rest[0] not in ROLLOUT_SUBCOMMANDS:
            return _deny("only rollout status/history are allowed")
        rest = rest[1:]
    if not rest:
        return _deny("resource required")
    resource, options = rest[0], rest[1:]
    if resource.startswith("-") or ".." in resource:
        return _deny("invalid resource")
    if verb == "logs" and not _LOGS_TARGET.match(resource):
        return _deny("invalid logs target")
    if verb == "rollout" and not _ROLLOUT_TARGET.match(resource):
        return _deny("rollout works on deployments only")
    if verb not in ("logs", "rollout"):
        match = _RESOURCE.match(resource)
        if not match or match.group(1) not in READ_KINDS:
            return _deny(f"resource kind not allowed: {resource.split('/')[0]}")
    names = 0
    i = 0
    while i < len(options):
        token = options[i]
        if token in ("-n", "--namespace"):
            i += 1
            if i >= len(options) or not _NAMESPACE.match(options[i]):
                return _deny("invalid namespace")
        elif token in ("-o", "--output"):
            i += 1
            if i >= len(options) or options[i] not in OUTPUT_FORMATS:
                return _deny("output format not allowed")
        elif _allowed_flag(verb, token):
            pass
        elif not token.startswith("-") and _NAME.match(token) and names == 0:
            names += 1
        else:
            return _deny(f"option not allowed: {token}")
        i += 1
    return PolicyDecision(allowed=True, argv=argv)
