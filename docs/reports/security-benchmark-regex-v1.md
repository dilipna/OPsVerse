# Injection detector on external data v1 (regex only)

*Generated 2026-11-02 by `python -m rype_security.benchmark`. LLM: `none (regex only)` (prompt v1).*

Recall, false-positive rate and precision with 95% Wilson intervals. LLM errors are
excluded from the main rates and shown separately, with the fail-closed rates that
treat an error as a flag. Reports list row indices only; no sample text.

## deepset-test

`deepset/prompt-injections` (Apache-2.0) split `test` at commit `4f61ecb038e9`, file SHA-256 `39ac797cabc1`. Rows: 116 (60 attacks, 56 benign).

| Detector | Recall | False-positive rate | Precision | Errors |
|---|---|---|---|---|
| `regex` | 0.100 [0.047, 0.202] | 0.000 [0.000, 0.064] | 1.000 [0.610, 1.000] | 0 |

## deepset-train

`deepset/prompt-injections` (Apache-2.0) split `train` at commit `4f61ecb038e9`, file SHA-256 `2e10bc7ab30f`. Rows: 546 (203 attacks, 343 benign).

| Detector | Recall | False-positive rate | Precision | Errors |
|---|---|---|---|---|
| `regex` | 0.074 [0.045, 0.118] | 0.000 [0.000, 0.011] | 1.000 [0.796, 1.000] | 0 |

## redteam-v1

Internal red-team set the regexes were tuned on (reference only). Rows: 33 (15 attacks, 18 benign).

| Detector | Recall | False-positive rate | Precision | Errors |
|---|---|---|---|---|
| `regex` | 1.000 [0.796, 1.000] | 0.000 [0.000, 0.176] | 1.000 [0.796, 1.000] | 0 |

## Limits

- Labels are the dataset authors'. External sets mix languages and include
  borderline rows; a disagreement is not automatically a detector error.
- An LLM classifier is itself an attack surface and adds latency and cost per
  document; this report measures whether it earns that before it is wired in.
- One model, one prompt version, temperature 0. Other models need their own runs.
