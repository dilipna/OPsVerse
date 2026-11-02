"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ask, bestSentence, buildIndex, tokenize } from "../../lib/ask.mjs";

const BLOB = "https://github.com/dilipna/OPsVerse/blob/main";
const SUGGESTIONS = [
  "How do you stop prompt injection?",
  "What happens if the classifier errors?",
  "Why hybrid search instead of dense only?",
  "How was the LLM judge validated?",
  "What can the agent not do?",
  "Why Qdrant over pgvector?",
  "What are the known limitations?",
  "Was continuous batching faster?",
];

type Chunk = { id: string; path: string; title: string; heading: string; text: string };
type Split = { n: number; hit1: number; hit3: number; misses: string[] };
type Corpus = { files: number; chunks: Chunk[]; evaluation: { dev: Split; heldout: Split } };
type Hit = { chunk: Chunk; score: number; matched: number };

const slug = (h: string) =>
  h
    .split(" › ")
    .pop()!
    .toLowerCase()
    .replace(/[^a-z0-9 -]/g, "")
    .trim()
    .replace(/\s+/g, "-");

/** Wraps question terms in <mark>; matching is on stems, like the ranker. */
function highlight(text: string, question: string): ReactNode[] {
  const q = new Set(tokenize(question));
  return text
    .split(/(\b[\w-]+\b)/)
    .map((part, i) =>
      /\w/.test(part) && tokenize(part).some((t) => q.has(t)) ? <mark key={i}>{part}</mark> : part,
    );
}

const snippet = (text: string, max = 300) =>
  text.length > max ? `${text.slice(0, max).replace(/\s+\S*$/, "")} …` : text;

export default function AskProject() {
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [failed, setFailed] = useState(false);
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState<{ hits: Hit[]; ms: number } | null>(null);
  const root = useRef<HTMLDivElement>(null);

  // Load the 340 KB corpus only when the section approaches the viewport.
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let started = false;
    const load = () => {
      if (started) return;
      started = true;
      fetch("/ask.json")
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then(setCorpus)
        .catch(() => setFailed(true));
    };
    if (!("IntersectionObserver" in window)) return load();
    const io = new IntersectionObserver((e) => e[0].isIntersecting && load(), {
      rootMargin: "600px",
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const index = useMemo(() => (corpus ? buildIndex(corpus.chunks) : null), [corpus]);

  function run(q: string) {
    const text = q.trim();
    setQuestion(text);
    if (!index || !text) return;
    const t0 = performance.now();
    const hits = ask(index, text, 4) as Hit[];
    setResult({ hits, ms: performance.now() - t0 });
    setAsked(text);
  }

  const top = result?.hits[0];
  const ev = corpus?.evaluation;

  return (
    <div className="ask" ref={root}>
      <form
        className="ask-form"
        onSubmit={(e) => {
          e.preventDefault();
          run(question);
        }}
      >
        <label htmlFor="ask-input" className="sr-only">
          Ask a question about RYPE
        </label>
        <input
          id="ask-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={index ? "Ask anything about how RYPE was built…" : "Loading the docs…"}
          maxLength={300}
          autoComplete="off"
        />
        <button type="submit" disabled={!index}>
          Ask
        </button>
      </form>
      <div className="ask-suggest" aria-label="Example questions">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" onClick={() => run(s)} disabled={!index}>
            {s}
          </button>
        ))}
      </div>
      {failed && <p className="ask-empty">The documentation index could not load. Please retry.</p>}

      <div aria-live="polite">
        {result && !top && (
          <p className="ask-empty">
            Nothing in the docs matches that. Try different words: the retriever is lexical, so it
            needs at least one term the documentation uses.
          </p>
        )}
        {top && (
          <div className="ask-result" key={asked}>
            <div className="ask-answer">
              <small>MOST RELEVANT SENTENCE</small>
              <p>{highlight(bestSentence(top.chunk.text, asked), asked)}</p>
              <span>
                from {top.chunk.title}
                {top.chunk.heading ? ` › ${top.chunk.heading}` : ""}
              </span>
            </div>
            <ol className="ask-sources">
              {result!.hits.map((h, i) => (
                <li key={h.chunk.id} style={{ animationDelay: `${i * 70}ms` }}>
                  <a
                    href={`${BLOB}/${h.chunk.path}${h.chunk.heading ? `#${slug(h.chunk.heading)}` : ""}`}
                  >
                    <b>[{i + 1}]</b> {h.chunk.title}
                    {h.chunk.heading && <em> › {h.chunk.heading}</em>} ↗
                  </a>
                  <code>{h.chunk.path}</code>
                  <p>{highlight(snippet(h.chunk.text), asked)}</p>
                  <span className="ask-score">BM25 {h.score.toFixed(2)}</span>
                </li>
              ))}
            </ol>
            <p className="ask-meta">
              Ranked {corpus!.chunks.length} passages in {result!.ms.toFixed(1)} ms, in your
              browser. No model wrote this answer: every word is quoted from the repository.
            </p>
          </div>
        )}
      </div>

      {ev && (
        <details className="ask-eval">
          <summary>
            Measured, not assumed: held-out hit@3{" "}
            <b>
              {ev.heldout.hit3}/{ev.heldout.n}
            </b>
            , dev{" "}
            <b>
              {ev.dev.hit3}/{ev.dev.n}
            </b>
          </summary>
          <p>
            Retrieval over {corpus!.files} files ({corpus!.chunks.length} passages) is scored on{" "}
            <a href={`${BLOB}/evalsets/ask-v1.json`}>{ev.dev.n + ev.heldout.n} questions</a> written
            before the retriever first ran, each labelled with the files that answer it. The dev
            half was used to fix a chunking bug and a stemming gap; the held-out half was never used
            for tuning (its aggregate was seen once, before any change). Hit@1: held-out{" "}
            {ev.heldout.hit1}/{ev.heldout.n}, dev {ev.dev.hit1}/{ev.dev.n}. CI recomputes these
            numbers with this exact code.
          </p>
          {ev.dev.misses.length + ev.heldout.misses.length > 0 && (
            <>
              <p>Questions where no labelled file reached the top 3:</p>
              <ul>
                {[
                  ...ev.heldout.misses.map((q) => [q, "held-out"]),
                  ...ev.dev.misses.map((q) => [q, "dev"]),
                ].map(([q, s]) => (
                  <li key={q}>
                    <button type="button" onClick={() => run(q)} disabled={!index}>
                      {q}
                    </button>{" "}
                    <small>{s}</small>
                  </li>
                ))}
              </ul>
            </>
          )}
        </details>
      )}
    </div>
  );
}
