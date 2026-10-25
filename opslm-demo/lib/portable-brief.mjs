import {redact} from "./troubleshoot.mjs";

export const MAX_BRIEF_BYTES=262144;
export const SAVED_GUIDES_KEY="opsverse.saved-guides.v1";

export function createBrief(result,notes,revision,createdAt=new Date().toISOString()){
  const review=redact(notes.slice(0,4000));
  return {schema_version:1,created_at:createdAt,...result,
    review:{status:"unreviewed",notes:review.text,notes_redactions:review.redactions},
    source_revision:revision,
    boundary:"Observed signals and documentation support; not a confirmed root cause. No commands executed. Credential redaction is best-effort."};
}

export function restoreBrief(text,corpus){
  if(new TextEncoder().encode(text).length>MAX_BRIEF_BYTES)throw Error("This file is too large. Choose an RYPE JSON download under 256 KB.");
  let data;try{data=JSON.parse(text);}catch{throw Error("This is not valid JSON. Choose an RYPE JSON download.");}
  if(!data||data.schema_version!==1||data.review?.status!=="unreviewed")throw Error("This file is not a supported RYPE investigation.");
  if(data.source_revision!==corpus.manifest.revision)throw Error("This file uses a different documentation snapshot. Copy its question into a new search instead.");
  if(typeof data.issue!=="string"||!data.issue.trim()||data.issue.length>500||typeof data.diagnostics!=="string"||data.diagnostics.length>12000||typeof data.review.notes!=="string"||data.review.notes.length>4000)throw Error("The question, logs or notes in this file are invalid.");
  // Imported answers, links, commands, timestamps and source passages are never
  // restored. The caller reruns retrieval against the current trusted corpus.
  return {issue:redact(data.issue).text,diagnostics:redact(data.diagnostics).text,notes:redact(data.review.notes).text};
}

function block(text){
  const longest=Math.max(2,...(String(text).match(/`+/g)||[]).map(x=>x.length));
  const fence="`".repeat(longest+1);
  return `${fence}text\n${text}\n${fence}`;
}

export function markdownBrief(brief){
  const sections=["# RYPE investigation notes",`Created: ${brief.created_at}`,"Status: Unreviewed. Documentation support is not a confirmed root cause.","## Question",block(brief.issue),"## Logs / error details",block(brief.diagnostics||"None provided."),"## Your notes",block(brief.review.notes||"None added.")];
  if(brief.diagnostics_truncated)sections.push("Only the first 2,000 log characters are included. The original search may have used additional status text.");
  if(brief.cloud_answer)sections.push("## OpenRouter answer — requires review",block(brief.cloud_answer));
  if(brief.routing)sections.push("## Routing and cost receipt",block(JSON.stringify(brief.routing,null,2)));
  if(brief.answer)sections.push("## AI draft — requires review",block(JSON.stringify(brief.answer,null,2)));
  sections.push("## Source passages");
  if(!brief.sources.length)sections.push("No supporting passages found.");
  for(const [i,s] of brief.sources.entries())sections.push(`### Source ${i+1}`,block(`${s.section}\nID: ${s.id}`),`Pinned source: <${s.source}>\n\nCurrent documentation: <${s.canonical}>`,block(s.text));
  sections.push("## Scope",block(brief.boundary),`Documentation revision: ${brief.source_revision}`);
  return sections.join("\n\n")+"\n";
}

export function savedGuideIds(text,corpus){
  if(typeof text!=="string"||text.length>65536)return [];
  let data;try{data=JSON.parse(text);}catch{return [];}
  if(data?.schema!==1||data.revision!==corpus.manifest.revision||!Array.isArray(data.ids))return [];
  const allowed=new Set(corpus.chunks.map(c=>c.id));
  return [...new Set(data.ids.filter(id=>typeof id==="string"&&allowed.has(id)))].slice(0,30);
}
