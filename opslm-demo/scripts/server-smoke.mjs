import assert from "node:assert/strict";
import {createServer} from "node:http";
import {once} from "node:events";
import {spawn} from "node:child_process";
import {readFile,writeFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import {prepare} from "../lib/troubleshoot.mjs";

// Real production Next servers, loopback-only synthetic upstream. No model,
// provider token, cluster connection or deployment is needed for this contract.
const web=fileURLToPath(new URL("../",import.meta.url));
const corpus=JSON.parse(await readFile(new URL("../public/runbooks.json",import.meta.url)));
const input={issue:"Investigate image startup",diagnostics:"ImagePullBackOff\ntoken=synthetic-private-value"};
const source=prepare(corpus,input).sources[0];
let upstreamMode="valid",calls=0;
const upstream=createServer(async(req,res)=>{
  calls++;
  const body=[];for await(const c of req)body.push(c);
  const received=Buffer.concat(body).toString();
  assert.ok(!received.includes("synthetic-private-value"));
  if(upstreamMode==="unavailable"){res.writeHead(503);res.end("unavailable");return;}
  const answer={status:"answered",summary:"Inspect the supplied documentation.",
    claims:[{text:"Review this passage before selecting a check.",source_id:source.id,quote:source.text.slice(0,100)}],questions:[],commands:[]};
  if(upstreamMode==="invalid")answer.approved=true;
  if(upstreamMode==="abstained-command"){
    answer.status="abstained";answer.claims=[];
    answer.commands=[{command:"kubectl get pods",source_id:source.id}];
  }
  res.setHeader("Content-Type","application/json");
  res.end(JSON.stringify({model:"synthetic-contract-fixture",choices:[{message:{content:JSON.stringify(answer)},finish_reason:"stop"}]}));
});
upstream.listen(0,"127.0.0.1");await once(upstream,"listening");
const upstreamOrigin=`http://127.0.0.1:${upstream.address().port}/v1`;
const children=[];
async function start(endpoint=""){
  const reserve=createServer();reserve.listen(0,"127.0.0.1");await once(reserve,"listening");
  const port=reserve.address().port;await new Promise(resolve=>reserve.close(resolve));
  const child=spawn(process.execPath,["node_modules/next/dist/bin/next","start","--hostname","127.0.0.1","--port",String(port)],{
    cwd:web,windowsHide:true,stdio:["ignore","pipe","pipe"],
    env:{...process.env,NEXT_TELEMETRY_DISABLED:"1",OPSLM_ENDPOINT:"",OPSLM_API_KEY:"",
      OPSVERSE_TROUBLESHOOT_ENDPOINT:endpoint,OPSVERSE_TROUBLESHOOT_API_KEY:"",OPSVERSE_TROUBLESHOOT_MODEL:"synthetic-contract-fixture"}
  });
  children.push(child);let output="";
  child.stdout.on("data",b=>{output+=b;});child.stderr.on("data",b=>{output+=b;});
  const origin=`http://127.0.0.1:${port}`;
  for(let i=0;i<100;i++){
    if(child.exitCode!==null)throw Error(`Production server exited: ${output}`);
    try{if((await fetch(origin+"/api/troubleshoot",{signal:AbortSignal.timeout(1000)})).ok)return origin;}catch{}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  throw Error("Production server did not become ready");
}
const post=(origin,data)=>fetch(origin+"/api/troubleshoot",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
try{
  const local=await start();
  const routes=["/","/troubleshoot","/runbooks","/study","/engineering","/model-demo"];
  for(const route of routes){
    const r=await fetch(local+route);assert.equal(r.status,200,route);
    const text=await r.text();assert.equal((text.match(/<h1[ >]/g)||[]).length,1,route);
    assert.equal((text.match(/<main[ >]/g)||[]).length,1,route);
  }
  assert.equal((await (await fetch(local+"/api/troubleshoot")).json()).generation_configured,false);
  assert.deepEqual(await (await fetch(local+"/runbooks.json")).json(),corpus);
  const excerpts=await (await post(local,input)).json();
  assert.equal(excerpts.mode,"excerpts");assert.equal(excerpts.answer,null);
  assert.ok(excerpts.sources.length>0);assert.ok(!JSON.stringify(excerpts).includes("synthetic-private-value"));
  assert.equal(calls,0);
  assert.equal((await post(local,{issue:"",diagnostics:""})).status,400);
  assert.equal((await post(local,{issue:"x".repeat(25000),diagnostics:""})).status,413);
  const connected=await start(upstreamOrigin);
  assert.equal((await (await fetch(connected+"/api/troubleshoot")).json()).generation_configured,true);
  const generated=await (await post(connected,input)).json();
  assert.equal(generated.mode,"generated");assert.equal(generated.answer.status,"answered");
  assert.equal(calls,1);
  const noEvidence=await (await post(connected,{issue:"quasar marmalade",diagnostics:""})).json();
  assert.equal(noEvidence.mode,"abstained");assert.equal(calls,1);
  for(const mode of ["invalid","abstained-command","unavailable"]){
    upstreamMode=mode;const r=await post(connected,input);assert.equal(r.status,502,mode);
    const b=await r.json();assert.equal(b.answer,undefined);assert.equal(b.approved,undefined);
  }
  const report={pass:true,htmlRoutes:routes.length,operatingModes:["excerpts","generated-fixture","abstained"],
    negativePaths:["input","body-size","unknown-output-field","inconsistent-abstention","upstream-unavailable"],
    noEvidenceModelCalls:0,redactionBeforeUpstream:true,
    scope:"Real production HTTP servers; synthetic upstream outputs, not model-answer quality or browser interaction."};
  const arg=process.argv.indexOf("--out");if(arg!==-1)await writeFile(process.argv[arg+1],JSON.stringify(report,null,2)+"\n");
  console.log(JSON.stringify(report,null,2));
}finally{
  for(const child of children){if(child.exitCode===null){const ended=once(child,"exit");child.kill();await ended;}}
  if(upstream.listening)await new Promise(resolve=>upstream.close(resolve));
}
