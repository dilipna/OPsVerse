import {test} from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {prepare} from "../lib/troubleshoot.mjs";
import {decideRoute,catalogueModels,costComparison,localRoutingResult} from "../lib/rype-routing.mjs";
import {routingMetadata,handleRypeRequest} from "../lib/rype-http.mjs";
const corpus=JSON.parse(fs.readFileSync(new URL("../public/runbooks.json",import.meta.url)));
const raw={data:[
  {id:"recursive/flint-v1.0:free",pricing:{prompt:"0",completion:"0"}},
  {id:"cohere/north-mini-code:free",pricing:{prompt:"0",completion:"0"}},
  {id:"dots-studio/dots-3-note-preview:free",pricing:{prompt:"0",completion:"0"}},
  {id:"anthropic/claude-sonnet-4.6",pricing:{prompt:"0.000003",completion:"0.000015"}},
].map(m=>({...m,context_length:131072,architecture:{input_modalities:["text"],output_modalities:["text"]}}))};
const metadata=await routingMetadata({apiKey:"synthetic",fetcher:async()=>Response.json(raw),cache:false,now:0});
const req=input=>new Request("http://rype.test/api/route",{method:"POST",body:JSON.stringify(input)});
const input={issue:"What does ImagePullBackOff mean?",diagnostics:"ImagePullBackOff token=synthetic-secret"};

