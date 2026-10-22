// #10346 local preview rig: phone + desktop hierarchy and catalogue navigation.
// API calls to api.bainluck.com are fulfilled by curl (session egress) and cached;
// stream endpoints are aborted (they reconnect forever and never settle).
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";

const BASE = process.argv[2] || "http://127.0.0.1:3461";
const OUT = process.argv[3] || "/tmp/d10346/shots";
const CACHE = "/tmp/d10346/apicache";
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(CACHE, { recursive: true });

const pwRoot = fs
  .readdirSync(`${process.env.HOME}/.npm/_npx`)
  .map((h) => `${process.env.HOME}/.npm/_npx/${h}/node_modules/playwright/index.mjs`)
  .find((p) => fs.existsSync(p));
const { chromium } = await import(pwRoot);
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
const args = ["--single-process", "--no-sandbox", "--disable-gpu", "--disable-crashpad", "--disable-dev-shm-usage"];
if (proxy) args.push(`--proxy-server=${proxy}`, "--proxy-bypass-list=127.0.0.1;localhost");
const report = {};

async function open(width, height, url) {
  const browser = await chromium.launch({ args });
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 2, isMobile: width < 500, hasTouch: width < 500 });
  await page.route("**://api.bainluck.com/**", async (route) => {
    const u = route.request().url();
    if (/stream|events\/\d+\/live-sse|\/sse/.test(u)) return route.abort();
    const key = createHash("sha1").update(u).digest("hex");
    const f = `${CACHE}/${key}.json`;
    let body;
    // Cache only: no new production read for this correction.
    if (!fs.existsSync(f)) { (report.misses ||= []).push(u); return route.abort(); }
    body = fs.readFileSync(f);
    return route.fulfill({ status: 200, contentType: "application/json", body, headers: { "access-control-allow-origin": "*" } });
  });
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 240000 });
  // The ordinary consent control, as a reader would use it (Design: judge the unobscured view).
  await page.getByRole("button", { name: /^Accept/ }).first().click({ timeout: 60000 }).then(() => (report.consentClicked = true)).catch(() => {});
  page.done = () => browser.close();
  return page;
}

for (const [name, width, height] of [["phone", 390, 844], ["desktop", 1280, 900]]) {
  const r = (report[name] = {});
  const page = await open(width, height, `${BASE}/events/15319563?highlights=preview`);
  await page.waitForSelector('[data-testid="event-highlights-preview"]', { timeout: 240000 });
  await page.waitForSelector('#all-markets details', { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(2500);
  const hl = page.locator('[data-testid="event-highlights-preview"]');
  await hl.scrollIntoViewIfNeeded();
  await page.evaluate(() => {
    const el = document.querySelector('[data-testid="event-highlights-preview"]');
    window.scrollBy(0, el.getBoundingClientRect().top - 70);
  });
  await page.waitForTimeout(600);
  r.cards = await page.$$eval("[data-highlight-id]", (els) =>
    els.map((e) => ({ id: e.getAttribute("data-highlight-id"), top: Math.round(e.getBoundingClientRect().top), left: Math.round(e.getBoundingClientRect().left), w: Math.round(e.getBoundingClientRect().width), text: e.innerText.replace(/\s+/g, " ") })),
  );
  r.row = await page.$eval('[data-testid="event-highlights-preview"] ol', (ol) => ({ scrollWidth: ol.scrollWidth, clientWidth: ol.clientWidth }));
  r.sectionOrder = await page.evaluate(() => {
    const hl = document.querySelector('[data-testid="event-highlights-preview"]');
    const cat = document.getElementById("all-markets");
    const wp = document.querySelector('[data-testid="win-probability-card"]');
    const y = (el) => (el ? Math.round(el.getBoundingClientRect().top + window.scrollY) : null);
    return { winProbabilityCard: y(wp), highlights: y(hl), catalogue: y(cat), pageHeight: document.body.scrollHeight };
  });
  r.catalogueOpenBefore = await page.$eval("#all-markets details", (d) => d.open).catch(() => "absent");
  await page.screenshot({ path: `${OUT}/10346-${name}-${width}-highlights.png` });
  await hl.screenshot({ path: `${OUT}/10346-${name}-${width}-section.png` });
  r.cardHeights = await page.$$eval("[data-highlight-id]", (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
  if (name === "phone") {
    await page.$eval('[data-testid="event-highlights-preview"] ol', (ol) => ol.scrollBy({ left: ol.clientWidth * 0.85, behavior: "instant" }));
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/10346-${name}-${width}-highlights-swiped.png` });
  }
  await page.click('[data-testid="event-highlights-all-markets"]');
  await page.waitForTimeout(1800);
  r.catalogueOpenAfter = await page.$eval("#all-markets details", (d) => d.open).catch(() => "absent");
  r.catalogueTopAfter = await page.$eval("#all-markets", (e) => Math.round(e.getBoundingClientRect().top)).catch(() => null);
  r.catalogueText = await page.$eval("#all-markets", (e) => e.innerText.replace(/\s+/g, " ").slice(0, 300)).catch(() => null);
  await page.screenshot({ path: `${OUT}/10346-${name}-${width}-after-tap-catalogue.png` });
  await page.done();

  // Control: the same page without the parameter renders no highlights.
  const ctl = await open(width, height, `${BASE}/events/15319563`);
  await ctl.waitForSelector("#all-markets details", { timeout: 240000 }).catch(() => {});
  await ctl.waitForTimeout(2500);
  r.controlHighlights = await ctl.$$eval('[data-testid="event-highlights-preview"]', (e) => e.length);
  r.controlCatalogue = await ctl.$$eval("#all-markets details", (e) => e.length);
  await ctl.done();
}
fs.writeFileSync(`${OUT}/census.json`, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
