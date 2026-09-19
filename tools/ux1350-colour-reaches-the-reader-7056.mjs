#!/usr/bin/env node
/**
 * #7056 / #4040 — does the restored palette actually reach a READER?
 *
 * The built-CSS census (`ux1350-dead-palette-census-7056.mjs`) proves the rules
 * exist in the stylesheet. That is necessary and not sufficient: a rule can be
 * present and still lose to specificity, or sit on an element nobody renders.
 * This probe asks the rendered DOM instead — for every element wearing an
 * `emerald`/`amber`/`slate` numeric utility, what colour does the browser
 * ACTUALLY compute?
 *
 * 🪤 Why not just read a screenshot: an element with no background is not
 * visibly distinguishable from one whose background is the same as its parent's,
 * and at 390px a 1px border is a downscale artifact away from invisible. The
 * computed style is the only thing that answers "did this element get its
 * colour" without an eyeball judgement call.
 *
 * Usage:
 *   node tools/ux1350-colour-reaches-the-reader-7056.mjs <url> [url...]
 *
 * exit 0 = every such element computes a real colour        (FIXED)
 * exit 3 = at least one computes none / fully transparent   (DEFECT)
 * exit 4 = no element wearing those classes was found on any page — NOTHING
 *          WAS CHECKED. Not a pass: pick a page that renders them.
 */
import { createRequire } from "module";
import { existsSync, readdirSync } from "fs";

function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) {
      const p = `${npx}/${d}/node_modules/`;
      if (existsSync(`${p}playwright`)) return p;
    }
  }
  return process.cwd() + "/";
}
const { chromium } = createRequire(findPlaywright())("playwright");

// The palette to compare against. Tailwind lives in the frontend tree, not
// beside this script, so resolve it from there explicitly — a bare import is
// ERR_MODULE_NOT_FOUND and reads as "the tool is broken".
let defaultColours;
try {
  defaultColours = createRequire(`${process.cwd()}/frontend/`)("tailwindcss/colors");
} catch {
  try {
    defaultColours = createRequire(import.meta.url)("tailwindcss/colors");
  } catch {
    console.error(
      "exit 2: cannot resolve tailwindcss/colors — run this from the repo root " +
        "(it reads frontend/node_modules). Without the palette there is nothing " +
        "to compare computed colours against and the probe would pass vacuously.",
    );
    process.exit(2);
  }
}

const urls = process.argv.slice(2);
if (urls.length === 0) {
  console.error("usage: node tools/ux1350-colour-reaches-the-reader-7056.mjs <url> [...]");
  process.exit(2);
}

const args = ["--single-process", "--no-sandbox"];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
// 🪤 The proxy is needed even when the URL is localhost. A locally served page
// is the whole point of the AFTER frame, but the page itself then calls
// `api.bainluck.com` for its data — so dropping the proxy for a loopback URL
// silently produces an EMPTY page, the probe finds no element wearing the
// class, and exit 4 reads as "nothing to check" when the truth is "nothing
// loaded". Always proxy; always bypass loopback so the page itself is direct.
if (proxy) {
  args.push(`--proxy-server=${proxy}`, "--proxy-bypass-list=localhost,127.0.0.1");
}

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });

/**
 * 🪤 "IS IT BLANK" IS THE WRONG QUESTION FOR HALF THESE UTILITIES.
 *
 * A dead BACKGROUND utility computes `rgba(0,0,0,0)` — visibly nothing, easy to
 * detect. A dead TEXT or FILL utility does not: the element simply INHERITS,
 * so `text-amber-500` on a dead palette computes `rgb(17,24,39)` — the page's
 * ordinary near-black. That is a real colour, so a blankness test calls it
 * "painted" and the probe reports a pass over the exact defect it exists to
 * find. Measured on production: `text-amber-500` read `rgb(17,24,39)` and the
 * first cut of this probe scored it green.
 *
 * So the test is EQUALITY WITH THE PALETTE, not non-blankness: the class names
 * a family and a rung, Tailwind defines exactly one colour for that pair, and
 * the element either computes it or it does not.
 */
