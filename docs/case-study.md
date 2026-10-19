# From an impressive stack to inspectable evidence

OpsVerse already combined ingestion, hybrid RAG, QLoRA artifacts and serving measurements.
The missing product property was a visitor workflow that worked without infrastructure.

The audit found that success-only latency percentiles could hide 99 failures out of 100.
The selector now requires consistent counts, acceptable errors, enough successes and valid
measurements. Regression tests pit a fast failing run against a slower reliable one.

Repeatability also pooled cache-on/off runs with different request counts and mislabeled
a relative range as symmetric uncertainty. Matching now requires model revision, engine
version, precision, cache policy, hardware, workload, output policy, protocol, concurrency,
request count and distinct run IDs. Missing historical metadata means uncertainty is unmeasured.

For the public workflow, a small excerpt navigator earned its complexity better than an
always-on generator. Six attributed official Kubernetes source files pass through the real
ingestion pipeline; the browser searches 180 passages and displays pinned source links.
CI starts at raw input and exercises the exact shipped retrieval function.

The experiment rejected an unnecessary upgrade: BM25 achieved 14/16 document hit@1,
term overlap 15/16, and both 16/16 hit@3. No significant advantage was established, so
overlap ships. The synthetic labels are coarse and selection used these results; these
cases are now regression data, not a perpetual untouched holdout.

Failures remain visible. Vague symptoms can miss, shared words can return unrelated text,
and instruction-like questions can retrieve passages. Provenance makes those failures
inspectable; it does not solve semantic retrieval. A future study should independently
label passage relevance and paraphrases before comparing the existing hybrid retriever.
A matched served base-versus-SFT experiment remains unverified; DPO has not earned priority.

This is a bounded public tool and a stronger release contract, with no invented users,
cost savings, training-quality gain or production-readiness claim.
