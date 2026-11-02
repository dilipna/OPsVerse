import assert from "node:assert/strict";
import test from "node:test";
import { readsSecrets } from "../lib/challenge.mjs";
import { checkKubectl } from "../lib/security.mjs";

const SECRET_READS = [
  "kubectl get secrets",
  "kubectl get secret db -n shop",
  "kubectl get Secret/db",
  "kubectl get secrets.v1.core",
  "kubectl describe secret db",
  "kubectl -n shop get secrets",
  "kubectl get -n shop secrets",
  "kubectl get --namespace=shop secrets",
  "kubectl get pods,secrets",
  "kubectl get ＳＥＣＲＥＴＳ",
];
const NOT_SECRET_READS = [
  "kubectl get pods secrets",
  "kubectl logs secrets",
  "kubectl get pods -n secrets",
  "kubectl get configmaps",
  "kubectl auth can-i get secrets",
  "helm get secrets",
  "",
];

test("recognizes requests for Secret objects", () => {
  for (const c of SECRET_READS) assert.equal(readsSecrets(c), true, c);
});

test("does not mistake a Pod or namespace named secrets for a Secret read", () => {
  for (const c of NOT_SECRET_READS) assert.equal(readsSecrets(c), false, c);
});

test("the agent policy refuses every Secret read in the challenge set", () => {
  for (const c of SECRET_READS) assert.equal(checkKubectl(c).allowed, false, c);
});
