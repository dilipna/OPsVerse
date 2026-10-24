import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";

const web=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const repo=path.resolve(web,"..");
let gitCommit=null,dirty=null;
try{
  const top=execFileSync("git",["rev-parse","--show-toplevel"],{cwd:repo,encoding:"utf8",stdio:["ignore","pipe","ignore"]}).trim();
  if(path.resolve(top).toLowerCase()===repo.toLowerCase()){
    gitCommit=execFileSync("git",["rev-parse","HEAD"],{cwd:repo,encoding:"utf8"}).trim();
    dirty=Boolean(execFileSync("git",["status","--porcelain"],{cwd:repo,encoding:"utf8"}).trim());
  }
}catch{ /* Immutable source archives identify their commit through build metadata. */ }
const sourceCommit=process.env.OPSVERSE_RELEASE_COMMIT||gitCommit;
if(!/^[a-f0-9]{40}$/.test(sourceCommit||""))throw Error("A full release commit is required for this build");
const files=["lib/troubleshoot.mjs","lib/troubleshoot-http.mjs","lib/investigation-evidence.mjs","lib/runbooks.mjs",
  "app/troubleshoot/page.tsx","app/runbooks/page.tsx","app/study/page.tsx","app/engineering/page.tsx",
  "app/globals.css","app/workspace.css","public/runbooks.json","public/study.json",
  "public/investigation-development.json","package-lock.json"];
const hash=value=>crypto.createHash("sha256").update(value).digest("hex");
const sources=Object.fromEntries(files.sort().map(file=>[file,hash(fs.readFileSync(path.join(web,file),"utf8").replace(/\r\n/g,"\n"))]));
const data={schema:1,source_commit:sourceCommit,git_commit:gitCommit,dirty_source:dirty,
  created_at:new Date().toISOString(),source_files:sources,source_files_sha256:hash(JSON.stringify(sources)),
  scope:"Build identity and normalized source hashes; not model health, answer accuracy or a CI certification."};
fs.writeFileSync(path.join(web,"public/release.json"),JSON.stringify(data,null,2)+"\n");
console.log(JSON.stringify({source_commit:sourceCommit,dirty_source:dirty,source_files_sha256:data.source_files_sha256}));
