# RYPE knowledge workspace

## Product behavior

“What is a pod in Kubernetes?” now returns a readable cited definition without an LLM request. The historical six-document, 180-passage research snapshot remains unchanged. A separate editorial Pod guide links to the official [Kubernetes Pod documentation](https://kubernetes.io/docs/concepts/workloads/pods/); it is a paraphrase, not a purported pinned quotation. Concept-guide results are labeled separately from original excerpts and private material.

The new workspace controller runs a bounded plan → retrieve → observe coverage → retry if applicable → answer or route flow. It is ReAct-style tool orchestration implemented with deterministic rules, **not an LLM reasoning agent** and not displayed chain-of-thought. At most two hybrid searches are performed; supported troubleshooting signals retain the original bounded family-based evidence selection. No tools execute cluster commands.

Hybrid retrieval combines BM25 word relevance and character-trigram cosine similarity via reciprocal-rank fusion (constant 60), with Unicode tokenization and small explicit Kubernetes aliases. It does **not** use dense semantic embeddings, a local neural model or an embedding API. This keeps the retrieval path inference-free. A term-overlap gate is not an entailment or answerability model: paraphrases can be missed, and factual support requires review. Definition questions must have their content terms in one readable paragraph; code-generation, comparison and unsupported mixed requests route instead. An explicit concept-guide preference prevents incidental Pod links from outranking the definition. Search observations and source IDs are inspectable.

## Private browser library

The user selected private browser storage with portable backups. IndexedDB stores document text across future sessions in the same browser profile and origin. It is not a shared global database, account sync, encrypted vault or permanent-storage guarantee. Clearing site data, private browsing or browser eviction can remove it. A user-initiated persistence request reports whether the browser granted it; it never claims guaranteed retention. See [IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API) and [persistent storage](https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/persist).

- Maximum 10 UTF-8 text/Markdown documents, 50 KB each and 250 KB total. Other formats must be converted to text by the user; no PDF/DOCX upload parser is claimed.
- Recognized credentials are redacted before storage; detection is best-effort. Do not store secrets.
- SHA-256 of redacted content identifies duplicate documents. Bounded 1,200-character chunks overlap by 200 characters; indices are rebuilt locally.
- Read/write transactions recheck size and duplicate limits against the latest stored state. Failed writes do not claim success. Other tabs receive only a change notification and reread storage.
- Individual deletion, confirmed clear-all, library JSON backup and additive restore are available. Restore validates and re-ingests text, ignoring supplied IDs, URLs or indices. It never follows document links or executes instructions.
- Documents and retrieved private passages are never included in OpenRouter requests. Public inference accepts only question and diagnostics fields. The fallback can answer generally but has no access to an uncovered private document; it must not claim otherwise.
- Private excerpts can be present in an answer or downloaded notes. Deleting the original library document does not erase already displayed discussion turns or previously downloaded files; clear the discussion separately.

## Discussion-aware downloads

The active tab retains up to 12 accepted answers and per-answer notes. Users can revisit answers, clear the discussion or copy an answer with its references. Discussion history is not persisted and is not sent as model conversation context; requests remain independent. This boundary is visible in the interface.

“Download notes” opens a preview with discussion/current-answer scope and an overridable format recommendation:

- Reading/study discussions: an actual locally generated PDF with questions, answer extracts, notes, source references, route/model/call/cost receipt and page numbers.
- Coding discussions: ZIP of actual fenced code blocks, safe generated filenames, a README and discussion Markdown. Unknown language labels become `.txt`. If a coding answer contains no fenced code, no script is invented; notes-only output is explained.
- Markdown remains available for any discussion, and the existing per-answer JSON reopen workflow remains compatible. Reopen reruns trusted retrieval and never accepts imported answer authority.

Code is not executed, sandbox-verified or declared safe. Output credential redaction is best-effort and may change code containing token/password literals; review before use. PDF generation uses a static instance of the existing OFL-licensed Inter font (`build-notes-font.py` reproduces it). Unsupported glyphs are explicitly written as Unicode code points rather than silently dropped; Markdown preserves original Unicode. Documents and discussions are never uploaded to generate a download. No extra inference call is used for formatting or summarization.

## Validation scope

`npm test` includes actual Pod routing/HTTP checks, hybrid score determinism, unsupported/mixed requests, private-document matching/removal, instruction-like text rejection, bounds, duplicate detection, backup re-ingestion, public-API private-field rejection, ZIP content/path safety and actual PDF parsing/pagination. Browser contracts exercise IndexedDB reload/restore/delete, storage denial, modal focus/mobile bounds, study PDF and code ZIP downloads, history/notes and zero-POST retrieval. Browser inference is stubbed, not a quality benchmark. All browser execution is restricted to GitHub runners; no desktop control or local browser installation.

The new features do not change the historical research evaluation inputs or justify new claims about real-user adoption, optimal routing, measured quality-matched savings or model-training-data membership. Existing free-only provider pricing caps, privacy restrictions and server-only key handling remain in force.
