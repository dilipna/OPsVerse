// Evaluates the same HTTP handler imported by /api/troubleshoot. Only public synthetic cases.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import os from "node:os";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {handleRequest} from "../lib/troubleshoot-http.mjs";
import {prepare,messages,SYSTEM} from "../lib/troubleshoot.mjs";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../..");
const args=process.argv.slice(2),arg=(name,fallback)=>{const i=args.indexOf(name);return i<0?fallback:args[i+1];};
const label=arg("--label","excerpts"),endpoint=arg("--endpoint",undefined),split=arg("--split","heldout");
const read=p=>fs.readFileSync(path.join(root,p));
const hash=s=>crypto.createHash("sha256").update(s).digest("hex");
const corpus=JSON.parse(read("opslm-demo/public/runbooks.json"));
const dataset=JSON.parse(read("evalsets/troubleshooting-v1/cases.json"));
const rows=dataset.cases.filter(c=>c.split===split);
if(!rows.length)throw new Error("No cases selected");
if(label!=="excerpts"&&!endpoint)throw new Error("A model label requires an explicit local endpoint");
if(endpoint&&!['127.0.0.1','localhost','[::1]'].includes(new URL(endpoint).hostname))throw new Error("This zero-cost study permits loopback endpoints only");
const git=a=>execFileSync("git",a,{cwd:root,encoding:"utf8"}).trim();
const provenance={run_id:crypto.randomUUID(),created_at:new Date().toISOString(),code_commit:git(["rev-parse","HEAD"]),dirty:Boolean(git(["status","--porcelain"])),
  dataset_sha256:hash(read("evalsets/troubleshooting-v1/cases.json")),corpus_sha256:hash(read("opslm-demo/public/runbooks.json")),prompt_sha256:hash(SYSTEM),
  implementation_sha256:hash(read("opslm-demo/lib/troubleshoot.mjs").toString().replace(/\r\n/g,"\n")),
  http_handler_sha256:hash(read("opslm-demo/lib/troubleshoot-http.mjs").toString().replace(/\r\n/g,"\n")),
  evidence_policy_sha256:hash(read("opslm-demo/lib/investigation-evidence.mjs").toString().replace(/\r\n/g,"\n")),
  node:process.version,hardware:{platform:os.platform(),arch:os.arch(),cpu:os.cpus()[0]?.model,ram_bytes:os.totalmem()},
  configuration:{label,split,temperature:0,seed:42,max_tokens:384,context_characters:6000,max_passages:3,diagnostic_characters:2000,timeout_ms:55000},
  limitations:dataset.authorship+" Valid source IDs and matching quotes do not prove entailment. Reference phrase coverage is not factual accuracy. Independent GGUF conversions confound causal SFT interpretation. Synthetic application tests are not an adversarial security certification.",exclusions:[]};
const manifest=arg("--manifest",undefined);if(manifest)provenance.model_manifest=JSON.parse(fs.readFileSync(manifest));
const observations=[];
const out=arg("--out",undefined);
for(const c of rows){
  const input={issue:c.issue,diagnostics:c.diagnostics},prepared=prepare(corpus,input);
  let raw=null,finish_reason=null,usage=null,upstream_status=null;
  const started=performance.now();
  const response=await handleRequest(new Request("http://localhost/api/troubleshoot",{method:"POST",body:JSON.stringify(input)}),{
    corpus,endpoint,model:label,fetcher:async(url,options)=>{
      const r=await fetch(url,options);upstream_status=r.status;
      const data=await r.json();raw=data?.choices?.[0]?.message?.content??null;
      finish_reason=data?.choices?.[0]?.finish_reason??null;usage=data?.usage??null;
      return Response.json(data,{status:r.status});
    }});
  const result=await response.json();
  const accepted=response.status===200&&result.mode==="generated";
  const observedStatus=accepted?result.answer.status:result.mode==="abstained"?"abstained":result.mode==="excerpts"?"excerpts":"error";
  const text=accepted?[result.answer.summary,...result.answer.claims.map(x=>x.text),...result.answer.questions].join(" ").toLowerCase():result.sources?.map(s=>s.text).join(" ").toLowerCase()??"";
  const facts=c.facts.map(alternatives=>({alternatives,covered:alternatives.some(s=>text.includes(s.toLowerCase()))}));
  observations.push({id:c.id,expected_status:c.expected_status,observed_status:observedStatus,http_status:response.status,
    latency_ms:Math.round(performance.now()-started),accepted_generated_answer:accepted,status_match:observedStatus===c.expected_status,
    reference_phrase_facts:facts,prompt_sha256:hash(JSON.stringify(messages(prepared))),retrieved_ids:prepared.sources.map(s=>s.id),
    raw_model_text:raw,finish_reason,usage,upstream_status,result});
  const valid=observations.filter(x=>x.accepted_generated_answer).length;
  const report={...provenance,summary:{cases:observations.length,planned_cases:rows.length,accepted_generated_answers:valid,
    status_matches:observations.filter(x=>x.status_match).length,reference_facts_covered:observations.flatMap(x=>x.reference_phrase_facts).filter(x=>x.covered).length,
    reference_facts_total:observations.flatMap(x=>x.reference_phrase_facts).length,request_errors:observations.filter(x=>x.http_status!==200).length},observations};
  if(out)fs.writeFileSync(out,JSON.stringify(report,null,2)+"\n");
  console.log(JSON.stringify({label,id:c.id,status:observedStatus,http:response.status,finish_reason,latency_ms:observations.at(-1).latency_ms}));
}

if(label==="excerpts" && observations.some(x=>x.http_status!==200||x.accepted_generated_answer))throw new Error("Excerpt workflow contract failed");
