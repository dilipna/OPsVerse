import {prepare,completeInvestigation} from "./troubleshoot.mjs";
import {terms} from "./runbooks.mjs";

export const BASELINE_MODEL="anthropic/claude-sonnet-4.6";
export const PROFILES={
  general:{label:"Everyday question",free:["recursive/flint-v1.0:free","cohere/north-mini-code:free"],paid:["google/gemini-2.5-flash-lite","openai/gpt-oss-120b"]},
  code:{label:"Coding question",free:["cohere/north-mini-code:free","recursive/flint-v1.0:free"],paid:["qwen/qwen3-coder-30b-a3b-instruct","qwen/qwen3-coder-next"]},
  reasoning:{label:"Reasoning question",free:["dots-studio/dots-3-note-preview:free","cohere/north-mini-code:free"],paid:["openai/gpt-oss-120b","qwen/qwen3-coder-next"]},
};
const RULES=[
  ["Image pull guidance",/ImagePullBackOff|ErrImagePull|image pull policy|imagepullpolicy/i,"images",/ImagePullBackOff|imagePullPolicy/],
  ["Memory-limit guidance",/OOMKilled|memory limits?/i,"resources",/OOMKilled|memory limit/i],
  ["Probe guidance",/readiness|liveness|startup probe/i,"probes",/readiness|liveness|startup/i],
  ["Restart guidance",/CrashLoopBackOff/i,"debug-pods",/restart|logs|crash/i],
  ["Scheduling guidance",/FailedScheduling|Insufficient cpu/i,"resources",/requests|cpu|schedul/i],
  ["Rollout guidance",/ProgressDeadlineExceeded/i,"deployments",/progress|deadline/i],
];

