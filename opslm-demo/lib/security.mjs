// Browser ports of RYPE's Python security controls, for the /lab page.
//
//   scanInjection   <- libs/security/src/rype_security/injection.py
//   redactSecrets   <- libs/security/src/rype_security/redact.py
//   sanitizeOutput  <- libs/security/src/rype_security/output_guard.py
//   checkKubectl    <- libs/agent/src/rype_agent/policy.py
//
// Parity is enforced, not hoped for: `python -m rype_security.lab_fixtures`
// runs the Python originals over a fixed set of inputs and writes
// public/lab-fixtures.json; scripts/lab.test.mjs requires these functions to
// return exactly the same results, and CI fails if the fixture is stale.

// ------------------------------------------------------------ injection scan

const SIGNALS = [
  [
    "override_instructions",
    2.0,
    /\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|your)\b[^.\n]{0,40}\b(instruction|prompt|rule|guideline|direction|context)s?\b/i,
  ],
  [
    "persona_hijack",
    1.5,
    /\b(you are now|act as|pretend to be|roleplay as|from now on you)\b[^.\n]{0,60}\b(unrestricted|jailbroken|DAN|no (?:rules|filter|restriction)s?|different (?:AI|assistant|persona))\b/i,
  ],
  [
    "prompt_exfiltration",
    2.0,
    /\b(reveal|show|print|repeat|output|tell me)\b[^.\n]{0,40}\b(system prompt|your (?:instructions|prompt|rules)|initial prompt|hidden (?:instructions|prompt))\b/i,
  ],
  [
    "assistant_directive",
    1.5,
    /^\s*(?:SYSTEM|ASSISTANT|AI|IMPORTANT INSTRUCTION)S?\s*[:>\]][^\n]{0,120}\b(you must|always|never|do not tell|without telling)\b/im,
  ],
  [
    "context_exfiltration",
    1.5,
    /\b(send|post|forward|exfiltrate|transmit)\b[^.\n]{0,50}\b(conversation|chat history|context|these documents|user data)\b[^.\n]{0,50}\bhttps?:\/\//i,
  ],
  [
    "refusal_suppression",
    1.0,
    /\b(do not|don't|never)\b[^.\n]{0,30}\b(refuse|decline|say no|mention (?:policy|rules|guidelines))\b/i,
  ],
  [
    "conceal_from_user",
    1.5,
    /\b(do not|don't|without|never)\b[^.\n]{0,20}\b(tell|telling|inform|informing|notify|alert|mention to)\b[^.\n]{0,20}\b(the )?(user|anyone|them|him|her)\b/i,
  ],
];
export const SUSPICION_THRESHOLD = 1.5;
const OBFUSCATION_WEIGHT = 0.5;

// Same table as injection.py::_CONFUSABLES (Cyrillic and Greek look-alikes).
const CONFUSABLE_FROM =
  "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u0458\u0455\u0501\u04cf" +
  "\u04bb\u051b\u051d\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421" +
  "\u0422\u0425\u0406\u0408\u0405\u03bf\u03b1\u03b5\u03b9\u03ba\u03bd\u03c1" +
  "\u03c4\u03c5\u03c7\u039f\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c" +
  "\u039d\u03a1\u03a4\u03a5\u03a7";
const CONFUSABLE_TO = "aeopcyxijsdlhqwABEKMHOPCTXIJSoaeikvptuxOABEZHIKMNPTYX";
const CONFUSABLES = new Map([...CONFUSABLE_FROM].map((c, i) => [c, CONFUSABLE_TO[i]]));

const FORMAT_CHAR = /\p{Cf}/u;
const stripInvisible = (text) => {
  const kept = [...text].filter((ch) => !FORMAT_CHAR.test(ch));
  return [kept.join(""), [...text].length - kept.length];
};
const mixedScriptWords = (text) =>
  (text.match(/\S+/gu) || []).filter(
    (w) => /[A-Za-z]/.test(w) && /[\u0370-\u03ff\u0400-\u04ff\u0500-\u052f]/u.test(w),
  ).length;

export function normalizeForScan(text) {
  const [stripped] = stripInvisible(text.normalize("NFKC"));
  return [...stripped].map((c) => CONFUSABLES.get(c) ?? c).join("");
}

export function scanInjection(text, { normalize = true } = {}) {
  let score = 0;
  const matched = [];
  let views = [text];
  if (normalize) {
    const normalized = normalizeForScan(text);
    views = [normalized, normalized.replace(/\s+/gu, " ")];
  }
  for (const [name, weight, pattern] of SIGNALS) {
    if (views.some((view) => pattern.test(view))) {
      score += weight;
      matched.push(name);
    }
  }
  if (normalize) {
    const [, invisible] = stripInvisible(text);
    if (invisible || mixedScriptWords(text.normalize("NFKC"))) {
      score += OBFUSCATION_WEIGHT;
      matched.push("obfuscation");
    }
  }
  return { score, matched, suspicious: score >= SUSPICION_THRESHOLD };
}

// ------------------------------------------------------------ secret redaction

const SECRET_PATTERNS = [
  ["aws_access_key_id", /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g],
  ["github_token", /\bgh[pousr]_[A-Za-z0-9]{36,255}\b/g],
  ["github_pat_fine", /\bgithub_pat_[A-Za-z0-9_]{60,255}\b/g],
  ["slack_token", /\bxox[baprs]-[A-Za-z0-9-]{10,250}\b/g],
  ["google_api_key", /\bAIza[0-9A-Za-z_-]{35}\b/g],
  ["anthropic_key", /\bsk-ant-[A-Za-z0-9_-]{20,200}\b/g],
  ["openai_key", /\bsk-(?!ant-)[A-Za-z0-9_-]{20,100}\b/g],
  ["stripe_key", /\b(?:sk|rk)_live_[A-Za-z0-9]{20,99}\b/g],
  ["huggingface_token", /\bhf_[A-Za-z0-9]{30,60}\b/g],
  ["aws_secret_access_key", /\baws_secret_access_key\b["']?\s*[:=]\s*["']?[A-Za-z0-9/+=]{40}\b/gi],
  ["gcp_private_key_id", /"private_key_id"\s*:\s*"[0-9a-f]{40}"/g],
  ["bearer_header", /\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/-]{20,}=*/gi],
  [
    "private_key_block",
    /-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]{0,4000}?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----/g,
  ],
  ["jwt", /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g],
  [
    "assigned_secret",
    /\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*['"]?(?!\{\{)[A-Za-z0-9_/+.-]{20,}['"]?/gi,
  ],
];
const URL_PASSWORD = /\b([a-z][a-z0-9+.-]{1,20}:\/\/[^\s:/@]{1,64}:)([^\s@/]{1,128})(@)/g;
const PLACEHOLDERS = new Set([
  "password",
  "pass",
  "passwd",
  "pwd",
  "secret",
  "changeme",
  "example",
  "xxx",
  "xxxx",
  "***",
]);
const isPlaceholder = (value) => {
  const v = value.toLowerCase();
  return (
    PLACEHOLDERS.has(v) ||
    ["$", "<", "{{", "%"].some((p) => v.startsWith(p)) ||
    v === v[0].repeat(v.length)
  );
};

export function redactSecrets(text) {
  const findings = {};
  for (const [name, pattern] of SECRET_PATTERNS) {
    let count = 0;
    text = text.replace(pattern, () => {
      count++;
      return `[REDACTED:${name}]`;
    });
    if (count) findings[name] = count;
  }
  let urlPasswords = 0;
  text = text.replace(URL_PASSWORD, (whole, head, password, at) => {
    if (isPlaceholder(password)) return whole;
    urlPasswords++;
    return `${head}[REDACTED:url_password]${at}`;
  });
  if (urlPasswords) findings.url_password = urlPasswords;
  return { text, findings };
}

// ------------------------------------------------------------ output guard

export const DEFAULT_ALLOWED_HOSTS = [
  "kubernetes.io",
  "docs.docker.com",
  "developer.hashicorp.com",
  "mlflow.org",
  "github.com",
  "prometheus.io",
  "helm.sh",
];
const TITLE = String.raw`(?:\s+"[^"\n]*")?`;
const MD_IMAGE = new RegExp(
  String.raw`!\[([^\]\n]*)\]\(\s*<?([^)\s>]*)>?` + TITLE + String.raw`\s*\)`,
  "g",
);
const REF_IMAGE = /!\[([^\]\n]*)\]\[[^\]\n]*\]/g;
const HTML_IMAGE = /<img\b[^>]*>/gi;
const MD_LINK = new RegExp(
  String.raw`(?<!!)\[([^\]\n]+)\]\(\s*<?([^)\s>]*)>?` + TITLE + String.raw`\s*\)`,
  "g",
);
const AUTOLINK = /<([a-zA-Z][a-zA-Z0-9+.-]*:[^>\s]+)>/g;
const REF_DEFINITION = /^( {0,3}\[[^\]\n]+\]:[ \t]*)(\S+)(.*)$/gm;

