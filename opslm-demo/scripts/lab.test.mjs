// The browser ports must give exactly the answers of the Python originals.
// Fixture: scripts/lab-fixtures.json, written by `python -m rype_agent.lab_fixtures`.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { checkKubectl, redactSecrets, sanitizeOutput, scanInjection } from "../lib/security.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtures = JSON.parse(fs.readFileSync(path.join(here, "lab-fixtures.json"), "utf8"));

test("injection scan matches Python on every fixture", () => {
  assert.ok(fixtures.scan.length > 300);
  for (const c of fixtures.scan) {
    const got = scanInjection(c.input, { normalize: c.normalize });
    assert.deepEqual(
      { score: got.score, matched: got.matched },
      { score: c.score, matched: c.matched },
      `${JSON.stringify(c.input)} normalize=${c.normalize}`,
    );
  }
});

test("secret redaction matches Python", () => {
  for (const c of fixtures.redact) {
    assert.deepEqual(redactSecrets(c.input), { text: c.text, findings: c.findings }, c.input);
  }
});

test("output guard matches Python", () => {
  for (const c of fixtures.guard) {
    assert.deepEqual(
      sanitizeOutput(c.input, fixtures.allowed_hosts),
      { text: c.text, findings: c.findings },
      c.input,
    );
  }
});

test("agent command policy matches Python, reasons included", () => {
  for (const c of fixtures.policy) {
    assert.deepEqual(checkKubectl(c.input), { allowed: c.allowed, reason: c.reason }, c.input);
  }
});
