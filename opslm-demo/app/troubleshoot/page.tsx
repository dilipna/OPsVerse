"use client";

import {useEffect,useRef,useState} from "react";
import {troubleshoot,redact,type Result} from "../../lib/troubleshoot.mjs";
import type {Corpus} from "../../lib/runbooks.mjs";

const EXAMPLES=[
  {title:"Image won't pull",issue:"Why has this container not started, and what should I inspect?",diagnostics:"Name: web\nNamespace: shop\nState: Waiting\nReason: ImagePullBackOff\nFailed to pull image registry.example/web:missing"},
  {title:"Readiness failed",issue:"The process is running, but the Pod receives no traffic. What does this signal mean?",diagnostics:"Name: api\nNamespace: shop\nWarning Unhealthy Readiness probe failed: HTTP probe failed with statuscode: 503"},
  {title:"Memory termination",issue:"What can I infer from this termination, and what evidence is still missing?",diagnostics:"Name: worker\nNamespace: batch\nLast State: Terminated\nReason: OOMKilled\nExit Code: 137\nNo memory-usage profile provided"},
];

export default function TroubleshootPage(){
  const [corpus,setCorpus]=useState<Corpus|null>(null),[loadError,setLoadError]=useState("");
  const [issue,setIssue]=useState(""),[diagnostics,setDiagnostics]=useState("");
  const [result,setResult]=useState<Result|null>(null),[error,setError]=useState("");
  const [busy,setBusy]=useState(false),[configured,setConfigured]=useState(false),[copied,setCopied]=useState("");
  const results=useRef<HTMLElement>(null);
  async function load(){
    setLoadError("");
    try{const r=await fetch("/runbooks.json");if(!r.ok)throw new Error();const c=await r.json();if(c.schema!==1||!Array.isArray(c.chunks))throw new Error();setCorpus(c);}
    catch{setLoadError("The documentation snapshot could not load. Check your connection and retry.");}
  }
  useEffect(()=>{void load();fetch("/api/troubleshoot").then(r=>r.json()).then(d=>setConfigured(d.generation_configured===true)).catch(()=>setConfigured(false));},[]);
  function edit(nextIssue:string,nextDiagnostics:string){setIssue(nextIssue);setDiagnostics(nextDiagnostics);setResult(null);setError("");setCopied("");}
  async function analyze(generate=false){
    if(!corpus||busy)return;
    setBusy(true);setError("");setResult(null);setCopied("");
    try{
      const local=await troubleshoot(corpus,{issue,diagnostics});
      setResult(local);
      if(generate&&local.sources.length){
        // Remove recognized credentials locally before any diagnostic text leaves this page.
        const payload={issue:redact(issue).text,diagnostics:redact(diagnostics).text};
        const response=await fetch("/api/troubleshoot",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload),signal:AbortSignal.timeout(58000)});
        const data=await response.json();if(!response.ok)throw new Error(data.error||"The model request failed.");
        setResult({...data,redactions:local.redactions});
      }
    }catch(e){setError(e instanceof Error?e.message:"The request failed. Please retry.");}
    finally{setBusy(false);requestAnimationFrame(()=>{results.current?.focus();results.current?.scrollIntoView({block:"start",behavior:"smooth"});});}
  }
  function exportBrief(){
    if(!result)return;
    const brief={created_at:new Date().toISOString(),...result,boundary:"Observed signals and documentation support; not a confirmed root cause. No commands executed. Credential redaction is best-effort."};
    const url=URL.createObjectURL(new Blob([JSON.stringify(brief,null,2)],{type:"application/json"}));
    const link=document.createElement("a");link.href=url;link.download="opsverse-incident-brief.json";link.click();URL.revokeObjectURL(url);
    setCopied("Incident brief downloaded. It contains the redacted input and displayed evidence.");
  }
  return <div className="navigator incident">
    <a className="skip" href="#incident-issue">Skip to incident input</a>
    <header className="site-header"><a className="wordmark" href="/">OPS<span>VERSE</span><small> / engineering lab</small></a><nav aria-label="Main navigation"><a href="/runbooks">Runbooks</a><a href="/engineering">Engineering</a><a href="https://github.com/dilipna/OPsVerse">GitHub ↗</a></nav></header>
    <main><section className="intro"><div className="intro-topline"><p className="eyebrow">KUBERNETES / INCIDENT WORKSPACE</p><a href="/engineering">Built by Dilip Nallamasa ↗</a></div><h1>Investigate the symptom.<br/><span>Show the evidence.</span></h1><p className="intro-copy">Turn Pod events and status output into a reviewable investigation brief, with source passages from official Kubernetes documentation.</p><div className="mode">Browser-based analysis · pinned source links · exportable incident brief</div><div className="workflow-strip" aria-label="Investigation workflow"><span><b>01</b> Describe the symptom</span><span><b>02</b> Inspect the evidence</span><span><b>03</b> Keep the brief</span></div></section>
    <div className="incident-layout"><section className="search-panel" aria-labelledby="intake-title"><h2 id="intake-title">Describe the incident</h2><p className="intake-note">Use sanitized diagnostic output. Recognized credential patterns are redacted locally, but detection is incomplete. Remove sensitive data before pasting.</p>
      <div className="examples">Synthetic examples{EXAMPLES.map(e=><button key={e.title} onClick={()=>edit(e.issue,e.diagnostics)} disabled={busy}>{e.title}</button>)}</div>
      <form onSubmit={e=>{e.preventDefault();void analyze();}}>
        <label htmlFor="incident-issue">What are you investigating?</label><textarea id="incident-issue" disabled={busy} value={issue} maxLength={501} rows={3} onChange={e=>edit(e.target.value,diagnostics)} placeholder="What happened, and what do you need to understand?"/>
        <label htmlFor="diagnostics">Diagnostic output (optional)</label><textarea id="diagnostics" disabled={busy} value={diagnostics} maxLength={12001} rows={8} onChange={e=>edit(issue,e.target.value)} placeholder="Paste sanitized events, status, or describe output. No cluster connection is made." aria-describedby="diagnostics-help"/>
        <p id="diagnostics-help" className="intake-note">Find evidence runs locally. Generation is offered only when a model endpoint has been configured.</p>
        <div className="incident-actions"><button disabled={!corpus||busy} type="submit">{busy?"Working…":"Find incident evidence →"}</button>{configured&&<button disabled={!corpus||busy} type="button" onClick={()=>void analyze(true)}>Ask configured model</button>}</div>
      </form>
      {configured?<p className="intake-note">Model availability is unverified. Asking the model sends the locally redacted issue and diagnostics to this app’s configured endpoint. A valid quote does not prove an explanation is correct.</p>:<p className="intake-note">This public deployment has no model endpoint configured. The evidence workflow is live; model examples, when available, are labeled recorded. <a href="https://github.com/dilipna/OPsVerse/blob/main/docs/troubleshooting.md">How this workflow works ↗</a></p>}
      {!corpus&&!loadError&&<p role="status">Loading pinned runbooks…</p>}{loadError&&<div role="alert"><p>{loadError}</p><button onClick={()=>void load()}>Retry loading</button></div>}
    </section>
    <section className="incident-results results" ref={results} tabIndex={-1} aria-label="Incident analysis" aria-live="polite">
      {error&&<p role="alert" className="error">{error}</p>}
      {!result&&!error&&<div className="before-search"><span>YOUR INVESTIGATION</span><h2>Start with one useful clue.</h2><p>Choose a synthetic example or describe your incident. We’ll match the symptom to a pinned runbook and keep the supporting passages visible.</p><div className="preview-observation"><span>EXAMPLE SIGNAL</span><code>ImagePullBackOff</code><p>Observed status → matching runbook → source evidence → investigation brief</p></div><p>The analysis uses the text you provide. Your cluster stays under your control.</p></div>}
      {result&&<><div className="result-heading"><h2>{result.mode==="generated"?"Model draft with evidence":result.mode==="abstained"?"No supporting evidence":"Incident evidence"}</h2><button onClick={exportBrief}>Export brief ↓</button></div>
        <p className="intake-note">{result.note}</p>
        {result.redactions>0&&<p className="redaction" role="status">{result.redactions} recognized credential pattern(s) redacted. Review the input for anything the detector missed.</p>}
        {result.diagnostics_truncated&&<p className="redaction">Only the first 2,000 diagnostic characters are included in the model context and exported analysis. Signals can still be recognized across the full allowed input.</p>}
        <div className="signal-row"><span>OBSERVED SIGNALS</span>{result.signals.length?result.signals.map(s=><b key={s}>{s}</b>):<p>Add a status such as ImagePullBackOff or a warning event to make the search more specific.</p>}</div>
        {result.answer&&<article className="model-draft"><span className="eyebrow">{result.answer.status.replaceAll("_"," ")} · {result.model}</span><h3>{result.answer.summary}</h3>{result.answer.claims.map((c,i)=><div key={i} className="claim"><p>{c.text}</p><blockquote>{c.quote}</blockquote><a href={result.sources.find(s=>s.id===c.source_id)?.source} target="_blank" rel="noreferrer">Source {c.source_id} ↗</a></div>)}
          {!!result.answer.questions.length&&<><h3>Evidence still needed</h3><ul>{result.answer.questions.map(q=><li key={q}>{q}</li>)}</ul></>}
          {!!result.answer.commands.length&&<><h3>Read-only suggestions · not executed</h3>{result.answer.commands.map(c=><pre tabIndex={0} key={c.command}>{c.command}</pre>)}</>}
        </article>}
        {!result.sources.length&&<div className="empty"><p>This six-document snapshot does not support a result. Try a concrete Kubernetes status or use the broader official documentation.</p><a href="https://kubernetes.io/docs/">Open Kubernetes docs ↗</a></div>}
        {result.sources.map((s,i)=><details className="incident-source" key={s.id} open={i===0}><summary>{i+1}. {s.section} <small>{s.id}</small></summary><pre tabIndex={0} aria-label={`Incident source ${i+1}`}>{s.text}</pre><a href={s.source} target="_blank" rel="noreferrer">Pinned official source ↗</a><a href={s.canonical} target="_blank" rel="noreferrer">Current docs ↗</a></details>)}
        <p className="intake-note">Open the source for full context. Signals identify observed text patterns; confirming a cause requires your diagnostic evidence.</p><p role="status">{copied}</p>
      </>}
    </section></div>
    <section className="evidence"><p className="eyebrow">02 / A VISIBLE DECISION PATH</p><div className="evidence-grid"><div><h3>Input → signals → evidence</h3><p>Known status strings expand the retrieval query. The same pinned passages remain inspectable, whether or not a model is configured.</p></div><div><h3>Model outputs must pass checks</h3><p>The optional answer path requires valid JSON, supplied source IDs, matching quotes, and supported read-only command forms. Failed or truncated responses are rejected.</p></div><div><h3>Measure before claiming a win</h3><p>A frozen protocol defines a future comparison of excerpt-only retrieval and base/SFT served artifacts. Model inference is deferred. Completion, evidence validity, phrase coverage and abstention are separate measurements.</p><a href="/study">Inspect the study →</a></div></div></section>
    </main><footer className="site-footer"><span>OpsVerse · built by Dilip Nallamasa</span><a href="/runbooks">Search all runbook passages</a><a href="/engineering">Architecture & engineering decisions →</a></footer>
  </div>;
}
