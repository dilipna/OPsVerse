import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  ask,
  bestSentence,
  buildIndex,
  chunkMarkdown,
  evaluate,
  stem,
  tokenize,
} from "../lib/ask.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const corpus = JSON.parse(fs.readFileSync(path.join(here, "../public/ask.json"), "utf8"));
const questions = JSON.parse(
  fs.readFileSync(path.join(here, "../../evalsets/ask-v1.json"), "utf8"),
);

test("stemming joins common inflections and leaves short words alone", () => {
  assert.equal(stem("injections"), "injection");
  assert.equal(stem("fetches"), stem("fetch"));
  assert.equal(stem("policies"), "policy");
  assert.equal(stem("ssrf"), "ssrf");
  assert.deepEqual(tokenize("How do the Agents work?"), ["agent", "work"]);
});

test("chunking keeps every table row and repeats the header", () => {
  const rows = Array.from({ length: 40 }, (_, i) => `| T-${i} | ${"word ".repeat(20)}|`);
  const md = `# Doc\n\n## Threats\n\n| ID | Threat |\n|---|---|\n${rows.join("\n")}\n`;
  const chunks = chunkMarkdown("doc.md", md, 400);
  assert.ok(chunks.length > 1);
  for (let i = 0; i < 40; i++)
    assert.ok(
      chunks.some((c) => c.text.includes(`T-${i} `)),
      `row ${i}`,
    );
  for (const c of chunks) assert.ok(c.text.startsWith("| ID | Threat |"), "header on every piece");
  assert.equal(chunks[0].heading, "Threats");
});

test("chunking ignores headings inside code fences and strips Markdown links", () => {
  const md =
    "# T\n\n## Real\n\nSee [the docs](https://x.test) for the details of this section here.\n\n```\n# not a heading\n```\n";
  const [c] = chunkMarkdown("a.md", md);
  assert.equal(c.heading, "Real");
  assert.ok(c.text.includes("See the docs for"));
  assert.ok(c.text.includes("# not a heading"));
});

test("answers come from distinct files, best first", () => {
  const index = buildIndex(corpus.chunks);
  const hits = ask(index, "Why did you choose Qdrant instead of pgvector?");
  assert.equal(hits[0].chunk.path, "docs/adr/0002-qdrant-over-pgvector-and-pinecone.md");
  assert.equal(new Set(hits.map((h) => h.chunk.path)).size, hits.length);
  assert.deepEqual(ask(index, "the and of"), []);
  assert.deepEqual(ask(index, "x".repeat(301)), []);
});

test("the extractive answer is the sentence sharing most question terms", () => {
  const text =
    "Qdrant was chosen. It supports hybrid sparse and dense search natively in one query. Other text follows here.";
  assert.match(bestSentence(text, "Does it support hybrid sparse search?"), /hybrid sparse/);
});

test("the evaluation shown on the site is what this code measures", () => {
  const index = buildIndex(corpus.chunks);
  for (const split of ["dev", "heldout"]) {
    const r = evaluate(index, questions[split], 3);
    assert.equal(r.hitk, corpus.evaluation[split].hit3, split);
    assert.equal(r.hit1, corpus.evaluation[split].hit1, split);
  }
});
