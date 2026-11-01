# Signal Studio

Historical design, superseded by the user's explicit
[white-and-teal engineering workspace](engineering-workspace-design.md) selection.

Current visual direction, replacing the earlier Evidence Atlas design after the
user requested different background, fonts and components throughout the product.

Lavender-gray canvas, deep-plum studio hero, lime calls to action, floating
navigation, rounded working surfaces and a stacked-card workflow illustration.
Space Grotesk handles headings, IBM Plex Sans the interface, and IBM Plex Mono
diagnostics/source material. All three are self-hosted WOFF2 assets, with official
OFL files and pinned source provenance retained in `opslm-demo/public/fonts/`.

The new hero and layered signal cards are illustrative, not live cluster telemetry.
Engineering decisions use an asymmetric reading grid. Library, evaluation, forms,
source excerpts and the retained console share this typography and color system.
No user metrics, model-quality claim or external integration is added by the theme.

Browser checks wait for font readiness before screenshot capture and verify actual
font requests, loaded font faces, computed families and binary hashes against the
deployed release identity. Existing retrieval/export/keyboard/retry checks remain.
No desktop/browser control on the owner's computer is permitted.

The hosted benchmark/claim archive uses `public/report-theme.css` and shared
research navigation. `scripts/publish-research.mjs` decorates the canonical offline
exports during builds; those original files remain self-contained and unchanged.
Research scripts and claim paragraphs are checked for byte-preserving publication.
Historical scope and the current claims ledger are visible before the old reports.
