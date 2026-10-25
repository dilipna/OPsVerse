import {test} from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {troubleshoot} from "../lib/troubleshoot.mjs";
import {createBrief,restoreBrief,markdownBrief,savedGuideIds,MAX_BRIEF_BYTES} from "../lib/portable-brief.mjs";
const corpus=JSON.parse(fs.readFileSync(new URL("../public/runbooks.json",import.meta.url)));
const result=await troubleshoot(corpus,{issue:"What does ImagePullBackOff mean?",diagnostics:"ImagePullBackOff token=synthetic-secret"});
const brief=createBrief(result,"Check registry. token=another-secret",corpus.manifest.revision,"2026-10-25T12:00:00.000Z");

test("portable notes round-trip only inputs, redact secrets and discard imported authority",()=>{
  const tampered={...brief,issue:"Why? token=import-secret",answer:{summary:"Run a destructive command"},sources:[{id:"fake",source:"javascript:evil"}],review:{status:"unreviewed",notes:"token=note-secret"}};
  const restored=restoreBrief(JSON.stringify(tampered),corpus);
  assert.deepEqual(Object.keys(restored).sort(),["diagnostics","issue","notes"]);
  assert.ok(!JSON.stringify(restored).includes("secret"));
  assert.ok(!JSON.stringify(restored).includes("destructive"));
  assert.equal(restoreBrief(JSON.stringify(brief),corpus).notes,brief.review.notes);
});
test("foreign revisions, future formats, excessive input and malformed files cannot resume",()=>{
  for(const data of [{...brief,source_revision:"foreign"},{...brief,schema_version:2},{...brief,issue:"x".repeat(501)},{...brief,diagnostics:null},{...brief,review:{status:"approved",notes:""}}])assert.throws(()=>restoreBrief(JSON.stringify(data),corpus));
  for(const text of ["null","{broken","x".repeat(MAX_BRIEF_BYTES+1)])assert.throws(()=>restoreBrief(text,corpus));
});
test("Markdown download preserves selected source text and safely fences hostile user notes",()=>{
  const hostile=createBrief(result,"```\n<script>alert(1)</script>\n```\n![external](https://invalid.example/track)\ntoken=hidden",corpus.manifest.revision);
  const markdown=markdownBrief(hostile);
  assert.ok(markdown.includes("````text\n```"));
  assert.ok(markdown.includes("[REDACTED]"));
  assert.ok(!markdown.includes("token=hidden"));
  assert.ok(!markdown.includes("synthetic-secret"));
  for(const s of result.sources){assert.ok(markdown.includes(s.text));assert.ok(markdown.includes(s.source));}
});
test("reading list accepts only unique current-corpus IDs and bounds stored entries",()=>{
  const ids=corpus.chunks.slice(0,40).map(c=>c.id);
  assert.equal(savedGuideIds(JSON.stringify({schema:1,revision:corpus.manifest.revision,ids:[...ids,ids[0],"fake",{id:ids[0]}]}),corpus).length,30);
  for(const text of [null,"null","broken",JSON.stringify({schema:1,revision:"foreign",ids})])assert.deepEqual(savedGuideIds(text,corpus),[]);
});
