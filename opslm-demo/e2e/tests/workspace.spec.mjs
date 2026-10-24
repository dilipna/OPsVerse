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
  expect((await (await request.get("/api/troubleshoot")).json()).generation_configured).toBe(false);
  expect((await (await request.get("/api/chat")).json()).live).toBe(false);
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
