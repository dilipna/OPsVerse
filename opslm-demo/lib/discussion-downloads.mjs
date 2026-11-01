import {redact} from "./troubleshoot.mjs";
export const MAX_TURNS=12;
const EXT={python:"py",py:"py",javascript:"js",js:"js",typescript:"ts",ts:"ts",tsx:"tsx",jsx:"jsx",bash:"sh",sh:"sh",shell:"sh",sql:"sql",json:"json",yaml:"yaml",yml:"yml",go:"go",golang:"go",rust:"rs",rs:"rs",java:"java",cpp:"cpp",c:"c",html:"html",css:"css",dockerfile:"Dockerfile",text:"txt",txt:"txt"};
export function answerText(result){return result.cloud_answer||result.library_answer||result.answer?.summary||result.sources.map(s=>s.text).join("\n\n")||"No accepted answer was available.";}
export function codeFiles(turns){
  const files=[];
  for(const [index,turn] of turns.slice(-MAX_TURNS).entries()){
    const text=answerText(turn.result);const re=/^(`{3,}|~{3,})([\w+-]*)[^\n]*\r?\n([\s\S]*?)^\1\s*$/gm;let m;
    while((m=re.exec(text))&&files.length<24){const language=m[2].toLowerCase(),extension=EXT[language]||"txt";files.push({name:`turn-${index+1}-snippet-${files.length+1}.${extension}`,language:language||"unlabeled",text:redact(m[3]).text,question:redact(turn.result.issue).text});}
  }
  return files;
}
export function downloadPlan(turns){
  const files=codeFiles(turns);
  const coding=files.length>0||turns.some(t=>t.result.routing?.category==="code");
  return {recommended:coding?"code":"pdf",files,reason:files.length?`${files.length} fenced code block(s) found in this discussion. Code is preserved, not executed or certified.`:coding?"This is a coding discussion, but no fenced code was returned. The bundle will contain notes only; no script is invented.":"A PDF keeps the discussion, source references and your notes together for reading or study."};
}
export function discussionMarkdown(turns){
  const parts=["# RYPE discussion notes","Unreviewed discussion export. Answers may be incomplete or incorrect. No code was executed. Sources and provider receipts are included for review."];
  for(const [i,t] of turns.slice(-MAX_TURNS).entries()){
    parts.push(`## ${i+1}. ${redact(t.result.issue).text}`,redact(answerText(t.result)).text);
    if(t.notes)parts.push("### Your notes",redact(t.notes).text);
    if(t.result.sources.length)parts.push("### Sources",...t.result.sources.map(s=>`${s.section} [${s.id}]\n${s.origin==="private"?"Private browser document (unverified; no public URL).":s.source}`));
    if(t.result.routing)parts.push("### Route receipt",JSON.stringify(t.result.routing,null,2));
  }
  return parts.join("\n\n")+"\n";
}
export async function codeBundle(turns){
  const {zipSync,strToU8}=await import("fflate"),files=codeFiles(turns);
  const entries={"README.md":strToU8("# RYPE code bundle\n\nUnreviewed snippets extracted from the accepted discussion answers, in turn order.\nNothing has been executed, dependency-checked or proven safe. Review before use.\nUnknown languages use .txt. Paths from model output are never used as filenames.\nRecognized credentials are redacted; redaction may miss sensitive values.\n\n"+files.map(f=>`- ${f.name} (${f.language}): ${f.question}`).join("\n")+(files.length?"":"\nNo fenced snippets were present; this bundle contains discussion notes only.")),"discussion.md":strToU8(discussionMarkdown(turns))};
  for(const file of files)entries[file.name]=strToU8(file.text);
  return zipSync(entries,{level:6});
}
export async function studyPdf(turns,fontBytes){
  const {PDFDocument,rgb}=await import("pdf-lib"),fontkit=(await import("@pdf-lib/fontkit")).default;
  const pdf=await PDFDocument.create();pdf.registerFontkit(fontkit);
  // Embed the static font intact: the upstream subsetter corrupts some Inter
  // outlines even when text extraction succeeds. Visual rendering is verified.
  const font=await pdf.embedFont(fontBytes,{subset:false}),supported=new Set(font.getCharacterSet());
  // Never silently drop unsupported glyphs: spell out their Unicode value.
  const printable=s=>Array.from(String(s)).map(c=>c==="\t"?"    ":c==="\r"?"":c==="\n"||supported.has(c.codePointAt(0))?c:`[U+${c.codePointAt(0).toString(16).toUpperCase()}]`).join("");
  let page,y;const width=595.28,height=841.89,margin=48,widths=new Map();
  const measure=(text,size)=>{const key=size+":"+text;if(!widths.has(key))widths.set(key,font.widthOfTextAtSize(text,size));return widths.get(key);};
  function fresh(){page=pdf.addPage([width,height]);y=height-65;page.drawText("RYPE / DISCUSSION NOTES",{x:margin,y:height-30,size:8,font,color:rgb(.24,.35,.42)});}
  function line(text,size=10){if(y<60)fresh();page.drawText(text,{x:margin,y,size,font,color:rgb(.1,.16,.22)});y-=size*1.55;}
  function paragraph(text,size=10){
    for(const raw of printable(text).split("\n")){
      let current="",used=0;const available=width-margin*2,space=measure(" ",size);
      for(const word of raw.split(/\s+/)){
        const wordWidth=measure(word,size);
        if(used+(current?space:0)+wordWidth>available&&current){line(current,size);current="";used=0;}
        if(wordWidth<=available){used+=(current?space:0)+wordWidth;current+=(current?" ":"")+word;}
        else for(const char of word){const w=measure(char,size);if(used+w>available){line(current,size);current="";used=0;}current+=char;used+=w;}
      }
      line(current,size);
    }y-=7;
  }
  fresh();paragraph("Your discussion, ready to revisit",21);
  paragraph("Unreviewed answers, source references and notes. No code executed. Unsupported font glyphs are written as [U+...]; use Markdown for original Unicode text.",9);
  for(const [index,t] of turns.slice(-MAX_TURNS).entries()){
    if(y<145)fresh();paragraph(`${index+1}. ${redact(t.result.issue).text}`,14);
    paragraph(redact(answerText(t.result)).text);
    if(t.notes){paragraph("Your notes",11);paragraph(redact(t.notes).text);}
    if(t.result.sources.length){paragraph("Sources",11);for(const s of t.result.sources)paragraph(`${s.section}\n${s.origin==="private"?"Private browser document - unverified":s.source}`,8);}
    if(t.result.routing){const r=t.result.routing;paragraph(`Route: ${r.kind}; model: ${r.model_used||"none"}; calls: ${r.model_calls}; reported inference cost: ${r.actual_cost_usd===null?"unknown":`$${r.actual_cost_usd}`}.`,8);paragraph("Savings shown in RYPE are hypothetical baseline estimates, not measured quality-matched reductions.",8);}
  }
  const pages=pdf.getPages();pages.forEach((p,i)=>p.drawText(`${i+1} / ${pages.length}`,{x:margin,y:30,size:8,font,color:rgb(.3,.4,.5)}));
  pdf.setTitle("RYPE discussion notes");pdf.setAuthor("RYPE");return pdf.save();
}
