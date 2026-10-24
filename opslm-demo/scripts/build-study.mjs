import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import crypto from "node:crypto";
import {SYSTEM} from "../lib/troubleshoot.mjs";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../..");
const read=p=>JSON.parse(fs.readFileSync(path.join(root,p)));
const retrieval=read("docs/reports/runbook-evaluation.json");
const contamination=read("docs/reports/troubleshooting-contamination-v1.json");
const dataset=read("evalsets/troubleshooting-v1/cases.json");
const artifact=read("evalsets/troubleshooting-v1/artifacts.json");
const corpus=read("opslm-demo/public/runbooks.json");
const investigationBaseline=read("docs/reports/investigation-development-baseline-v1.json");
const investigationCandidate=read("docs/reports/investigation-development-candidate-v1.json");
const hash=b=>crypto.createHash("sha256").update(b).digest("hex");
const bytes=p=>fs.readFileSync(path.join(root,p));
const code=p=>bytes(p).toString().replace(/\r\n/g,"\n");
if(investigationBaseline.dataset_sha256!==investigationCandidate.dataset_sha256
  || investigationCandidate.dataset_sha256!==hash(bytes("evalsets/investigation-development-v1.json"))
  || investigationCandidate.implementation_sha256!==hash(code("opslm-demo/lib/troubleshoot.mjs"))
  || investigationCandidate.evidence_policy_sha256!==hash(code("opslm-demo/lib/investigation-evidence.mjs")))throw Error("Stale investigation development evidence");
const models=["base","sft"].flatMap(label=>{
  const file=`docs/reports/troubleshooting-${label}-v1.json`;
  if(!fs.existsSync(path.join(root,file)))return [];
  const report=read(file);
  const expected=dataset.cases.filter(c=>c.split==="heldout").map(c=>c.id).sort();
  const observed=report.observations.map(r=>r.id).sort();
  if(report.prompt_sha256!==hash(SYSTEM)||report.dataset_sha256!==hash(bytes("evalsets/troubleshooting-v1/cases.json"))||report.corpus_sha256!==hash(bytes("opslm-demo/public/runbooks.json"))||report.implementation_sha256!==hash(code("opslm-demo/lib/troubleshoot.mjs"))||report.http_handler_sha256!==hash(code("opslm-demo/lib/troubleshoot-http.mjs"))||report.evidence_policy_sha256!==hash(code("opslm-demo/lib/investigation-evidence.mjs"))||JSON.stringify(observed)!==JSON.stringify(expected))throw new Error("Stale or incomplete model release evidence: "+file);
  return [{label,summary:report.summary,code_commit:report.code_commit,run_id:report.run_id,observations:report.observations.map(r=>({id:r.id,status:r.observed_status,http:r.http_status,latency_ms:r.latency_ms,raw_model_text:r.raw_model_text,finish_reason:r.finish_reason,result:r.result}))}];
});
const data={documents:corpus.manifest.documents.length,passages:corpus.chunks.length,source_revision:corpus.manifest.revision,
  investigation:{baseline:investigationBaseline.summary,candidate:investigationCandidate.summary,
    limitations:investigationCandidate.limitations,release_evidence:false},
  retrieval:{cases:retrieval.results.overlap.heldout.n,overlap:retrieval.results.overlap.heldout.hit_at_1,bm25:retrieval.results.bm25.heldout.hit_at_1,hit_at_3:retrieval.results.overlap.heldout.hit_at_3,limitations:retrieval.limitations},
  troubleshooting:{protocol:"troubleshooting-v1",freeze_commit:"19f2295",development:dataset.cases.filter(c=>c.split==="development").length,heldout:dataset.cases.filter(c=>c.split==="heldout").length,contamination_flags:contamination.flagged,sft_inputs:contamination.sft_inputs},
  model_artifacts:artifact.models,models,model_comparison_complete:models.length===2&&models.every(m=>m.summary.cases===24),
  limitations:"Synthetic, agent-authored scenarios and coarse reference checks. No independent human answer-quality scoring. Matching source quotes do not prove entailment. Independent GGUF conversions confound causal SFT interpretation. No external-user impact established."};
const text=JSON.stringify(data,null,2)+"\n",out=path.join(root,"opslm-demo/public/study.json");
if(process.argv.includes("--check")){if(fs.readFileSync(out,"utf8").replace(/\r\n/g,"\n")!==text)throw new Error("Study display is stale; run build-study.mjs");console.log("Study display matches recorded artifacts");}
else {fs.writeFileSync(out,text);console.log("Study display generated from recorded artifacts");}
const investigationText=JSON.stringify({baseline:investigationBaseline,candidate:investigationCandidate},null,2)+"\n";
const investigationOut=path.join(root,"opslm-demo/public/investigation-development.json");
if(process.argv.includes("--check")){
  if(fs.readFileSync(investigationOut,"utf8").replace(/\r\n/g,"\n")!==investigationText)throw Error("Development comparison download is stale");
}else fs.writeFileSync(investigationOut,investigationText);
