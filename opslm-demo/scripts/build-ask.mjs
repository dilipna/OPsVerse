// Builds public/ask.json for the "Ask the project" section: the repository's own
// documentation, chunked by heading, plus the retrieval evaluation measured with the
// exact ranking code the page runs (lib/ask.mjs). `--check` fails when either the
// corpus or the reported evaluation is stale.
//
//   node opslm-demo/scripts/build-ask.mjs           # write
//   node opslm-demo/scripts/build-ask.mjs --check   # CI
//   node opslm-demo/scripts/build-ask.mjs --report  # print per-question results
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildIndex, chunkMarkdown, evaluate } from "../lib/ask.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const list = (dir) =>
  fs
    .readdirSync(path.join(root, dir))
    .filter((f) => f.endsWith(".md"))
    .sort()
    .map((f) => `${dir}/${f}`);

// Documents that explain the project. Runbook content (the product's own corpus) and
// historical planning notes are left out so answers describe the system, not Kubernetes.
const EXCLUDE = new Set([
  "docs/demo-runbook.md",
  "docs/opslm-before-after-runbook.md",
  "docs/opslm-before-after-aws-runbook.md",
  "docs/local-research.md",
  "docs/migration-plan.md",
]);
const files = [
  "README.md",
  ...list("docs"),
  ...list("docs/security"),
  ...list("docs/adr"),
  ...list("docs/blog"),
  ...list("docs/reports"),
].filter((f) => !EXCLUDE.has(f));

const chunks = files.flatMap((f) => chunkMarkdown(f, read(f)));
const index = buildIndex(chunks);
const questions = JSON.parse(read("evalsets/ask-v1.json"));
const split = (name) => {
  const r = evaluate(index, questions[name], 3);
  return {
    n: r.n,
    hit1: r.hit1,
    hit3: r.hitk,
    misses: r.rows.filter((x) => !x.rank).map((x) => x.q),
  };
};
const evaluation = {
  dataset: "evalsets/ask-v1.json",
  k: 3,
  dev: split("dev"),
  heldout: split("heldout"),
};

if (process.argv.includes("--report")) {
  for (const name of ["dev", "heldout"]) {
    const r = evaluate(index, questions[name], 3);
    console.log(`\n${name}: hit@1 ${r.hit1}/${r.n}, hit@3 ${r.hitk}/${r.n}`);
    for (const row of r.rows)
      console.log(`  ${row.rank ?? "-"}  ${row.q}\n       ${row.got.join("\n       ")}`);
  }
}

const data = {
  schema: 1,
  generated_by: "node opslm-demo/scripts/build-ask.mjs",
  files: files.length,
  evaluation,
  chunks: chunks.map(({ id, path: p, title, heading, text }) => ({
    id,
    path: p,
    title,
    heading,
    text,
  })),
};
const out = path.join(root, "opslm-demo/public/ask.json");
const rendered = JSON.stringify(data) + "\n";
if (process.argv.includes("--check")) {
  if (!fs.existsSync(out) || fs.readFileSync(out, "utf8") !== rendered)
    throw new Error(
      "Ask corpus or its evaluation is stale; run node opslm-demo/scripts/build-ask.mjs",
    );
  console.log(
    `Ask corpus current: ${files.length} files, ${chunks.length} passages; held-out hit@3 ${evaluation.heldout.hit3}/${evaluation.heldout.n}`,
  );
} else if (!process.argv.includes("--report")) {
  fs.writeFileSync(out, rendered);
  console.log(
    `Ask corpus written: ${files.length} files, ${chunks.length} passages, ${(rendered.length / 1024).toFixed(0)} KB`,
  );
}