export function previewSource(text){
  const paragraphs=text.replace(/^---\n[\s\S]*?\n---\n/,"").replace(/```[\s\S]*?```/g,"").split(/\n\s*\n/);
  const prose=paragraphs.filter(p=>/^[A-Z]/.test(p)&&p.length>=60&&p.length<=900&&!/[{}<>]|^\s*[-*#|]/m.test(p));
  const selected=prose.find(p=>/\bmeans\b|\bindicates\b/.test(p))||prose[0];
  return selected?.replace(/\[([^\]]+)\]\([^)]*\)/g,"$1").replace(/`([^`]+)`/g,"$1").replace(/\*\*([^*]+)\*\*/g,"$1").replace(/\s+/g," ").trim();
}

export function decideRoute(prepared){
  const question=prepared.issue.toLowerCase(),text=question+"\n"+prepared.diagnostics;
  const category=/\b(prove|proof|derive|trade[- ]?offs?|multi[- ]step|complex|reasoning|architecture)\b/.test(question)?"reasoning":/\b(code|implement|function|program|algorithm|python|javascript|typescript|sql|dockerfile|yaml|bash|golang|rust|java|debug|refactor|write.*script)\b/.test(question)?"code":"general";
  const custom=/\b(write|generate|implement|prove|derive|refactor|algorithm|compare|versus|vs|redis|postgres|terraform|dockerfile|javascript|python|quantum|poem|email)\b/.test(question);
  const matched=RULES.filter(([,pattern])=>pattern.test(text));
  const stem=t=>t.replace(/(?:ing|ed|s)$/,"");
  const vocabulary=new Set(terms(prepared.sources.map(s=>s.text).join(" ")).map(stem));
  const generic=new Set("has have had not no next inspect investigate understand explain mean means process running receives happened started status signal signals issue help tell about please".split(" ").map(stem));
  const questionCovered=terms(question).every(t=>generic.has(stem(t))||vocabulary.has(stem(t)));
  const covered=matched.length>0&&!custom&&questionCovered&&!prepared.evidence_policy.missing_signals.length&&matched.every(([, ,family,pattern])=>prepared.sources.some(s=>s.document===family&&pattern.test(s.text)&&previewSource(s.text)));
  return covered?{kind:"retrieval",category:"library",reason:`Covered documentation topic: ${matched.map(r=>r[0]).join(", ")}. Returning source text without generation.`}:{kind:"model",category,reason:custom?"This request asks for work beyond the covered documentation excerpts.":"The limited documentation snapshot does not fully cover this request."};
}

const amount=v=>typeof v==="string"&&v.trim()!==""||typeof v==="number"?Number(v):NaN;
export function catalogueModels(raw){
  if(!Array.isArray(raw?.data))throw Error("Model catalogue is unavailable.");
  return raw.data.filter(m=>typeof m.id==="string"&&m.architecture?.input_modalities?.includes("text")&&m.architecture?.output_modalities?.includes("text")&&!m.architecture.output_modalities.includes("audio"))
    .map(m=>({id:m.id,prompt:amount(m.pricing?.prompt),completion:amount(m.pricing?.completion),request:m.pricing?.request===undefined?0:amount(m.pricing.request),reasoning:m.pricing?.internal_reasoning===undefined?0:amount(m.pricing.internal_reasoning),context:m.context_length}))
    .filter(m=>[m.prompt,m.completion,m.request,m.reasoning].every(n=>Number.isFinite(n)&&n>=0)&&Number.isFinite(m.context)&&m.context>0);
}
export function selectModel(category,models,{freeOnly=true,maxRequestUsd=0,inputBytes=0,maxTokens=768}={}){
  const profile=PROFILES[category]||PROFILES.general;
  const allowed=freeOnly?profile.free:[...profile.free,...profile.paid];
  return models.filter(m=>allowed.includes(m.id)&&m.context>=inputBytes+maxTokens+1024)
    .filter(m=>freeOnly?m.prompt===0&&m.completion===0&&m.request===0&&m.reasoning===0:(m.prompt*(inputBytes+1024)+Math.max(m.completion,m.reasoning)*maxTokens+m.request)<=maxRequestUsd)
    .sort((a,b)=>(a.prompt*500+a.completion*maxTokens+a.request)-(b.prompt*500+b.completion*maxTokens+b.request)||allowed.indexOf(a.id)-allowed.indexOf(b.id))[0]||null;
}
export function costComparison({actualCost=null,inputTokens=null,outputTokens=null,baseline=null,estimatedTokens=false}){
  const validTokens=[inputTokens,outputTokens].every(n=>Number.isSafeInteger(n)&&n>=0);
  const baselineValid=baseline&&[baseline.prompt,baseline.completion,baseline.request].every(n=>Number.isFinite(n)&&n>=0);
  const baselineCost=baselineValid&&validTokens?baseline.prompt*inputTokens+baseline.completion*outputTokens+baseline.request:null;
  const delta=Number.isFinite(actualCost)&&actualCost>=0&&Number.isFinite(baselineCost)?baselineCost-actualCost:null;
  return {actual_cost_usd:Number.isFinite(actualCost)&&actualCost>=0?actualCost:null,baseline_model:baseline?.id||null,baseline_estimated_usd:baselineCost,estimated_difference_usd:delta,
    estimated_reduction_percent:delta!==null&&baselineCost>0?delta/baselineCost*100:null,input_tokens:inputTokens,output_tokens:outputTokens,
    token_basis:estimatedTokens?"Approximate characters / 4; no tokenizer or baseline inference was run.":"Selected model's reported tokens, reused for a hypothetical baseline; tokenizer and answer quality can differ.",
    comparison_scope:"Estimated inference-token comparison only. Baseline not run; excludes hosting, taxes and other fees. Not a measured quality-matched saving."};
}
export function localRoutingResult(result,metadata=null,{restored=false}={}){
  const decision=decideRoute(result),baseline=metadata?.baseline||null;
  const model=decision.kind==="model"?metadata?.profiles?.[decision.category]||null:null;
  const comparison=decision.kind==="retrieval"?costComparison({actualCost:0,inputTokens:Math.ceil((result.issue.length+result.diagnostics.length)/4),outputTokens:Math.ceil(result.sources.map(s=>previewSource(s.text)||"").join(" ").length/4),baseline,estimatedTokens:true}):costComparison({actualCost:0});
  return {...result,routing:{...decision,status:decision.kind==="retrieval"?"completed":restored?"not_requested":"unavailable",model_used:null,model_selected:model?.id||null,model_calls:0,price_checked_at:metadata?.checked_at||null,
    ...comparison,note:decision.kind==="retrieval"?"Retrieved guidance, not a generated diagnosis. No inference request was made.":restored?"Reopened locally. Press Send to request a model route; saved answers were not reused.":"OpenRouter is not connected or no eligible model is available. No inference request was made."}};
}
export async function prepareLocalRoute(corpus,input,metadata){return localRoutingResult(await completeInvestigation(prepare(corpus,input)),metadata);}
