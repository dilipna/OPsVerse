# Incident investigation workspace

The public homepage is an evidence workflow: sanitized symptom and optional diagnostic
text -> recognized status signatures -> up to three pinned official passages ->
exportable JSON brief. `/runbooks` exposes general passage search; `/engineering`
explains decisions; `/study` exposes recorded evidence and limitations.

## Implementation contract

`opslm-demo/lib/troubleshoot.mjs` supplies preparation, best-effort credential-pattern
redaction, signal recognition, bounded retrieval context, prompt construction and
output validation. The browser uses it directly without transmitting diagnostic
text. Six raw official documents flow through the existing Python ingestion pipeline
into 180 passages. The generated corpus is checked against raw inputs in CI.

The export contains the redacted issue, up to 2,000 diagnostic characters, detected
signals, retrieved passages, source links, and analysis mode. Input limits are 500
issue characters and 12,000 diagnostic characters. Signal recognition scans the
allowed input; context truncation is displayed. Redaction is incomplete: users must
sanitize secrets before pasting. Normal hosting request logs still apply.

## Optional generation (not enabled on the public deployment)

No models were loaded for this release, at the project owner's request. The public
workflow needs no model or paid service. To connect an already running local
OpenAI-compatible server when resources permit, configure these server-only variables:

```text
OPSVERSE_TROUBLESHOOT_ENDPOINT=http://127.0.0.1:8011/v1
OPSVERSE_TROUBLESHOOT_MODEL=your-local-model-name
# OPSVERSE_TROUBLESHOOT_API_KEY is optional for an authenticated endpoint
```

Then run the Next.js application locally. Endpoint configuration does not verify
availability. The explicit model button sends locally redacted input to this app's
server, which redacts again before calling the configured endpoint. It never inherits
the separate sample console's endpoint. Production localhost cannot reach a user's
computer. No hosted inference or infrastructure is provisioned by these instructions.

`/api/troubleshoot` invokes the shared `troubleshoot-http.mjs` handler. It rejects
malformed or oversized input; bounds context to three passages / 6,000 characters;
uses temperature 0, seed 42, max_tokens 384, and a 55-second upstream timeout.
With no supporting passages it abstains before calling a model. With no endpoint
it returns excerpts. Upstream, schema or completion failures return 502 without a
fabricated answer. Successful output requires recognized status, bounded arrays,
real source IDs and matching 20-600 character quotes. Command suggestions pass a
restricted kubectl get/describe/logs/rollout status/history grammar. No commands run.
These structural checks establish provenance, not factual entailment, command
relevance, or a security certification. A model can still misinterpret real quotes.

The separate Python SSE RAG service also abstains when retrieval fails or returns
no chunks; tests assert no model call in those paths.

## Evaluation and reproduction

```bash
uv run python -m opsverse_evals.troubleshooting_contamination --check
node opslm-demo/scripts/build-study.mjs --check
node opslm-demo/scripts/model-study.mjs --label excerpts --out /tmp/excerpts.json
cd opslm-demo && npm test && npm run build
```

The runner calls the same HTTP handler as the application and records every case,
errors, source IDs, prompt/implementation/data hashes, commit and dirty state.
The 30 synthetic scenarios (6 development / 24 held-out) were frozen in commit
19f2295 before model inference. The lexical contamination report checks all 30
against the actual 593 committed SFT inputs: no exact or thresholded 5-gram overlap
was flagged. Semantic and pretraining overlap are unknown. Reference phrase coverage
in returned passages is not generated-answer accuracy; excerpt mode cannot answer
questions or satisfy answer-status labels. No base/SFT improvement is reported.
The independent pinned GGUF conversions would confound a causal training claim.

## Recorded excerpt-only run

[Per-case report](reports/troubleshooting-excerpts-v1.json): clean commit
`2f88668fb9b0eeb469ff6d70e6b2c47899aa0839` completed all 24 held-out requests with HTTP 200 and
zero generated answers. Returned passages covered 31 of 32 reference phrase groups;
this measures lexical presence, not whether an answer is correct. Three cases
abstained with no passages. A Redis out-of-scope scenario still retrieved tangential
Kubernetes material: nonempty retrieval must not be read as answerability. No cases
were removed or tuned after this run.
