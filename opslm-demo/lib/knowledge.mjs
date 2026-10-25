import {redact} from "./troubleshoot.mjs";

export const LIBRARY_LIMITS={documents:10,documentBytes:50000,totalBytes:250000,backupBytes:600000};
const bytes=s=>new TextEncoder().encode(s).length;
const STOP=new Set("a an and are as at be by can could describe do does explain for from give how i in is it me of on or please tell that the this to was what when where which why with would you your about mean means".split(" "));
const aliases={pods:"pod",k8s:"kubernetes",containers:"container",deployments:"deployment",replicas:"replica",definitions:"definition"};
export function tokens(text){return (text.normalize("NFKC").toLowerCase().match(/[\p{L}\p{N}]+/gu)||[]).map(t=>aliases[t]||t).filter(t=>t.length>1&&!STOP.has(t));}
// A small, separately versioned concept supplement. These are editorial
// paraphrases, not quotations from, or additions to, the frozen research corpus.
export const CONCEPTS=[{id:"concept-pod-v1",document:"concept-pods",section:"What is a Kubernetes Pod?",source:"https://kubernetes.io/docs/concepts/workloads/pods/",canonical:"https://kubernetes.io/docs/concepts/workloads/pods/",origin:"concept",text:"A Kubernetes Pod is the smallest unit you can deploy and manage in Kubernetes. It groups one or more containers that run together on a node and share networking and storage resources. Containers in the same Pod share an IP address and can communicate over localhost. A Pod is usually managed by a workload controller, such as a Deployment, rather than being created manually. A Pod is not a whole cluster or a virtual machine."}];
export function validateDocument(name,text){
  if(typeof name!=="string"||!name.trim()||name.length>100||/[\x00-\x1f]/.test(name))throw Error("Use a document title of 1–100 characters.");
  if(typeof text!=="string"||!text.trim()||bytes(text)>LIBRARY_LIMITS.documentBytes||/\x00/.test(text))throw Error("Use nonempty UTF-8 text under 50 KB. Binary files are not supported.");
  return {name:redact(name.trim()).text,text:redact(text.trim()).text};
}
export async function makeDocument(name,text){
  const clean=validateDocument(name,text);
  const hash=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(clean.text));
  return {...clean,id:Array.from(new Uint8Array(hash),n=>n.toString(16).padStart(2,"0")).join(""),created_at:new Date().toISOString()};
}
export function validateLibrary(documents){
  if(!Array.isArray(documents)||documents.length>LIBRARY_LIMITS.documents)throw Error("Your private library holds up to 10 documents.");
  let total=0;
  for(const d of documents){validateDocument(d.name,d.text);if(!/^[a-f0-9]{64}$/.test(d.id)||typeof d.created_at!=="string")throw Error("Invalid library record.");total+=bytes(d.text);}
  if(total>LIBRARY_LIMITS.totalBytes)throw Error("Your private library holds up to 250 KB of text. Remove a document first.");
  if(new Set(documents.map(d=>d.id)).size!==documents.length)throw Error("This document is already in your library.");
  return documents;
}
export function libraryBackup(documents){validateLibrary(documents);return JSON.stringify({format:"rype-private-library",version:1,documents:documents.map(({name,text})=>({name,text}))},null,2);}
export async function parseLibraryBackup(text){
  if(bytes(text)>LIBRARY_LIMITS.backupBytes)throw Error("Choose a library backup under 600 KB.");
  let value;try{value=JSON.parse(text);}catch{throw Error("Choose a valid RYPE library JSON backup.");}
  if(value?.format!=="rype-private-library"||value.version!==1||!Array.isArray(value.documents)||value.documents.length>10)throw Error("Unsupported library backup.");
  // Never trust imported ids, links, indices or embeddings; rebuild from text.
  return validateLibrary(await Promise.all(value.documents.map(d=>makeDocument(d.name,d.text))));
}
export function documentChunks(documents){
  return documents.flatMap(d=>{const chunks=[];for(let start=0;start<d.text.length;start+=1000){const text=d.text.slice(start,start+1200);chunks.push({id:`private-${d.id}-${start}`,document:d.id,section:d.name,text,source:"",canonical:"",origin:"private"});}return chunks;});
}
function grams(text){const str=tokens(text).join(" "),out=new Set();for(let i=0;i<str.length-2;i++)out.add(str.slice(i,i+3));return out;}
export function hybridSearch(chunks,query,limit=3){
  const q=[...new Set(tokens(query))];if(!q.length)return [];
  const docs=chunks.map(s=>tokens(s.section+" "+s.text)),avg=docs.reduce((n,d)=>n+d.length,0)/(docs.length||1);
  const df=new Map(q.map(t=>[t,docs.filter(d=>d.includes(t)).length])),gq=grams(query);
  const scores=chunks.map((s,i)=>{const words=docs[i],set=new Set(words);let bm25=0,matched=0;for(const t of q){const tf=words.filter(w=>w===t).length;if(tf){matched++;bm25+=Math.log(1+(docs.length-df.get(t)+.5)/(df.get(t)+.5))*tf*2.2/(tf+1.2*(.25+.75*words.length/avg));}}const gs=grams(s.section+" "+s.text);const shared=[...gq].filter(g=>gs.has(g)).length;return {...s,bm25,character_similarity:shared/Math.sqrt((gq.size||1)*(gs.size||1)),matched,coverage:q.filter(t=>set.has(t)).length/q.length};});
  const lexical=[...scores].filter(s=>s.bm25>0).sort((a,b)=>b.bm25-a.bm25||a.id.localeCompare(b.id));
  const character=[...scores].filter(s=>s.character_similarity>.01).sort((a,b)=>b.character_similarity-a.character_similarity||a.id.localeCompare(b.id));
  return scores.map(s=>{const a=lexical.findIndex(x=>x.id===s.id),b=character.findIndex(x=>x.id===s.id);return {...s,score:(a<0?0:1/(60+a+1))+(b<0?0:1/(60+b+1))};}).filter(s=>s.matched>0).sort((a,b)=>b.score-a.score||b.coverage-a.coverage||a.id.localeCompare(b.id)).slice(0,limit);
}
const instruction=/ignore (?:all |the |previous )?instructions|system prompt|developer message|reveal .*secret|act as|you (?:must|should) (?:ignore|obey)/i;
export function knowledgeLookup(corpus,input,documents=[]){
  const question=redact(input.issue).text,privateChunks=documentChunks(documents);
  const prose=text=>text.replace(/^---\n[\s\S]*?\n---\n/,"").replace(/```[\s\S]*?```/g,"").split(/\n\s*\n/).filter(p=>/^[\p{L}]/u.test(p.trim())&&p.trim().length>40&&!/[{}<>]|^\s*[-*#|]/m.test(p)).map(p=>p.replace(/\[([^\]]+)\]\([^)]*\)/g,"$1")).join("\n\n");
  const chunks=[...CONCEPTS,...privateChunks,...corpus.chunks.map(s=>({...s,origin:"snapshot"}))].map(s=>({...s,text:prose(s.text)})).filter(s=>s.text.length>30);
  const steps=[{action:"plan",observation:"Search the local library before considering a model. Uploaded text stays on this device."}];
  let query=question,found=hybridSearch(chunks,query),attempts=1;
  steps.push({action:"hybrid_search",observation:`BM25 + character-trigram similarity, reciprocal-rank fusion; ${found.length} candidates.`,source_ids:found.map(s=>s.id)});
  // Retry expansion is bounded and deterministic. No hidden reasoning, model
  // inference, network access, embeddings or untrusted document instructions.
  if(!found.some(s=>s.coverage===1)&&/\bk8s\b|\bpods\b/i.test(query)){
    query=query.replace(/\bk8s\b/gi,"kubernetes").replace(/\bpods\b/gi,"pod");found=hybridSearch(chunks,query);attempts++;
    steps.push({action:"retry",observation:"Normalized Kubernetes aliases and searched again.",source_ids:found.map(s=>s.id)});
  }
  const wantsWork=/\b(write|generate|implement|prove|derive|refactor|compare|versus|vs|execute|run|delete)\b/i.test(question);
  const contentTerms=tokens(question).filter(t=>!new Set(["definition","basic","simple","terms"]).has(t));
  // For basic definitions, favor the explicit concept guide rather than a
  // high-scoring incidental mention in a troubleshooting passage.
  if(/^(what (?:is|are)|define|explain|describe)\b/i.test(question)&&tokens(question).every(t=>["kubernetes","pod","definition","basic","simple","terms"].includes(t))){const concept=hybridSearch(chunks.filter(s=>s.origin==="concept"),question);found=[...concept,...found.filter(s=>!concept.some(c=>c.id===s.id))].slice(0,3);steps.push({action:"prefer_definition",observation:"Prefer the explicit Pod concept guide over incidental troubleshooting mentions.",source_ids:concept.map(s=>s.id)});}
  const safe=found.filter(s=>!instruction.test(s.text));
  const paragraphSupports=p=>{const vocabulary=new Set(tokens(p));return contentTerms.length>0&&contentTerms.every(t=>vocabulary.has(t));};
  const support=safe.find(s=>s.text.split(/\n\s*\n/).some(paragraphSupports));
  // Do not infer a complete answer from term overlap for arbitrary task requests.
  const definition=/^(?:what (?:is|are|does)|define|explain|describe|tell me about|how (?:does|do))\b/i.test(question.trim());
  const covered=!!support&&!wantsWork&&definition&&!input.diagnostics.trim();
  const sources=covered?[support,...safe.filter(s=>s.id!==support.id&&s.document===support.document)].slice(0,2):safe.slice(0,3);
  const extracts=covered?support.text.split(/\n\s*\n/).filter(p=>p.trim().length>30&&paragraphSupports(p)).slice(0,2).join("\n\n").slice(0,1800):"";
  const accepted=covered&&extracts.length>30;
  steps.push({action:"check_coverage",observation:accepted?"A single passage contains all question terms; return cited extracts. This is a lexical support check, not a factual guarantee.":"Coverage is insufficient or this task needs generation. Do not claim the library knows the answer."});
  steps.push({action:accepted?"answer_from_library":"route_if_allowed",observation:accepted?"Zero inference calls. Source text is evidence, never instructions.":"Only the question and redacted diagnostics may be routed; private documents are not sent."});
  return {covered:accepted,answer:accepted?extracts:null,sources:accepted?sources:[],trace:{version:1,strategy:"bm25-character-rrf",attempts,steps},private_candidates:privateChunks.length};
}
