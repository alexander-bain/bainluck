// #7112 after-check — a venue-graded match is not counted under "Live & Paused".
//
//   node tools/ux1348-settled-not-live-7112.mjs [league-path]
//   default: /sports/tennis_atp
//
// Exit 0 = PAID · 3 = the defect is still on production · 4 = UNPAID, the page
// holds no graded row so there is nothing to find (NOT a pass) · 5 = could not
// read the page.
//
// 🔴 WHY IT READS THE MARKUP AND NOT THE PAYLOAD. The defect is a disagreement
// between the card's sentence and the heading above it. Both come from modules
// that never meet until the rendered page, so the payload cannot show it and
// neither can a unit test. The probe reads the section headings and the
// `Settled · …` sentences out of the same DOM, exactly as the jest capture arm
// reads them out of the same markup string.
//
// 🔴 EXIT 4 IS THE ROTATION TRAP. The graded rows on a tour page age out within
// a day. A run that finds no `Settled · …` card has checked NOTHING; it must
// not print green. Same family as ux/1347's specimen-bound after-check.
//
// 🪤 Node's global `fetch` has no egress in a lane shell, and so does
// `page.request`. Only the page context does — hence playwright, resolved the
// way `~/bainluck/tools/shop-shot.mjs` resolves it, with the same sandbox and
// proxy launch args.

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

const path = process.argv[2] || "/sports/tennis_atp";
const url = `https://bainluck.com${path}`;
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
const args = ["--single-process"];
if (proxy) args.push(`--proxy-server=${proxy}`, "--proxy-bypass-list=<-loopback>");

const browser = await chromium.launch({ args });
let code = 5;
try {
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  // NOT `networkidle` — a league page with a live match polls forever.
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForSelector("[data-league-section]", { timeout: 30000 });
  await page.waitForTimeout(2000);

  const read = await page.evaluate(() => {
    const out = [];
    for (const sec of document.querySelectorAll("[data-league-section]")) {
      const heading = sec.querySelector("[data-league-section-title]");
      const cards = [...sec.querySelectorAll('a[href^="/events/"]')].map((a) => ({
        id: a.getAttribute("href").split("/").pop(),
        settled: /Settled\s*·/.test(a.textContent || ""),
        text: (a.textContent || "").replace(/\s+/g, " ").trim().slice(0, 70),
      }));
      out.push({
        key: sec.getAttribute("data-league-section"),
        title: (heading?.textContent || "").replace(/\s+/g, " ").trim(),
        cards,
      });
    }
    return out;
  });

  console.log(`url=${url} width=390`);
  for (const s of read) {
    console.log(`  [${s.key}] ${s.title}  (${s.cards.length} cards)`);
    for (const c of s.cards.filter((c) => c.settled)) {
      console.log(`      Settled card ${c.id}: ${c.text}`);
    }
  }

  const settled = read.flatMap((s) => s.cards.filter((c) => c.settled).map((c) => ({ ...c, sec: s })));
  console.log(`\nsections: ${read.length}   settled cards on the page: ${settled.length}`);

  if (settled.length === 0) {
    console.log(
      "\nUNPAID — no card on this page prints 'Settled · …', so nothing was checked.\n" +
        "The graded rows rotate out within a day. Find a league that has one (a tour page\n" +
        "a few hours after its last match) and re-run. This is NOT a pass.",
    );
    code = 4;
  } else {
    const misfiled = settled.filter((c) => c.sec.key !== "finished");
    if (misfiled.length > 0) {
      console.log(
        `\n🔴 OFFENDERS=${misfiled.length}/${settled.length} settled cards are NOT under Finished:`,
      );
      for (const c of misfiled) console.log(`   ${c.id} sits under "${c.sec.title}"`);
      code = 3;
    } else {
      const live = read.find((s) => s.key === "live");
      console.log(
        `\nVERDICT: all ${settled.length} settled cards are under Finished.` +
          (live ? `  Live heading reads "${live.title}".` : "  No live section on the page."),
      );
      code = 0;
    }
  }
} catch (err) {
  console.error(`could not read the page: ${err.message}`);
  code = 5;
} finally {
  await browser.close();
}
process.exit(code);
