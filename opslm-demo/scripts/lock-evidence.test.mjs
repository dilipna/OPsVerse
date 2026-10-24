import {test} from "node:test";
import assert from "node:assert/strict";
import {semanticHash, changedPaths} from "./lock-evidence.mjs";

test("lock proof accepts JSON formatting and object key ordering only", () => {
  assert.equal(semanticHash('{"a":1,"b":{"c":2,"d":3}}'), semanticHash('{ "b": {"d":3,"c":2}, "a":1 }'));
});

for (const field of ["version", "integrity", "resolved", "license", "hasInstallScript"]) {
  test(`lock proof detects changed ${field}`, () => {
    const source = {packages: {"node_modules/example": {[field]: "original"}}};
    const build = structuredClone(source); build.packages["node_modules/example"][field] = "changed";
    assert.notEqual(semanticHash(JSON.stringify(source)), semanticHash(JSON.stringify(build)));
    assert.deepEqual(changedPaths(source, build), [`$/packages/node_modules~1example/${field}`]);
  });
}

test("lock proof detects added dependencies and root declarations", () => {
  assert.deepEqual(changedPaths({packages:{}}, {packages:{example:{version:"1"}}}), ["$/packages/example"]);
  assert.deepEqual(changedPaths({dependencies:{a:"1"}}, {dependencies:{a:"2"}}), ["$/dependencies/a"]);
});
