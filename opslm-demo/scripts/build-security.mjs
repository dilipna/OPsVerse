// Builds public/security.json for the /security page from committed artifacts only:
// the robustness and red-team summaries, and the threat model's own table.
// `--check` fails when the page data is stale, so CI keeps the page honest.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const text = (p) => fs.readFileSync(path.join(root, p), "utf8").replace(/\r\n/g, "\n");
const json = (p) => JSON.parse(text(p));

const robustness = json("docs/reports/security-robustness-v1-summary.json");
const redteam = json("docs/reports/security-redteam-v1-summary.json");
const threatModel = text("docs/security/threat-model.md");
const external = json("docs/reports/security-classifier-v1-summary.json");

const transforms = Object.keys(robustness.results)
  .filter((key) => key.startsWith("raw/"))
  .map((key) => key.slice(4));
const rows = transforms.map((name) => {
  const raw = robustness.detail[`raw/${name}`];
  const normalized = robustness.detail[`normalized/${name}`];
  return {
    transform: name,
    raw_tpr: raw.tpr_recall,
    normalized_tpr: normalized.tpr_recall,
    raw_specificity: raw.specificity,
    normalized_specificity: normalized.specificity,
  };
});

// One row per threat: "| T-01 | threat | OWASP | control | evidence | status |".
const threats = threatModel
  .split("\n")
  .filter((line) => /^\| T-\d+ \|/.test(line))
  .map((line) => {
    const cells = line.split(" | ").map((cell) =>
      cell
        .replace(/^\| ?| ?\|$/g, "")
        .replace(/`/g, "")
        .trim(),
    );
    const status = cells[5].match(/\*\*([^*]+)\*\*/);
    return {
      id: cells[0],
      threat: cells[1],
      owasp: cells[2],
      status: status ? status[1].replace(/\.$/, "") : "See threat model",
    };
  });
if (threats.length === 0) throw new Error("No threats parsed from docs/security/threat-model.md");

const data = {
  schema: 1,
  generated_from: [
    "docs/reports/security-robustness-v1-summary.json",
    "docs/reports/security-redteam-v1-summary.json",
    "docs/security/threat-model.md",
    "docs/reports/security-classifier-v1-summary.json",
  ],
  classifier_model: external.model,
  external: Object.entries(external.datasets)
    .filter(([name]) => name.startsWith("deepset"))
    .map(([name, block]) => ({
      name,
      attacks: block.meta.attacks,
      benign: block.meta.benign,
      tpr: block.results.regex.tpr,
      tpr_ci95: block.results.regex.tpr_ci95,
      layered_tpr: block.results.regex_or_llm.tpr,
      layered_tpr_ci95: block.results.regex_or_llm.tpr_ci95,
      layered_fpr: block.results.regex_or_llm.fpr,
      layered_fpr_ci95: block.results.regex_or_llm.fpr_ci95,
      llm_errors: block.results.llm.errors,
    })),
  redteam: {
    attacks: redteam.detail.attacks,
    benign: redteam.detail.benign,
    tpr: redteam.detail.tpr_recall,
    specificity: redteam.detail.specificity,
  },
  robustness: { date: robustness.date, cases: robustness.cases, rows },
  threats,
};

const out = path.join(root, "opslm-demo/public/security.json");
const rendered = JSON.stringify(data, null, 2) + "\n";
if (process.argv.includes("--check")) {
  if (!fs.existsSync(out) || fs.readFileSync(out, "utf8").replace(/\r\n/g, "\n") !== rendered)
    throw new Error("Security page data is stale; run build-security.mjs");
  console.log("Security page matches committed reports and threat model");
} else {
  fs.writeFileSync(out, rendered);
  console.log(`Security page data generated: ${threats.length} threats, ${rows.length} transforms`);
}
