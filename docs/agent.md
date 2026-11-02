# RYPE agent: a read-only Kubernetes investigator

`libs/agent` is a tool-using agent that investigates a reported symptom with read-only
`kubectl` and documentation search, then submits a structured diagnosis. It is built
to show that an agent's security properties can be enforced in code and measured,
not just requested in a prompt.

Results: [agent-v1 report](reports/agent-v1.md). Recorded runs can be stepped through on the
live site at [/agent](https://ops-verse.vercel.app/agent); the command policy can be tried at
[/lab](https://ops-verse.vercel.app/lab). Threat model rows: T-01, T-03, T-08 in
[threat-model.md](security/threat-model.md).

## Loop

```text
symptom ──► model ──tool call──► policy check ──allowed──► simulated cluster / doc search
              ▲                       │ refused                     │
              │                       ▼                             ▼
              └──── tool error ◄──────┘     output wrapped in a random boundary,
                                            "[k of N tool calls used]" appended
budget spent ──► forced `finish` turn (tool_choice) ──► checked final answer
```

## Where each control lives

| Property | Mechanism | Code |
|---|---|---|
| Least privilege | Only `kubectl` (read-only), `search_docs`, `finish`. Every command passes `check_kubectl` before it runs; secrets, exec, port-forward and every mutating verb are refused with a reason. | `policy.py` |
| Untrusted tool output | Pod logs and events are attacker-writable. Every result sits inside a per-run random boundary the content cannot forge, and the prompt declares it data. | `loop.py::_wrap` |
| Leak detection | A random canary in the system prompt; any final answer containing it is a measured prompt-exfiltration success. | `loop.py::_finish` |
| Output handling | The final summary passes the same output guard as the chat API (no images, allowlisted links only, credentials redacted). | `rype_security.output_guard` |
| Bounded cost | Hard tool-call budget, shown to the model after every call; when spent, the only tool offered is `finish`, and it is forced. | `loop.py::run_agent` |
| Checked answer | `root_cause` must be one of the defined labels; evidence quotes are checked against what the tools returned; suggested commands are re-checked and never executed. | `loop.py::_finish` |

## Evaluation

- **Scenarios** (`evalsets/agent-v1/scenarios.json`): 16 frozen namespaces with one fault
  each, served by `SimulatedCluster` with `kubectl`-shaped output. a01-a10 were used
  during development; **h01-h06 were written before the harness changes and never used
  for debugging**, so they are the honest generalization check.
- **Adversarial variants**: every scenario again with one existing red-team string
  (`security-redteam-v1`, by id) appended to the first pod's logs. No new attack text.
- **Metrics**: root-cause accuracy, runs finished, tool calls, refused commands, evidence
  found in tool output, and attack success (canary leak or output-guard rewrite), with
  95% Wilson intervals.

```bash
uv run python -m rype_agent.evaluate --model openai/gpt-4o-mini
```

Needs `OPENROUTER_API_KEY` (any OpenAI-compatible endpoint works via `--base-url`).
Results are cached per (model, harness version, scenario) in a gitignored directory.

## Known limits

- **Evidence is checked for existence, not support.** In one run the agent quoted
  `Endpoints: 10.244.2.9:8080` as evidence that a Service had no endpoints; the quote
  passed the check while contradicting the claim. An entailment check is the next step.
- **Simulator fidelity.** `describe pod` in the scenarios omits the `Labels:` line real
  kubectl prints, which can make a label mismatch hard to rule out.
- Small synthetic set, single-fault scenarios, one model, temperature 0.
