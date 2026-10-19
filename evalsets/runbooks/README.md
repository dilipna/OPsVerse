# Public runbook evaluation fixture

Six Markdown snapshots from Kubernetes website revision
`3d8f3d7b579d7dfcef7b835fee8da2a37199012d`; hashes, links and date are in `manifest.json`.
Documentation © Kubernetes Authors, CC BY 4.0, redistributed with attribution.

`queries.json` was specified before the first metric run: six development, 16 initially
held-out positives, four negatives (one empty) and four stress cases. Questions and coarse
document labels were agent-authored, without external users or independent human rating.
The same corpus, tokenizer and query set are used for both rankers.

Thresholds fixed before the run: hit@3 ≥0.65; negative empty rate ≥0.75. Both rankers must
meet both. Stress outcomes are descriptive and all are reported. Selection used these
results; a future generalization claim requires a new holdout and better passage labels.

```bash
uv run python -m opsverse_evals.runbook_fixture --check
node opslm-demo/scripts/evaluate-runbooks.mjs --out docs/reports/runbook-evaluation.json
```

CI starts with raw input, then evaluates the actual browser module. A fresh report artifact
records commit, dirty status, code/corpus/dataset hashes, run ID, revision, hardware and
exclusions. Stored historical reports do not pass this gate. No model or answer quality is evaluated.
