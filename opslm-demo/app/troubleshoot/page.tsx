"use client";

import {sourceFile} from "../../lib/source-links";


import {useEffect,useRef,useState} from "react";
import {redact,type Result} from "../../lib/troubleshoot.mjs";
import type {Corpus} from "../../lib/runbooks.mjs";
import {createBrief,restoreBrief,markdownBrief,savedGuideIds,MAX_BRIEF_BYTES,SAVED_GUIDES_KEY} from "../../lib/portable-brief.mjs";
import {previewSource,type RoutingMetadata} from "../../lib/rype-routing.mjs";
import {workspaceRoute} from "../../lib/workspace-routing.mjs";
import {readLibrary} from "../../lib/private-library.mjs";
import type {PrivateDocument} from "../../lib/knowledge.mjs";
import {MAX_TURNS,answerText,type Turn} from "../../lib/discussion-downloads.mjs";
import PrivateLibrary from "./private-library";
import DownloadDiscussion from "./download-discussion";

const EXAMPLES=[
  {title:"What is a Pod?",issue:"What is a pod in Kubernetes?",diagnostics:""},
  {title:"Image won't pull",issue:"Why has this container not started, and what should I inspect?",diagnostics:"Name: web\nNamespace: shop\nState: Waiting\nReason: ImagePullBackOff\nFailed to pull image registry.example/web:missing"},
  {title:"Readiness failed",issue:"The process is running, but the Pod receives no traffic. What does this signal mean?",diagnostics:"Name: api\nNamespace: shop\nWarning Unhealthy Readiness probe failed: HTTP probe failed with statuscode: 503"},
  {title:"Memory termination",issue:"How does Kubernetes enforce container memory limits?",diagnostics:"Name: worker\nNamespace: batch\nLast State: Terminated\nReason: OOMKilled\nExit Code: 137\nNo memory-usage profile provided"},
];

// A reading preview, not a generated answer. Skip code, frontmatter and template
// fragments; retain the source paragraph's words, removing inline Markdown only.
const preview=previewSource;
const money=(value:number|null)=>value===null?"Unavailable":`$${value===0?"0":value.toFixed(8).replace(/0+$/,"")}`;

