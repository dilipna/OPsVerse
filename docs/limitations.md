# Limitations and scope

The README leads with what the project does. This page holds every boundary on those
claims, in one place, so none of them is lost. The full falsification record (claims the
project tested and withdrew) is in [evidence.md](evidence.md); the per-claim status table
is in [claims.md](claims.md).

## Security scope

See the *Status / open* column of the [threat model](security/threat-model.md). In short:
the injection detector is regex-based and cannot catch rewording, translation or encodings;
credential redaction is pattern-based; URL ingestion still has a DNS-rebinding window;
there is no per-client rate limiting; the deployment is single-tenant.

## Public workspace

The default analysis runs in the browser over six official documents / 180 passages.
It does not upload diagnostic text or execute commands; normal hosting access logs
still apply. Credential-pattern redaction is best-effort: sanitize input first. The
optional model path validates JSON, source IDs, exact quotes, output completion and
permitted read-only command forms. Those checks do not prove factual support. No model
endpoint is configured on the public deployment. `/model-demo` is a separately labelled
sample console and is not part of the evidence workflow.

## Serving-evidence corrections (October 2026)

The repository already contained hybrid retrieval, ingestion, model training and
inference experiments. This redevelopment makes one small workflow usable and
corrects the decision logic behind serving claims:

- Capacity admission checks errors, successful sample counts, finite latency and
  throughput, and count consistency. Defaults: zero errors and at least 20 successes.
  Twenty observations are a bounded minimum, not precise p95 uncertainty estimation.
- Repeatability requires complete matching identities and distinct run IDs.
  Cache settings and request counts cannot be pooled. Historical identities are
  incomplete, so historical repeatability is **not measured**.
- CI rebuilds the browser corpus through the actual ingestion pipeline and reruns
  the same retrieval function used by the browser, starting from raw documents.

## Reproducible evidence

| Result | Scope and limitations |
|---|---|
| Term overlap: 15/16 document hit@1, 16/16 hit@3 | Synthetic agent-authored questions, specified before the first run; six docs / 180 passages. Document labels do not establish passage answer quality. Selection used these results; cases are now public regression data. |
| BM25: 14/16 hit@1, 16/16 hit@3 | Same inputs. No significant superiority claim. The simpler term-overlap ranker ships. |
| 4/4 negative cases empty | One empty and three unrelated queries; not calibrated answerability or security evidence. |
| Historical vLLM FP16: 233.18 reported tokens/s at c=16; Ollama Q4: 37.22 at c=1 | Recomputed stored T4 summaries under p95 TTFT ≤1s, latency ≤30s, zero errors, ≥20 successes. Not new GPU measurements; engine and precision both differ. |

[Per-case retrieval report](reports/runbook-evaluation.json) ·
[Capacity decisions and reasons](reports/capacity-and-slo-v1.md).
Stress queries demonstrate vocabulary mismatch and tangential matches. Instruction-like
queries can match ordinary text. The app presents excerpts, not diagnoses or safety verdicts.

## Research boundaries

- [Retrieval studies](reports/retrieval-golden-v1.md) are stored experiments, not newly
  rerun model studies. Preserve original dataset scope and judge limitations.
- [OpsLM-v1](https://huggingface.co/dhf1234/OpsLM-v1) is a published SFT artifact
  (534 train / 59 validation pairs). A matched base-versus-SFT task-quality gain is
  unverified. DPO code exists; a completed DPO run is not established.
- [Historical serving dashboard](https://ops-verse.vercel.app/dashboard.html): 13.4× is
  within-vLLM c=1→16 scaling. Cross-engine comparisons do not isolate scheduling;
  token-counting provenance is incomplete. Cost uses an assumed $0.35 GPU/hour.
- [Model demo](https://ops-verse.vercel.app/model-demo) shows labeled samples without an
  endpoint. Configuration does not establish availability, and the proxy does not retrieve
  context. Upstream failures return errors.
- Original Eval Gate checks 15 committed-report assertions and two live retrieval
  thresholds over prechunked fixtures. The new navigator CI independently exercises raw
  input. Neither reruns every historical model study.

No hosted GPU, paid jobs, production maturity, external users, adoption impact,
completed DPO training or measured SFT quality improvement is claimed.
Kubernetes documentation © Kubernetes Authors, CC BY 4.0; attribution and pinned
sources are in the [manifest](../evalsets/runbooks/manifest.json). The project's own license
is separate. See the [evaluation protocol](../evalsets/runbooks/README.md).
