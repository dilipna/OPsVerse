import {test} from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {search} from "../lib/runbooks.mjs";
const corpus=JSON.parse(fs.readFileSync(new URL("../public/runbooks.json",import.meta.url)));
test("empty, stopword and unsupported queries have no passages",()=>{
  for(const q of ["","the a is","quasar marmalade"])assert.deepEqual(search(corpus,q),[]);
});
test("oversize query fails with a usable error",()=>assert.throws(()=>search(corpus,"a".repeat(501)),/500/));
test("source text is an exact corpus excerpt with pinned attribution",()=>{
  const hits=search(corpus,"readiness probe failure");
  assert.ok(hits.length);
  for(const h of hits){
    assert.equal(corpus.chunks.find(c=>c.id===h.id).text,h.text);
    assert.ok(h.source.includes(corpus.manifest.revision));
    assert.equal(new URL(h.canonical).hostname,"kubernetes.io");
  }
});
test("ranking is stable and the result limit is respected",()=>{
  assert.equal(search(corpus,"probe",2).length,2);
  assert.deepEqual(search(corpus,"probe",2),search(corpus,"probe",2));
});
test("removing source content changes actual retrieval",()=>{
  const broken={...corpus,chunks:corpus.chunks.map(c=>({...c,text:""}))};
  assert.deepEqual(search(broken,"readiness probe failure"),[]);
});
