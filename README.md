# RYPE — Route Your Prompt Efficiently

**Retrieve covered guidance first. Route other tasks to eligible free models. Inspect the route and cost.**

[Open the workspace](https://ops-verse.vercel.app/) | [Engineering case study](https://ops-verse.vercel.app/engineering) | [Evaluation](https://ops-verse.vercel.app/study) | [Resume evidence](docs/resume-and-interview.md)

The deployed flagship implementation is on
[`improve/flagship-investigation`](https://github.com/dilipna/OPsVerse/tree/improve/flagship-investigation),
reviewable in [PR #4](https://github.com/dilipna/OPsVerse/pull/4). The release was
approved without a `main` merge. Select that branch when reproducing the public
website; its exact deployed commit and source hashes are at
[`/release.json`](https://ops-verse.vercel.app/release.json).

RYPE returns covered Kubernetes guidance from its pinned documentation library without model inference. Other questions use explicit everyday, coding or reasoning profiles and can route to eligible free OpenRouter models when a server-side key is configured. Paid models and paid fallbacks are disabled. Each response shows its route, model actually used, reported inference charge and explicitly estimated comparison against a named baseline. No claim is made about a model's training-data membership or measured quality-matched savings.

The knowledge workspace adds an inference-free Pod definition, inspectable BM25/character-rank retrieval, an optional private browser document library with backups, and discussion-aware study PDF / code ZIP downloads. See [implementation and storage limits](docs/rype-knowledge-workspace.md).

The existing Night Orbit UI, source library, portable JSON/Markdown notes, device reading list and research evidence remain. Covered questions stay in the browser; cloud-routed questions and redacted logs are sent to OpenRouter. No cluster connection or command execution. Credential redaction is best-effort: remove secrets first. See [routing, setup and cost methodology](docs/rype-routing.md) for server-only key configuration, free-only enforcement, billing limits and verification scope.
Explore [all runbooks](https://ops-verse.vercel.app/runbooks),
[architecture and decisions](https://ops-verse.vercel.app/engineering), or
[the implementation contract](docs/troubleshooting.md). The original sample model
console remains at `/model-demo`; it is separate from this evidence workflow.

## What changed

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

[Per-case retrieval report](docs/reports/runbook-evaluation.json) ·
[Capacity decisions and reasons](docs/reports/capacity-and-slo-v1.md).
Stress queries demonstrate vocabulary mismatch and tangential matches. Instruction-like
queries can match ordinary text. The app presents excerpts, not diagnoses or safety verdicts.

## Quickstart

CI uses Node 24 and Python 3.12+ with uv.

```bash
git clone https://github.com/dilipna/OPsVerse.git
cd OPsVerse
uv sync --all-packages --frozen
uv run python -m opsverse_evals.runbook_fixture --check
cd opslm-demo
npm ci
npm test
npm run eval
npm run build
npm start
# open http://localhost:3000
```

Python is for verification/regeneration; runtime search needs only the static corpus.
From the repository root:

```bash
uv run python -m opsverse_evals.runbook_fixture
node opslm-demo/scripts/evaluate-runbooks.mjs --out docs/reports/runbook-evaluation.json
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python benchmarks/capacity.py --out docs/reports/capacity-and-slo-v1.md
```

Reports record run ID, code commit, dirty status, implementation hashes, dataset/corpus
hashes, upstream revision, runtime, hardware and exclusions. CI uploads a fresh evaluation
for the tested commit. A dirty-tree run is developmental evidence, not a clean release run.

## Architecture

```text
Pinned Kubernetes Markdown + SHA-256 manifest
  → existing parser → chunker → quality → redact/quarantine pipeline (Python)
  → generated runbooks.json (checked against raw inputs in CI)
  → browser term-overlap retrieval → original excerpts + source links

Separate local research stack:
FastAPI / MCP → hybrid BGE + BM25 / Qdrant → optional reranker → LLM gateway
Serving harness → session JSON → failure-aware capacity analysis
```

[Product architecture](docs/runbook-architecture.md) · [Full-stack design](docs/architecture.md) ·
[Optional local research setup](docs/local-research.md) · [22 historical ADRs](docs/adr/).

## Research boundaries

- [Retrieval studies](docs/reports/retrieval-golden-v1.md) are stored experiments, not newly
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
sources are in the [manifest](evalsets/runbooks/manifest.json). The project's own license
is separate. See the [evaluation protocol](evalsets/runbooks/README.md).
