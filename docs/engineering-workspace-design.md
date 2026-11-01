# OpsVerse — question-first product experience

The user clarified that the workbench still looked too technical and requested the abstraction and usability of a chat website. The primary surface is now a centered question composer with starter examples, optional logs and a readable response. The primary interaction stays simple while visual themes are documented below.

- One primary action: Send question. Enter submits; Shift+Enter adds a line; IME composition does not submit.
- Optional log input sits behind Add logs or error details. Sensitive-input guidance is adjacent to the field.
- A response leads with relevant guide titles and source-derived prose previews. Previews remove only inline Markdown formatting and use existing source words; they are not synthesized answers or a root-cause finding. Code, frontmatter and template fragments are omitted from previews, with full source passages still available.
- Source passages, retrieval details, budget counters and personal notes are available on demand. No engineering metrics or architecture panels occupy the empty conversation view.
- New question and Ask another question clear both fields, the response and notes, close optional logs and focus the question. Each question is an independent search. There is no persistent chat history or claim of contextual follow-up.
- The page explicitly says that its Kubernetes library is limited and no AI model is connected. If a model is configured in a separate deployment, it remains a separate explicit Ask AI model action and its data boundary is disclosed.
- Research, source library and engineering documentation stay available in secondary navigation. Small screens retain access through Explore guides and About this assistant.

Existing retrieval, redaction, truncation, abstention, validation and exported JSON semantics are preserved. Exports remain unreviewed notes with exact source provenance. Full-evidence gap notices stay visible rather than being hidden with implementation detail.

Browser tests run only on GitHub. Responsive coverage includes the simplified empty state, actual documentation response, optional controls, Enter/Shift+Enter, exact-source preview grounding, reset, error/retry, note redaction and actual downloads. No desktop control or local browser install, paid calls, hosted model, main merge or hosting-setting changes.
## Previous visual theme: Field Notes

Following the user's request to try a different theme, the current appearance uses ivory paper, a dark charcoal navigation rail, copper/orange controls and Georgia/Times serif editorial headings. Inter remains the interface font; Plus Jakarta Sans remains the wordmark and IBM Plex Mono supports diagnostic details. Serif headings use available platform fonts rather than installing a font or adding a network service. All existing licensed self-hosted files remain unchanged.

The chat interaction is unchanged. Guides, engineering pages and hosted research archives share the warm palette and serif heading treatment. The archive's explicit dark toggle uses a warm charcoal variant and retains distinct chart series. Historical scripts/data/claim text are unchanged. Browser checks retain existing user journeys and verify the new computed heading family.

## Current visual theme: Night Orbit

Midnight indigo pages, electric yellow controls, blue source links and geometric Space Grotesk headings replace the warm editorial appearance. Existing licensed Space Grotesk WOFF2 is self-hosted, preloaded and included with its OFL in release identity. Inter remains the UI font, Plus Jakarta Sans the wordmark and IBM Plex Mono the diagnostic font. No font installation or new dependency. Secondary pages share the night palette; research archives offer a blue daylight view and indigo dark toggle while preserving measured scripts/data/claims.

## Useful extensions

- Markdown downloads preserve the redacted question, diagnostic excerpt, unreviewed notes and selected source passages with pinned/current URLs. User/model/source text uses dynamically sized fences so embedded backticks cannot close a block and introduce executable Markdown/HTML.
- Reopen notes accepts an explicit user-selected JSON file up to 256 KiB, checks schema/status/current corpus revision and bounded string fields, redacts recognized secrets and restores only question/logs/notes. It reruns trusted retrieval and ignores imported answers, commands, timestamps, URLs and passages. Foreign-revision files must be copied into a new question manually. Downloads may contain only the first 2,000 diagnostic characters; the UI discloses this on restore. No model is called by restore.
- Save for later is opt-in device storage of up to 30 current public passage IDs and their corpus revision. Questions/logs are never included in this key. Unknown IDs, duplicate IDs, stale revisions and malformed storage are ignored. Quota/denied storage retains this tab's list with an explicit notice. The reading-list dialog supports Escape, focus return, individual removal and clearing.

These are bounded product integrations: portable versioned checkpoints adapt the recovery intent of idea 2 without claiming a durable orchestration state machine; idea 7 gains actual download/import/storage-failure browser trajectories, and sanitization boundaries extend to untrusted files. This is not three-tier memory (idea 6), a new retrieval-quality result, hosted inference or an inter-agent proxy. See the fifteen-idea decisions in flagship-release-plan.md.
## RYPE routing evolution

The visible application is now RYPE (Route Your Prompt Efficiently), retaining Night Orbit and portable tools. The home page explains covered-document retrieval without inference, task-based routing to eligible free OpenRouter models and cost receipts. No model-training membership claim. No paid inference/fallback is permitted. Receipts distinguish actual reported cost from hypothetical baseline estimates; no fixed reduction percentage or quality-equivalence claim. See rype-routing.md for the full contract and setup. This adapts idea 4 as explicit heuristics, not a learned optimal router. Restoring exported notes stays local and never reuses an imported answer or triggers inference automatically.
