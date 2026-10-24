import crypto from "node:crypto";

export function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  }
  return value;
}

export const semanticHash = text => crypto.createHash("sha256")
  .update(JSON.stringify(canonical(JSON.parse(text)))).digest("hex");

export function changedPaths(left, right, prefix = "$") {
  if (JSON.stringify(canonical(left)) === JSON.stringify(canonical(right))) return [];
  if (left === null || right === null || typeof left !== "object" || typeof right !== "object"
    || Array.isArray(left) || Array.isArray(right)) return [prefix];
  return [...new Set([...Object.keys(left), ...Object.keys(right)])].sort().flatMap(key => {
    const next = `${prefix}/${key.replaceAll("~", "~0").replaceAll("/", "~1")}`;
    return key in left && key in right ? changedPaths(left[key], right[key], next) : [next];
  });
}