function urlAllowed(url, allowed) {
  // Mirrors urllib.parse.urlsplit: only http(s) with an allowlisted host passes.
  const match = /^([a-zA-Z][a-zA-Z0-9+.-]*):\/\/([^/?#]*)/.exec(url);
  if (!match || !["http", "https"].includes(match[1].toLowerCase())) return false;
  let host = match[2].split("@").pop();
  host = (
    host.startsWith("[") ? host.slice(0, host.indexOf("]") + 1) : host.split(":")[0]
  ).toLowerCase();
  return allowed.some((a) => host === a || host.endsWith("." + a));
}

export function sanitizeOutput(text, allowedHosts = DEFAULT_ALLOWED_HOSTS) {
  const allowed = allowedHosts.map((h) => h.toLowerCase().replace(/^\.+/, ""));
  const found = {};
  const bump = (k) => (found[k] = (found[k] || 0) + 1);
  text = text.replace(MD_IMAGE, (_, alt) => {
    bump("image_removed");
    return `[image removed${alt.trim() ? ": " + alt.trim() : ""}]`;
  });
  text = text.replace(REF_IMAGE, (_, alt) => {
    bump("image_removed");
    return `[image removed${alt.trim() ? ": " + alt.trim() : ""}]`;
  });
  text = text.replace(HTML_IMAGE, () => {
    bump("image_removed");
    return "[image removed]";
  });
  text = text.replace(MD_LINK, (whole, label, url) => {
    if (url.startsWith("#") || urlAllowed(url, allowed)) return whole;
    bump("link_removed");
    return `${label} [link removed]`;
  });
  text = text.replace(AUTOLINK, (whole, url) => {
    if (urlAllowed(url, allowed)) return whole;
    bump("link_removed");
    return "[link removed]";
  });
  text = text.replace(REF_DEFINITION, (whole, head, url) => {
    if (urlAllowed(url.replace(/^<+|>+$/g, ""), allowed)) return whole;
    bump("link_removed");
    return `${head}#link-removed`;
  });
  const redaction = redactSecrets(text);
  for (const [kind, n] of Object.entries(redaction.findings)) {
    found[`secret_redacted:${kind}`] = (found[`secret_redacted:${kind}`] || 0) + n;
  }
  return { text: redaction.text, findings: found };
}

// ------------------------------------------------------------ agent command policy

const VERBS = ["get", "describe", "logs", "rollout"];
const READ_KINDS = new Set(
  (
    "pod pods po deployment deployments deploy service services svc endpoint endpoints ep " +
    "event events ev replicaset replicasets rs node nodes no configmap configmaps cm " +
    "resourcequota resourcequotas quota limitrange limitranges limits ingress ingresses ing " +
    "namespace namespaces ns"
  ).split(" "),
);
const deny = (reason) => ({ allowed: false, reason });

export function checkKubectl(command) {
  if (typeof command !== "string") return deny("command must be a string");
  if (command.length > 240) return deny("command too long");
  if (!/^[a-zA-Z0-9_./=:\s-]*$/.test(command))
    return deny("characters outside the allowed set (no shell syntax)");
  const tokens = command.split(/\s+/).filter(Boolean);
  if (!tokens.length || tokens[0] !== "kubectl") return deny("only kubectl is available");
  const argv = tokens.slice(1);
  if (!argv.length || !VERBS.includes(argv[0]))
    return deny(`verb not allowed: ${argv.length ? argv[0] : "(none)"}`);
  const verb = argv[0];
  let rest = argv.slice(1);
  if (verb === "rollout") {
    if (!rest.length || !["status", "history"].includes(rest[0]))
      return deny("only rollout status/history are allowed");
    rest = rest.slice(1);
  }
  if (!rest.length) return deny("resource required");
  const [resource, ...options] = rest;
  if (resource.startsWith("-") || resource.includes("..")) return deny("invalid resource");
  if (verb === "logs" && !/^(?:pods?\/)?[a-z0-9][a-z0-9.-]*$/.test(resource))
    return deny("invalid logs target");
  if (verb === "rollout" && !/^(deployments?|deploy)(\/[a-z0-9][a-z0-9.-]*)?$/.test(resource))
    return deny("rollout works on deployments only");
  if (verb !== "logs" && verb !== "rollout") {
    const m = /^([a-z]+)(\/[a-z0-9][a-z0-9.-]*)?$/.exec(resource);
    if (!m || !READ_KINDS.has(m[1]))
      return deny(`resource kind not allowed: ${resource.split("/")[0]}`);
  }
  let names = 0;
  for (let i = 0; i < options.length; i++) {
    const token = options[i];
    if (token === "-n" || token === "--namespace") {
      i++;
      if (i >= options.length || !/^[a-z0-9][a-z0-9-]*$/.test(options[i]))
        return deny("invalid namespace");
    } else if (token === "-o" || token === "--output") {
      i++;
      if (i >= options.length || !["wide", "json", "yaml"].includes(options[i]))
        return deny("output format not allowed");
    } else if (
      /^--namespace=[a-z0-9][a-z0-9-]*$/.test(token) ||
      (verb === "logs" && (token === "--previous" || /^--tail=\d{1,4}$/.test(token)))
    ) {
      continue;
    } else if (!token.startsWith("-") && /^[a-z0-9][a-z0-9.-]*$/.test(token) && names === 0) {
      names++;
    } else {
      return deny(`option not allowed: ${token}`);
    }
  }
  return { allowed: true, reason: "allowed" };
}
