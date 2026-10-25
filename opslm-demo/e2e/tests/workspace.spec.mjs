import {test,expect} from "@playwright/test";
import fs from "node:fs/promises";
import {createHash} from "node:crypto";
import corpus from "../../public/runbooks.json" with {type:"json"};

test.beforeEach(async({page})=>{
  // Browser contracts never spend provider quota. Live free inference is checked separately.
  await page.route("**/api/route",async route=>{if(route.request().method()==="POST")await route.fulfill({status:503,json:{error:"External inference disabled in this browser contract."}});else await route.continue();});
  page.__applicationErrors=[];
  page.on("pageerror",e=>page.__applicationErrors.push(e.message));
});
test.afterEach(async({page},info)=>{
  await info.attach("application-errors",{body:JSON.stringify(page.__applicationErrors),contentType:"application/json"});
  expect(page.__applicationErrors).toEqual([]);
});

for(const width of [360,768,1440])for(const route of ["/","/troubleshoot","/runbooks","/study","/engineering","/model-demo","/dashboard.html","/overturns.html"]){
  test(`layout ${width} ${route}`,async({page},info)=>{
    await page.setViewportSize({width,height:1000});
    const response=await page.goto(route);expect(response.status()).toBe(200);
    if(route==="/"||route==="/troubleshoot")await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
    if(route==="/runbooks")await expect(page.getByRole("button",{name:"Find passages →"})).toBeEnabled();
    await page.evaluate(()=>document.fonts.ready);
    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.locator("h1")).toHaveCount(1);
    if(route==="/"&&width===1440){
      const rail=await page.locator(".chat-sidebar").boundingBox(),main=await page.locator("main").boundingBox();
      const composer=await page.locator(".chat-composer").boundingBox();
      expect(rail.x+rail.width).toBeLessThanOrEqual(main.x);
      expect(Math.abs(composer.x+composer.width/2-(main.x+main.width/2))).toBeLessThan(2);
      expect(composer.width).toBeLessThanOrEqual(820);
      await expect(page.locator(".chat-response")).toBeHidden();
      await expect(page.locator("#diagnostics")).toBeHidden();
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
    const screenshot=info.outputPath("layout.png");await page.screenshot({path:screenshot,fullPage:true});
    await info.attach("layout",{path:screenshot,contentType:"image/png"});
  });
}

test("research archive navigation, chart rendering and theme toggle",async({page})=>{
  await page.emulateMedia({colorScheme:"light"});
  await page.goto("/dashboard.html");await page.evaluate(()=>document.fonts.ready);
  await expect(page.getByRole("navigation",{name:"Research navigation"})).toBeVisible();
  await expect(page.getByRole("complementary",{name:"Historical research scope"})).toContainText("Historical research snapshot");
  expect(await page.locator("svg").count()).toBeGreaterThan(0);
  await page.getByRole("button",{name:"Toggle light and dark theme"}).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
  expect(await page.locator("svg").count()).toBeGreaterThan(0);
  await page.getByRole("button",{name:"Toggle light and dark theme"}).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme","light");
  await page.getByRole("navigation",{name:"Research navigation"}).getByRole("link",{name:"Workspace",exact:true}).click();
  await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await page.goto("/overturns.html");await page.evaluate(()=>document.fonts.ready);
  await expect(page.locator("article.card")).toHaveCount(8);
  await expect(page.getByRole("link",{name:"Read current corrections and limitations ↗"})).toHaveAttribute("href",/improve\/flagship-investigation\/docs\/claims.md$/);
});

test("public identity and model-free operating mode",async({request})=>{
  const identity=await (await request.get("/release.json")).json();
  expect(identity.source_commit).toMatch(/^[a-f0-9]{40}$/);
  if(process.env.OPSVERSE_EXPECTED_COMMIT)expect(identity.source_commit).toBe(process.env.OPSVERSE_EXPECTED_COMMIT);
  expect(identity.source_files["lib/troubleshoot.mjs"]).toMatch(/^[a-f0-9]{64}$/);
  expect(identity.source_files["package.json"]).toMatch(/^[a-f0-9]{64}$/);
  expect(identity.dirty_source).toBe(false);
  expect((await (await request.get("/api/troubleshoot")).json()).generation_configured).toBe(false);
  expect((await (await request.get("/api/chat")).json()).live).toBe(false);
});

