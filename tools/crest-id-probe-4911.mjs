#!/usr/bin/env node
/**
 * #4911 — read the crest id actually rendered beside each team name on a live page.
 *
 * The defect is invisible to a screenshot unless you already know which club's crest
 * you are looking at, so pair the rendered NAME with the ESPN id in the <img> src and
 * let the fixture say whether they agree.
 *
 * Usage: node tools/crest-id-probe-4911.mjs <url> [sport]
 */
import { createRequire } from "node:module";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// Playwright lives in the npx cache, not in a node_modules beside us — same resolver
// shop-shot.mjs uses, for the same reason.
function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) {
      const p = `${npx}/${d}/node_modules/`;
      if (existsSync(`${p}playwright`)) return p;
    }
  }
  return `${process.cwd()}/`;
}
const { chromium } = createRequire(findPlaywright())("playwright");

const url = process.argv[2];
const sport = process.argv[3] ?? "mlb";
if (!url) {
  console.error("usage: node tools/crest-id-probe-4911.mjs <url> [sport]");
  process.exit(2);
}

const here = dirname(fileURLToPath(import.meta.url));
const fx = JSON.parse(readFileSync(resolve(here, "../frontend/__tests__/fixtures/espn-team-ids.json"), "utf8"));
const byId = new Map(fx.teams[sport].map((t) => [t.id, t.displayName]));

// Same launch args as shop-shot.mjs — a default multi-process launch is refused by the
// sandbox here (mach port rendezvous, Permission denied), and the browser does not
// inherit the session egress proxy, so production reads come back ERR_ACCESS_DENIED.
const args = ["--no-sandbox", "--single-process", "--disable-gpu", "--disable-crashpad", "--disable-dev-shm-usage"];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const isLoopback = /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/.test(url);
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  // `--proxy-bypass-list=<-loopback>` REMOVES Chromium's built-in localhost bypass, so
  // adding it against a local server sends 127.0.0.1 through the egress proxy and the
  // page never loads. Only production targets want it.
  if (!isLoopback) args.push("--proxy-bypass-list=<-loopback>");
}
const browser = await chromium.launch({ args });
const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
await page.waitForTimeout(2500);

const pairs = await page.evaluate(() => {
  const out = [];
  for (const img of document.querySelectorAll("img")) {
    const m = /\/teamlogos\/([a-z]+)\/\d+\/(\d+)\.png/.exec(img.src || "");
    if (!m) continue;
    // the team name is the nearest following text node of the row
    let el = img.parentElement;
    let name = "";
    for (let i = 0; i < 4 && el && !name; i++, el = el.parentElement) {
      const t = (el.innerText || "").trim().split("\n")[0].trim();
      if (t && t.length < 40) name = t;
    }
    out.push({ sport: m[1], id: m[2], name, natural: img.naturalWidth });
  }
  return out;
});

await browser.close();

let wrong = 0;
const seen = new Set();
for (const p of pairs) {
  if (p.sport !== sport) continue;
  const key = `${p.name}|${p.id}`;
  if (seen.has(key)) continue;
  seen.add(key);
  const draws = byId.get(p.id) ?? `(no such ESPN ${sport} id)`;
  const ok = p.name && draws.toLowerCase().includes(p.name.toLowerCase().split(" ").pop());
  if (!ok) wrong++;
  console.log(`${ok ? "ok  " : "WRONG"} name=${(p.name || "?").padEnd(24)} id=${p.id.padEnd(7)} draws=${draws}  natural=${p.natural}`);
}
console.log(`\n${seen.size} distinct name/crest pairs, ${wrong} mismatched`);
process.exit(wrong > 0 ? 1 : 0);
