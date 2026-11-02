// "Ask the project": retrieval over RYPE's own documentation, run in the browser.
// The build script (scripts/build-ask.mjs) and the page import this same file, so the
// evaluation numbers shown on the site are measured on exactly this ranking code.

const STOP = new Set(
  (
    "a about after all also an and any are as at be been but by can could did do does " +
    "for from had has have how i if in into is it its me my no not of on or our should so " +
    "than that the their them then there these they this those to too used using via was " +
    "we were what when where which while who why will with would you your"
  ).split(" "),
);

/** Very light stemmer: enough to match "injections" with "injection". */
export function stem(t) {
  if (t.length > 5 && t.endsWith("ing")) return t.slice(0, -3);
  if (t.length > 4 && t.endsWith("ies")) return `${t.slice(0, -3)}y`;
  if (t.length > 4 && t.endsWith("ed")) return t.slice(0, -2);
  if (t.length > 4 && /(ch|sh|x|z|ss)es$/.test(t)) return t.slice(0, -2);
  if (t.length > 3 && t.endsWith("s") && !t.endsWith("ss")) return t.slice(0, -1);
  return t;
}

export function tokenize(text) {
  return (
    String(text)
      .toLowerCase()
      .match(/[a-z0-9]+(?:[-][a-z0-9]+)*/g) || []
  )
    .filter((t) => t.length > 1 && !STOP.has(t))
    .map(stem);
}

/** Split Markdown into heading-scoped passages of at most `max` characters. */
export function chunkMarkdown(path, markdown, max = 900) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const chunks = [];
  const trail = [];
  let title = path;
  let buffer = [];
  let inFence = false;
  const flush = () => {
    const text = buffer
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    buffer = [];
    if (text.replace(/[^a-zA-Z]/g, "").length < 60) return;
    const paragraphs = text.split(/\n\n+/).flatMap((p) => splitLong(p, max));
    let part = "";
    for (const p of paragraphs) {
      if (part && part.length + p.length + 2 > max) {
        chunks.push({ path, title, heading: trail.join(" › "), text: part });
        part = "";
      }
      part = part ? `${part}\n\n${p}` : p;
    }
    if (part) chunks.push({ path, title, heading: trail.join(" › "), text: part });
  };
  for (const line of lines) {
    if (/^```/.test(line)) inFence = !inFence;
    const h = !inFence && line.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      flush();
      const level = h[1].length;
      const name = h[2].replace(/[`*_]/g, "").trim();
      if (level === 1) {
        title = name;
        trail.length = 0;
      } else {
        trail.length = Math.max(0, level - 2);
        trail.push(name);
      }
      continue;
    }
    buffer.push(line);
  }
  flush();
  return chunks.map((c, i) => ({ id: `${path}#${i}`, ...c, text: cleanMarkdown(c.text) }));
}

/** Break an over-long block at line ends; a table keeps its header row on every piece. */
function splitLong(block, max) {
  if (block.length <= max) return [block];
  const lines = block.split("\n");
  const isTable = lines[0].startsWith("|") && /^\|[\s:|-]+\|$/.test(lines[1] ?? "");
  const header = isTable ? `${lines[0]}\n${lines[1]}\n` : "";
  const body = isTable ? lines.slice(2) : lines;
  const pieces = [];
  let piece = "";
  for (const line of body) {
    if (piece && header.length + piece.length + line.length + 1 > max) {
      pieces.push(header + piece);
      piece = "";
    }
    piece = piece ? `${piece}\n${line}` : line;
  }
  if (piece) pieces.push(header + piece);
  return pieces;
}

export function cleanMarkdown(text) {
  return text
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/<\/?[a-z][^>]*>/gi, "")
    .replace(/\*\*|__/g, "")
    .replace(/(^|[\s(])\*([^*\n]+?)\*(?=$|[\s).,;:])/gm, "$1$2")
    .replace(/`/g, "")
    .replace(/^>\s?/gm, "")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

/** Precompute term statistics once per corpus. */
export function buildIndex(chunks) {
  const docs = chunks.map((c) => {
    const tf = new Map();
    for (const t of tokenize(c.text)) tf.set(t, (tf.get(t) || 0) + 1);
    // Titles and headings say what a passage is about; count them three times.
    for (const t of tokenize(`${c.title} ${c.heading}`)) tf.set(t, (tf.get(t) || 0) + 3);
    let length = 0;
    for (const n of tf.values()) length += n;
    return { tf, length };
  });
  const df = new Map();
  for (const d of docs) for (const t of d.tf.keys()) df.set(t, (df.get(t) || 0) + 1);
  const avg = docs.reduce((n, d) => n + d.length, 0) / (docs.length || 1);
  return { chunks, docs, df, avg };
}

/** BM25 (k1 = 1.2, b = 0.75). Returns the top `k` passages with their scores. */
export function ask(index, question, k = 4) {
  if (typeof question !== "string" || question.length > 300) return [];
  const q = [...new Set(tokenize(question))];
  if (!q.length) return [];
  const n = index.docs.length;
  const scored = [];
  index.docs.forEach((d, i) => {
    let score = 0;
    let matched = 0;
    for (const t of q) {
      const tf = d.tf.get(t);
      if (!tf) continue;
      matched += 1;
      const df = index.df.get(t) || 0;
      const idf = Math.log(1 + (n - df + 0.5) / (df + 0.5));
      score += (idf * tf * 2.2) / (tf + 1.2 * (0.25 + (0.75 * d.length) / index.avg));
    }
    if (matched) scored.push({ chunk: index.chunks[i], score, matched });
  });
  scored.sort((a, b) => b.score - a.score || a.chunk.id.localeCompare(b.chunk.id));
  // One passage per file keeps the answer from repeating a single document.
  const seen = new Set();
  const out = [];
  for (const s of scored) {
    if (seen.has(s.chunk.path)) continue;
    seen.add(s.chunk.path);
    out.push(s);
    if (out.length === k) break;
  }
  return out;
}

/** The sentence of a passage that shares the most question terms: the extractive answer. */
export function bestSentence(text, question) {
  const q = new Set(tokenize(question));
  const sentences = text
    .replace(/\n+/g, " ")
    .split(/(?<=[.!?])\s+(?=[A-Z0-9])/)
    .filter((s) => s.length > 30 && s.length < 400);
  let best = sentences[0] ?? text.slice(0, 240);
  let bestScore = -1;
  for (const s of sentences) {
    const hits = new Set(tokenize(s).filter((t) => q.has(t))).size;
    if (hits > bestScore) {
      bestScore = hits;
      best = s;
    }
  }
  return best;
}

/** hit@k over questions with one or more acceptable source files. */
export function evaluate(index, questions, k = 3) {
  const rows = questions.map(({ q, expect }) => {
    const got = ask(index, q, k).map((r) => r.chunk.path);
    const rank = got.findIndex((p) => expect.includes(p));
    return { q, expect, got, rank: rank === -1 ? null : rank + 1 };
  });
  const hit = (n) => rows.filter((r) => r.rank !== null && r.rank <= n).length;
  return { n: rows.length, hit1: hit(1), hitk: hit(k), k, rows };
}
