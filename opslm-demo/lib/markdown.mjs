// A small Markdown parser for the site's write-ups. It produces a plain JSON tree that
// the page renders as React elements, so no HTML from a post ever reaches the DOM as
// markup. Supported: headings, paragraphs, lists, block quotes, fenced code, tables,
// rules, and inline code, bold, italic and links. Links survive only with http(s),
// mailto or in-page targets; anything else is kept as plain text.

const SAFE_LINK = /^(https?:\/\/|mailto:|#)/i;

/** Parse inline Markdown into nodes: text, code, strong, em, link. */
export function parseInline(src) {
  const out = [];
  let i = 0;
  let text = "";
  const flush = () => {
    if (text) out.push({ t: "text", v: text });
    text = "";
  };
  while (i < src.length) {
    const c = src[i];
    if (c === "\\" && i + 1 < src.length && /[\\`*_[\]()#|<>!-]/.test(src[i + 1])) {
      text += src[i + 1];
      i += 2;
      continue;
    }
    if (c === "`") {
      const run = src.slice(i).match(/^`+/)[0];
      const end = src.indexOf(run, i + run.length);
      if (end !== -1) {
        flush();
        out.push({ t: "code", v: src.slice(i + run.length, end).trim() });
        i = end + run.length;
        continue;
      }
    }
    if ((c === "*" || c === "_") && src[i + 1] === c) {
      const end = src.indexOf(c + c, i + 2);
      if (end > i + 2) {
        flush();
        out.push({ t: "strong", c: parseInline(src.slice(i + 2, end)) });
        i = end + 2;
        continue;
      }
    }
    if (c === "*" || (c === "_" && !/\w/.test(src[i - 1] ?? ""))) {
      const end = findClosing(src, c, i + 1);
      if (end > i + 1) {
        flush();
        out.push({ t: "em", c: parseInline(src.slice(i + 1, end)) });
        i = end + 1;
        continue;
      }
    }
    if (c === "[") {
      const m = matchLink(src, i);
      if (m) {
        flush();
        const children = parseInline(m.label);
        if (SAFE_LINK.test(m.href)) out.push({ t: "link", href: m.href, c: children });
        else out.push(...children);
        i = m.end;
        continue;
      }
    }
    text += c;
    i += 1;
  }
  flush();
  return out;
}

function findClosing(src, mark, from) {
  for (let j = from; j < src.length; j++) {
    if (src[j] === "`") {
      const close = src.indexOf("`", j + 1);
      if (close === -1) return -1;
      j = close;
      continue;
    }
    if (src[j] === mark && src[j + 1] !== mark && src[j - 1] !== " ") {
      if (mark === "_" && /\w/.test(src[j + 1] ?? "")) continue;
      return j;
    }
  }
  return -1;
}

function matchLink(src, start) {
  let depth = 0;
  let j = start;
  for (; j < src.length; j++) {
    if (src[j] === "[") depth++;
    else if (src[j] === "]" && --depth === 0) break;
  }
  if (j >= src.length || src[j + 1] !== "(") return null;
  // The target may itself contain balanced parentheses.
  let close = -1;
  for (let k = j + 2, parens = 1; k < src.length; k++) {
    if (src[k] === "(") parens++;
    else if (src[k] === ")" && --parens === 0) {
      close = k;
      break;
    }
  }
  if (close === -1) return null;
  const href = src
    .slice(j + 2, close)
    .trim()
    .split(/\s+/)[0];
  return { label: src.slice(start + 1, j), href, end: close + 1 };
}

const splitRow = (line) =>
  line
    .trim()
    .replace(/^\||\|$/g, "")
    .split(/(?<!\\)\|/)
    .map((cell) => parseInline(cell.trim().replace(/\\\|/g, "|")));

/** Parse a Markdown document into block nodes. */
export function parseMarkdown(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  const isBlank = (l) => !l || !l.trim();
  const startsBlock = (l) =>
    /^(#{1,6}\s|```|>|\s*[-*+]\s|\s*\d+[.)]\s|\||---+\s*$|\*\*\*+\s*$)/.test(l);
  while (i < lines.length) {
    const line = lines[i];
    if (isBlank(line)) {
      i++;
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (h) {
      blocks.push({ t: "h", level: h[1].length, c: parseInline(h[2]) });
      i++;
      continue;
    }
    if (/^```/.test(line)) {
      const lang = line.slice(3).trim();
      const body = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++]);
      i++;
      blocks.push({ t: "code", lang, v: body.join("\n") });
      continue;
    }
    if (/^(---+|\*\*\*+)\s*$/.test(line)) {
      blocks.push({ t: "hr" });
      i++;
      continue;
    }
    if (/^>/.test(line)) {
      const body = [];
      while (i < lines.length && /^>/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push({ t: "quote", c: parseMarkdown(body.join("\n")) });
      continue;
    }
    if (/^\|/.test(line) && /^\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1] ?? "")) {
      const head = splitRow(line);
      const align = lines[i + 1]
        .trim()
        .replace(/^\||\|$/g, "")
        .split("|")
        .map((a) => (/^\s*:-+:\s*$/.test(a) ? "center" : /-:\s*$/.test(a) ? "right" : "left"));
      const rows = [];
      i += 2;
      while (i < lines.length && /^\|/.test(lines[i])) rows.push(splitRow(lines[i++]));
      blocks.push({ t: "table", head, align, rows });
      continue;
    }
    const li = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (li) {
      const ordered = /\d/.test(li[2]);
      const start = ordered ? parseInt(li[2], 10) : 1;
      const items = [];
      while (i < lines.length) {
        const m = lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        if (m && /\d/.test(m[2]) === ordered && m[1].length <= li[1].length) {
          items.push([m[3]]);
          i++;
        } else if (!isBlank(lines[i]) && /^\s+\S/.test(lines[i]) && items.length) {
          items[items.length - 1].push(lines[i].trim());
          i++;
        } else break;
      }
      blocks.push({ t: "list", ordered, start, items: items.map((p) => parseInline(p.join(" "))) });
      continue;
    }
    const para = [];
    while (i < lines.length && !isBlank(lines[i]) && (para.length === 0 || !startsBlock(lines[i])))
      para.push(lines[i++].trim());
    blocks.push({ t: "p", c: parseInline(para.join(" ")) });
  }
  return blocks;
}

/** Plain text of inline nodes, for titles, excerpts and reading time. */
export function inlineText(nodes) {
  return nodes.map((n) => (n.t === "text" || n.t === "code" ? n.v : inlineText(n.c))).join("");
}
