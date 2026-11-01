import {test} from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {publishResearch,researchSources} from "./publish-research.mjs";

for(const [name,source] of Object.entries(researchSources))test(`published ${name} preserves research scripts and claim values`,()=>{
  const original=fs.readFileSync(new URL("../../"+source,import.meta.url),"utf8").replace(/\r\n/g,"\n");
  const output=publishResearch(original);
  const bodies=html=>[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(match=>match[1]);
  assert.deepEqual(bodies(output),bodies(original),"measured chart data and rendering scripts must not be rewritten");
  const numbers=html=>[...html.matchAll(/<p class="(?:belief|verdict|detail|changed)">([\s\S]*?)<\/p>/g)].map(match=>match[1]);
  assert.deepEqual(numbers(output),numbers(original),"published historical claim text must stay intact");
  assert.equal((output.match(/<main[\s>]/g)||[]).length,1);
  assert.equal((output.match(/<\/main>/g)||[]).length,1);
  assert.ok(output.includes('aria-label="Historical research scope"'));
  assert.ok(output.includes('href="/report-theme.css"'));
  assert.throws(()=>publishResearch(output),/canonical offline source/);
});
