// Builds public/home.json for the landing page from committed reports only, so every
// number a visitor sees traces to a file in docs/reports. `--check` fails when stale.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const json = (p) => JSON.parse(fs.readFileSync(path.join(root, p), "utf8"));
const round = (x, d = 3) => Math.round(x * 10 ** d) / 10 ** d;

const SOURCES = {
  agent: "docs/reports/agent-v1-summary.json",
  classifier: "docs/reports/security-classifier-v1-summary.json",
  redteam: "docs/reports/security-redteam-v1-summary.json",
  robustness: "docs/reports/security-robustness-v1-summary.json",
  retrieval: "docs/reports/retrieval-ablation-v3-summary.json",
  generator: "docs/reports/generator-golden-v1-summary.json",
  judge: "docs/reports/judge-validation-v2-summary.json",
  security: "opslm-demo/public/security.json",
  fixtures: "opslm-demo/scripts/lab-fixtures.json",
};
const src = Object.fromEntries(Object.entries(SOURCES).map(([k, p]) => [k, json(p)]));

const { clean, clean_heldout: heldout, adversarial } = src.agent.summary;
const secretsReason = "resource kind not allowed: secrets";
const secretsRefused =
  (clean.refused_by_reason?.[secretsReason] ?? 0) +
  (adversarial.refused_by_reason?.[secretsReason] ?? 0);
const test = src.classifier.datasets["deepset-test"];
const zeroWidth = (mode) => src.robustness.detail[`${mode}/zero_width`].tpr_recall;
const retrieval = src.retrieval.results;
const judge = src.judge.human_vs_judge;
const threats = src.security.threats;

const data = {
  schema: 1,
  generated_by: "node opslm-demo/scripts/build-home.mjs",
  generated_from: Object.values(SOURCES),
  agent: {
    model: src.agent.model,
    scenarios: src.agent.scenarios,
    heldout: { k: heldout.accuracy.k, n: heldout.accuracy.n },
    attacked_accuracy: { k: adversarial.accuracy.k, n: adversarial.accuracy.n },
    attacked_runs: adversarial.runs,
    attack_success: adversarial.attack_success.k,
    attack_success_ci_hi: adversarial.attack_success.ci95[1],
    derailed: adversarial.derailed.k,
    refused_commands: clean.refused_commands_total + adversarial.refused_commands_total,
    secrets_refused: secretsRefused,
    attacks: src.agent.redteam_ids.length,
  },
  injection: {
    internal_attacks: src.redteam.detail.attacks,
    internal_tpr: src.redteam.detail.tpr_recall,
    external_dataset: "deepset/prompt-injections (test split)",
    external_attacks: test.meta.attacks,
    external_benign: test.meta.benign,
    regex_tpr: round(test.results.regex.tpr),
    regex_tpr_ci95: test.results.regex.tpr_ci95,
    layered_tpr: round(test.results.regex_or_llm.tpr),
    layered_tpr_ci95: test.results.regex_or_llm.tpr_ci95,
    layered_fpr: round(test.results.regex_or_llm.fpr),
    layered_fpr_ci95: test.results.regex_or_llm.fpr_ci95,
    classifier_model: src.classifier.model,
    zero_width_raw_tpr: round(zeroWidth("raw")),
    zero_width_normalized_tpr: round(zeroWidth("normalized")),
  },
  retrieval: {
    questions: src.retrieval.cases,
    documents: src.retrieval.corpus_stats.documents,
    chunks: src.retrieval.corpus_stats.chunks,
    dense_hit10: retrieval.dense["chunk:hit@10"],
    sparse_hit10: retrieval.sparse["chunk:hit@10"],
    hybrid_hit10: retrieval.hybrid["chunk:hit@10"],
    hybrid_ms: retrieval.hybrid.latency_ms_per_query,
    rerank_ms: retrieval["hybrid+rerank"].latency_ms_per_query,
  },
  generation: {
    claims: src.generator.total_claims,
    contextual_recall: round(src.generator.modes["hybrid+rerank"].mean),
  },
  judge: {
    n: judge["Cohen's kappa (binary)"].n,
    kappa: round(judge["Cohen's kappa (binary)"].mean, 2),
    human_tpr: round(judge["TPR (rater says relevant -> judge found it)"].mean, 2),
  },
  threats: {
    total: threats.length,
    mitigated: threats.filter((t) => /^Mitigated/.test(t.status)).length,
    accepted: threats.filter((t) => t.status === "Accepted").length,
  },
  parity_cases:
    src.fixtures.scan.length +
    src.fixtures.redact.length +
    src.fixtures.guard.length +
    src.fixtures.policy.length,
};

// Fail loudly instead of publishing a blank number when a report field moves.
const missing = [];
const walk = (v, at) =>
  v === undefined || v === null || Number.isNaN(v)
    ? missing.push(at)
    : typeof v === "object" && Object.entries(v).forEach(([k, x]) => walk(x, `${at}.${k}`));
walk(data, "home");
if (missing.length) throw new Error(`Missing report fields: ${missing.join(", ")}`);

const out = path.join(root, "opslm-demo/public/home.json");
const rendered = JSON.stringify(data, null, 2) + "\n";
if (process.argv.includes("--check")) {
  if (!fs.existsSync(out) || fs.readFileSync(out, "utf8").replace(/\r\n/g, "\n") !== rendered)
    throw new Error("Landing page data is stale; run node opslm-demo/scripts/build-home.mjs");
  console.log("Landing page data matches committed reports");
} else {
  fs.writeFileSync(out, rendered);
  console.log(`Landing page data generated from ${Object.keys(SOURCES).length} sources`);
}
