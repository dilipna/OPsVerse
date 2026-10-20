# Resume evidence and interview notes

- Built and deployed a Kubernetes investigation workspace that turns diagnostic text
  into source-linked incident briefs over 180 passages from six revision-pinned
  official documents; connected ingestion, browser retrieval, export and CI checks.
- Hardened optional model output handling with source/quote validation and restricted
  command suggestions; added failure-path tests and made the RAG service abstain
  without invoking a model when retrieval is unavailable or empty.
- Compared term overlap and BM25 on 16 synthetic held-out questions; shipped the simpler
  baseline after 15/16 document hit@1 and 16/16 hit@3, documenting paraphrase failures
  and coarse-label limitations.
- Hardened LLM serving-capacity analysis to reject failed or undersampled runs and
  separate nonmatching configurations; recomputed historical T4 results with explicit
  error, sample, provenance and assumed-cost constraints.

Evidence: [evaluation](reports/runbook-evaluation.json), [capacity](reports/capacity-and-slo-v1.md),
[claims](claims.md), `test_admission_evidence.py`, and `test_runbook_fixture.py`.
Do not turn a 16-case result into general accuracy or historical T4 data into a fresh run.

Interview talking points:

1. Excerpts keep evidence visible and avoid paid always-on inference. Hybrid RAG/SFT remain
   separate research, not secretly implied by the public tool.
2. Success-only p95 concealed errors; the decision function now requires all evidence.
3. BM25 did not establish an advantage. Keep the cheaper baseline; inspect paired failures.
4. Selection used the initially held-out cases. Future claims need fresh questions and
   independent passage relevance labels; public cases now serve as regression data.
5. “My app keeps dying” can miss. Lexical relevance is not answerability. Compare matched
   hybrid retrieval on paraphrases before training another model.
6. Unknowns: base-versus-SFT quality, completed DPO, generated-answer quality, external-user
   usefulness and production reliability. No fabricated adoption or impact.

Demo sequence: open the workspace, choose Image won't pull, find evidence, inspect
the pinned source, export the brief, then show /engineering and /study. Explain
why the public path works without inference. Model comparisons remain deferred;
structural quote validation is not an answer-quality guarantee.
