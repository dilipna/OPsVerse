import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {semanticHash,changedPaths} from "./lock-evidence.mjs";

const web=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const repo=path.resolve(web,"..");
let gitCommit=null,dirty=null;
try{
  const top=execFileSync("git",["rev-parse","--show-toplevel"],{cwd:repo,encoding:"utf8",stdio:["ignore","pipe","ignore"]}).trim();
  if(path.resolve(top).toLowerCase()===repo.toLowerCase()){
    gitCommit=execFileSync("git",["rev-parse","HEAD"],{cwd:repo,encoding:"utf8"}).trim();
    // Hosting may generate untracked configuration. Report it separately;
    // source cleanliness means tracked source, never silently modified files.
    const status=execFileSync("git",["status","--porcelain","--untracked-files=no"],{cwd:repo,encoding:"utf8"}).trim();
    dirty=Boolean(status);
    if(dirty)console.log(JSON.stringify({build_changed_paths:status.split("\n")}));
  }
}catch{ /* Immutable source archives identify their commit through build metadata. */ }
const sourceCommit=process.env.OPSVERSE_RELEASE_COMMIT||gitCommit;
if(!/^[a-f0-9]{40}$/.test(sourceCommit||""))throw Error("A full release commit is required for this build");
if(gitCommit){
  const committedLock=execFileSync("git",["show",`${gitCommit}:opslm-demo/package-lock.json`],{cwd:repo,encoding:"utf8",maxBuffer:8*1024*1024});
  const installedLock=fs.readFileSync(path.join(web,"package-lock.json"),"utf8");
  const differences=changedPaths(JSON.parse(committedLock),JSON.parse(installedLock));
  console.log(JSON.stringify({lock_source_sha256:semanticHash(committedLock),lock_build_sha256:semanticHash(installedLock),lock_changed_paths:differences}));
  if(differences.length)throw Error("Build changed committed dependency lock semantics; release blocked");
}
const files=["lib/rype-routing.mjs","lib/rype-http.mjs","app/api/route/route.ts","lib/portable-brief.mjs","lib/troubleshoot.mjs","lib/troubleshoot-http.mjs","lib/investigation-evidence.mjs","lib/runbooks.mjs","lib/source-links.ts",
  "app/troubleshoot/page.tsx","app/troubleshoot/evidence-atlas.tsx","app/layout.tsx","app/runbooks/page.tsx","app/study/page.tsx","app/engineering/page.tsx",
  "app/globals.css","app/workspace.css","public/runbooks.json","public/study.json",
  "public/investigation-development.json","package-lock.json","package.json",
  "scripts/release-identity.mjs","scripts/lock-evidence.mjs","scripts/publish-research.mjs",
  "public/report-theme.css","public/dashboard.html","public/overturns.html",
  "public/fonts/SpaceGrotesk.woff2","public/fonts/SpaceGrotesk-OFL.txt","public/fonts/PlusJakartaSans.woff2","public/fonts/Inter.woff2","public/fonts/IBMPlexMono.woff2",
  "public/fonts/PlusJakartaSans-OFL.txt","public/fonts/Inter-OFL.txt","public/fonts/IBMPlexMono-OFL.txt"];
const hash=value=>crypto.createHash("sha256").update(value).digest("hex");
const sources=Object.fromEntries(files.sort().map(file=>[file,hash(/\.woff2$/.test(file)?fs.readFileSync(path.join(web,file)):fs.readFileSync(path.join(web,file),"utf8").replace(/\r\n/g,"\n"))]));
const data={schema:1,source_commit:sourceCommit,git_commit:gitCommit,dirty_source:dirty,
  created_at:new Date().toISOString(),source_files:sources,source_files_sha256:hash(JSON.stringify(sources)),
  scope:"Build identity and normalized source hashes. dirty_source covers tracked files; hosting-generated untracked files are excluded. Not model health, answer accuracy or a CI certification."};
fs.writeFileSync(path.join(web,"public/release.json"),JSON.stringify(data,null,2)+"\n");
console.log(JSON.stringify({source_commit:sourceCommit,dirty_source:dirty,source_files_sha256:data.source_files_sha256}));
