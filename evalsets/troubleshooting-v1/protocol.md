# Troubleshooting artifact comparison v1

Freeze before model inference. User: an engineer interpreting sanitized Kubernetes
diagnostics and deciding which read-only check to make next. Public-data, synthetic
scenarios only; no external users or independent human labels.

Compare excerpt-only, Qwen3-4B-Base Q4_K_M, and OpsLM-v1 Q4_K_M through the same
application request preparation, retrieval, context budget, prompt, decoding and
validation functions. The GGUFs were independently converted: conversion provenance
is a confound. This is a served-artifact comparison, not an isolated causal SFT effect.
No paid API, hosted GPU, model training or DPO run is authorized by this protocol.

Use six development cases for prompt/debugging only. Freeze 24 held-out cases before
their first inference. Do not change the prompt or ranker based on held-out outcomes.
All attempts, failures, timeouts, exclusions and raw model responses must be recorded.
Never silently repair a failed response or substitute canned output.

Measure separately: request completion; JSON/schema validity; source-ID and verbatim
quote validity; reference-fact phrase coverage; abstention/clarification status; unsafe
command rejection; latency. Phrase coverage is a coarse deterministic diagnostic,
not independently judged factual accuracy. Valid citations do not prove entailment.
Report numerators and denominators per model, plus paired per-case results. Do not
infer significant superiority from point estimates on this small synthetic set.

Fixed configuration: temperature=0, seed=42, max_tokens=384, context: at most three
passages and 6000 characters; diagnostic text in prompt at most 2000 characters.
Same chat template for base and SFT. Report model revisions and SHA-256, runtime
version, template, actual server arguments, code commit/dirty status, dataset/corpus/
prompt hashes, hardware, run ID, token usage, truncation and memory exclusions.
Minimum 2.5 GiB available host RAM before a CPU model load; otherwise do not load.
Do not stop other people's services or applications to satisfy that requirement.

Release contract: no retrieval results must not invoke a model. Failed retrieval,
invalid generation, missing or invented citations, mismatched quotes, and unsupported
command forms must not appear as successful grounded answers. A valid response only
passes structural/provenance checks; answer support still needs review.

Before inference, check questions against committed SFT train/validation inputs with
the existing normalized exact and 5-gram Jaccard>=0.6 checks. Preserve all cases and
flag overlaps, rather than manufacturing a cleaner metric by silent exclusions.
Pretraining and semantic overlap are unknown. Questions/labels are agent-authored.

The public site must identify live retrieval, configured local generation, and recorded
model examples separately. It may offer the real excerpt workflow without a model
endpoint; it must not claim an always-on hosted model. Keep the prior navigator usable.
