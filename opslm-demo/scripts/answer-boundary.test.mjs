import {test} from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {prepare, validateAnswer} from "../lib/troubleshoot.mjs";
import {handleRequest} from "../lib/troubleshoot-http.mjs";

// Development counterexamples frozen before the validator repair. These are
// contract tests, not held-out model-quality or prompt-injection benchmarks.
const corpus=JSON.parse(fs.readFileSync(new URL("../public/runbooks.json",import.meta.url)));
const input={issue:"Investigate an unavailable image",diagnostics:"Reason: ImagePullBackOff"};
const sources=prepare(corpus,input).sources;
const answer={status:"answered",summary:"Inspect the original documentation.",claims:[{
  text:"Review this passage before selecting a diagnostic check.",source_id:sources[0].id,
  quote:sources[0].text.slice(0,100)
}],questions:[],commands:[]};
const command={command:"kubectl get pods",source_id:sources[0].id};
const abstention={status:"abstained",summary:"The evidence does not support an answer.",claims:[],questions:[],commands:[]};

for(const [name,mutate] of [
  ["abstention carrying a claim",()=>({...abstention,claims:answer.claims})],
  ["abstention carrying a command",()=>({...abstention,commands:[command]})],
  ["unknown root approval",()=>({...answer,approved:true})],
  ["unknown claim approval",()=>({...answer,claims:[{...answer.claims[0],approved:true}]})],
  ["unknown command execution flag",()=>({...answer,commands:[{...command,execute:true}]})],
]){
  test(name+" cannot cross the shared validator",()=>{
    assert.throws(()=>validateAnswer(JSON.stringify(mutate()),sources));
  });
  test(name+" fails closed through the actual HTTP handler",async()=>{
    let calls=0;
    const response=await handleRequest(new Request("http://localhost/api/troubleshoot",{
      method:"POST",body:JSON.stringify(input)
    }),{corpus,endpoint:"http://localhost/v1",fetcher:async()=>{
      calls++;
      return Response.json({choices:[{message:{content:JSON.stringify(mutate())},finish_reason:"stop"}]});
    }});
    assert.equal(calls,1);
    assert.equal(response.status,502);
    const body=await response.json();
    assert.equal(body.answer,undefined);
    assert.equal(body.approved,undefined);
  });
}

test("a genuine abstention and a cited clarification remain valid",()=>{
  assert.deepEqual(validateAnswer(JSON.stringify(abstention),sources),abstention);
  const clarification={...answer,status:"needs_details",questions:["What warning events are present?"]};
  assert.deepEqual(validateAnswer(JSON.stringify(clarification),sources),clarification);
});

test("oversized streamed bodies are cancelled before reading the entire input",async()=>{
  let pulls=0,cancelled=false,calls=0;
  const body=new ReadableStream({pull(controller){pulls++;controller.enqueue(new Uint8Array(8192));
    if(pulls===20)controller.close();},cancel(){cancelled=true;}});
  const response=await handleRequest(new Request("http://localhost/api/troubleshoot",{
    method:"POST",body,duplex:"half"
  }),{corpus,endpoint:"http://localhost/v1",fetcher:async()=>{calls++;throw Error("must not call");}});
  assert.equal(response.status,413);
  assert.equal(cancelled,true);
  assert.ok(pulls<20);
  assert.equal(calls,0);
});
