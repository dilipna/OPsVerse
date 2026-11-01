import {troubleshoot} from "./troubleshoot.mjs";
import {localRoutingResult,costComparison} from "./rype-routing.mjs";
import {knowledgeLookup} from "./knowledge.mjs";
export async function workspaceRoute(corpus,input,metadata=null,{documents=[],restored=false}={}){
  const base=localRoutingResult(await troubleshoot(corpus,input),metadata,{restored});
  const lookup=knowledgeLookup(corpus,{issue:base.issue,diagnostics:base.diagnostics},documents);
  if(base.routing.kind==="retrieval")return {...base,knowledge:{...lookup.trace,steps:[...lookup.trace.steps.slice(0,2),{action:"existing_evidence_gate",observation:"The bounded troubleshooting gate covers this status and preserves the original diagnostic evidence."},{action:"answer_from_library",observation:"Zero inference calls; source excerpts returned."}]}};
  if(!lookup.covered)return {...base,knowledge:lookup.trace};
  const sources=lookup.sources;
  return {...base,mode:"excerpts",sources,library_answer:lookup.answer,knowledge:lookup.trace,note:"Cited library extracts, not a generated answer. Uploaded documents are unverified user-provided material.",
    routing:{...base.routing,kind:"retrieval",category:"library",status:"completed",reason:"Hybrid local retrieval found a passage covering the question terms. Returning cited extracts without inference.",model_selected:null,model_used:null,model_calls:0,
      ...costComparison({actualCost:0,inputTokens:Math.ceil(base.issue.length/4),outputTokens:Math.ceil(lookup.answer.length/4),baseline:metadata?.baseline,estimatedTokens:true}),note:"No model request. BM25 and character-trigram ranks were fused locally; no embedding model was called."},
    evidence_policy:{...base.evidence_policy,attempts:[{kind:"initial",query:base.issue,returned:sources.map(s=>s.id)}],coverage:[],missing_signals:[],usage:{passages:sources.length,characters:sources.reduce((n,s)=>n+s.text.length,0),retrieval_attempts:lookup.trace.attempts},scope:"Hybrid lexical coverage, not a guarantee of factual support. Read the cited source and check uploaded documents."}};
}
