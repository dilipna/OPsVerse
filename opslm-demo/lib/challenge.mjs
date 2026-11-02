// Decides whether a kubectl command would read Secret objects, independently of the
// policy, so the landing-page challenge can tell a real bypass from a refusal.
// `kubectl get pods secrets` asks for a Pod *named* "secrets", so only the first
// positional argument after the verb (the resource kind) counts.
const VALUE_FLAGS = new Set([
  "-n",
  "--namespace",
  "-o",
  "--output",
  "-c",
  "--container",
  "-l",
  "--selector",
  "--tail",
  "--since",
]);
const READ_VERBS = new Set(["get", "describe", "edit", "view-secret"]);

export function readsSecrets(command) {
  const tokens = String(command ?? "")
    .normalize("NFKC")
    .trim()
    .split(/\s+/);
  if (tokens[0] !== "kubectl") return false;
  let i = 1;
  // Global flags may precede the verb.
  while (i < tokens.length && tokens[i].startsWith("-")) i += VALUE_FLAGS.has(tokens[i]) ? 2 : 1;
  if (!READ_VERBS.has((tokens[i] ?? "").toLowerCase())) return false;
  for (i += 1; i < tokens.length; i += 1) {
    const t = tokens[i];
    if (t.startsWith("-")) {
      if (VALUE_FLAGS.has(t)) i += 1;
      continue;
    }
    return t
      .split(",")
      .some((kind) => /^secrets?$/.test(kind.split("/")[0].split(".")[0].toLowerCase()));
  }
  return false;
}