test("custom fonts load from this release rather than a fallback or font service",async({page,request})=>{
  const fontRequests=[];page.on("request",r=>{if(r.resourceType()==="font")fontRequests.push(r.url());});
  await page.goto("/");await page.evaluate(()=>document.fonts.ready);
  const identity=await (await request.get("/release.json")).json();
  for(const [file,family] of [["SpaceGrotesk","Space Grotesk"],["PlusJakartaSans","Plus Jakarta Sans"],["Inter","Inter"],["IBMPlexMono","IBM Plex Mono"]]){
    expect(fontRequests.some(url=>new URL(url).pathname===`/fonts/${file}.woff2`)).toBe(true);
    const response=await request.get(`/fonts/${file}.woff2`);expect(response.status()).toBe(200);
    expect(createHash("sha256").update(await response.body()).digest("hex")).toBe(identity.source_files[`public/fonts/${file}.woff2`]);
    expect(await page.evaluate(name=>Array.from(document.fonts).some(f=>f.family.replaceAll('"',"")===name&&f.status==="loaded"),family)).toBe(true);
  }
  for(const url of fontRequests)expect(new URL(url).origin).toBe(new URL(page.url()).origin);
  expect(await page.locator("h1").evaluate(e=>getComputedStyle(e).fontFamily)).toContain("Space Grotesk");
  expect(await page.locator(".intro-copy").evaluate(e=>getComputedStyle(e).fontFamily)).toContain("Inter");
  expect(await page.locator("textarea").first().evaluate(e=>getComputedStyle(e).fontFamily)).toContain("Inter");
});

for(const route of ["/","/runbooks"]){
  test(`documentation download failure and retry ${route}`,async({page})=>{
    let attempts=0;
    await page.route("**/runbooks.json",async request=>{
      attempts++;
      if(attempts===1)await request.fulfill({status:503,body:"Synthetic documentation outage"});
      else await request.continue();
    });
    await page.goto(route);
    const submit=page.getByRole("button",{name:route==="/"?"Send question":"Find passages →"});
    const loadAlert=page.locator("main").getByRole("alert");
    await expect(loadAlert).toContainText("could not load");
    await expect(submit).toBeDisabled();
    await page.getByRole("button",{name:/Retry loading/}).click();
    await expect(submit).toBeEnabled();await expect(loadAlert).toHaveCount(0);
    expect(attempts).toBe(2);
    if(route==="/"){
      await page.getByRole("button",{name:"Image won't pull",exact:true}).click();await submit.click();
      await expect(page.locator(".incident-source").first()).toContainText("ImagePullBackOff");
    }else{
      await page.locator("#question").fill("ImagePullBackOff image pull policy");await submit.click();
      await expect(page.locator(".passage").first()).toContainText("ImagePullBackOff");
    }
  });
}

test("reviewer links and reproduction select the released branch",async({page})=>{
  await page.goto("/engineering");
  await expect(page.getByRole("link",{name:"Source code ↗",exact:true})).toHaveAttribute("href","https://github.com/dilipna/OPsVerse/tree/improve/flagship-investigation");
  await expect(page.getByRole("link",{name:"Read the failure-path tests ↗",exact:true})).toHaveAttribute("href","https://github.com/dilipna/OPsVerse/blob/improve/flagship-investigation/opslm-demo/scripts/troubleshoot.test.mjs");
  await expect(page.locator(".study-code")).toContainText("git clone --branch improve/flagship-investigation");
  expect(await page.locator('a[href*="/blob/main/"]').count()).toBe(0);
});

