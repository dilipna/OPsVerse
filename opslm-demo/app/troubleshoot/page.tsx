"use client";

import {sourceFile} from "../../lib/source-links";


import {useEffect,useRef,useState} from "react";
import {troubleshoot,redact,type Result} from "../../lib/troubleshoot.mjs";
import type {Corpus} from "../../lib/runbooks.mjs";
import {createBrief,restoreBrief,markdownBrief,savedGuideIds,MAX_BRIEF_BYTES,SAVED_GUIDES_KEY} from "../../lib/portable-brief.mjs";

const EXAMPLES=[
  {title:"Image won't pull",issue:"Why has this container not started, and what should I inspect?",diagnostics:"Name: web\nNamespace: shop\nState: Waiting\nReason: ImagePullBackOff\nFailed to pull image registry.example/web:missing"},
  {title:"Readiness failed",issue:"The process is running, but the Pod receives no traffic. What does this signal mean?",diagnostics:"Name: api\nNamespace: shop\nWarning Unhealthy Readiness probe failed: HTTP probe failed with statuscode: 503"},
  {title:"Memory termination",issue:"How does Kubernetes enforce container memory limits?",diagnostics:"Name: worker\nNamespace: batch\nLast State: Terminated\nReason: OOMKilled\nExit Code: 137\nNo memory-usage profile provided"},
];