export default function TroubleshootPage(){
  const [corpus,setCorpus]=useState<Corpus|null>(null),[loadError,setLoadError]=useState("");
  const [issue,setIssue]=useState(""),[diagnostics,setDiagnostics]=useState("");
  const [result,setResult]=useState<Result|null>(null),[error,setError]=useState("");
  const [busy,setBusy]=useState(false),[metadata,setMetadata]=useState<RoutingMetadata|null>(null),[copied,setCopied]=useState("");
  const [notes,setNotes]=useState("");
  const [documents,setDocuments]=useState<PrivateDocument[]>([]),[libraryReady,setLibraryReady]=useState(false),[libraryError,setLibraryError]=useState("");
  const [turns,setTurns]=useState<Turn[]>([]),activeTurn=useRef("");
  const [saved,setSaved]=useState<string[]>([]),[savedReady,setSavedReady]=useState(false),[storeMessage,setStoreMessage]=useState("");
  const results=useRef<HTMLElement>(null);
  const prompt=useRef<HTMLTextAreaElement>(null),logs=useRef<HTMLDetailsElement>(null);
  const importFile=useRef<HTMLInputElement>(null),readingList=useRef<HTMLDialogElement>(null);
  const metadataLoad=useRef<Promise<RoutingMetadata|null>|null>(null);
  function reset(){if(busy)return;edit("","");if(logs.current)logs.current.open=false;requestAnimationFrame(()=>prompt.current?.focus());}
  async function load(){
    setLoadError("");
    try{const r=await fetch("/runbooks.json");if(!r.ok)throw new Error();const c=await r.json();if(c.schema!==1||!Array.isArray(c.chunks))throw new Error();setCorpus(c);}
    catch{setLoadError("The documentation snapshot could not load. Check your connection and retry.");}
  }
  useEffect(()=>{void load();metadataLoad.current=fetch("/api/route").then(r=>{if(!r.ok)throw Error();return r.json();}).then(d=>{setMetadata(d);return d;}).catch(()=>{setMetadata(null);return null;});},[]);
  useEffect(()=>{let mounted=true;const refresh=()=>readLibrary().then(d=>{if(mounted){setDocuments(d);setLibraryReady(true);setLibraryError("");}}).catch(e=>{if(mounted)setLibraryError(e.message);});void refresh();const channel=typeof BroadcastChannel!=="undefined"?new BroadcastChannel("rype-library-changed"):null;if(channel)channel.onmessage=()=>void refresh();return()=>{mounted=false;channel?.close();};},[]);
  function libraryChanged(next:PrivateDocument[]){setDocuments(next);setLibraryReady(true);setLibraryError("");const channel=typeof BroadcastChannel!=="undefined"?new BroadcastChannel("rype-library-changed"):null;channel?.postMessage("changed");channel?.close();}
  function finish(value:Result){setResult(value);const id=crypto.randomUUID();activeTurn.current=id;setNotes("");setTurns(current=>[...current,{id,result:value,notes:""}].slice(-MAX_TURNS));}
  function updateNotes(value:string){setNotes(value);setCopied("");setTurns(current=>current.map(t=>t.id===activeTurn.current?{...t,notes:value}:t));}
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
  async function analyze(){
    if(!corpus||busy)return;
    setBusy(true);setError("");setResult(null);setCopied("");
    try{
      const base=await workspaceRoute(corpus,{issue,diagnostics},metadata,{documents});
      let routingMeta=metadata,local=base;
      if(local.routing?.kind==="model"&&!routingMeta&&metadataLoad.current){routingMeta=await metadataLoad.current;local=await workspaceRoute(corpus,{issue,diagnostics},routingMeta,{documents});}
      setResult(local);
      if(local.routing?.kind==="model"&&routingMeta?.cloud_configured){
        // Remove recognized credentials locally before any diagnostic text leaves this page.
        const payload={issue:redact(issue).text,diagnostics:redact(diagnostics).text};
        const response=await fetch("/api/route",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload),signal:AbortSignal.timeout(58000)});
        const data=await response.json();if(!response.ok){if(data.result)setResult(data.result);throw new Error(data.error||"The free model request failed.");}
        finish({...data,redactions:local.redactions});
      }else finish(local);
    }catch(e){setError(e instanceof Error?e.message:"The request failed. Please retry.");}
    finally{setBusy(false);requestAnimationFrame(()=>{results.current?.focus();results.current?.scrollIntoView({block:"start",behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});});}
  }
  function exportBrief(format:"json"|"markdown"="json"){
    if(!result||!corpus)return;
    const brief=createBrief(result,notes,corpus.manifest.revision);
    const url=URL.createObjectURL(new Blob([format==="json"?JSON.stringify(brief,null,2):markdownBrief(brief)],{type:format==="json"?"application/json":"text/markdown;charset=utf-8"}));
    const link=document.createElement("a");link.href=url;link.download=`rype-investigation.${format==="json"?"json":"md"}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    setCopied(format==="json"?"JSON notes downloaded. Use Reopen notes to continue later.":"Markdown notes downloaded with your question, redacted notes and source passages.");
  }
  async function reopen(file:File){
    if(!corpus||busy)return;
    setBusy(true);setError("");setCopied("");
    try{
      if(file.size>MAX_BRIEF_BYTES)throw Error("This file is too large. Choose an RYPE JSON download under 256 KB.");
      const restored=restoreBrief(await file.text(),corpus);
      const current=await workspaceRoute(corpus,restored,metadata,{documents,restored:true});
      setIssue(restored.issue);setDiagnostics(restored.diagnostics);finish(current);setNotes(restored.notes);setTurns(t=>t.map(turn=>turn.id===activeTurn.current?{...turn,notes:restored.notes}:turn));
      setCopied("Question and notes reopened. Sources were searched again; imported answers were not reused. The download may contain only the first 2,000 log characters.");
    }catch(e){setError(e instanceof Error?e.message:"The file could not be reopened.");}
    finally{setBusy(false);requestAnimationFrame(()=>{results.current?.focus();results.current?.scrollIntoView({block:"start",behavior:"auto"});});}
  }
  return <div className={`chat-app${result?" has-response":""}`}>
    <a className="skip" href="#incident-issue">Skip to question</a>
    <dialog className="saved-dialog" ref={readingList} aria-labelledby="saved-title" onClick={e=>{if(e.target===e.currentTarget)readingList.current?.close();}}><div className="saved-dialog-heading"><h2 id="saved-title">Your reading list</h2><button onClick={()=>readingList.current?.close()}>Close</button></div><p>Saved on this device: public documentation passages only. Questions and logs are not stored here.</p>{storeMessage&&<p role="status">{storeMessage}</p>}{!saved.length?<p className="saved-empty">Find a guide, then choose Save for later.</p>:<><ol>{saved.map(id=>{const s=corpus?.chunks.find(c=>c.id===id);return s?<li key={id}><a href={s.canonical} target="_blank" rel="noreferrer">{s.section} ↗</a>{preview(s.text)&&<p>{preview(s.text)}</p>}<div><a href={s.source} target="_blank" rel="noreferrer">Pinned source ↗</a><button onClick={()=>toggleSaved(id)} aria-label={`Remove ${s.section}`}>Remove</button></div></li>:null;})}</ol><button onClick={()=>updateSaved([])}>Clear saved guides</button></>}</dialog>
    <aside className="chat-sidebar" aria-label="Workspace navigation">
      <a className="chat-brand" href="/" aria-label="RYPE home"><span aria-hidden="true">↗</span>RYPE</a>
      <button className="new-question" onClick={reset} disabled={busy}><span aria-hidden="true">＋</span> New question</button>
      {!!turns.length&&<details className="discussion-history"><summary>This discussion · {turns.length}</summary><ol>{turns.map(t=><li key={t.id}><button disabled={busy} onClick={()=>{activeTurn.current=t.id;setIssue(t.result.issue);setDiagnostics(t.result.diagnostics);setResult(t.result);setNotes(t.notes);setError("");}}>{t.result.issue}</button></li>)}</ol><button disabled={busy} onClick={()=>{setTurns([]);activeTurn.current="";reset();}}>Clear discussion</button><p>Last 12 answers in this tab only. Earlier questions are not sent as model context.</p></details>}
      <nav aria-label="Main navigation"><a href="/runbooks"><span aria-hidden="true">▤</span> Browse guides</a></nav>
      <div className="sidebar-bottom"><p>Retrieve first.<br/>Route when needed.</p><nav aria-label="About RYPE"><a href="/engineering">Behind RYPE ↗</a><a href="/study">Research & evaluation</a></nav><small>Built by Dilip Nallamasa</small></div>
    </aside>
    <main className="chat-main">
      <header className="chat-topbar"><span>Route-first assistant</span><div><PrivateLibrary documents={documents} onChange={libraryChanged} ready={libraryReady}/><button className="saved-guides-button" onClick={()=>readingList.current?.showModal()}>Saved guides <span>{saved.length}</span></button><a href="/runbooks">Explore guides ↗</a></div></header>
      <div className="chat-stage">
        <section className="chat-welcome"><div className="welcome-mark" aria-hidden="true">↗</div><h1>{result?"Let’s work through it.":"What can I help you understand?"}</h1><p className="intro-copy">Route Your Prompt Efficiently. Covered docs first. A free model only when needed.</p>{!result&&<><div className="routing-intro"><span>Covered docs → No inference</span><span>Other questions → Free model</span><span>Every response → Route & cost</span></div><details className="routing-explainer"><summary>How RYPE decides</summary><p>RYPE checks covered Kubernetes topics against its source library. A supported match returns retrieved guidance without model inference. Other questions are classified as everyday, coding or reasoning tasks and sent to an eligible free OpenRouter model when configured. This is a transparent heuristic, not a claim about what a model was trained on or proof of answer quality.</p><p>{metadata?.cloud_configured?"A server-side OpenRouter key is configured. Free model availability can vary.":"OpenRouter is not connected yet. Covered library questions still work."} Paid models and paid fallbacks are disabled.</p><p>Cost comparisons use a named baseline and are estimates; the baseline is never called just to calculate savings.</p></details></>}</section>
        <section className="incident-results chat-response" hidden={!result&&!error} ref={results} tabIndex={-1} aria-label="Response" aria-live="polite" aria-busy={busy}>
          {error&&<p role="alert" className="chat-error">{error}</p>}
          {result&&<>
            <div className="question-bubble"><span className="sr-only">Your question</span>{result.issue}</div>
            <div className="answer-brand"><span aria-hidden="true">↗</span> RYPE <small>{result.mode==="routed"?"OpenRouter answer":result.mode==="generated"?"AI draft":"Documentation search"}</small></div>
            <h2>{result.mode==="routed"?"Your answer":result.mode==="generated"?"A draft to review":result.sources.length?"What I found":"No matches yet"}</h2>
            {result.mode!=="generated"&&result.mode!=="routed"&&<p>{result.sources.length?"These sources may help. Check their labels: private documents are unverified and documentation does not confirm a root cause.":"I couldn’t find supporting information in this small documentation library. Try a Kubernetes status or error message, or check the full documentation."}</p>}
            {result.routing&&<aside className="routing-receipt" aria-label="Routing and cost"><div className="receipt-heading"><strong>{result.routing.kind==="retrieval"?"Library route · no inference":`${result.routing.category} route · ${result.routing.status.replaceAll("_"," ")}`}</strong><span>{result.routing.model_calls} model {result.routing.model_calls===1?"call":"calls"}</span></div><dl><div><dt>Model used</dt><dd>{result.routing.model_used||"None"}</dd></div><div><dt>{result.routing.model_calls?"Reported charge":"Inference charge"}</dt><dd>{money(result.routing.actual_cost_usd)}</dd></div></dl>{result.routing.model_selected&&!result.routing.model_used&&<p>Selected model: {result.routing.model_selected}. It has not returned an accepted answer.</p>}{result.routing.estimated_difference_usd!==null&&<p className="cost-comparison">{result.routing.kind==="retrieval"?"Estimated baseline charge avoided":result.routing.estimated_difference_usd>=0?"Estimated charge reduction":"Estimated additional charge"}: {money(Math.abs(result.routing.estimated_difference_usd))}{result.routing.kind!=="retrieval"&&result.routing.estimated_reduction_percent!==null&&` (${Math.abs(result.routing.estimated_reduction_percent).toFixed(1)}%)`} vs {result.routing.baseline_model}. Baseline not run.</p>}<details><summary>Why this route and cost?</summary><p>{result.routing.reason}</p><p>{result.routing.note}</p><p>{result.routing.token_basis}</p><p>{result.routing.comparison_scope}</p>{result.routing.baseline_model&&<p>Baseline: {result.routing.baseline_model} · estimated charge {money(result.routing.baseline_estimated_usd)} · {result.routing.input_tokens} input / {result.routing.output_tokens} output tokens · prices checked {result.routing.price_checked_at||"unavailable"}.</p>}<p>Free models only. A routing rule is not a measured guarantee of answer quality or minimum cost.</p></details></aside>}
            {result.knowledge&&<details className="knowledge-trace"><summary>See the retrieval steps</summary><p>Bounded search–check–retry controller. These are tool observations, not model chain-of-thought. Hybrid means BM25 + character-trigram similarity fused by rank; no embedding or inference call.</p><ol>{result.knowledge.steps.map((step,i)=><li key={i}><strong>{step.action.replaceAll("_"," ")}</strong><p>{step.observation}</p>{step.source_ids&&<small>{step.source_ids.join(" · ")||"No candidates"}</small>}</li>)}</ol></details>}
            {result.library_answer&&<article className="library-answer"><h3>From your library</h3><p>{result.library_answer}</p><small>Cited extracts, not a generated answer. {result.sources.some(s=>s.origin==="private")?"Includes an unverified private document.":"Editorial concept guide or documentation passage."}</small></article>}
            {result.cloud_answer&&<article className="cloud-answer"><p className="chat-notice">Generated by {result.routing?.model_used||"OpenRouter"}. Not verified against the library; review before acting.</p><div>{result.cloud_answer}</div></article>}
            {result.redactions>0&&<p className="chat-notice" role="status">Some text that looked like credentials was removed. Check that no other sensitive information remains.</p>}
            {result.diagnostics_truncated&&<p className="chat-notice">Saved notes include only the first 2,000 log characters. Matching status text can still use your full input.</p>}
            {!!result.evidence_policy?.missing_signals.length&&<div className="chat-notice" role="status"><strong>Some details are missing</strong><p>The selected guides don’t cover every status in your question: {result.evidence_policy.missing_signals.join(", ")}. This is a starting point, not a complete investigation.</p></div>}
            {result.answer&&<article className="model-draft"><p className="chat-notice">AI-generated draft. Matching source quotes do not guarantee a correct explanation.</p><h3>{result.answer.summary}</h3>{result.answer.claims.map((c,i)=><div key={i}><p>{c.text}</p><blockquote>{c.quote}</blockquote><a href={result.sources.find(s=>s.id===c.source_id)?.source} target="_blank" rel="noreferrer">View supporting source ↗</a></div>)}
              {!!result.answer.questions.length&&<><h3>More information would help</h3><ul>{result.answer.questions.map(q=><li key={q}>{q}</li>)}</ul></>}
              {!!result.answer.commands.length&&<><h3>Suggested checks</h3><p>These commands have not been run.</p>{result.answer.commands.map(c=><pre tabIndex={0} key={c.command}>{c.command}</pre>)}</>}
            </article>}
            {result.mode!=="generated"&&result.sources.map((s,i)=><article className="guide-preview" key={s.id} data-source-id={s.id}><div className="guide-number" aria-hidden="true">{i+1}</div><div><h3>{s.origin==="private"?s.section:<a href={s.canonical} target="_blank" rel="noreferrer">{s.section.replace(/\s*\{#[^}]+\}/g,"")} ↗</a>}</h3>{!result.library_answer&&preview(s.text)&&<p>{preview(s.text)}</p>}<small>{s.origin==="private"?"Your private document · unverified":s.origin==="concept"?"Editorial concept guide · official reference linked":"Excerpt from Kubernetes documentation"} · not an AI-generated answer</small>{corpus?.chunks.some(c=>c.id===s.id)&&<button className="save-guide" aria-label={`${saved.includes(s.id)?"Unsave":"Save"} guide ${i+1}`} disabled={!savedReady} onClick={()=>toggleSaved(s.id)}>{saved.includes(s.id)?"Saved ✓":"Save for later +"}</button>}</div></article>)}
            {!result.sources.length&&!result.cloud_answer&&<a href="https://kubernetes.io/docs/" target="_blank" rel="noreferrer">Search the full Kubernetes docs ↗</a>}
            {!!result.sources.length&&<details className="chat-sources"><summary>View {result.sources.length} source passages</summary>{result.sources.map((s,i)=><details className="incident-source" key={s.id}><summary>{i+1}. {s.section} <small>{s.id}</small></summary><pre tabIndex={0} aria-label={`Incident source ${i+1}`}>{s.text}</pre>{s.origin==="private"?<p>Private browser document. Unverified content; never sent to a model.</p>:<><a href={s.source} target="_blank" rel="noreferrer">{s.origin==="concept"?"Official reference ↗":"Pinned official source ↗"}</a> · <a href={s.canonical} target="_blank" rel="noreferrer">Current docs ↗</a></>}</details>)}</details>}
            {result.evidence_policy&&result.mode!=="routed"&&<details className="chat-method"><summary>How this search worked</summary><p>{result.note}</p><p>Matched status text: {result.signals.join(", ")||"None"}. Text can refer to past or hypothetical events; a match is not a confirmed condition.</p><p>{result.sources.length} passages · {result.evidence_policy.usage.characters.toLocaleString()} / 6,000 characters · {result.evidence_policy.usage.retrieval_attempts} / 4 search attempts</p><details className="decision-trace"><summary>Search details</summary><p>{result.evidence_policy.scope}</p><ol>{result.evidence_policy.attempts.map((a,i)=><li key={i}><b>{a.kind==="initial"?"Initial search":`Retry within ${a.family}`}</b><code>{a.query}</code><span>{a.returned.length?a.returned.join(" · "):"No matching passages"}</span></li>)}</ol>{!!result.evidence_policy.omitted.length&&<p>Some passages were shortened. Open the original for full context.</p>}</details></details>}
            <details className="chat-notes"><summary>Add your own notes</summary><label htmlFor="review-notes">Your notes</label><textarea id="review-notes" rows={3} maxLength={4000} value={notes} onChange={e=>updateNotes(e.target.value)} placeholder="What did you learn? What would you check next?"/><p>Included as unreviewed notes. The discussion keeps the last 12 answers in this tab for download.</p></details>
            <div className="response-actions"><DownloadDiscussion turns={turns.length?turns:[{id:"current",result,notes}]} currentId={activeTurn.current||"current"}/><button onClick={()=>exportBrief()}>Download JSON ↓</button><button onClick={()=>exportBrief("markdown")}>Download Markdown ↓</button><button onClick={async()=>{try{await navigator.clipboard.writeText(answerText(result)+"\n\n"+result.sources.map(s=>`${s.section}: ${s.source||"Private document"}`).join("\n"));setCopied("Answer copied with source references.");}catch{setCopied("Clipboard unavailable. Use a download instead.");}}}>Copy answer</button><button onClick={reset} disabled={busy}>Ask another question</button></div><p className="download-status" role="status">{copied}</p>{storeMessage&&<p className="download-status" role="status">{storeMessage}</p>}
          </>}
        </section>
        <section className="chat-composer" aria-label="Ask a question">
          <input ref={importFile} type="file" accept=".json,application/json" hidden aria-label="Reopen notes file" disabled={!corpus||busy} onChange={e=>{const file=e.currentTarget.files?.[0];e.currentTarget.value="";if(file)void reopen(file);}}/>
          <form onSubmit={e=>{e.preventDefault();void analyze();}}>
            <label className="sr-only" htmlFor="incident-issue">Your question</label><textarea ref={prompt} id="incident-issue" disabled={busy} value={issue} maxLength={501} rows={3} onChange={e=>edit(e.target.value,diagnostics)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.form?.requestSubmit();}}} placeholder="Ask a question. RYPE finds the route…" aria-describedby="question-help"/>
            <details className="chat-logs" ref={logs}><summary>Add logs or error details {diagnostics&&<span>Added</span>}</summary><label htmlFor="diagnostics">Logs or error details (optional)</label><textarea id="diagnostics" disabled={busy} value={diagnostics} maxLength={12001} rows={5} onChange={e=>edit(issue,e.target.value)} placeholder="Paste the relevant error or status. Remove passwords, tokens and other sensitive information first." aria-describedby="diagnostics-help"/><p id="diagnostics-help">Never include secrets. Automatic redaction can miss them.</p></details>
            <div className="composer-bottom"><button className="reopen-button" type="button" disabled={!corpus||busy} onClick={()=>importFile.current?.click()}>Reopen notes ↗</button><div><button className="send-question" aria-label="Send question" disabled={!corpus||busy} type="submit"><span>{busy?"Searching…":"Send"}</span><span aria-hidden="true">↑</span></button></div></div>
          </form>
          <p id="question-help" className="composer-help">{metadata?.cloud_configured?"Covered library questions stay in this browser. Other questions and redacted logs go to OpenRouter. Free models only.":"Covered library questions stay in this browser. OpenRouter is not connected; no cloud answer is simulated."}</p>
          {!corpus&&!loadError&&<p role="status" className="composer-help">Loading documentation…</p>}{libraryError&&<p role="status" className="composer-help">{libraryError} Open My library to retry.</p>}{loadError&&<div role="alert" className="chat-error"><p>{loadError}</p><button onClick={()=>void load()}>Retry loading</button></div>}
        </section>
        {!result&&<div className="chat-starters"><span>Not sure where to start? Try an example.</span><div>{EXAMPLES.map(e=><button key={e.title} onClick={()=>{edit(e.issue,e.diagnostics);prompt.current?.focus();}} disabled={busy}>{e.title}<span aria-hidden="true">↗</span></button>)}</div></div>}
      </div>
      <footer className="chat-footer"><span>Nothing connects to your cluster. Discussion stays in this tab; your private library stays in this browser.</span><details><summary>About this assistant</summary><p>RYPE combines a pinned Kubernetes snapshot, an editorial Pod concept guide and your optional private documents. A bounded controller checks retrieval coverage before routing other questions to free models. Documents are never sent to a model. It doesn’t run commands or confirm a root cause. Questions are separate searches; earlier turns are kept for your downloads, not sent as model context. Browser storage is not cloud sync; keep a library backup. <a href={sourceFile("docs/rype-routing.md")}>Read how it works ↗</a></p><nav aria-label="Product details"><a href="/engineering">Behind RYPE</a><a href="/study">Research & evaluation</a></nav></details></footer>
    </main>
  </div>;
}
