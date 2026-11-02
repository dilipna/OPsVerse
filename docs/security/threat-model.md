# OpsVerse threat model

*Last reviewed 2026-11-02 (later passes: T-03 alerting, T-07 rebinding, T-10 rate limits, T-09 Kubernetes hardening and blocking Trivy). Scope: the research stack (FastAPI API, arq worker, Next.js
console, MCP server), the public browser workspace (`opslm-demo`), and the training
and serving artifacts. Mapped to the [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/).*

Each threat lists its control, the evidence that the control works (a test or report a
reviewer can rerun), and what is still open. "Open" items are deliberate: they say
where the next unit of work goes.

## System and trust boundaries

```text
                    untrusted                      trusted code                 untrusted
 ┌──────────────┐  (B1) query, history,   ┌──────────────────────┐  (B4) model  ┌───────────────┐
 │ user / MCP   │───── image ────────────►│ API  /v1/chat        │◄── output ───│ LLM provider  │
 │ client       │◄── sanitized answer ────│  scan → retrieve →   │──── prompt ─►│ (Gemini/vLLM) │
 └──────────────┘                         │  prompt → GUARD      │              └───────────────┘
                                          └─────────▲────────────┘
 ┌──────────────┐  (B2) URL, upload,                │ chunks (B3: retrieved text is untrusted)
 │ admin (key)  │───── GitHub repo ──► worker ──► redact → scan/quarantine ──► Postgres/Qdrant
 └──────────────┘                      │ (B5) outbound fetch: public addresses only
                                       ▼
                                   internet
```

| Boundary | Crossing | What can be attacker-controlled |
|---|---|---|
| B1 | user → API | query text, conversation history, image |
| B2 | admin → ingest | which documents enter the corpus |
| B3 | corpus → prompt | any text inside an ingested document |
| B4 | model → user | everything the model writes, including Markdown |
| B5 | worker → network | the URL and every redirect it leads to |

The public browser workspace has no server-side model by default. Its boundaries are
B1 (pasted diagnostics) and B4 (optional model output, validated against a JSON schema,
source IDs, verbatim quotes and a read-only command allowlist before display).

## Threats

