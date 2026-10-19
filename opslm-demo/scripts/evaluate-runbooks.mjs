import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import os from "node:os";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {search} from "../lib/runbooks.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const read = p => fs.readFileSync(path.join(root,p));
const hash = b => crypto.createHash("sha256").update(b).digest("hex");
const code = p => Buffer.from(read(p).toString("utf8").replace(/\r\n/g,"\n"));
const corpus = JSON.parse(read("opslm-demo/public/runbooks.json"));
const cases = JSON.parse(read("evalsets/runbooks/queries.json"));
const evaluate = (set, mode) => set.map(c => {
  const hits = search(corpus,c.query,5,mode);
  return {id:c.id, query:c.query, expected:c.document ?? null, returned:hits.map(h=>h.id),
    hit_at_1:c.document ? Number(hits[0]?.document === c.document):null,
    hit_at_3:c.document ? Number(hits.slice(0,3).some(h=>h.document===c.document)):null,
    empty:hits.length===0};
});
const mean = values => values.reduce((a,b)=>a+b,0)/(values.length||1);
const results = {};
for (const mode of ["overlap","bm25"]) {
  results[mode] = {};
  for (const split of ["development","heldout","negative","stress"]) {
    const rows = evaluate(cases[split],mode);
    const positive = rows.filter(r=>r.expected);
    results[mode][split] = {n:rows.length, hit_at_1:mean(positive.map(r=>r.hit_at_1)),hit_at_3:mean(positive.map(r=>r.hit_at_3)),empty_rate:mean(rows.map(r=>Number(r.empty))),rows};
  }
}
const git = args => execFileSync("git",args,{cwd:root,encoding:"utf8"}).trim();
const report = {protocol:cases.protocol,run_id:crypto.randomUUID(),created_at:new Date().toISOString(),
  code_commit:git(["rev-parse","HEAD"]),dirty:Boolean(git(["status","--porcelain"])),
  evaluated_source_sha256:hash(code("opslm-demo/lib/runbooks.mjs")),
  ingestion_source_sha256:hash(Buffer.concat([code("libs/ingestion/src/opsverse_ingestion/parsers/markdown.py"),code("libs/ingestion/src/opsverse_ingestion/chunking.py"),code("libs/ingestion/src/opsverse_ingestion/pipeline.py"),code("libs/ingestion/src/opsverse_ingestion/quality.py")])),
  corpus_sha256:hash(read("opslm-demo/public/runbooks.json")),dataset_sha256:hash(read("evalsets/runbooks/queries.json")),
  upstream_revision:corpus.manifest.revision,documents:corpus.manifest.documents.length,passages:corpus.chunks.length,
  configuration:{retrieval:"BM25 k1=1.2 b=0.75; two distinct query terms when available",k:5,model:"none",hardware:`${os.platform()} ${os.arch()} ${os.cpus()[0]?.model}`,node:process.version},
  exclusions:[],limitations:cases.authorship+" Document-level relevance only; no human answer-quality scoring. Lexical negatives are not a safety or answerability benchmark. Stress queries are descriptive and not release thresholds.",results};
const passed = ["overlap","bm25"].every(mode => results[mode].heldout.hit_at_3 >= cases.policy.heldout_hit_at_3_min && results[mode].negative.empty_rate >= cases.policy.negative_empty_min);
report.selected_implementation="term-overlap: tied hit@3, higher observed hit@1; no significant superiority claimed; selection used these now-public cases";
report.release_gate={passed,policy:cases.policy};
const out=process.argv.indexOf("--out");
if(out>=0)fs.writeFileSync(path.resolve(root,process.argv[out+1]),JSON.stringify(report,null,2)+"\n");
console.log(JSON.stringify({release_gate:report.release_gate,bm25:results.bm25.heldout,overlap:results.overlap.heldout,stress:results.bm25.stress},null,2));
if(!passed)process.exitCode=1;
