import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {prepare} from "../lib/troubleshoot.mjs";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../..");
const read=p=>fs.readFileSync(path.join(root,p));
const hash=b=>crypto.createHash("sha256").update(b).digest("hex");
const data=JSON.parse(read("evalsets/investigation-development-v1.json"));
const corpus=JSON.parse(read("opslm-demo/public/runbooks.json"));
const observations=data.cases.map(c=>{
  const p=prepare(corpus,{issue:c.issue,diagnostics:c.diagnostics});
  const docs=new Set(p.sources.map(s=>s.document));
  return {id:c.id,expected_documents:c.documents,returned:p.sources.map(s=>s.id),
    covered:c.documents.filter(d=>docs.has(d)),missing:c.documents.filter(d=>!docs.has(d)),
    empty_correct:c.expect_empty ? p.sources.length===0 : null,
    sources:p.sources.length,characters:p.sources.reduce((n,s)=>n+s.text.length,0),
    within_budget:p.sources.length<=3&&p.sources.reduce((n,s)=>n+s.text.length,0)<=6000};
});
const report={created_at:new Date().toISOString(),
  commit:execFileSync("git",["rev-parse","HEAD"],{cwd:root,encoding:"utf8"}).trim(),
  dirty:Boolean(execFileSync("git",["status","--porcelain"],{cwd:root,encoding:"utf8"}).trim()),
  dataset_sha256:hash(read("evalsets/investigation-development-v1.json")),
  implementation_sha256:hash(read("opslm-demo/lib/troubleshoot.mjs").toString().replace(/\r\n/g,"\n")),
  evidence_policy_sha256:fs.existsSync(path.join(root,"opslm-demo/lib/investigation-evidence.mjs"))
    ? hash(read("opslm-demo/lib/investigation-evidence.mjs").toString().replace(/\r\n/g,"\n")) : null,
  limitations:data.purpose+" "+data.authorship,
  summary:{cases:observations.length,document_targets:observations.reduce((n,r)=>n+r.expected_documents.length,0),
    covered:observations.reduce((n,r)=>n+r.covered.length,0),
    complete:observations.filter(r=>r.expected_documents.length&&!r.missing.length).length,
    empty_correct:observations.filter(r=>r.empty_correct===true).length,
    budget_violations:observations.filter(r=>!r.within_budget).length},observations};
const i=process.argv.indexOf("--out");
if(i!==-1)fs.writeFileSync(path.resolve(process.argv[i+1]),JSON.stringify(report,null,2)+"\n");
console.log(JSON.stringify(report.summary));
if(observations.some(r=>!r.within_budget||r.empty_correct===false))throw Error("Investigation budget or empty-query contract failed");
const baselinePath=path.join(root,"docs/reports/investigation-development-baseline-v1.json");
if(fs.existsSync(baselinePath)){
  const baseline=JSON.parse(fs.readFileSync(baselinePath));
  if(baseline.dataset_sha256!==report.dataset_sha256)throw Error("Development set changed: freeze a new experiment before replacing this baseline");
  for(const before of baseline.observations){
    const after=observations.find(r=>r.id===before.id);
    if(!after || before.covered.some(d=>!after.covered.includes(d)))throw Error("Document-family regression: "+before.id);
  }
}
