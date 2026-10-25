import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const web=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
export const researchSources={"dashboard.html":"benchmarks/dashboard.html","overturns.html":"docs/overturns.html"};

export function publishResearch(html){
  html=html.replace(/\r\n/g,"\n");
  if(html.includes('data-report-theme="studio"'))throw Error("Publish from the canonical offline source, not an already themed copy");
  if(!html.includes('<html lang="en">')||!html.includes('</head>')||!html.includes('<body>')||!html.includes('</body>'))throw Error("Unexpected research document structure");
  const hasMain=/<main[\s>]/i.test(html);
  const nav='<nav class="research-nav" aria-label="Research navigation"><a class="research-brand" href="/">↗ OPSVERSE</a><div><a href="/">Workspace</a><a href="/runbooks">Runbooks</a><a href="/study">Evaluation</a><a href="/engineering">Engineering ↗</a></div><span>RESEARCH ARCHIVE</span></nav>';
  const notice='<aside class="research-notice" aria-label="Historical research scope"><strong>Historical research snapshot.</strong> Original measurements and conclusions retain their recorded scope. The current workspace uses live evidence retrieval; its separate model console uses labeled samples. <a href="https://github.com/dilipna/OPsVerse/blob/improve/flagship-investigation/docs/claims.md">Read current corrections and limitations ↗</a></aside>';
  return html.replace('<html lang="en">','<html lang="en" data-report-theme="studio">')
    .replace('</head>','<link rel="stylesheet" href="/report-theme.css">\n</head>')
    .replace(/<body>/i,'<body>'+nav+notice+(hasMain?'':'<main class="research-content">'))
    .replace('</body>',(hasMain?'':'</main>')+'</body>')
    .replaceAll('https://github.com/dilipna/OPsVerse/blob/main/','https://github.com/dilipna/OPsVerse/blob/improve/flagship-investigation/');
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  for(const [target,source] of Object.entries(researchSources)){
    const output=publishResearch(fs.readFileSync(path.resolve(web,"..",source),"utf8"));
    const destination=path.join(web,"public",target);
    if(!fs.existsSync(destination)||fs.readFileSync(destination,"utf8").replace(/\r\n/g,"\n")!==output)fs.writeFileSync(destination,output);
  }
}