const EXPECTED = (family, rung) => {
  const hex = defaultColours?.[family]?.[rung];
  if (!hex || !/^#[0-9a-f]{6}$/i.test(hex)) return null;
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
};

/** Pull the r,g,b out of `rgb(a b c)` / `rgba(a, b, c, d)` in any spelling. */
const rgbOf = (v) => {
  const m = String(v || "").match(/-?[\d.]+/g);
  return m && m.length >= 3 ? m.slice(0, 3).map(Number) : null;
};

/** Alpha of a computed colour; 1 when unstated. */
const alphaOf = (v) => {
  const m = String(v || "").match(/-?[\d.]+/g);
  return m && m.length >= 4 ? Number(m[3]) : 1;
};

let totalFound = 0;
let totalBlank = 0;

for (const url of urls) {
  let rows;
  try {
    await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForTimeout(1500);
    rows = await page.evaluate(() => {
      const FAM = /\b(bg|text|border|ring|from|via|to|divide|fill|stroke)-(emerald|amber|slate)-(\d{2,3})\b/;
      const out = [];
      for (const el of document.querySelectorAll("*")) {
        const cls = typeof el.className === "string" ? el.className : el.className?.baseVal || "";
        const m = cls.match(FAM);
        if (!m) continue;
        const cs = getComputedStyle(el);
        out.push({
          cls: m[0],
          util: m[1],
          family: m[2],
          rung: m[3],
          bg: cs.backgroundColor,
          fg: cs.color,
          border: cs.borderTopColor,
          bw: cs.borderTopWidth,
          fill: cs.fill,
          text: (el.textContent || "").trim().slice(0, 40),
        });
      }
      return out;
    });
  } catch (err) {
    console.error(`  !! ${url}: ${err.message}`);
    continue;
  }

  console.log(`\n=== ${url} — ${rows.length} element(s) wearing a restored utility`);
  for (const r of rows) {
    // Judge the property the utility actually sets, not all of them.
    const value =
      r.util === "bg" ? r.bg
      : r.util === "text" ? r.fg
      : r.util === "border" ? r.border
      : r.util === "fill" ? r.fill
      : r.bg;

    const want = EXPECTED(r.family, r.rung);
    const got = rgbOf(value);
    let bad, note;

    if (!want) {
      // Not a family/rung Tailwind defines — nothing to compare against, so
      // say so rather than scoring it either way.
      [bad, note] = [false, "no palette entry — not judged"];
    } else if (!got) {
      [bad, note] = [true, `expected rgb(${want}), got ${value}`];
    } else if (alphaOf(value) === 0 && r.util === "bg") {
      // A fully transparent background is the classic dead-utility signature.
      [bad, note] = [true, `expected rgb(${want}), got ${value} (alpha 0)`];
    } else if (want.some((c, i) => Math.abs(c - got[i]) > 1)) {
      // Off-palette: the element inherited or was overridden. This is the case
      // a blankness test misses entirely.
      [bad, note] = [true, `expected rgb(${want}), got ${value}`];
    } else {
      [bad, note] = [false, value];
    }

    totalFound += 1;
    if (bad) totalBlank += 1;
    console.log(`  ${bad ? "DEAD   " : "painted"}  ${r.cls.padEnd(22)} ${String(note).padEnd(46)} ${r.text}`);
  }
}

await browser.close();

console.log(`\n${totalFound} element(s) checked, ${totalBlank} painting nothing`);
if (totalFound === 0) {
  console.error("exit 4: no element wore a restored utility on any page given — NOTHING WAS CHECKED.");
  process.exit(4);
}
if (totalBlank > 0) {
  console.error("exit 3: DEFECT — an element wears the class and computes no colour");
  process.exit(3);
}
console.log("exit 0: every element wearing a restored utility computes a real colour");
process.exit(0);
