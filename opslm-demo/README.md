# OpsVerse public website

Next.js / React, existing Vercel deployment: https://ops-verse.vercel.app/.
The primary path is browser-only runbook retrieval; `/model-demo` is a labeled sample
console. No model backend or cluster access is required by the navigator.

```bash
npm ci
npm test
npm run eval
npm run build
npm start
```

From repository root regenerate/check raw ingestion with
`uv run python -m opsverse_evals.runbook_fixture [--check]`.
Browser and evaluator share `lib/runbooks.mjs`. No questions are uploaded by that module.

Existing Vercel root directory: `opslm-demo`. Publish checked source to that project;
do not create a new project or enable paid services. The optional proxy uses existing
OPSLM_ENDPOINT / OPSLM_MODEL / OPSLM_API_KEY variables. Its configuration flag is not a
health check, it does not retrieve context, and upstream failures return 502.
