"use client";

import {sourceFile} from "../../lib/source-links";
import {EvidenceAtlas} from "./evidence-atlas";


import {useEffect,useRef,useState} from "react";
import {troubleshoot,redact,type Result} from "../../lib/troubleshoot.mjs";
import type {Corpus} from "../../lib/runbooks.mjs";

const EXAMPLES=[
  {title:"Image won't pull",issue:"Why has this container not started, and what should I inspect?",diagnostics:"Name: web\nNamespace: shop\nState: Waiting\nReason: ImagePullBackOff\nFailed to pull image registry.example/web:missing"},
  {title:"Readiness failed",issue:"The process is running, but the Pod receives no traffic. What does this signal mean?",diagnostics:"Name: api\nNamespace: shop\nWarning Unhealthy Readiness probe failed: HTTP probe failed with statuscode: 503"},
  {title:"Memory termination",issue:"How does Kubernetes enforce container memory limits?",diagnostics:"Name: worker\nNamespace: batch\nLast State: Terminated\nReason: OOMKilled\nExit Code: 137\nNo memory-usage profile provided"},
];

export default function TroubleshootPage(){
  const [corpus,setCorpus]=useState<Corpus|null>(null),[loadError,setLoadError]=useState("");
  const [issue,setIssue]=useState(""),[diagnostics,setDiagnostics]=useState("");
  const [result,setResult]=useState<Result|null>(null),[error,setError]=useState("");
  const [busy,setBusy]=useState(false),[configured,setConfigured]=useState(false),[copied,setCopied]=useState("");
  const [notes,setNotes]=useState("");
  const results=useRef<HTMLElement>(null);
  async function load(){
    setLoadError("");
    try{const r=await fetch("/runbooks.json");if(!r.ok)throw new Error();const c=await r.json();if(c.schema!==1||!Array.isArray(c.chunks))throw new Error();setCorpus(c);}
    catch{setLoadError("The documentation snapshot could not load. Check your connection and retry.");}
  }
  useEffect(()=>{void load();fetch("/api/troubleshoot").then(r=>r.json()).then(d=>setConfigured(d.generation_configured===true)).catch(()=>setConfigured(false));},[]);
  function edit(nextIssue:string,nextDiagnostics:string){setIssue(nextIssue);setDiagnostics(nextDiagnostics);setResult(null);setNotes("");setError("");setCopied("");}
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
    const reviewNotes=redact(notes.slice(0,4000));
    const brief={schema_version:1,created_at:new Date().toISOString(),...result,
      review:{status:"unreviewed",notes:reviewNotes.text,notes_redactions:reviewNotes.redactions},
      source_revision:corpus?.manifest.revision,
      boundary:"Observed signals and documentation support; not a confirmed root cause. No commands executed. Credential redaction is best-effort."};
    const url=URL.createObjectURL(new Blob([JSON.stringify(brief,null,2)],{type:"application/json"}));
    const link=document.createElement("a");link.href=url;link.download="opsverse-incident-brief.json";link.click();URL.revokeObjectURL(url);
    setCopied("Incident brief downloaded. It contains the redacted input and displayed evidence.");
  }
  return <div className="navigator incident flagship-workspace">
    <a className="skip" href="#incident-issue">Skip to incident input</a>
    <header className="site-header"><a className="wordmark" href="/">OPS<span>VERSE</span><small> / engineering workspace</small></a><nav aria-label="Main navigation"><a className="active-nav" href="/" aria-current="page">Workspace</a><a href="/runbooks">Runbooks</a><a href="/study">Evaluation</a><a href="/engineering">Engineering ↗</a></nav></header>
    <main><section className="intro"><div className="intro-topline"><p className="eyebrow"><span className="status-dot"/> KUBERNETES / INVESTIGATION WORKSPACE</p><a href="/engineering">An engineering project by Dilip Nallamasa ↗</a></div><div className="workspace-title"><div><div className="workspace-label">EVIDENCE-FIRST ENGINEERING</div><h1>Investigate Kubernetes.<br/><span>Keep the evidence clear.</span></h1><p className="intro-copy">A focused workspace for diagnostic text, official documentation and reviewable incident briefs. Understand what the source supports—and what is still missing.</p><div className="workspace-actions"><a className="workspace-start" href="#incident-issue">Start investigating <span aria-hidden="true">↓</span></a><a href="/engineering">Inside the engineering ↗</a></div><div className="hero-facts"><span><b>06</b> pinned documents</span><span><b>180</b> source passages</span><span><b>Zero</b> commands executed</span></div></div><EvidenceAtlas/></div><div className="workflow-strip" aria-label="Investigation workflow"><span><b>01</b> Capture a symptom</span><span><b>02</b> Inspect the source</span><span><b>03</b> Keep a reviewable brief</span></div></section>
    <div className="workspace-section-label"><span>INVESTIGATION WORKBENCH</span><span>LOCAL INPUT · PINNED SOURCES · HUMAN REVIEW</span></div>
    <div className="incident-layout"><section className="search-panel" aria-labelledby="intake-title"><div className="panel-heading"><span className="panel-number">01</span><div><p className="eyebrow">INCIDENT INPUT</p><h2 id="intake-title">Start with what you observed.</h2></div></div><p className="intake-note">Use sanitized diagnostic output. Recognized credential patterns are redacted locally, but detection is incomplete. Remove sensitive data before pasting.</p>
      <div className="examples">Synthetic examples{EXAMPLES.map(e=><button key={e.title} onClick={()=>edit(e.issue,e.diagnostics)} disabled={busy}>{e.title}</button>)}</div>
      <form onSubmit={e=>{e.preventDefault();void analyze();}}>
        <label htmlFor="incident-issue">What are you investigating?</label><textarea id="incident-issue" disabled={busy} value={issue} maxLength={501} rows={3} onChange={e=>edit(e.target.value,diagnostics)} placeholder="What happened, and what do you need to understand?"/>
        <label htmlFor="diagnostics">Diagnostic output (optional)</label><textarea id="diagnostics" disabled={busy} value={diagnostics} maxLength={12001} rows={8} onChange={e=>edit(issue,e.target.value)} placeholder="Paste sanitized events, status, or describe output. No cluster connection is made." aria-describedby="diagnostics-help"/>
        <p id="diagnostics-help" className="intake-note">A status or warning event helps narrow the search. Input is not saved across page reloads.</p>
        <div className="incident-actions"><button disabled={!corpus||busy} type="submit">{busy?"Working…":"Find incident evidence →"}</button>{configured&&<button disabled={!corpus||busy} type="button" onClick={()=>void analyze(true)}>Ask configured model</button>}</div>
      </form>
      {configured?<p className="intake-note">Model availability is unverified. Asking the model sends the locally redacted issue and diagnostics to this app’s configured endpoint. A valid quote does not prove an explanation is correct.</p>:<p className="intake-note">This public deployment has no model endpoint configured. The evidence workflow is live; model examples, when available, are labeled recorded. <a href={sourceFile("docs/troubleshooting.md")}>How this workflow works ↗</a></p>}
      {!corpus&&!loadError&&<p role="status">Loading pinned runbooks…</p>}{loadError&&<div role="alert"><p>{loadError}</p><button onClick={()=>void load()}>Retry loading</button></div>}
    </section>
    <section className="incident-results results" ref={results} tabIndex={-1} aria-label="Incident analysis" aria-live="polite">
      {error&&<p role="alert" className="error">{error}</p>}
      {!result&&!error&&<div className="before-search"><span className="eyebrow">02 / EVIDENCE CANVAS</span><h2>A useful investigation<br/>leaves a visible trail.</h2><p>Choose an example on the left, or bring your own sanitized diagnostic text. The supporting passages will appear here.</p><div className="preview-observation"><span>EXAMPLE OBSERVATION</span><code><i/> ImagePullBackOff</code><div className="evidence-preview-path"><p><b>01</b> A status is observed</p><p><b>02</b> The image runbook is retrieved</p><p><b>03</b> You inspect what it supports</p></div></div><div className="empty-canvas-meta"><span>06 pinned documents</span><span>180 source passages</span><a href="/runbooks">Browse the library ↗</a></div></div>}
      {result&&<><div className="result-heading"><h2>{result.mode==="generated"?"Model draft with evidence":result.mode==="abstained"?"No supporting evidence":"Incident evidence"}</h2><button onClick={exportBrief}>Export brief ↓</button></div>
        <p className="intake-note">{result.note}</p>
        {result.redactions>0&&<p className="redaction" role="status">{result.redactions} recognized credential pattern(s) redacted. Review the input for anything the detector missed.</p>}
        {result.diagnostics_truncated&&<p className="redaction">Only the first 2,000 diagnostic characters are included in the model context and exported analysis. Signals can still be recognized across the full allowed input.</p>}
        <div className="signal-row"><span>RECOGNIZED STATUS TEXT</span>{result.signals.length?result.signals.map(s=><b key={s}>{s}</b>):<p>Add a status such as ImagePullBackOff or a warning event to make the search more specific.</p>}<p className="signal-meaning">Text matches can be historical, hypothetical or negated. They do not establish a current condition.</p></div>
        {result.evidence_policy&&<div className="evidence-audit">
          <div className="investigation-metrics"><div><strong>{result.sources.length}<small> / 3</small></strong><span>passages selected</span></div><div><strong>{result.evidence_policy.usage.characters.toLocaleString()}<small> / 6,000</small></strong><span>evidence characters</span></div><div><strong>{result.evidence_policy.usage.retrieval_attempts}<small> / 4</small></strong><span>retrieval attempts</span></div></div>
          {!!result.evidence_policy.missing_signals.length&&<div className="evidence-gap" role="status"><strong>Documentation gap</strong><p>No selected passage from the expected documentation family for: {result.evidence_policy.missing_signals.join(", ")}. The source snapshot or passage budget may be insufficient. Do not treat the result as a complete investigation.</p></div>}
          <details className="decision-trace"><summary>Why these passages? <span>Inspect retrieval decisions ↗</span></summary><p>{result.evidence_policy.scope}</p><ol>{result.evidence_policy.attempts.map((a,i)=><li key={i}><b>{a.kind==="initial"?"Initial search":`Retry within ${a.family}`}</b><code>{a.query}</code><span>{a.returned.length?a.returned.join(" · "):"No matching passages"}</span></li>)}</ol>{!!result.evidence_policy.omitted.length&&<p>{result.evidence_policy.omitted.length} passage(s) shortened to stay within the character budget. Open the original source for full context.</p>}</details>
        </div>}
        {result.answer&&<article className="model-draft"><span className="eyebrow">{result.answer.status.replaceAll("_"," ")} · {result.model}</span><h3>{result.answer.summary}</h3>{result.answer.claims.map((c,i)=><div key={i} className="claim"><p>{c.text}</p><blockquote>{c.quote}</blockquote><a href={result.sources.find(s=>s.id===c.source_id)?.source} target="_blank" rel="noreferrer">Source {c.source_id} ↗</a></div>)}
          {!!result.answer.questions.length&&<><h3>Evidence still needed</h3><ul>{result.answer.questions.map(q=><li key={q}>{q}</li>)}</ul></>}
          {!!result.answer.commands.length&&<><h3>Read-only suggestions · not executed</h3>{result.answer.commands.map(c=><pre tabIndex={0} key={c.command}>{c.command}</pre>)}</>}
        </article>}
        {!result.sources.length&&<div className="empty"><p>This six-document snapshot does not support a result. Try a concrete Kubernetes status or use the broader official documentation.</p><a href="https://kubernetes.io/docs/">Open Kubernetes docs ↗</a></div>}
        {result.sources.map((s,i)=><details className="incident-source" key={s.id} open={i===0}><summary>{i+1}. {s.section} <small>{s.id}</small></summary><pre tabIndex={0} aria-label={`Incident source ${i+1}`}>{s.text}</pre><a href={s.source} target="_blank" rel="noreferrer">Pinned official source ↗</a><a href={s.canonical} target="_blank" rel="noreferrer">Current docs ↗</a></details>)}
        <div className="review-notes"><label htmlFor="review-notes">Your investigation notes <span>Optional · included only in the exported brief</span></label><textarea id="review-notes" rows={3} maxLength={4000} value={notes} onChange={e=>{setNotes(e.target.value);setCopied("");}} placeholder="What does the evidence support? What is still missing?"/><p>Notes remain unreviewed. Editing the incident clears these notes and the previous result.</p></div>
        <p className="intake-note">Open the source for full context. Signals identify observed text patterns; confirming a cause requires your diagnostic evidence.</p><p role="status">{copied}</p>
      </>}
    </section></div>
    <section className="evidence"><p className="eyebrow">02 / A VISIBLE DECISION PATH</p><div className="evidence-grid"><div><h3>Input → signals → evidence</h3><p>Known status strings expand the retrieval query. The same pinned passages remain inspectable, whether or not a model is configured.</p></div><div><h3>Model outputs must pass checks</h3><p>The optional answer path requires valid JSON, supplied source IDs, matching quotes, and supported read-only command forms. Failed or truncated responses are rejected.</p></div><div><h3>Measure before claiming a win</h3><p>A frozen protocol defines a future comparison of excerpt-only retrieval and base/SFT served artifacts. Model inference is deferred. Completion, evidence validity, phrase coverage and abstention are separate measurements.</p><a href="/study">Inspect the study →</a></div></div></section>
    </main><footer className="site-footer"><span>OpsVerse · built by Dilip Nallamasa</span><a href="/runbooks">Search all runbook passages</a><a href="/engineering">Architecture & engineering decisions →</a></footer>
  </div>;
}
