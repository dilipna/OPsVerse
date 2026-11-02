// Builds public/writing.json for /writing from docs/blog/*.md, parsed by lib/markdown.mjs
// into a tree the page renders as React elements. `--check` fails when it is stale.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { inlineText, parseMarkdown } from "../lib/markdown.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const dir = path.join(root, "docs/blog");
const BLOB = "https://github.com/dilipna/OPsVerse/blob/main";

const words = (blocks) =>
  blocks
    .map((b) =>
      b.t === "p" || b.t === "h"
        ? inlineText(b.c)
        : b.t === "list"
          ? b.items.map(inlineText).join(" ")
          : b.t === "quote"
            ? words(b.c)
            : b.t === "table"
              ? b.rows.flat().map(inlineText).join(" ")
              : "",
    )
    .join(" ");

const posts = fs
  .readdirSync(dir)
  .filter((f) => /^\d+-.*\.md$/.test(f))
  .sort()
  .map((file) => {
    const markdown = fs.readFileSync(path.join(dir, file), "utf8");
    const blocks = parseMarkdown(markdown);
    const titleBlock = blocks.find((b) => b.t === "h" && b.level === 1);
    if (!titleBlock) throw new Error(`${file} has no # title`);
    const body = blocks.filter((b) => b !== titleBlock);
    const published = markdown.match(/Published at \[(https:\/\/[^\]]+)\]/)?.[1] ?? null;
    const lead = body.find((b) => b.t === "p");
    const n = file.match(/^(\d+)-/)[1];
    return {
      n,
      slug: file.replace(/^\d+-/, "").replace(/\.md$/, ""),
      title: inlineText(titleBlock.c),
      status: published ? "published" : /\bDraft\b/.test(markdown.slice(0, 400)) ? "draft" : "repo",
      canonical: published,
      source: `${BLOB}/docs/blog/${file}`,
      excerpt: lead ? inlineText(lead.c).slice(0, 260) : "",
      minutes: Math.max(1, Math.round(words(body).split(/\s+/).length / 230)),
      blocks: body,
    };
  });

const out = path.join(root, "opslm-demo/public/writing.json");
const rendered =
  JSON.stringify({ schema: 1, generated_by: "node opslm-demo/scripts/build-writing.mjs", posts }) +
  "\n";
if (process.argv.includes("--check")) {
  if (!fs.existsSync(out) || fs.readFileSync(out, "utf8") !== rendered)
    throw new Error("Writing data is stale; run node opslm-demo/scripts/build-writing.mjs");
  console.log(`Writing data current: ${posts.length} posts`);
} else {
  fs.writeFileSync(out, rendered);
  console.log(
    `Writing data written: ${posts.map((p) => `${p.slug} (${p.status}, ${p.minutes} min)`).join("; ")}`,
  );
}
