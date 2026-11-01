import {test} from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {prepare,troubleshoot} from "../lib/troubleshoot.mjs";
const corpus=JSON.parse(fs.readFileSync(new URL("../public/runbooks.json",import.meta.url)));
const mixed={issue:"What should I inspect next?",diagnostics:"OOMKilled\nReadiness probe failed"};

test("different observed families retain distinct actual source passages",()=>{
  const p=prepare(corpus,mixed);
  assert.ok(p.sources.some(s=>s.document==="resources"));
  assert.ok(p.sources.some(s=>s.document==="probes"));
  assert.deepEqual(p.evidence_policy.missing_signals,[]);
  for(const s of p.sources)assert.ok(corpus.chunks.find(c=>c.id===s.id).text.startsWith(s.text));
});
test("deleted source families produce explicit gaps rather than invented passages",()=>{
  const p=prepare({...corpus,chunks:corpus.chunks.filter(s=>s.document!=="resources")},mixed);
  assert.ok(p.evidence_policy.missing_signals.includes("OOMKilled"));
  assert.ok(!p.sources.some(s=>s.document==="resources"));
});
test("more observed families than slots stays bounded and exposes omissions",()=>{
  const p=prepare(corpus,{issue:"What happened?",diagnostics:"ImagePullBackOff\nOOMKilled\nReadiness probe failed\nProgressDeadlineExceeded"});
  assert.equal(p.sources.length,3);
  assert.equal(p.evidence_policy.missing_signals.length,1);
  assert.ok(p.evidence_policy.attempts.length<=4);
  assert.ok(p.sources.reduce((n,s)=>n+s.text.length,0)<=6000);
  assert.equal(p.evidence_policy.usage.characters,p.sources.reduce((n,s)=>n+s.text.length,0));
});
test("context truncation preserves provenance and accounts for the actual boundary",()=>{
  const huge={...corpus,chunks:corpus.chunks.map(s=>({...s,text:s.text+" evidence".repeat(4000)}))};
  const p=prepare(huge,mixed);
  assert.equal(p.evidence_policy.usage.characters,6000);
  assert.ok(p.evidence_policy.omitted.length>0);
  assert.ok(p.sources.every(s=>s.text.length<=2500));
});
test("empty corpus terminates without inference despite recognized signals",async()=>{
  let calls=0;
  const result=await troubleshoot({...corpus,chunks:[]},mixed,async()=>{calls++;throw new Error("must not run");});
  assert.equal(calls,0);
  assert.equal(result.mode,"abstained");
  assert.equal(result.sources.length,0);
  assert.ok(result.evidence_policy.missing_signals.length>0);
  assert.ok(result.evidence_policy.attempts.length<=4);
});
test("retrieval decisions are deterministic for the same sanitized input and corpus",()=>{
  assert.deepEqual(prepare(corpus,mixed),prepare(corpus,mixed));
});
