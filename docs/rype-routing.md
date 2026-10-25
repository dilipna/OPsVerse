# RYPE — Route Your Prompt Efficiently

RYPE retains the existing site, repository, Night Orbit theme, portable notes and reading list. It adds retrieval-first routing with per-response cost receipts. Existing Python module names, source URLs, historical research artifacts and the legacy reading-list storage key remain compatible; the public application branding is RYPE.

## Route policy

1. Prepare bounded input and redact recognized credential patterns.
2. Run the existing lexical retrieval over six pinned Kubernetes documents.
3. A conservative, transparent coverage gate checks a known topic, matching document family, readable source paragraph, question-term support and missing-signal gaps. Custom code, mixed-domain and unsupported requests are not treated as covered solely because some text matched. This is a heuristic, not calibrated answerability or a test of a model's training data.
4. Covered questions return source-derived guidance locally without an inference POST. This is extractive retrieval, not an LLM-written diagnosis.
5. Other requests are classified using explicit everyday/coding/reasoning rules. The server selects an eligible zero-price candidate from that task's small allowlist, checked against OpenRouter's live model catalogue. The policy does not establish optimal model quality.

The current free profiles include Liquid LFM for everyday tasks, Cohere North Mini Code for code and NVIDIA Nemotron 3 Super for reasoning, with named free alternatives. Actual availability is checked at request time. No arbitrary user-selected model, endpoint or price setting is accepted by the public API. Paid models are never enabled by request fields. Server provider price caps are zero for prompt, completion, per-request and image charges; paid/provider fallbacks and automatic retries are disabled. No tools or command execution.

## Server configuration

Set `OPENROUTER_API_KEY` (or `RYPE_OPENROUTER_API_KEY`) as a sensitive server-only Production environment variable in the existing Vercel project `asmq333/inferllm`. Never use a NEXT_PUBLIC_ variable, commit a key, or submit a key as a question. Redeploy to make a new variable available. The key is forwarded only as an authorization header to the fixed `https://openrouter.ai/api/v1/chat/completions` endpoint. Free-only enforcement is in source, not a mutable browser flag. No paid inference is authorized.

`GET /api/route` returns only configuration presence, eligible public model metadata and baseline pricing; no credentials. The catalogue is cached in server memory for up to five minutes. Catalogue failures do not authorize stale/unpriced inference. `POST /api/route` bounds the body at 24,000 bytes, recomputes the policy server-side, limits completion to 768 tokens, times out at 28 seconds and bounds upstream responses. A missing key, changed price, unavailable free provider, incomplete response or unexpected returned model produces an explicit failure rather than a sample answer or paid retry. A failed/timeout call may have unknown billing and is never shown as a zero-cost success.

Covered questions stay in the browser. Other questions and redacted logs are transmitted to OpenRouter only when a key is configured and the user presses Send. Redaction is best-effort: remove secrets before pasting. Provider availability/quotas vary. Existing `/api/troubleshoot` structured local-model experiments and the recorded `/model-demo` console remain separate historical/research paths; their fixtures do not establish live OpenRouter answer quality.

## Cost receipts

Every response records route reason, selected versus actually returned model, attempted call count, reported charge (if supplied), price-check time and comparison scope. JSON/Markdown exports preserve the receipt; reopening ignores imported answers/receipts and performs local retrieval without automatic cloud calls.

- Retrieval: actual inference charge is $0 and model calls are zero. An optional baseline amount uses approximate question/answer characters divided by four. It is labeled an estimated avoided inference charge, not measured savings.
- Cloud: the actual charge comes from OpenRouter's `usage.cost`, never a hardcoded saving. Missing billing stays unavailable, including failures. Returned model IDs are checked against the requested model. Paid-charge anomalies fail acceptance while preserving the reported cost in the failure receipt.
- Comparison: the named baseline is `anthropic/claude-sonnet-4.6`, if present in the current catalogue. Estimated baseline cost is input tokens × prompt price + output tokens × completion price + per-request price. For cloud answers these are the selected model's reported token counts; different tokenizers, caching and answer quality can differ. The baseline is not called. The displayed difference/percentage is explicitly estimated, can be negative and excludes hosting, taxes and other fees. Missing rates/tokens/charges suppress invented comparisons.

Primary references checked October 25, 2026:
- [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [Model catalogue API](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties)
- [Provider max-price and fallback controls](https://openrouter.ai/docs/guides/routing/provider-selection)

## Evidence and limits

Unit/HTTP transport fixtures verify zero library inference, task profiles, redaction, free-price enforcement, unavailable credentials/catalogue, provider failures, incomplete/wrong-model outputs, billing honesty and body/schema boundaries. Browser contracts stub external inference so CI never consumes provider quota; synthetic output is labeled as fixture evidence. Real authorized free-model smoke checks are recorded separately when the production key is available. A working router does not establish improved answer quality, globally minimum cost, a learned triage model or a measured counterfactual saving.

This directly adapts the original triage-router idea (#4) as a rules-based, retrieval-first free-model policy. It builds on bounded corrective retrieval and trajectory CI rather than claiming a new learned router, trained-data lookup or all fifteen ideas completed.