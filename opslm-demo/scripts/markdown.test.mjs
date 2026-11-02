import assert from "node:assert/strict";
import test from "node:test";
import { inlineText, parseInline, parseMarkdown } from "../lib/markdown.mjs";

test("inline code is literal, even when it looks like an image or a link", () => {
  const nodes = parseInline("a split construct (`![x](https://att` … `acker.test/...)`) here");
  assert.deepEqual(
    nodes.filter((n) => n.t === "code").map((n) => n.v),
    ["![x](https://att", "acker.test/...)"],
  );
  assert.ok(!nodes.some((n) => n.t === "link"));
});

test("only http(s), mailto and in-page links survive; others become plain text", () => {
  assert.deepEqual(parseInline("[ok](https://x.test/a)"), [
    { t: "link", href: "https://x.test/a", c: [{ t: "text", v: "ok" }] },
  ]);
  for (const bad of ["javascript:alert(1)", "data:text/html,hi", "vbscript:x", "//evil.test"]) {
    const nodes = parseInline(`[click](${bad})`);
    assert.ok(!nodes.some((n) => n.t === "link"), bad);
    assert.equal(inlineText(nodes), "click");
  }
});

test("bold, italic and escapes", () => {
  assert.deepEqual(parseInline("**bold** and *it* and snake_case_name and \\*no\\*"), [
    { t: "strong", c: [{ t: "text", v: "bold" }] },
    { t: "text", v: " and " },
    { t: "em", c: [{ t: "text", v: "it" }] },
    { t: "text", v: " and snake_case_name and *no*" },
  ]);
});

test("raw HTML stays text: the tree has no node type that renders markup", () => {
  const blocks = parseMarkdown("Hello <img src=x onerror=alert(1)> world");
  assert.equal(blocks[0].t, "p");
  assert.equal(inlineText(blocks[0].c), "Hello <img src=x onerror=alert(1)> world");
});

test("blocks: headings, quotes, lists, tables, code and rules", () => {
  const md = [
    "# Title",
    "",
    "> **Note** quoted",
    "> second line",
    "",
    "- one",
    "  continued",
    "- two",
    "",
    "1. first",
    "2. second",
    "",
    "| a | b |",
    "|---|--:|",
    "| `x|y` | 2 |",
    "",
    "```bash",
    "echo hi",
    "```",
    "",
    "---",
    "Para line one",
    "line two",
  ].join("\n");
  const b = parseMarkdown(md);
  assert.deepEqual(
    b.map((x) => x.t),
    ["h", "quote", "list", "list", "table", "code", "hr", "p"],
  );
  assert.equal(inlineText(b[1].c[0].c), "Note quoted second line");
  assert.equal(inlineText(b[2].items[0]), "one continued");
  assert.equal(b[3].ordered, true);
  assert.deepEqual(b[4].align, ["left", "right"]);
  assert.equal(b[5].v, "echo hi");
  assert.equal(inlineText(b[7].c), "Para line one line two");
});