// A reading preview, not a generated answer. Skip code, frontmatter and template
// fragments; retain the source paragraph's words, removing inline Markdown only.
function preview(text:string){
  const paragraphs=text.replace(/^---\n[\s\S]*?\n---\n/,"").replace(/```[\s\S]*?```/g,"").split(/\n\s*\n/);
  const prose=paragraphs.filter(p=>/^[A-Z]/.test(p)&&p.length>=60&&p.length<=900&&!/[{}<>]|^\s*[-*#|]/m.test(p));
  const selected=prose.find(p=>/\bmeans\b|\bindicates\b/.test(p))||prose[0];
  return selected?.replace(/\[([^\]]+)\]\([^)]*\)/g,"$1").replace(/`([^`]+)`/g,"$1").replace(/\*\*([^*]+)\*\*/g,"$1").replace(/\s+/g," ").trim();
}

export default function TroubleshootPage(){
  const [corpus,setCorpus]=useState<Corpus|null>(null),[loadError,setLoadError]=useState("");
  const [issue,setIssue]=useState(""),[diagnostics,setDiagnostics]=useState("");
  const [result,setResult]=useState<Result|null>(null),[error,setError]=useState("");
  const [busy,setBusy]=useState(false),[configured,setConfigured]=useState(false),[copied,setCopied]=useState("");
  const [notes,setNotes]=useState("");
  const [saved,setSaved]=useState<string[]>([]),[savedReady,setSavedReady]=useState(false),[storeMessage,setStoreMessage]=useState("");
  const results=useRef<HTMLElement>(null);
  const prompt=useRef<HTMLTextAreaElement>(null),logs=useRef<HTMLDetailsElement>(null);
  const importFile=useRef<HTMLInputElement>(null),readingList=useRef<HTMLDialogElement>(null);
  function reset(){if(busy)return;edit("","");if(logs.current)logs.current.open=false;requestAnimationFrame(()=>prompt.current?.focus());}
  async function load(){
    setLoadError("");
    try{const r=await fetch("/runbooks.json");if(!r.ok)throw new Error();const c=await r.json();if(c.schema!==1||!Array.isArray(c.chunks))throw new Error();setCorpus(c);}
    catch{setLoadError("The documentation snapshot could not load. Check your connection and retry.");}
  }
  useEffect(()=>{void load();fetch("/api/troubleshoot").then(r=>r.json()).then(d=>setConfigured(d.generation_configured===true)).catch(()=>setConfigured(false));},[]);
  useEffect(()=>{if(!corpus)return;try{setSaved(savedGuideIds(localStorage.getItem(SAVED_GUIDES_KEY),corpus));}catch{setStoreMessage("Device storage is unavailable. Saved guides will stay in this tab only.");}finally{setSavedReady(true);}},[corpus]);
  function updateSaved(next:string[]){
    if(!corpus)return;
    setSaved(next);
    try{localStorage.setItem(SAVED_GUIDES_KEY,JSON.stringify({schema:1,revision:corpus.manifest.revision,ids:next}));setStoreMessage("");}
    catch{setStoreMessage("Device storage is unavailable. Saved guides will stay in this tab only.");}
  }
  function toggleSaved(id:string){
    if(!corpus?.chunks.some(c=>c.id===id))return;
    if(saved.includes(id))updateSaved(saved.filter(x=>x!==id));
    else if(saved.length<30)updateSaved([...saved,id]);
    else setStoreMessage("Your reading list holds up to 30 passages. Remove one to save another.");
  }
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
    finally{setBusy(false);requestAnimationFrame(()=>{results.current?.focus();results.current?.scrollIntoView({block:"start",behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});});}
  }
  function exportBrief(format:"json"|"markdown"="json"){
    if(!result||!corpus)return;
    const brief=createBrief(result,notes,corpus.manifest.revision);
    const url=URL.createObjectURL(new Blob([format==="json"?JSON.stringify(brief,null,2):markdownBrief(brief)],{type:format==="json"?"application/json":"text/markdown;charset=utf-8"}));
    const link=document.createElement("a");link.href=url;link.download=`opsverse-incident-brief.${format==="json"?"json":"md"}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    setCopied(format==="json"?"JSON notes downloaded. Use Reopen notes to continue later.":"Markdown notes downloaded with your question, redacted notes and source passages.");
  }
  async function reopen(file:File){
    if(!corpus||busy)return;
    setBusy(true);setError("");setCopied("");
    try{
      if(file.size>MAX_BRIEF_BYTES)throw Error("This file is too large. Choose an OpsVerse JSON download under 256 KB.");
      const restored=restoreBrief(await file.text(),corpus);
      const current=await troubleshoot(corpus,restored);
      setIssue(restored.issue);setDiagnostics(restored.diagnostics);setNotes(restored.notes);setResult(current);
      setCopied("Question and notes reopened. Sources were searched again; imported answers were not reused. The download may contain only the first 2,000 log characters.");
    }catch(e){setError(e instanceof Error?e.message:"The file could not be reopened.");}
    finally{setBusy(false);requestAnimationFrame(()=>{results.current?.focus();results.current?.scrollIntoView({block:"start",behavior:"auto"});});}
  }
  return <div className={`chat-app${result?" has-response":""}`}>
    <a className="skip" href="#incident-issue">Skip to question</a>
    <dialog className="saved-dialog" ref={readingList} aria-labelledby="saved-title" onClick={e=>{if(e.target===e.currentTarget)readingList.current?.close();}}><div className="saved-dialog-heading"><h2 id="saved-title">Your reading list</h2><button onClick={()=>readingList.current?.close()}>Close</button></div><p>Saved on this device: public documentation passages only. Questions and logs are not stored here.</p>{storeMessage&&<p role="status">{storeMessage}</p>}{!saved.length?<p className="saved-empty">Find a guide, then choose Save for later.</p>:<><ol>{saved.map(id=>{const s=corpus?.chunks.find(c=>c.id===id);return s?<li key={id}><a href={s.canonical} target="_blank" rel="noreferrer">{s.section} ↗</a>{preview(s.text)&&<p>{preview(s.text)}</p>}<div><a href={s.source} target="_blank" rel="noreferrer">Pinned source ↗</a><button onClick={()=>toggleSaved(id)} aria-label={`Remove ${s.section}`}>Remove</button></div></li>:null;})}</ol><button onClick={()=>updateSaved([])}>Clear saved guides</button></>}</dialog>
    <aside className="chat-sidebar" aria-label="Workspace navigation">
      <a className="chat-brand" href="/" aria-label="OpsVerse home"><span aria-hidden="true">↗</span>OpsVerse</a>
      <button className="new-question" onClick={reset} disabled={busy}><span aria-hidden="true">＋</span> New question</button>
      <nav aria-label="Main navigation"><a href="/runbooks"><span aria-hidden="true">▤</span> Browse guides</a></nav>
      <div className="sidebar-bottom"><p>A little clarity<br/>for your cluster.</p><nav aria-label="About OpsVerse"><a href="/engineering">Behind OpsVerse ↗</a><a href="/study">Research & evaluation</a></nav><small>Built by Dilip Nallamasa</small></div>
    </aside>
    <main className="chat-main">
      <header className="chat-topbar"><span>Kubernetes help</span><div><button className="saved-guides-button" onClick={()=>readingList.current?.showModal()}>Saved guides <span>{saved.length}</span></button><a href="/runbooks">Explore guides ↗</a></div></header>
      <div className="chat-stage">
        <section className="chat-welcome"><div className="welcome-mark" aria-hidden="true">↗</div><h1>{result?"Let’s work through it.":"What can I help you understand?"}</h1><p className="intro-copy">Describe a Kubernetes problem. Find a clearer way forward.</p></section>
        <section className="incident-results chat-response" hidden={!result&&!error} ref={results} tabIndex={-1} aria-label="Response" aria-live="polite" aria-busy={busy}>
          {error&&<p role="alert" className="chat-error">{error}</p>}
          {result&&<>
            <div className="question-bubble"><span className="sr-only">Your question</span>{result.issue}</div>
            <div className="answer-brand"><span aria-hidden="true">↗</span> OpsVerse <small>{result.mode==="generated"?"AI draft":"Documentation search"}</small></div>
            <h2>{result.mode==="generated"?"A draft to review":result.sources.length?"What I found":"No matches yet"}</h2>
            {result.mode!=="generated"&&<p>{result.sources.length?"These guides from Kubernetes documentation may help. They explain the topic; they don’t confirm what caused your issue.":"I couldn’t find supporting information in this small documentation library. Try a Kubernetes status or error message, or check the full documentation."}</p>}
            {result.redactions>0&&<p className="chat-notice" role="status">Some text that looked like credentials was removed. Check that no other sensitive information remains.</p>}
            {result.diagnostics_truncated&&<p className="chat-notice">Saved notes include only the first 2,000 log characters. Matching status text can still use your full input.</p>}
            {!!result.evidence_policy?.missing_signals.length&&<div className="chat-notice" role="status"><strong>Some details are missing</strong><p>The selected guides don’t cover every status in your question: {result.evidence_policy.missing_signals.join(", ")}. This is a starting point, not a complete investigation.</p></div>}
            {result.answer&&<article className="model-draft"><p className="chat-notice">AI-generated draft. Matching source quotes do not guarantee a correct explanation.</p><h3>{result.answer.summary}</h3>{result.answer.claims.map((c,i)=><div key={i}><p>{c.text}</p><blockquote>{c.quote}</blockquote><a href={result.sources.find(s=>s.id===c.source_id)?.source} target="_blank" rel="noreferrer">View supporting source ↗</a></div>)}
              {!!result.answer.questions.length&&<><h3>More information would help</h3><ul>{result.answer.questions.map(q=><li key={q}>{q}</li>)}</ul></>}
              {!!result.answer.commands.length&&<><h3>Suggested checks</h3><p>These commands have not been run.</p>{result.answer.commands.map(c=><pre tabIndex={0} key={c.command}>{c.command}</pre>)}</>}
            </article>}
            {result.mode!=="generated"&&result.sources.map((s,i)=><article className="guide-preview" key={s.id} data-source-id={s.id}><div className="guide-number" aria-hidden="true">{i+1}</div><div><h3><a href={s.canonical} target="_blank" rel="noreferrer">{s.section.replace(/\s*\{#[^}]+\}/g,"")} ↗</a></h3>{preview(s.text)&&<p>{preview(s.text)}</p>}<small>Excerpt from Kubernetes documentation · not an AI-generated answer</small><button className="save-guide" aria-label={`${saved.includes(s.id)?"Unsave":"Save"} guide ${i+1}`} disabled={!savedReady} onClick={()=>toggleSaved(s.id)}>{saved.includes(s.id)?"Saved ✓":"Save for later +"}</button></div></article>)}
            {!result.sources.length&&<a href="https://kubernetes.io/docs/" target="_blank" rel="noreferrer">Search the full Kubernetes docs ↗</a>}
            {!!result.sources.length&&<details className="chat-sources"><summary>View {result.sources.length} source passages</summary>{result.sources.map((s,i)=><details className="incident-source" key={s.id}><summary>{i+1}. {s.section} <small>{s.id}</small></summary><pre tabIndex={0} aria-label={`Incident source ${i+1}`}>{s.text}</pre><a href={s.source} target="_blank" rel="noreferrer">Pinned official source ↗</a> · <a href={s.canonical} target="_blank" rel="noreferrer">Current docs ↗</a></details>)}</details>}
            {result.evidence_policy&&<details className="chat-method"><summary>How this search worked</summary><p>{result.note}</p><p>Matched status text: {result.signals.join(", ")||"None"}. Text can refer to past or hypothetical events; a match is not a confirmed condition.</p><p>{result.sources.length} passages · {result.evidence_policy.usage.characters.toLocaleString()} / 6,000 characters · {result.evidence_policy.usage.retrieval_attempts} / 4 search attempts</p><details className="decision-trace"><summary>Search details</summary><p>{result.evidence_policy.scope}</p><ol>{result.evidence_policy.attempts.map((a,i)=><li key={i}><b>{a.kind==="initial"?"Initial search":`Retry within ${a.family}`}</b><code>{a.query}</code><span>{a.returned.length?a.returned.join(" · "):"No matching passages"}</span></li>)}</ol>{!!result.evidence_policy.omitted.length&&<p>Some passages were shortened. Open the original for full context.</p>}</details></details>}
            <details className="chat-notes"><summary>Add your own notes</summary><label htmlFor="review-notes">Your notes</label><textarea id="review-notes" rows={3} maxLength={4000} value={notes} onChange={e=>{setNotes(e.target.value);setCopied("");}} placeholder="What did you learn? What would you check next?"/><p>Included in your download as unreviewed notes. Starting a new question clears them.</p></details>
            <div className="response-actions"><button onClick={()=>exportBrief()}>Download notes ↓</button><button onClick={()=>exportBrief("markdown")}>Download Markdown ↓</button><button onClick={reset} disabled={busy}>Ask another question</button></div><p className="download-status" role="status">{copied}</p>{storeMessage&&<p className="download-status" role="status">{storeMessage}</p>}
          </>}
        </section>
        <section className="chat-composer" aria-label="Ask a question">
          <input ref={importFile} type="file" accept=".json,application/json" hidden aria-label="Reopen notes file" disabled={!corpus||busy} onChange={e=>{const file=e.currentTarget.files?.[0];e.currentTarget.value="";if(file)void reopen(file);}}/>
          <form onSubmit={e=>{e.preventDefault();void analyze();}}>
            <label className="sr-only" htmlFor="incident-issue">Your Kubernetes question</label><textarea ref={prompt} id="incident-issue" disabled={busy} value={issue} maxLength={501} rows={3} onChange={e=>edit(e.target.value,diagnostics)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.form?.requestSubmit();}}} placeholder="Ask about a Kubernetes problem…" aria-describedby="question-help"/>
            <details className="chat-logs" ref={logs}><summary>Add logs or error details {diagnostics&&<span>Added</span>}</summary><label htmlFor="diagnostics">Logs or error details (optional)</label><textarea id="diagnostics" disabled={busy} value={diagnostics} maxLength={12001} rows={5} onChange={e=>edit(issue,e.target.value)} placeholder="Paste the relevant error or status. Remove passwords, tokens and other sensitive information first." aria-describedby="diagnostics-help"/><p id="diagnostics-help">Never include secrets. Automatic redaction can miss them.</p></details>
            <div className="composer-bottom"><button className="reopen-button" type="button" disabled={!corpus||busy} onClick={()=>importFile.current?.click()}>Reopen notes ↗</button><div>{configured&&<button className="model-button" disabled={!corpus||busy} type="button" onClick={()=>void analyze(true)}>Ask AI model</button>}<button className="send-question" aria-label="Send question" disabled={!corpus||busy} type="submit"><span>{busy?"Searching…":"Send"}</span><span aria-hidden="true">↑</span></button></div></div>
          </form>
          <p id="question-help" className="composer-help">{configured?"Search stays in your browser. “Ask AI model” sends redacted text to the configured endpoint.":"Searches a limited Kubernetes library. No AI model is connected."}</p>
          {!corpus&&!loadError&&<p role="status" className="composer-help">Loading documentation…</p>}{loadError&&<div role="alert" className="chat-error"><p>{loadError}</p><button onClick={()=>void load()}>Retry loading</button></div>}
        </section>
        {!result&&<div className="chat-starters"><span>Not sure where to start? Try an example.</span><div>{EXAMPLES.map(e=><button key={e.title} onClick={()=>{edit(e.issue,e.diagnostics);prompt.current?.focus();}} disabled={busy}>{e.title}<span aria-hidden="true">↗</span></button>)}</div></div>}
      </div>
      <footer className="chat-footer"><span>Nothing connects to your cluster. Questions aren’t saved after a reload.</span><details><summary>About this assistant</summary><p>OpsVerse finds passages from six pinned Kubernetes documents. It doesn’t run commands or confirm a root cause. Preview paragraphs retain the source’s words with inline formatting removed. Each question is a separate search; earlier questions are not used as context. <a href={sourceFile("docs/troubleshooting.md")}>Read how it works ↗</a></p><nav aria-label="Product details"><a href="/engineering">Behind OpsVerse</a><a href="/study">Research & evaluation</a></nav></details></footer>
    </main>
  </div>;
}
