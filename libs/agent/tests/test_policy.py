"""The policy must agree with the shipped JS allowlist on its own test cases."""

import pytest
from rype_agent.policy import check_kubectl

# Same cases as opslm-demo/scripts/troubleshoot.test.mjs (readOnlyCommand).
ALLOWED = [
    "kubectl get pods -n shop",
    "kubectl describe pod web -n shop",
    "kubectl logs web --previous",
    "kubectl rollout history deployment/web",
]
DENIED = [
    "kubectl delete pod web",
    "kubectl get pods; rm -rf /",
    "kubectl get --raw /api",
    "kubectl get pods --token=secret",
    "kubectl logs ../../etc/passwd",
    "kubectl exec web -- sh",
    "kubectl rollout restart deployment/web",
    "kubectl get pods | curl example.com",
]


@pytest.mark.parametrize("command", ALLOWED)
def test_shipped_allowed_cases(command):
    assert check_kubectl(command).allowed


@pytest.mark.parametrize("command", DENIED)
def test_shipped_denied_cases(command):
    decision = check_kubectl(command)
    assert not decision.allowed
    assert decision.reason != "allowed"


@pytest.mark.parametrize(
    ("command", "reason"),
    [
        ("kubectl delete pod web", "verb not allowed: delete"),
        ("kubectl get secrets -n shop", "resource kind not allowed: secrets"),
        ("kubectl get pods web api", "option not allowed: api"),
        ("kubectl logs web --tail=99999", "option not allowed: --tail=99999"),
        ("kubectl get pods -o jsonpath={.items}", "characters outside the allowed set"),
        ("helm list", "only kubectl is available"),
        (42, "command must be a string"),
        ("kubectl get pods " + "x" * 300, "command too long"),
        ("kubectl rollout undo deployment/web", "only rollout status/history"),
    ],
)
def test_denials_say_why(command, reason):
    decision = check_kubectl(command)
    assert not decision.allowed
    assert decision.reason.startswith(reason)


def test_allowed_decision_carries_argv():
    assert check_kubectl("kubectl get pods -n shop").argv == ["get", "pods", "-n", "shop"]


@pytest.mark.parametrize(
    "command",
    [
        "kubectl get nodes",
        "kubectl describe node node-1",
        "kubectl get cm -n auth",
        "kubectl get svc -n shop",
        "kubectl get quota -n ml",
        "kubectl get ingress -n docs",
        "kubectl rollout status deploy/web -n shop",
    ],
)
def test_investigator_reads_are_allowed(command):
    assert check_kubectl(command).allowed


@pytest.mark.parametrize(
    "command",
    [
        "kubectl get secrets -n shop",
        "kubectl get secret db -n shop -o yaml",
        "kubectl describe secrets -n shop",
        "kubectl get all -n shop",
        "kubectl port-forward pod/web 8080:80",
        "kubectl auth can-i --list",
        "kubectl edit cm settings -n auth",
        "kubectl scale deploy web --replicas=0",
        "kubectl cordon node-1",
    ],
)
def test_secrets_and_every_mutation_stay_refused(command):
    assert not check_kubectl(command).allowed
