import {test,expect} from "@playwright/test";
import fs from "node:fs/promises";
import corpus from "../../public/runbooks.json" with {type:"json"};

test.beforeEach(async({page})=>{
  page.__applicationErrors=[];
  page.on("pageerror",e=>page.__applicationErrors.push(e.message));
});
test.afterEach(async({page},info)=>{
  await info.attach("application-errors",{body:JSON.stringify(page.__applicationErrors),contentType:"application/json"});
  expect(page.__applicationErrors).toEqual([]);
});

for(const width of [360,768,1440])for(const route of ["/","/troubleshoot","/runbooks","/study","/engineering","/model-demo"]){
  test(`layout ${width} ${route}`,async({page},info)=>{
    await page.setViewportSize({width,height:1000});
    const response=await page.goto(route);expect(response.status()).toBe(200);
    if(route==="/"||route==="/troubleshoot")await expect(page.getByRole("button",{name:"Find incident evidence →"})).toBeEnabled();
    if(route==="/runbooks")await expect(page.getByRole("button",{name:"Find passages →"})).toBeEnabled();
    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.locator("h1")).toHaveCount(1);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
    const screenshot=info.outputPath("layout.png");await page.screenshot({path:screenshot,fullPage:true});
    await info.attach("layout",{path:screenshot,contentType:"image/png"});
  });
}

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

for(const route of ["/","/runbooks"]){
  test(`documentation download failure and retry ${route}`,async({page})=>{
    let attempts=0;
    await page.route("**/runbooks.json",async request=>{
      attempts++;
      if(attempts===1)await request.fulfill({status:503,body:"Synthetic documentation outage"});
      else await request.continue();
    });
    await page.goto(route);
    const submit=page.getByRole("button",{name:route==="/"?"Find incident evidence →":"Find passages →"});
    await expect(page.getByRole("alert")).toContainText("could not load");
    await expect(submit).toBeDisabled();
    await page.getByRole("button",{name:/Retry loading/}).click();
    await expect(submit).toBeEnabled();await expect(page.getByRole("alert")).toHaveCount(0);
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
  await expect(page.getByRole("button",{name:"Find incident evidence →"})).toBeEnabled();
  await page.getByRole("button",{name:"Image won't pull",exact:true}).click();
  await expect(page.locator("#diagnostics")).toHaveValue(/ImagePullBackOff/);
  await page.getByRole("button",{name:"Find incident evidence →"}).click();
  await expect(page.getByRole("heading",{name:"Incident evidence",exact:true})).toBeVisible();
  await expect(page.locator(".incident-source")).toHaveCount(3);
  await expect(page.locator(".incident-source").first()).toContainText("ImagePullBackOff");
  await page.locator("#review-notes").fill("CI QA: root cause unconfirmed. token=synthetic-private-value");
  const downloaded=page.waitForEvent("download");
  await page.getByRole("button",{name:"Export brief ↓"}).click();
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
  await expect(page.getByRole("heading",{name:"Incident evidence",exact:true})).toHaveCount(0);
});

test("multiple families expose budget gaps and unsupported input abstains",async({page})=>{
  await page.goto("/");await expect(page.getByRole("button",{name:"Find incident evidence →"})).toBeEnabled();
  await page.locator("#incident-issue").fill("What should I inspect next?");
  await page.locator("#diagnostics").fill("ImagePullBackOff\nOOMKilled\nReadiness probe failed\nProgressDeadlineExceeded");
  await page.getByRole("button",{name:"Find incident evidence →"}).click();
  await expect(page.getByText("Documentation gap",{exact:true})).toBeVisible();
  await expect(page.locator(".incident-source")).toHaveCount(3);
  await page.locator(".decision-trace summary").click();
  await expect(page.locator(".decision-trace")).toContainText("Document-family presence only");
  await page.locator("#incident-issue").fill("quasar marmalade");await page.locator("#diagnostics").fill("");
  await page.getByRole("button",{name:"Find incident evidence →"}).click();
  await expect(page.getByRole("heading",{name:"No supporting evidence",exact:true})).toBeVisible();
  await expect(page.locator(".incident-source")).toHaveCount(0);
});

test("keyboard investigation and invalid-input recovery",async({page})=>{
  await page.goto("/");await expect(page.getByRole("button",{name:"Find incident evidence →"})).toBeEnabled();
  await page.getByRole("button",{name:"Find incident evidence →"}).click();
  await expect(page.getByText("Describe the issue first.",{exact:true})).toBeVisible();
  // Analysis deliberately moves focus on the next animation frame. Wait for
  // that completed transition before testing the independent skip-link action.
  await expect(page.getByRole("region",{name:"Incident analysis",exact:true})).toBeFocused();
  await page.getByRole("link",{name:"Skip to incident input",exact:true}).focus();
  await page.keyboard.press("Enter");await expect(page.locator("#incident-issue")).toBeFocused();
  await page.locator("#incident-issue").fill("Investigate this Pod");
  await page.locator("#diagnostics").fill("OOMKilled");
  await page.locator("#diagnostics").press("Tab");
  await expect(page.getByRole("button",{name:"Find incident evidence →"})).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region",{name:"Incident analysis",exact:true})).toBeFocused();
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