test("coverage gate accepts source-covered guidance and rejects tangential and mixed requests",()=>{
  assert.equal(decideRoute(prepare(corpus,input)).kind,"retrieval");
  for(const issue of ["Explain Redis connection pooling","What does ImagePullBackOff mean and what is the capital of France?","Write a Python Kubernetes operator"]){assert.equal(decideRoute(prepare(corpus,{issue,diagnostics:""})).kind,"model",issue);}
  assert.equal(decideRoute(prepare(corpus,{issue:"Write a Python function",diagnostics:""})).category,"code");
  assert.equal(decideRoute(prepare(corpus,{issue:"Write a Dockerfile",diagnostics:""})).category,"code");
  assert.equal(decideRoute(prepare(corpus,{issue:"Prove a theorem",diagnostics:""})).category,"reasoning");
});
test("library response makes zero inference requests and separates estimated comparison from actual zero charge",async()=>{
  let calls=0;const response=await handleRypeRequest(req(input),{corpus,apiKey:"synthetic",metadata,fetcher:async()=>{calls++;throw Error();}});
  assert.equal(response.status,200);const result=await response.json();assert.equal(calls,0);assert.equal(result.routing.model_used,null);assert.equal(result.routing.actual_cost_usd,0);assert.equal(result.routing.model_calls,0);assert.match(result.routing.token_basis,/Approximate/);assert.match(result.routing.comparison_scope,/Baseline not run/);assert.ok(!JSON.stringify(result).includes("synthetic-secret"));
});
for(const [issue,category] of [["Write a Python function to sort records","code"],["Prove a theorem step by step","reasoning"],["Explain why the sky is blue","general"]])test(`free-only ${category} route selects a distinct allowlisted model and reports returned cost`,async()=>{
  let calls=0;
  const response=await handleRypeRequest(req({issue,diagnostics:"token=synthetic-secret"}),{corpus,apiKey:"synthetic",metadata,fetcher:async(url,options)=>{
    calls++;assert.equal(url,"https://openrouter.ai/api/v1/chat/completions");const body=JSON.parse(options.body);
    assert.equal(body.model,metadata.profiles[category].id);assert.equal(body.provider.allow_fallbacks,false);assert.deepEqual(body.provider.max_price,{prompt:0,completion:0,request:0,image:0});assert.equal(body.max_tokens,768);assert.ok(!JSON.stringify(body).includes("synthetic-secret"));
    return Response.json({model:body.model,choices:[{message:{content:"Synthetic transport fixture, not a model-quality result."},finish_reason:"stop"}],usage:{cost:0,prompt_tokens:100,completion_tokens:25}});
  }});
  const result=await response.json();assert.equal(response.status,200);assert.equal(calls,1);assert.equal(result.mode,"routed");assert.equal(result.routing.model_used,metadata.profiles[category].id);assert.equal(result.routing.actual_cost_usd,0);assert.equal(result.routing.baseline_estimated_usd,0.000675);assert.equal(result.routing.estimated_reduction_percent,100);
});
test("paid prices, missing credentials and catalogue outages fail closed without inference",async()=>{
  let calls=0;const fetcher=async()=>{calls++;throw Error("must not call");};
  for(const deps of [{metadata,apiKey:undefined},{metadata:{...metadata,profiles:{general:{...metadata.profiles.general,prompt:0.1}}},apiKey:"synthetic"},{metadata:{...metadata,profiles:{}},apiKey:"synthetic"}]){const r=await handleRypeRequest(req({issue:"Explain a rainbow",diagnostics:""}),{corpus,fetcher,...deps});assert.equal(r.status,503);assert.equal((await r.json()).result.routing.model_calls,0);}
  assert.equal(calls,0);
  assert.equal(catalogueModels({data:[{...raw.data[0],pricing:{prompt:"unknown",completion:"0"}}]}).length,0);
});
test("failed, charged, truncated and unexpected-model responses are never fake zero-cost successes",async()=>{
  for(const data of [{model:metadata.profiles.general.id,choices:[{message:{content:"truncated"},finish_reason:"length"}],usage:{cost:0.01,prompt_tokens:10,completion_tokens:3}},{model:"unexpected/model",choices:[{message:{content:"wrong model"},finish_reason:"stop"}],usage:{cost:0}},{model:metadata.profiles.general.id,choices:[{message:{content:"paid response"},finish_reason:"stop"}],usage:{cost:0.01}}]){
    const r=await handleRypeRequest(req({issue:"Explain a rainbow",diagnostics:""}),{corpus,apiKey:"synthetic",metadata,fetcher:async()=>Response.json(data)});const result=await r.json();assert.equal(r.status,502);assert.equal(result.result.cloud_answer,undefined);assert.equal(result.result.routing.actual_cost_usd,data.usage.cost);
  }
  const r=await handleRypeRequest(req({issue:"Explain a rainbow",diagnostics:""}),{corpus,apiKey:"synthetic",metadata,fetcher:async()=>{throw Error("timeout");}});assert.equal((await r.json()).result.routing.actual_cost_usd,null);
});
test("missing or invalid billing never manufactures a saving and expensive calls can show a negative difference",()=>{
  for(const actualCost of [null,-1,NaN]){const receipt=costComparison({actualCost,inputTokens:100,outputTokens:25,baseline:metadata.baseline});assert.equal(receipt.estimated_difference_usd,null);}
  assert.ok(costComparison({actualCost:1,inputTokens:100,outputTokens:25,baseline:metadata.baseline}).estimated_difference_usd<0);
});
test("restored unsupported notes do not trigger inference or preserve imported model authority",()=>{
  const prepared=prepare(corpus,{issue:"Write Python code",diagnostics:""});const result=localRoutingResult({...prepared,mode:"excerpts",answer:null,note:"restored"},metadata,{restored:true});assert.equal(result.routing.status,"not_requested");assert.equal(result.routing.model_calls,0);assert.equal(result.routing.model_used,null);
});
test("route HTTP bounds bodies and rejects client attempts to select paid models",async()=>{
  for(const body of [JSON.stringify({...input,model:"paid/model"}),"{broken",JSON.stringify({issue:"",diagnostics:""})]){const r=await handleRypeRequest(new Request("http://rype.test",{method:"POST",body}),{corpus,metadata});assert.equal(r.status,400);}
  const r=await handleRypeRequest(new Request("http://rype.test",{method:"POST",body:"x".repeat(24001)}),{corpus,metadata});assert.equal(r.status,413);
});

test("account-filtered catalogue can exclude public free models without weakening privacy or selecting paid models",async()=>{
  const requests=[];
  const m=await routingMetadata({apiKey:"synthetic-account-key",cache:false,fetcher:async(url,options)=>{
    requests.push(url);if(url.endsWith("/models/user")){assert.equal(options.headers.authorization,"Bearer synthetic-account-key");return Response.json({data:raw.data.filter(x=>x.id==="cohere/north-mini-code:free")});}
    assert.equal(options.headers.authorization,undefined);return Response.json(raw);
  }});
  assert.equal(requests.length,2);assert.equal(m.profiles.general.id,"cohere/north-mini-code:free");assert.equal(m.profiles.reasoning.id,"cohere/north-mini-code:free");assert.equal(m.profiles.code.id,"cohere/north-mini-code:free");assert.equal(m.baseline.id,"anthropic/claude-sonnet-4.6");assert.ok(!JSON.stringify(m).includes("synthetic-account-key"));
});