| ID | Threat | OWASP 2025 | Control | Evidence | Status / open |
|---|---|---|---|---|---|
| T-01 | Instructions planted in an ingested document steer the model (indirect injection) | LLM01, LLM04 | Ingest scan on normalized text (NFKC, invisible characters, look-alikes, line splits); flagged documents are quarantined and contribute zero chunks. System prompt marks context as untrusted data. | [`security-redteam-v1`](../reports/security-redteam-v1-summary.json); [`security-robustness-v1`](../reports/security-robustness-v1.md): raw recall 0.00–0.07 under 4 of 5 transforms, normalized 1.00, specificity 1.00 | **Partly mitigated.** Regexes cannot catch rewording, translation or encodings. Next: a learned classifier layer measured on an external benchmark, and spotlighting (delimiting/encoding retrieved text). |
| T-02 | User types instructions to override the assistant (direct injection) | LLM01 | Flagged in `request_ledger.meta.injection_flags`, not blocked (ADR-0007): the chat path has no tools and no write access, so the impact is limited to the user's own answer. | `apps/api/tests/test_chat.py`; ADR-0007 | **Accepted** for a read-only assistant. Revisit when any tool can change state (see T-08). |
| T-03 | Model output exfiltrates data (auto-loading image URLs, links to attacker hosts, `javascript:` links) | LLM05 | Output guard on the token stream: images removed; links kept only for source hosts plus official documentation sites; non-http(s) schemes removed. The web console renderer enforces the same rules again (`disallowedElements`, `urlTransform`, `rel=noopener noreferrer nofollow`). Guard findings are recorded on the `done` event and in the ledger. | `libs/security/tests/test_output_guard.py` (including constructs split across stream tokens); `libs/rag/tests/test_chat_service.py::test_answer_is_sanitized_before_streaming` | **Mitigated** for Markdown and HTML images and links. Any guard rewrite raises an alert in `GET /v1/security/summary`, because it suggests a poisoned document got past T-01 (`apps/api/tests/test_security_summary.py`). |
| T-04 | Credentials reach the corpus, answers or traces | LLM02 | Redaction at ingest (before storage and embedding), on model output, and on trace payloads. The browser workspace redacts before any optional network call. Documentation placeholders are preserved. | `libs/security/tests/test_security.py` (16 credential formats, placeholder cases) | **Mitigated for known formats.** Pattern-based by design (ADR-0007); unlabelled high-entropy strings are not caught. |
| T-05 | System prompt disclosure | LLM07 | Prompts contain no secrets or authorization logic; they are public in this repository. Disclosure requests raise an ingest/query signal. | `libs/rag/src/opsverse_rag/chat.py` | **Accepted.** Nothing confidential to leak; access control never lives in a prompt. |
| T-06 | Corpus poisoning through the ingest API | LLM04, LLM08 | All `/v1/ingest` routes require an admin key (`OPSVERSE_ADMIN_API_KEY`, constant-time comparison). Outside `dev`, a missing key disables ingestion (fail closed). | `apps/api/tests/test_security_controls.py` | **Mitigated** for unauthenticated writes. Open: per-document provenance and signing for imported repositories. |
| T-07 | SSRF: the worker is pointed at internal services or cloud metadata | (web) | URL shape checked in the request handler; every redirect hop re-checked; the transport's network backend resolves once, requires every address to be public and **connects to that exact IP** (TLS still verified against the hostname), so DNS rebinding has no second lookup to exploit; proxy variables ignored; ports 80/443; responses capped at 20 MB. | `libs/security/tests/test_netguard.py`; `test_dns_rebinding_between_check_and_connect_is_refused`; `test_connection_goes_to_the_checked_address_not_a_new_lookup` | **Mitigated.** |
| T-08 | The assistant takes harmful actions | LLM06 | No tool can change state: the chat path has no tools, the five MCP tools are read-only, and the workspace's suggested `kubectl` commands are allowlisted to `get`/`describe`/`logs`/`rollout status/history` and never executed. | `opslm-demo/scripts/troubleshoot.test.mjs`; `apps/mcp-server/src/opsverse_mcp/server.py` | **Mitigated by design.** Any future agent with cluster access needs a policy engine on tool arguments and human approval for mutations before it ships. |
| T-09 | Compromised or vulnerable dependency, model artifact or deployment misconfiguration | LLM03 | `uv.lock` installed with `--frozen`; **blocking** `pip-audit` with a [reviewed register](../../.github/security/pip-audit-accepted.txt) giving a reason and exit condition per accepted advisory; **blocking** `npm audit` (high and above) for both Next.js apps; **blocking** Trivy scan of dependencies, secrets, Dockerfiles and Kubernetes manifests (HIGH and CRITICAL); Kubernetes workloads run non-root with read-only root filesystems and dropped capabilities; CycloneDX SBOM published by every CI run; gitleaks pre-commit hook. | CI `security-scan`, `runbook-product` and `web-console` jobs; [infra/k8s/README.md](../../infra/k8s/README.md) | **Partly mitigated.** Open: embedding models are fetched by name through fastembed, which takes no revision or hash; the hardened manifests pass Trivy but have not been applied to a live cluster. Accepted: pillow (capped by fastembed), litellm (held below 1.92 by the tracing pin), diskcache (no fix). |
| T-10 | Unbounded consumption (cost, memory, quota) | LLM10 | Per-client rate limits per route group (chat 20, search 60, ingest 10 per minute by default), shared across replicas through Redis and charged per WebSocket message, with a local fallback if Redis is down; gateway daily USD kill switch and response cache (ADR-0008); size limits on query, history, uploads and URL fetches. | `apps/api/tests/test_ratelimit.py`; `libs/core/tests/test_gateway.py`; `test_chat_and_search_reject_oversized_input` | **Mitigated** for single-source abuse. Open: distributed abuse from many addresses needs an edge rate limiter. |
| T-11 | Confident ungrounded answers | LLM09 | Abstain before generation when retrieval fails or is empty; numbered citations; the workspace verifies every claim's quote verbatim against its cited passage. | `libs/rag/tests/test_chat_service.py`; `docs/reports/troubleshooting-excerpts-v1.json` | **Partly mitigated.** Citation presence does not prove support; answer-level faithfulness evaluation is in [the eval reports](../evidence.md). |
| T-12 | Cross-user data exposure through the vector store | LLM08 | Single-tenant by design: the corpus is public vendor documentation and no user data is stored at rest (ADR-0007). | ADR-0007 | **Accepted** for a single tenant. Multi-tenant use needs permission-filtered retrieval before any private document is ingested. |
| T-13 | Path traversal or odd object keys from upload filenames | (web) | Filenames reduced to a safe basename and charset before use in object keys. | `test_safe_filename` | **Mitigated.** |

## How to verify

```bash
uv run pytest -q libs/security apps/api/tests/test_security_controls.py
```

```bash
uv run python -m opsverse_security.robustness
```

```bash
uv run python -m opsverse_security.evaluate
```

## Detect and respond

`GET /v1/security/summary?hours=24` (admin key required) reports flagged queries by
signal, output-guard rewrites by kind, quarantined documents, the 20 most recent security
events and plain-language alerts. It returns no query or answer text; the ledger never
stores any.

## Next steps, in order

1. **Learned injection classifier as a second T-01 layer**, scored on an external
   benchmark the regexes were not written against, reported as recall and false-positive
   rate with confidence intervals using the existing `opsverse_evals.stats`.
2. **Spotlighting for retrieved context**, ablated against attack success and answer
   quality on the existing golden set, so the security gain and its utility cost are
   measured together.
3. **Model artifact pinning**: load embedding models from a hash-checked local path (T-09).
