# Runbook navigator architecture

The user is an engineer finding an official passage while learning or troubleshooting
Kubernetes. No external users or partner corpus are assumed.

The manifest pins upstream revision and SHA-256 for six raw Markdown files.
`opsverse_evals.runbook_fixture` verifies each hash and calls `ingest_bytes`: parsing,
section-aware chunking, quality/deduplication, secret redaction, injection quarantine.
It fails if a document yields no usable chunks. Each passage retains document ID,
section, pinned source and canonical URL. CI compares the generated JSON byte-for-byte.

Next.js serves that static corpus. Browser and evaluator import the same module.
Default ranking counts distinct query-term overlap with deterministic ID tie-breaking;
two matching terms are required when a query has at least two. BM25 is an evaluated
alternative (k1=1.2, b=0.75). Neither score is a confidence or answerability probability.

React displays escaped original text; Markdown and HTML are not executed. Excerpts
may retain upstream template markers or refer to unbundled code examples. Follow the
source link for context. Query edits clear old results; result focus moves into view.
Loading/retry, empty, malformed and oversized-input states are explicit.

No model, vector server, database or search API runs for a browser query. Questions are
not uploaded by the search code, although hosting access logs apply to asset requests.
No cluster commands execute. The separate model sample console validates input, bounds
conversation size, times out calls and reports upstream failures; its proxy does not retrieve.

## Evaluation and limits

Six development, 16 initially held-out positive, four negative (one empty), and four
stress queries were specified before the first metric run. The agent authored synthetic
questions and coarse document labels; this is not independent human assessment.
Selection between rankers used those results. Future improvements need new independent
passage labels and a fresh holdout for generalization claims.

Hit@k does not establish answer correctness. Generic words can return tangential passages;
paraphrases can miss. Limited coverage cannot answer arbitrary Kubernetes questions.
Pinned docs age while current links change. Stress cases remain in the report. No generated
answer quality, model-training gain or attack resistance is established by these tests.

CI exercises raw-input parity, actual ranker tests, both baselines and the production build.
A deliberate empty chunker fails fixture generation; removing passage text changes retrieval.
These checks complement the existing Qdrant smoke test rather than replacing the full stack.
