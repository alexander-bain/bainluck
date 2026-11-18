// 227-A point 6: capture the week's ten phone screens for /grade/screens.
//
//   node tools/ranking/capture_screens.mjs --base https://www.bainluck.com --week 2026-w47 --out DIR
//
// For each sampled page and scroll position: a 390x844 picture at 2x
// (`screen-NN.png`) and the counts 227-A names for that one screen, measured
// from the drawn page:
//   pictures      images (crests up: >= 20 px, mostly on screen) plus charts (svg/canvas >= 120x60)
//   forms         the `data-card-form` of each card on screen, top to bottom
//   longest_run   most consecutive cards in one form (point 2)
//   form_count    distinct forms on screen (point 3)
//   kinds         content kinds on screen and the largest kind's share (point 4)
// A page whose cards carry no `data-card-form` reports forms as null (unknown),
// never a guess. Writes DIR/manifest.json; nothing is uploaded or committed here.
//
// Public pages only, read signed out. Playwright from the repo's frontend
// node_modules (or PLAYWRIGHT_MODULE); a headless shell via CHROMIUM_PATH.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const arg = (name, dflt) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : dflt;
};
const BASE = arg("base", "https://www.bainluck.com").replace(/\/$/, "");
const WEEK = arg("week");
const OUT = arg("out");  // required: no default folder (CodeQL js/insecure-temporary-file)

// The pool: every surface 227-A counts. The week seeds which screen of each page is taken.
export const POOL = [
  { page: "/", screens: [0, 1, 2, 4] },
  { page: "/sports", screens: [0, 1] },
  { page: "/politics", screens: [0, 1] },
  { page: "/economics", screens: [0] },
  { page: "/entertainment", screens: [0] },
  { page: "/weather", screens: [0] },
  { page: "/search?q=Chiefs", screens: [0] },
  { page: "/search?q=Taylor%20Swift", screens: [0] },
];

function seeded(week) {
  let h = 2166136261;
  for (const c of week) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0;
  return () => ((h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0), h / 2 ** 32);
}

/** Ten (page, screen) picks: Discover's first screen always, the rest drawn by the week's seed. */
export function sample(week, n = 10) {
  const rnd = seeded(week);
  const all = POOL.flatMap((p) => p.screens.map((s) => ({ page: p.page, screen: s })));
  const first = all.find((x) => x.page === "/" && x.screen === 0);
  const rest = all.filter((x) => x !== first).sort(() => rnd() - 0.5);
  return [first, ...rest].slice(0, n);
}

export function kindOf(form) {
  if (form === "game" || form === "roundup:coin_flip_matchups" || form === "roundup:matchup_slate") return "games";
  if (form === "group") return "grouped";
  return "futures";
}

export function countForms(forms) {
  if (forms === null) return { longest_run: null, form_count: null, kinds: null };
  let run = 0, best = 0, prev = null;
  for (const f of forms) {
    run = f === prev ? run + 1 : 1;
    best = Math.max(best, run);
    prev = f;
  }
  const tally = {};
  for (const f of forms) tally[kindOf(f)] = (tally[kindOf(f)] || 0) + 1;
  const largest = forms.length ? Math.max(...Object.values(tally)) / forms.length : 0;
  return { longest_run: best, form_count: new Set(forms).size, kinds: { tally, largest_share: Math.round(largest * 100) / 100 } };
}

async function main() {
  if (!/^\d{4}-w\d{2}$/.test(WEEK || "")) {
    console.error("--week YYYY-wNN is required");
    process.exit(2);
  }
  if (!OUT) {
    console.error("--out DIR is required");
    process.exit(2);
  }
  const require = createRequire(import.meta.url);
  const pw = require(process.env.PLAYWRIGHT_MODULE || path.resolve("frontend/node_modules/playwright"));
  const args = ["--single-process", "--disable-crashpad", "--disable-gpu", "--no-sandbox"];
  if (process.env.HTTPS_PROXY) args.push(`--proxy-server=${process.env.HTTPS_PROXY}`);
  const browser = await pw.chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH, args });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  fs.mkdirSync(OUT, { recursive: true });
  const manifest = [];
  const picks = sample(WEEK);
  for (const [i, pick] of picks.entries()) {
    const page = await ctx.newPage();
    await page.goto(BASE + pick.page, { waitUntil: "domcontentloaded", timeout: 90000 });
    const decline = await page.waitForSelector("text=Decline", { timeout: 8000 }).catch(() => null);
    if (decline) await decline.click();
    await page.waitForTimeout(6000);
    await page.evaluate((y) => window.scrollTo(0, y), pick.screen * 844);
    await page.waitForTimeout(2500);
    const file = `screen-${String(i + 1).padStart(2, "0")}.png`;
    await page.screenshot({ path: path.join(OUT, file) });
    const measured = await page.evaluate(() => {
      const H = window.innerHeight;
      const onScreen = (r) => r.bottom > 0 && r.top < H && Math.min(r.bottom, H) - Math.max(r.top, 0) >= r.height / 2;
      let pictures = 0;
      for (const el of document.querySelectorAll("img")) {
        const r = el.getBoundingClientRect();
        if (el.naturalWidth > 0 && r.width >= 20 && r.height >= 20 && onScreen(r)) pictures++;
      }
      for (const el of document.querySelectorAll("svg, canvas")) {
        const r = el.getBoundingClientRect();
        if (r.width >= 120 && r.height >= 60 && onScreen(r)) pictures++;
      }
      const cards = [...document.querySelectorAll("[data-card-form]")]
        .map((el) => ({ form: el.getAttribute("data-card-form"), r: el.getBoundingClientRect() }))
        .filter(({ r }) => r.bottom > 0 && r.top < H)
        .sort((a, b) => a.r.top - b.r.top);
      return { pictures, forms: cards.length ? cards.map((c) => c.form) : null };
    });
    manifest.push({ n: i + 1, page: pick.page, screen: pick.screen, file, counts: { pictures: measured.pictures, forms: measured.forms, ...countForms(measured.forms) } });
    console.log(`${i + 1}. ${pick.page} screen ${pick.screen + 1}: ${measured.pictures} pictures, forms ${JSON.stringify(measured.forms)}`);
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify({ week: WEEK, base: BASE, screens: manifest }, null, 2) + "\n");
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