test("real evidence, notes, redaction and actual JSON download",async({page},info)=>{
  let modelPosts=0;page.on("request",r=>{if(r.method()==="POST"&&r.url().includes("/api/troubleshoot"))modelPosts++;});
  await page.goto("/");
  await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await page.getByRole("button",{name:"Image won't pull",exact:true}).click();
  await expect(page.locator("#diagnostics")).toHaveValue(/ImagePullBackOff/);
  await page.getByRole("button",{name:"Send question"}).click();
  await expect(page.getByRole("heading",{name:"What I found",exact:true})).toBeVisible();
  await expect(page.locator(".incident-source")).toHaveCount(3);
  await expect(page.locator(".incident-source").first()).toContainText("ImagePullBackOff");
  const evidenceScreenshot=info.outputPath("desktop-evidence.png");await page.screenshot({path:evidenceScreenshot,fullPage:true});
  await info.attach("actual-desktop-evidence",{path:evidenceScreenshot,contentType:"image/png"});
  await page.locator(".chat-notes > summary").click();
  await page.locator("#review-notes").fill("CI QA: root cause unconfirmed. token=synthetic-private-value");
  const downloaded=page.waitForEvent("download");
  await page.getByRole("button",{name:"Download JSON ↓"}).click();
  const download=await downloaded,file=info.outputPath("incident-brief.json");await download.saveAs(file);
  const brief=JSON.parse(await fs.readFile(file,"utf8"));
  expect(brief.mode).toBe("excerpts");expect(brief.answer).toBeNull();
  expect(brief.review.status).toBe("unreviewed");expect(brief.review.notes).not.toContain("synthetic-private-value");
  expect(brief.review.notes).toContain("[REDACTED]");
  expect(brief.source_revision).toBe(corpus.manifest.revision);
  for(const source of brief.sources){
    const original=corpus.chunks.find(c=>c.id===source.id);
    expect(original).toBeTruthy();expect(original.text.startsWith(source.text)).toBe(true);
    expect(source.source).toBe(original.source);
  }
  expect(brief.evidence_policy.usage.characters).toBeLessThanOrEqual(6000);
  expect(modelPosts).toBe(0);
  await info.attach("actual-download",{path:file,contentType:"application/json"});
  await page.locator("#incident-issue").fill("A changed incident");
  await expect(page.locator("#review-notes")).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"What I found",exact:true})).toHaveCount(0);
});

test("multiple families expose budget gaps and unsupported input abstains",async({page})=>{
  await page.goto("/");await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await page.locator("#incident-issue").fill("What should I inspect next?");
  await page.locator(".chat-logs > summary").click();
  await page.locator("#diagnostics").fill("ImagePullBackOff\nOOMKilled\nReadiness probe failed\nProgressDeadlineExceeded");
  await page.getByRole("button",{name:"Send question"}).click();
  await expect(page.getByText("Some details are missing",{exact:true})).toBeVisible();
  await expect(page.locator(".incident-source")).toHaveCount(3);
  await page.locator(".chat-method > summary").click();
  await page.locator(".decision-trace summary").click();
  await expect(page.locator(".decision-trace")).toContainText("Document-family presence only");
  await page.locator("#incident-issue").fill("quasar marmalade");await page.locator("#diagnostics").fill("");
  await page.getByRole("button",{name:"Send question"}).click();
  await expect(page.getByRole("heading",{name:"No matches yet",exact:true})).toBeVisible();
  await expect(page.locator(".incident-source")).toHaveCount(0);
});

test("keyboard investigation and invalid-input recovery",async({page})=>{
  await page.goto("/");await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await page.getByRole("button",{name:"Send question"}).click();
  await expect(page.getByText("Describe the issue first.",{exact:true})).toBeVisible();
  // Analysis deliberately moves focus on the next animation frame. Wait for
  // that completed transition before testing the independent skip-link action.
  await expect(page.getByRole("region",{name:"Response",exact:true})).toBeFocused();
  await page.getByRole("link",{name:"Skip to question",exact:true}).focus();
  await page.keyboard.press("Enter");await expect(page.locator("#incident-issue")).toBeFocused();
  await page.locator("#incident-issue").fill("Investigate this Pod");
  await page.locator(".chat-logs > summary").click();
  await page.locator("#diagnostics").fill("OOMKilled");
  await page.locator("#diagnostics").press("Tab");
  await expect(page.getByRole("button",{name:"Reopen notes ↗",exact:true})).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button",{name:"Send question"})).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region",{name:"Response",exact:true})).toBeFocused();
  await expect(page.locator(".incident-source").first()).toContainText("resources:");
});

