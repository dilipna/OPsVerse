// The browser and release evaluation import this exact implementation.
const STOP = new Set("a an and are as at be by can do does for from how i if in is it me my of on or should that the this to was what when where which why will with you your".split(" "));
export function terms(text) {
  return (text.toLowerCase().match(/[a-z0-9]+(?:[.-][a-z0-9]+)*/g) || []).filter(t => t.length > 1 && !STOP.has(t));
}
export function search(corpus, query, limit = 5, mode = "overlap") {
  if (typeof query !== "string" || query.length > 500) throw new Error("Use a question of 500 characters or fewer.");
  const q = [...new Set(terms(query))];
  if (!q.length) return [];
  const docs = corpus.chunks.map(c => terms(c.text));
  const avg = docs.reduce((n, d) => n + d.length, 0) / (docs.length || 1);
  const df = Object.fromEntries(q.map(t => [t, docs.filter(d => d.includes(t)).length]));
  // At least two distinct matching terms for multi-term questions. This is a
  // lexical guard, not a calibrated answerability probability.
  const minMatch = Math.min(2, q.length);
  return corpus.chunks.map((chunk, i) => {
    const d = docs[i];
    let score = 0, matched = 0;
    for (const t of q) {
      const tf = d.filter(w => w === t).length;
      if (!tf) continue;
      matched++;
      const idf = Math.log(1 + (docs.length - df[t] + 0.5) / (df[t] + 0.5));
      score += mode === "overlap" ? 1 : idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * d.length / avg));
    }
    return {...chunk, score, matched};
  }).filter(c => c.matched >= minMatch).sort((a, b) => b.score - a.score || a.id.localeCompare(b.id)).slice(0, limit);
}
