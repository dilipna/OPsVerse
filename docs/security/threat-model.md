# OpsVerse threat model

*Last reviewed 2026-11-02. Scope: the research stack (FastAPI API, arq worker, Next.js
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
| T-03 | Model output exfiltrates data (auto-loading image URLs, links to attacker hosts, `javascript:` links) | LLM05 | Output guard on the token stream: images removed; links kept only for source hosts plus official documentation sites; non-http(s) schemes removed. The web console renderer enforces the same rules again (`disallowedElements`, `urlTransform`, `rel=noopener noreferrer nofollow`). Guard findings are recorded on the `done` event and in the ledger. | `libs/security/tests/test_output_guard.py` (including constructs split across stream tokens); `libs/rag/tests/test_chat_service.py::test_answer_is_sanitized_before_streaming` | **Mitigated** for Markdown and HTML images and links. Open: alert when `output_guard` findings appear, since they suggest a poisoned document got past T-01. |
| T-04 | Credentials reach the corpus, answers or traces | LLM02 | Redaction at ingest (before storage and embedding), on model output, and on trace payloads. The browser workspace redacts before any optional network call. Documentation placeholders are preserved. | `libs/security/tests/test_security.py` (16 credential formats, placeholder cases) | **Mitigated for known formats.** Pattern-based by design (ADR-0007); unlabelled high-entropy strings are not caught. |
| T-05 | System prompt disclosure | LLM07 | Prompts contain no secrets or authorization logic; they are public in this repository. Disclosure requests raise an ingest/query signal. | `libs/rag/src/opsverse_rag/chat.py` | **Accepted.** Nothing confidential to leak; access control never lives in a prompt. |
| T-06 | Corpus poisoning through the ingest API | LLM04, LLM08 | All `/v1/ingest` routes require an admin key (`OPSVERSE_ADMIN_API_KEY`, constant-time comparison). Outside `dev`, a missing key disables ingestion (fail closed). | `apps/api/tests/test_security_controls.py` | **Mitigated** for unauthenticated writes. Open: per-document provenance and signing for imported repositories. |
| T-07 | SSRF: the worker is pointed at internal services or cloud metadata | (web) | URL shape checked in the request handler; before every fetch **and every redirect hop**, the hostname is resolved and every address must be publicly routable; ports limited to 80/443; responses capped at 20 MB. | `libs/security/tests/test_netguard.py`; `test_fetch_rechecks_every_redirect_hop` | **Mitigated** except DNS rebinding between check and connect. Next: pin the connection to the checked address. |
| T-08 | The assistant takes harmful actions | LLM06 | No tool can change state: the chat path has no tools, the five MCP tools are read-only, and the workspace's suggested `kubectl` commands are allowlisted to `get`/`describe`/`logs`/`rollout status/history` and never executed. | `opslm-demo/scripts/troubleshoot.test.mjs`; `apps/mcp-server/src/opsverse_mcp/server.py` | **Mitigated by design.** Any future agent with cluster access needs a policy engine on tool arguments and human approval for mutations before it ships. |
| T-09 | Compromised or vulnerable dependency or model artifact | LLM03 | `uv.lock` installed with `--frozen`; **blocking** `pip-audit` in CI with a [reviewed register](../../.github/security/pip-audit-accepted.txt) giving a reason and exit condition per accepted advisory; Trivy filesystem scan; gitleaks pre-commit hook. | CI `security-scan` job | **Partly mitigated.** Open: Trivy is still advisory; models are pulled by name, not by pinned revision and hash; no SBOM yet. Accepted: pillow (capped by fastembed), litellm (held below 1.92 by the tracing pin), diskcache (no fix). |
| T-10 | Unbounded consumption (cost, memory, quota) | LLM10 | Gateway daily USD kill switch and response cache (ADR-0008); request size limits on every public route; upload 50 MB, URL fetch 20 MB, `k ≤ 20`, history capped at 8 turns. | `libs/core/tests/test_gateway.py` | **Partly mitigated.** Open: no per-client rate limit on the API. |
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

## Next steps, in order

1. **Learned injection classifier as a second T-01 layer**, scored on an external
   benchmark the regexes were not written against, reported as recall and false-positive
   rate with confidence intervals using the existing `opsverse_evals.stats`.
2. **Spotlighting for retrieved context**, ablated against attack success and answer
   quality on the existing golden set, so the security gain and its utility cost are
   measured together.
3. **Connection pinning** for URL ingestion (closes the T-07 rebinding gap).
4. **Pinned model revisions and hashes, an SBOM, and a blocking Trivy gate** (T-09).
5. **Per-client rate limiting** (T-10).