test("runbook search and explicit empty state",async({page})=>{
  await page.goto("/runbooks");await expect(page.getByRole("button",{name:"Find passages →"})).toBeEnabled();
  await page.locator("#question").fill("ImagePullBackOff image pull policy");
  await page.getByRole("button",{name:"Find passages →"}).click();
  await expect(page.getByRole("heading",{name:"Matching passages",exact:true})).toBeVisible();
  await expect(page.locator(".passage").first()).toContainText("ImagePullBackOff");
  await page.locator("#question").fill("quasar marmalade");await page.getByRole("button",{name:"Find passages →"}).click();
  await expect(page.getByRole("heading",{name:"No matching passages",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Clear search",exact:true}).click();
  await expect(page.locator("#question")).toHaveValue("");
});

test("mobile evidence remains readable after a real investigation",async({page},info)=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/");
  await page.evaluate(()=>document.fonts.ready);
  await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await expect(page.getByRole("heading",{name:"What can I help you understand?",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Image won't pull",exact:true}).click();
  await page.getByRole("button",{name:"Send question"}).click();
  await expect(page.locator(".incident-source").first()).toContainText("ImagePullBackOff");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await expect(page.getByRole("button",{name:"Download JSON ↓"})).toBeVisible();
  const screenshot=info.outputPath("mobile-evidence.png");
  await page.screenshot({path:screenshot,fullPage:true});
  await info.attach("actual-mobile-evidence",{path:screenshot,contentType:"image/png"});
});

test("simple question flow reveals detail only on request and resets cleanly",async({page})=>{
  let modelPosts=0;page.on("request",r=>{if(r.method()==="POST"&&r.url().includes("/api/troubleshoot"))modelPosts++;});
  await page.goto("/");await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await expect(page.locator("#diagnostics")).toBeHidden();
  await expect(page.locator(".chat-response")).toBeHidden();
  await page.locator("#incident-issue").fill("What does ImagePullBackOff mean?");
  await page.locator("#incident-issue").press("Shift+Enter");
  await expect(page.locator("#incident-issue")).toHaveValue("What does ImagePullBackOff mean?\n");
  await page.locator("#incident-issue").press("Enter");
  await expect(page.getByRole("heading",{name:"What I found",exact:true})).toBeVisible();
  await expect(page.locator(".chat-sources")).not.toHaveAttribute("open");
  await expect(page.locator(".chat-method")).not.toHaveAttribute("open");
  await expect(page.locator("#review-notes")).toBeHidden();
  const normalize=t=>t.replace(/\[([^\]]+)\]\([^)]*\)/g,"$1").replace(/`([^`]+)`/g,"$1").replace(/\*\*([^*]+)\*\*/g,"$1").replace(/\s+/g," ").trim();
  for(const card of await page.locator(".guide-preview").all()){
    const id=await card.getAttribute("data-source-id"),source=corpus.chunks.find(c=>c.id===id);
    expect(source).toBeTruthy();
    const paragraph=card.locator("p");if(await paragraph.count())expect(normalize(source.text)).toContain(normalize(await paragraph.innerText()));
  }
  await page.locator(".chat-sources > summary").click();
  await page.locator(".incident-source").first().locator("summary").click();
  await expect(page.getByLabel("Incident source 1",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Ask another question",exact:true}).click();
  await expect(page.locator("#incident-issue")).toHaveValue("");
  await expect(page.locator("#diagnostics")).toHaveValue("");
  await expect(page.locator(".chat-response")).toBeHidden();
  await expect(page.locator("#incident-issue")).toBeFocused();
  expect(modelPosts).toBe(0);
});

test("portable JSON resumes trusted retrieval and Markdown saves readable redacted notes",async({page},info)=>{
  await page.goto("/");await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await page.getByRole("button",{name:"Image won't pull",exact:true}).click();await page.getByRole("button",{name:"Send question"}).click();
  await expect(page.getByRole("heading",{name:"What I found",exact:true})).toBeVisible();
  await page.locator(".chat-notes > summary").click();await page.locator("#review-notes").fill("Check registry. token=portable-secret");
  const mdEvent=page.waitForEvent("download");await page.getByRole("button",{name:"Download Markdown ↓",exact:true}).click();
  const mdDownload=await mdEvent,mdPath=info.outputPath("investigation.md");await mdDownload.saveAs(mdPath);
  const markdown=await fs.readFile(mdPath,"utf8");expect(markdown).toContain("# RYPE investigation notes");expect(markdown).toContain("[REDACTED]");expect(markdown).not.toContain("portable-secret");expect(markdown).toContain("ImagePullBackOff");
  await info.attach("actual-markdown-download",{path:mdPath,contentType:"text/markdown"});
  const jsonEvent=page.waitForEvent("download");await page.getByRole("button",{name:"Download JSON ↓",exact:true}).click();
  const jsonDownload=await jsonEvent,jsonPath=info.outputPath("portable-notes.json");await jsonDownload.saveAs(jsonPath);
  const brief=JSON.parse(await fs.readFile(jsonPath,"utf8"));
  brief.answer={summary:"UNTRUSTED_IMPORTED_AUTHORITY"};brief.sources=[{source:"javascript:untrusted",text:"UNTRUSTED_IMPORTED_AUTHORITY"}];
  await page.getByRole("button",{name:"Ask another question",exact:true}).click();
  await page.getByLabel("Reopen notes file",{exact:true}).setInputFiles({name:"notes.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(brief))});
  await expect(page.getByRole("heading",{name:"What I found",exact:true})).toBeVisible();
  await expect(page.locator(".chat-response")).not.toContainText("UNTRUSTED_IMPORTED_AUTHORITY");
  await expect(page.locator(".incident-source").first()).toContainText("ImagePullBackOff");
  await expect(page.locator("#incident-issue")).toHaveValue(brief.issue);
  await page.locator(".chat-notes > summary").click();await expect(page.locator("#review-notes")).toHaveValue(brief.review.notes);
  expect(await page.locator('a[href^="javascript:"]').count()).toBe(0);
});

test("unsupported and oversized note files preserve the active question",async({page})=>{
  await page.goto("/");await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await page.locator("#incident-issue").fill("Keep this question");
  const upload=(text)=>page.getByLabel("Reopen notes file",{exact:true}).setInputFiles({name:"notes.json",mimeType:"application/json",buffer:Buffer.from(text)});
  await upload(JSON.stringify({schema_version:1,review:{status:"unreviewed",notes:""},source_revision:"foreign",issue:"overwrite",diagnostics:""}));
  await expect(page.locator(".chat-response").getByRole("alert")).toContainText("different documentation snapshot");await expect(page.locator("#incident-issue")).toHaveValue("Keep this question");
  await upload("x".repeat(262145));await expect(page.locator(".chat-response").getByRole("alert")).toContainText("too large");
  await upload("{broken");await expect(page.locator(".chat-response").getByRole("alert")).toContainText("not valid JSON");
  await expect(page.locator("#incident-issue")).toHaveValue("Keep this question");
});

test("reading list survives reload without saving questions or logs",async({page},info)=>{
  await page.goto("/");await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await page.getByRole("button",{name:"Image won't pull",exact:true}).click();await page.getByRole("button",{name:"Send question"}).click();
  await page.getByRole("button",{name:"Save guide 1",exact:true}).click();
  await expect(page.getByRole("button",{name:"Unsave guide 1",exact:true})).toBeVisible();
  const stored=await page.evaluate(()=>localStorage.getItem("opsverse.saved-guides.v1"));
  expect(Object.keys(JSON.parse(stored)).sort()).toEqual(["ids","revision","schema"]);expect(stored).not.toContain("registry.example");expect(stored).not.toContain("Why has this container");
  await page.reload();await expect(page.locator(".saved-guides-button")).toContainText("1");await page.locator(".saved-guides-button").click();
  const dialog=page.getByRole("dialog",{name:"Your reading list"});await expect(dialog).toBeVisible();await expect(dialog.locator("li")).toHaveCount(1);await expect(dialog).toContainText("ImagePullBackOff");
  const desktopList=info.outputPath("reading-list-desktop.png");await page.screenshot({path:desktopList,fullPage:true});await info.attach("saved-guides-desktop",{path:desktopList,contentType:"image/png"});
  await page.setViewportSize({width:390,height:844});
  const bounds=await dialog.boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(390);
  const mobileList=info.outputPath("reading-list-mobile.png");await page.screenshot({path:mobileList,fullPage:true});await info.attach("saved-guides-mobile",{path:mobileList,contentType:"image/png"});
  await page.keyboard.press("Escape");await expect(dialog).not.toBeVisible();await expect(page.locator(".saved-guides-button")).toBeFocused();
  await page.locator(".saved-guides-button").click();await dialog.getByRole("button",{name:"Clear saved guides",exact:true}).click();await expect(dialog.locator("li")).toHaveCount(0);
  await dialog.getByRole("button",{name:"Close",exact:true}).click();await page.reload();await expect(page.locator(".saved-guides-button")).toContainText("0");
});

test("unavailable storage keeps saved guides usable in the active tab",async({page})=>{
  await page.addInitScript(()=>{Storage.prototype.setItem=function(){throw new DOMException("Synthetic quota failure","QuotaExceededError");};});
  await page.goto("/");await expect(page.getByRole("button",{name:"Send question"})).toBeEnabled();
  await page.getByRole("button",{name:"Image won't pull",exact:true}).click();await page.getByRole("button",{name:"Send question"}).click();
  await page.getByRole("button",{name:"Save guide 1",exact:true}).click();
  await expect(page.locator(".chat-response").getByRole("status").filter({hasText:"Device storage is unavailable"})).toBeVisible();
  await page.locator(".saved-guides-button").click();const dialog=page.getByRole("dialog",{name:"Your reading list"});await expect(dialog.locator("li")).toHaveCount(1);await expect(dialog).toContainText("this tab only");
});

test("RYPE explains retrieval-first routing and a covered question makes no cloud POST",async({page})=>{
  let calls=0;page.on("request",r=>{if(r.method()==="POST"&&new URL(r.url()).pathname==="/api/route")calls++;});
  await page.goto("/");await expect(page.getByRole("link",{name:"RYPE home",exact:true})).toBeVisible();
  await expect(page.locator(".intro-copy")).toContainText("Route Your Prompt Efficiently");await expect(page.locator(".routing-intro")).toContainText("No inference");
  await page.getByRole("button",{name:"Image won't pull",exact:true}).click();await page.getByRole("button",{name:"Send question"}).click();
  const receipt=page.getByRole("complementary",{name:"Routing and cost"});await expect(receipt).toContainText("Library route · no inference");await expect(receipt).toContainText("0 model calls");await expect(receipt.locator("dd").first()).toHaveText("None");await expect(receipt.locator("dd").nth(1)).toHaveText("$0");expect(calls).toBe(0);
});

test("routed answer shows the returned model and explicitly estimated comparison",async({page},info)=>{
  await page.route("**/api/route",async route=>{
    if(route.request().method()==="GET")return route.fulfill({json:{cloud_configured:true,free_only:true,checked_at:"2026-10-25T00:00:00Z",profiles:{},baseline:null,catalogue_available:true}});
    const body=route.request().postDataJSON();expect(Object.keys(body).sort()).toEqual(["diagnostics","issue"]);expect(JSON.stringify(body)).not.toContain("browser-private-value");
    return route.fulfill({json:{issue:body.issue,diagnostics:body.diagnostics,mode:"routed",answer:null,sources:[],signals:[],redactions:1,cloud_answer:"Synthetic browser transport fixture, not live inference. <img src=x onerror=alert(1)>",note:"Fixture",routing:{kind:"model",category:"code",status:"completed",reason:"Coding task",model_used:"fixture/free-code",model_selected:"fixture/free-code",model_calls:1,actual_cost_usd:0,baseline_model:"fixture/baseline",baseline_estimated_usd:0.001,estimated_difference_usd:0.001,estimated_reduction_percent:100,input_tokens:100,output_tokens:25,token_basis:"Fixture tokens",comparison_scope:"Estimated comparison; baseline not run.",note:"Synthetic fixture",price_checked_at:"2026-10-25T00:00:00Z"}}});
  });
  await page.goto("/");await expect(page.locator("#question-help")).toContainText("go to OpenRouter");await page.locator("#incident-issue").fill("Write a Python function");await page.locator(".chat-logs > summary").click();await page.locator("#diagnostics").fill("token=browser-private-value");await page.getByRole("button",{name:"Send question"}).click();
  await expect(page.getByRole("heading",{name:"Your answer",exact:true})).toBeVisible();const receipt=page.getByRole("complementary",{name:"Routing and cost"});await expect(receipt).toContainText("fixture/free-code");await expect(receipt).toContainText("Estimated charge reduction");await expect(receipt).toContainText("Baseline not run");await expect(receipt).toContainText("1 model call");await expect(page.locator(".cloud-answer")).toContainText("<img");expect(await page.locator(".cloud-answer img").count()).toBe(0);
  const screenshot=info.outputPath("routing-receipt-fixture.png");await page.screenshot({path:screenshot,fullPage:true});await info.attach("synthetic-browser-contract-not-live-inference",{path:screenshot,contentType:"image/png"});
});