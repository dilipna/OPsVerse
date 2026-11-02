// Browser smoke test for the built site. Starts `next start`, visits every page at
// desktop and phone widths, and exercises the interactive features. Fails on a non-200
// response, a console error, a missing heading, horizontal overflow, or a broken feature.
//
//   npm run build && npm run smoke
//   CHROMIUM_PATH=/path/to/chromium npm run smoke   # use an existing browser binary
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = path.dirname(fileURLToPath(import.meta.url));
const site = path.resolve(here, "..");
const PORT = Number(process.env.SMOKE_PORT || 3217);
const BASE = `http://127.0.0.1:${PORT}`;
const writing = JSON.parse(fs.readFileSync(path.join(site, "public/writing.json"), "utf8"));

const ROUTES = [
  "/",
  "/lab",
  "/agent",
  "/security",
  "/troubleshoot",
  "/engineering",
  "/study",
  "/runbooks",
  "/brief",
  "/writing",
  ...writing.posts.map((p) => `/writing/${p.slug}`),
];
const VIEWPORTS = [
  ["desktop", 1280, 800],
  ["phone", 390, 844],
];

const failures = [];
const fail = (msg) => {
  failures.push(msg);
  console.log(`  ✗ ${msg}`);
};

async function waitForServer(child) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error("next start exited early");
    try {
      if ((await fetch(BASE)).ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error("next start did not become ready in 60s");
}

async function checkPage(browser, route, [label, width, height]) {
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  const res = await page.goto(BASE + route, { waitUntil: "networkidle" });
  if (res?.status() !== 200) fail(`${route} (${label}): HTTP ${res?.status()}`);
  if (!(await page.locator("h1").count())) fail(`${route} (${label}): no <h1>`);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  if (overflow > 1) fail(`${route} (${label}): ${overflow}px horizontal overflow`);
  for (const e of errors) fail(`${route} (${label}): console error: ${e.slice(0, 200)}`);
  await page.close();
}

async function checkFeatures(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  const step = async (name, fn) => {
    try {
      await fn();
      console.log(`  ✓ ${name}`);
    } catch (e) {
      fail(`${name}: ${e instanceof Error ? e.message.split("\n")[0] : e}`);
    }
  };

  await step("hero console renders live verdicts", async () => {
    await page.locator(".console-body li.tone-bad").first().waitFor({ timeout: 15_000 });
  });
  await step("challenge refuses a Secrets read", async () => {
    await page.fill("#breakit-input", "kubectl get secrets -n shop");
    await page.press("#breakit-input", "Enter");
    const row = page.locator(".breakit-log li").first();
    await row.waitFor();
    if (!(await row.getAttribute("class"))?.includes("no")) throw new Error("not refused");
  });
  await step("Ask the project returns a cited answer", async () => {
    await page.locator("#ask").scrollIntoViewIfNeeded();
    await page.waitForFunction(
      () =>
        !document.querySelector("#ask-input")?.getAttribute("placeholder")?.startsWith("Loading"),
      null,
      { timeout: 15_000 },
    );
    await page.fill("#ask-input", "Why did you choose Qdrant instead of pgvector?");
    await page.press("#ask-input", "Enter");
    await page.locator(".ask-sources li").first().waitFor();
    const first = await page.locator(".ask-sources code").first().textContent();
    if (!first?.includes("0002-qdrant")) throw new Error(`top source was ${first}`);
  });
  await step("architecture map updates on click", async () => {
    await page.locator(".arch-node", { hasText: "Command policy" }).click();
    await page.locator(".arch-detail h3", { hasText: "Command policy" }).waitFor();
  });
  await step("command palette opens with Ctrl+K and filters", async () => {
    await page.keyboard.press("Escape");
    await page.locator("body").click({ position: { x: 5, y: 5 } });
    await page.keyboard.press("Control+k");
    await page.locator(".palette input").waitFor();
    await page.keyboard.type("threat");
    if (!(await page.locator(".palette li[role=option]").count())) throw new Error("no results");
    await page.keyboard.press("Escape");
  });
  await step("guided tour starts from /?tour and advances", async () => {
    await page.goto(BASE + "/?tour", { waitUntil: "networkidle" });
    await page.locator(".tour-card").waitFor();
    await page.locator(".tour-target").waitFor();
    await page.locator(".tour-actions .primary").click();
    await page.locator(".tour-card small", { hasText: "2 /" }).waitFor();
  });
  await step("brief prints to exactly one page", async () => {
    await page.goto(BASE + "/brief", { waitUntil: "networkidle" });
    const pdf = await page.pdf({
      format: "Letter",
      printBackground: true,
      preferCSSPageSize: true,
    });
    const pages = (pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
    if (pages !== 1) throw new Error(`${pages} pages`);
  });
  for (const e of errors) fail(`features: page error: ${e.slice(0, 200)}`);
  await page.close();
}

const server = spawn(
  process.execPath,
  [path.join(site, "node_modules/next/dist/bin/next"), "start", "-p", String(PORT)],
  {
    cwd: site,
    stdio: "ignore",
  },
);
try {
  await waitForServer(server);
  const browser = await chromium.launch(
    process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  );
  console.log(`Pages (${ROUTES.length} routes × ${VIEWPORTS.length} widths)`);
  for (const route of ROUTES) for (const vp of VIEWPORTS) await checkPage(browser, route, vp);
  console.log("Features");
  await checkFeatures(browser);
  await browser.close();
} finally {
  server.kill();
}
if (failures.length) {
  console.error(`\n${failures.length} smoke check(s) failed`);
  process.exit(1);
}
console.log(
  `\nSmoke test passed: ${ROUTES.length} routes at ${VIEWPORTS.length} widths, 7 features`,
);
