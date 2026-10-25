# OpsVerse — question-first product experience

The user clarified that the workbench still looked too technical and requested the abstraction and usability of a chat website. The primary surface is now a centered question composer with starter examples, optional logs and a readable response. It retains the selected white/teal identity and self-hosted sans-serif fonts.

- One primary action: Send question. Enter submits; Shift+Enter adds a line; IME composition does not submit.
- Optional log input sits behind Add logs or error details. Sensitive-input guidance is adjacent to the field.
- A response leads with relevant guide titles and source-derived prose previews. Previews remove only inline Markdown formatting and use existing source words; they are not synthesized answers or a root-cause finding. Code, frontmatter and template fragments are omitted from previews, with full source passages still available.
- Source passages, retrieval details, budget counters and personal notes are available on demand. No engineering metrics or architecture panels occupy the empty conversation view.
- New question and Ask another question clear both fields, the response and notes, close optional logs and focus the question. Each question is an independent search. There is no persistent chat history or claim of contextual follow-up.
- The page explicitly says that its Kubernetes library is limited and no AI model is connected. If a model is configured in a separate deployment, it remains a separate explicit Ask AI model action and its data boundary is disclosed.
- Research, source library and engineering documentation stay available in secondary navigation. Small screens retain access through Explore guides and About this assistant.

Existing retrieval, redaction, truncation, abstention, validation and exported JSON semantics are preserved. Exports remain unreviewed notes with exact source provenance. Full-evidence gap notices stay visible rather than being hidden with implementation detail.

Browser tests run only on GitHub. Responsive coverage includes the simplified empty state, actual documentation response, optional controls, Enter/Shift+Enter, exact-source preview grounding, reset, error/retry, note redaction and actual downloads. No desktop control or local browser install, paid calls, hosted model, main merge or hosting-setting changes.