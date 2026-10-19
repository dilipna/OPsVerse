"use client";

import {useEffect, useRef, useState} from "react";
import {search, type Corpus} from "../lib/runbooks.mjs";

const examples = ["readiness probe failure", "ImagePullBackOff image pull policy", "memory limit OOMKilled", "deployment rollback revision"];
type Hit = ReturnType<typeof search>[number];

export default function Page() {
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState("");
  const [busy, setBusy] = useState(false);
  const resultRef = useRef<HTMLElement>(null);

  async function load() {
    setLoadError("");
    try {
      const r = await fetch("/runbooks.json");
      if (!r.ok) throw new Error("download failed");
      const data = await r.json();
      if (data.schema !== 1 || !Array.isArray(data.chunks) || !data.chunks.length) throw new Error("invalid corpus");
      setCorpus(data);
    } catch { setLoadError("The runbooks could not load. Check your connection and retry."); }
  }
  useEffect(() => {void load();}, []);
  function edit(text: string) {setQuery(text); setHits(null); setError(""); setSearched("");}
  async function run(text: string) {
    if (!corpus || busy) return;
    setQuery(text); setHits(null); setError(""); setBusy(true);
    try {
      if (!text.trim()) throw new Error("Enter a Kubernetes symptom or question first.");
      const result = search(corpus, text);
      setHits(result); setSearched(text.trim());
    } catch (e) {setError(e instanceof Error ? e.message : "Search failed. Please retry.");}
    finally {setBusy(false);}
    requestAnimationFrame(() => {resultRef.current?.focus(); resultRef.current?.scrollIntoView({block:"start", behavior:"smooth"});});
  }
  return <div className="navigator">
    <a className="skip" href="#question">Skip to search</a>
    <header className="site-header"><a className="wordmark" href="/">OPS<span>VERSE</span><small> / engineering lab</small></a>
      <nav aria-label="Main navigation"><a href="#evidence">Evidence</a><a href="/model-demo">Model demo</a><a href="https://github.com/dilipna/OPsVerse">GitHub ↗</a></nav></header>
    <main>
      <section className="intro"><p className="eyebrow">01 / RUNBOOK NAVIGATOR</p>
        <h1>Find the passage.<br/><span>Check the source.</span></h1>
        <p className="intro-copy">Troubleshooting Kubernetes? Search a small, pinned set of official docs. See the original passages and follow the evidence before changing your cluster.</p>
        <div className="mode"><span aria-hidden="true">●</span> Live lexical search · source excerpts · no generated answers</div>
      </section>
      <section className="search-panel" aria-labelledby="search-title"><div className="panel-heading"><h2 id="search-title">What are you investigating?</h2><span>6 documents / Kubernetes</span></div>
        <form onSubmit={e => {e.preventDefault(); void run(query);}}><label htmlFor="question">Symptom, command, or question</label>
          <textarea id="question" value={query} onChange={e => edit(e.target.value)} rows={3} maxLength={501} placeholder="e.g. Why does a failing readiness probe stop traffic?" aria-describedby="search-help"/>
          <div className="search-bottom"><p id="search-help">Runs in your browser. Your question stays on this page.</p><button type="submit" disabled={!corpus || busy}>{busy ? "Searching…" : "Find passages →"}</button></div>
        </form>
        <div className="examples"><span>Try a search</span>{examples.map(q => <button key={q} disabled={!corpus || busy} onClick={() => void run(q)}>{q}</button>)}</div>
        {!corpus && !loadError && <p role="status">Loading the public documentation snapshot…</p>}
        {loadError && <div role="alert"><p>{loadError}</p><button onClick={() => void load()}>Retry loading</button></div>}
      </section>
      <section ref={resultRef} tabIndex={-1} className="results" aria-label="Search results" aria-live="polite">
        {error && <p className="error" role="alert">{error}</p>}
        {hits !== null && <><div className="result-heading"><h2>{hits.length ? "Matching passages" : "No matching passages"}</h2><button onClick={() => edit("")}>Clear search</button></div><p>For “{searched}” · ranked by distinct query-term overlap</p>
          {!hits.length && <div className="empty"><h3>There is no supported result in this snapshot.</h3><p>Try exact Kubernetes terms, or consult the full official docs. This collection covers probes, Pod and Service debugging, resource limits, deployments, and images. Lexical matches cannot establish that a passage answers your question.</p><a href="https://kubernetes.io/docs/">Open Kubernetes documentation ↗</a></div>}
          {hits.map((hit, i) => <article className="passage" key={hit.id}><div className="passage-meta"><span>EXCERPT {String(i+1).padStart(2,"0")} / {hit.document}</span><span>{hit.matched} query terms matched</span></div><h3>{hit.section}</h3><pre tabIndex={0} aria-label={`Source excerpt ${i+1}`}>{hit.text}</pre><div className="source-links"><a href={hit.source} target="_blank" rel="noreferrer">Pinned source ↗</a><a href={hit.canonical} target="_blank" rel="noreferrer">Current docs ↗</a><small>{hit.id}</small></div></article>)}
        </>}
        {hits === null && !error && <div className="before-search"><span>READY WHEN YOU ARE</span><p>Results will show exact source text. This tool does not diagnose your cluster or execute commands.</p></div>}
      </section>
      <section id="evidence" className="evidence"><p className="eyebrow">02 / WHAT YOU CAN VERIFY</p><h2>A small tool with a visible evidence chain.</h2>
        <div className="evidence-grid"><div><h3>From raw docs to passages</h3><p>Six official Markdown files pass through OpsVerse’s parser, chunker, quality filters, and security checks. The browser searches that generated corpus with term overlap.</p></div><div><h3>Bounded evaluation</h3><p>Development and held-out query cases compare term overlap against BM25. Results include failures and unsupported queries. These checks evaluate retrieval, not model answer quality.</p><a href="https://github.com/dilipna/OPsVerse/blob/main/docs/reports/runbook-evaluation.json">Inspect evaluation ↗</a></div><div><h3>Serving research, separately</h3><p>The historical T4 experiments compare full serving configurations. GPU results are stored evidence; SFT improvement and completed DPO are not established.</p><a href="https://github.com/dilipna/OPsVerse/blob/main/docs/claims.md">Read the claims ledger ↗</a></div></div>
        {corpus && <p className="provenance">Snapshot {corpus.manifest.retrieved_at} · <a href={`https://github.com/kubernetes/website/tree/${corpus.manifest.revision}`}>source {corpus.manifest.revision.slice(0,12)}</a> · {corpus.chunks.length} indexed passages · documentation © Kubernetes Authors, CC BY 4.0. Source passages retain upstream Markdown and may include template markers.</p>}
      </section>
    </main><footer className="site-footer"><span>Built by Dilip Nallamasa · OpsVerse</span><a href="https://github.com/dilipna/OPsVerse#quickstart">Reproduce locally ↗</a><span>Public-data prototype · no adoption claim</span></footer>
  </div>;
}
