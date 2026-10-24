# OpsVerse flagship website release candidate

This release improves the real browser-local Kubernetes investigation workflow and
the research stack's tested failure boundaries. It does not establish a generated
answer-quality gain or deploy a hosted model. The user's latest request authorizes
completion and deployment; production remains unchanged until the release gates pass.

## Changes

- Shared workspace/library/evaluation/engineering design, evidence provenance,
  explicit documentation-family gaps, context accounting and review-note export.
- Bounded, deterministic signal-family retrieval: at most four retrieval attempts,
  three passages and 6,000 evidence characters. Development family coverage changes
  from 14/20 to 19/20, with no final per-case regression on the frozen development
  set. This is not held-out diagnosis accuracy.
- Exact model-output fields, consistent abstention states, valid source IDs/quotes
  and restricted command forms. No command executes. Oversized request streams are
  cancelled before consuming their full body.
- Budgeted research calls fail closed on unavailable/corrupt counters. Post-call
  accounting still lacks in-flight reservation and complete retry billing; do not
  describe it as a hard spending cap.
- Build identity and normalized source hashes are served at `/release.json`.
  The identity includes dependency declarations, lockfile and identity scripts.
  A build compares every parsed lockfile field with the committed file and blocks
  dependency drift. An initial production fingerprint mismatch was rolled back;
  diagnostics isolated four removed `peer` flags. Removing those four flags
  reproduced the deployed lockfile byte hash exactly, with no version, integrity
  or resolved-URL changes. The corrected committed lock retains strict checks.

## Verification

Local: 333 Python tests, 49 Node tests, Ruff, Pyright, TypeScript, optimized build,
raw-source corpus regeneration, contamination identity, development coverage checks
and real production HTTP mode/failure tests passed. npm and the installed default
Python environment report no known vulnerabilities at the time of their audits.
Local workspace packages are tested source, not packages audited by PyPI advisories.

Before the desktop-control prohibition, Chrome QA verified actual example retrieval,
review-note entry, keyboard focus, an actual downloaded/redacted brief, desktop
rendering and 360-pixel library/evaluation layouts. This was the prior candidate;
subsequent typography/status-label/request-reader changes are checked by build and
HTTP tests. No desktop or browser control is allowed on the user's computer now.

The new browser suite runs **only on GitHub's ephemeral runner**. It captures all six
HTML routes at 360/768/1440 pixels, checks overflow and landmarks, actual retrieval,
keyboard use, invalid/empty inputs, source gaps, actual JSON download/redaction and
stale-result clearing. It must pass remotely before the website release. The same
suite can verify public production through the PR's `verify-production` label.
No browser is installed or launched on the user's machine by these checks.

## Security compatibility and exclusions

Targeted dependency updates remove reported advisories from the default installed
environment. Historical DVC tooling moves to the optional `data-tools` group; its
unpatched diskcache advisories remain documented. That group is not installed by
default or in the API runtime. The filesystem scan remains advisory and may include
optional lockfile packages; do not equate it with a clean runtime scan.

Pillow 13 is an explicit application-maintained override beyond FastEmbed 0.8/0.9's
declared upper bound. A matched one-thread comparison of two actual 384-dimensional
CPU text vectors under verified Pillow 12.3.0 and 13.0.0 returned maximum difference
0.0. This covers the cached small text model only; image/PDF workflows and default
768-dimensional model-quality equivalence are not established. A mismatched
historical-reference comparison differed by 0.0004222; an initial reference setup
inherited the override and was excluded. Those attempts are retained in task evidence.

Docker is unavailable locally. A manifest-only reproduction found the API Docker
stage omitted required workspace manifests; adding them passes offline lock parsing.
The real image must pass GitHub CI. No Docker Desktop or unrelated service was started.

## Hosting and recovery

Existing project: `asmq333/inferllm`, ID `prj_8UGX0twOpNshJdINyjfud5NQG2UC`.
Git link: `dilipna/OPsVerse`, root `opslm-demo`, production branch `main`.
Public domain: https://ops-verse.vercel.app/.
Prior production: `dpl_5ytLEX1tfSXGLuJYfjzX9TnfTTV7`, source
`c385cc5f867834dc63dc93daa98d323dc98c48fe`, retained for rollback.

Publish an isolated branch/PR and require exact-head CI. Preserve main and project
settings. Deploy the immutable, full-root source archive (root `.gitattributes`
preserves canonical line endings); do not use a web-only Git subtree archive. Verify
public release identity, routes, source downloads, operating modes and error paths.
Trigger remote production-browser checks; roll back on a material release failure.
No paid service/model call, new hosting project, confidential input, or resume change.
