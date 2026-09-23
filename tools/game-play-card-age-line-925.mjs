// game-play-card-age-line-925.mjs — does the #925 "as of" line FIT the scrub readout
// at phone width, and does it appear only when the readout is actually carried? (ux, #925)
//
// ── WHY A RENDER PROBE AND NOT ANOTHER UNIT TEST ─────────────────────────────────────────
// `independentStateClocks925.test.tsx` proves the STRINGS: which badge text, which age, when
// no age at all. It renders to static markup, so it is blind to the only thing that can go
// wrong once the strings are right — the age line is a THIRD row added to a
// `shrink-0 flex flex-col` column that already holds the badge and the time-of-day, and it
// sits in a `flex` row beside the score and the probability sentence on a 390px phone. Whether
// that column grows, wraps, or squeezes the sentence beside it is a layout-engine fact, so ask
// the layout engine. (ux/1456 §4: a pure-string fix owes a render when it changes the string's
// LENGTH; this one adds a whole line.)
//
// Real component, real production CSS: the card is server-rendered through React and dropped
// into a page that loads the built stylesheet from `.next/static/css`, so the classes resolve
// to the same rules the site ships. It is NOT a production page — the scrub readout only exists
// under a pointer on a live chart, and a camera cannot photograph a hover (ux/1441). What this
// answers is the layout question; what production answers is the data question, and the two are
// deliberately separate runs.
//
// Read from getBoundingClientRect, never from pixels:
//   * the badge column  -> did the new row change its width (a wrap shows up as a jump)
//   * the card root     -> does anything now cross the 390px viewport edge
//   * the age line      -> is it present, and on which states
//
// Exit: 0 all states fit and the age line appears exactly where expected · 1 a state
//       overflows or the age line is on the wrong states · 2 bad usage/setup
import { createRequire } from "module";
import { existsSync, readdirSync, mkdirSync, writeFileSync, readFileSync } from "fs";
import { execFileSync } from "child_process";

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

const FRONTEND = process.argv[2] || `${process.env.HOME}/bainluck-dev/ux/frontend`;
const OUTDIR = process.argv[3] || `${process.env.HOME}/bainluck-dev/ux/artifacts/ux-1457`;
const WIDTH = Number(process.env.SHOT_W || 390);

// The five states the card can be in, as ActiveChartPoint props. Names are the verdicts.
const STATES = [
  { name: "exact-both-observed", expectAge: false, point: {
      timestamp: "2026-09-22T20:03:00Z", homeProb: 0.62, awayProb: 0.38,
      homeScore: 101, awayScore: 98, period: "4", clock: "1:09",
      clockApprox: false, periodApprox: false,
      clockObservedAt: "2026-09-22T20:03:00Z", periodObservedAt: "2026-09-22T20:03:00Z" } },
  { name: "clock-carried-period-fresh", expectAge: true, point: {
      timestamp: "2026-09-22T20:03:00Z", homeProb: 0.62, awayProb: 0.38,
      homeScore: 101, awayScore: 98, period: "4", clock: "1:09",
      clockApprox: true, periodApprox: false,
      clockObservedAt: "2026-09-22T20:00:00Z", periodObservedAt: "2026-09-22T20:03:00Z" } },
  { name: "period-carried-clock-fresh", expectAge: true, point: {
      timestamp: "2026-09-22T20:03:00Z", homeProb: 0.62, awayProb: 0.38,
      homeScore: 101, awayScore: 98, period: "4", clock: "0:41",
      clockApprox: false, periodApprox: true,
      clockObservedAt: "2026-09-22T20:03:00Z", periodObservedAt: "2026-09-22T19:58:00Z" } },
  { name: "both-carried", expectAge: true, point: {
      timestamp: "2026-09-22T20:03:00Z", homeProb: 0.62, awayProb: 0.38,
      homeScore: 101, awayScore: 98, period: "4", clock: "1:09",
      clockApprox: true, periodApprox: true,
      clockObservedAt: "2026-09-22T20:00:00Z", periodObservedAt: "2026-09-22T20:00:00Z" } },
  // The longest string this card can produce: a spelled-out baseball half-inning with a
  // tilde, a score, and the age line, on the narrowest phone. If anything shears, here.
  { name: "baseball-period-only-carried", expectAge: true, sportKey: "baseball_mlb", point: {
      timestamp: "2026-09-22T20:12:00Z", homeProb: 0.55, awayProb: 0.45,
      homeScore: 10, awayScore: 8, period: "Top 8th", clock: null,
      clockApprox: false, periodApprox: true,
      clockObservedAt: null, periodObservedAt: "2026-09-22T19:58:00Z" } },
];

function buildHtml() {
  // Server-render each state through the REAL component. The renderer is jest: its
  // `moduleNameMapper` is the only configured resolver in this repo that understands the
  // `@/` alias (tsconfig declares `paths` but no `baseUrl`, so `tsconfig-paths` skips it and
  // ts-node cannot load the component's own imports). Reusing the suite's resolver means the
  // module graph here is byte-for-byte the one the tests and the app compile against.
  //
  // The harness is written, run and deleted. It lives OUTSIDE `__tests__/`, so even if a crash
  // leaves it behind, the committed suite's `testMatch` cannot pick it up and no test count moves.
  const harness = `${FRONTEND}/gpc925harness.test.tsx`;
  const dump = `${FRONTEND}/.gpc925-rendered.json`;
  writeFileSync(harness, `
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { writeFileSync } from "fs";
import GamePlayCard from "@/components/GamePlayCard";
const STATES: any[] = ${JSON.stringify(STATES)};
test("render the #925 card states for the layout probe", () => {
  const out = STATES.map((s) => ({
    name: s.name,
    html: renderToStaticMarkup(
      React.createElement(GamePlayCard, {
        activePoint: s.point,
        homeTeam: "Boston Celtics",
        awayTeam: "Oklahoma City Thunder",
        sportKey: s.sportKey || "basketball_nba",
      } as any),
    ),
  }));
  writeFileSync(${JSON.stringify(dump)}, JSON.stringify(out));
  expect(out.length).toBe(STATES.length);
});
`);
  let rendered;
  try {
    execFileSync("npx", ["jest", "--silent", "--rootDir", ".",
                         "--testMatch", "**/gpc925harness.test.tsx"],
                 { cwd: FRONTEND, encoding: "utf8", stdio: "pipe", maxBuffer: 1 << 24 });
    rendered = JSON.parse(readFileSync(dump, "utf8"));
  } finally {
    try { execFileSync("rm", ["-f", harness, dump]); } catch {}
  }

  const cssDir = `${FRONTEND}/.next/static/css`;
  const css = readdirSync(cssDir)
    .map((f) => `<link rel="stylesheet" href="file://${cssDir}/${f}">`)
    .join("\n");

  const cards = rendered.map((r) =>
    `<section data-state="${r.name}" style="padding:8px 12px;border-bottom:1px solid #eee">
       <div style="font:600 10px system-ui;color:#999;margin-bottom:2px">${r.name}</div>
       <div data-card>${r.html}</div>
     </section>`).join("\n");

  return `<!doctype html><html><head><meta charset="utf-8">${css}
    <style>body{margin:0;background:#fff;width:${WIDTH}px}</style></head>
    <body>${cards}</body></html>`;
}

(async () => {
  mkdirSync(OUTDIR, { recursive: true });
  const html = buildHtml();
  const htmlPath = `${OUTDIR}/gpc-925-states.html`;
  writeFileSync(htmlPath, html);

  // `--single-process` is the load-bearing one: a bare `chromium.launch()` dies in the agent
  // sandbox on `bootstrap_check_in ... Permission denied (1100)` before a page exists, and
  // `dangerouslyDisableSandbox` does NOT help (measured both ways here). No proxy args — the
  // target is a `file://` URL, and shop-shot's `<-loopback>` bypass would send it through the
  // egress proxy and render an SSL error as page text.
  const browser = await chromium.launch({
    args: ["--no-sandbox", "--single-process", "--disable-gpu",
           "--disable-crashpad", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage({ viewport: { width: WIDTH, height: 900 },
                                       deviceScaleFactor: 2 });
  await page.goto(`file://${htmlPath}`, { waitUntil: "load" });

  const measured = await page.evaluate((vw) => {
    return [...document.querySelectorAll("section[data-state]")].map((s) => {
      const badgeCol = s.querySelector(".flex-col");
      const ageLine = s.querySelector('[data-testid="game-play-card-state-as-of"]');
      const card = s.querySelector("[data-card] > div");
      const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect();
        return { left: +b.left.toFixed(1), right: +b.right.toFixed(1),
                 width: +b.width.toFixed(1), height: +b.height.toFixed(1) }; };
      return {
        state: s.getAttribute("data-state"),
        badgeText: s.querySelector(".bg-surface-secondary")?.textContent?.trim() ?? null,
        ageText: ageLine?.textContent?.trim() ?? null,
        badgeCol: r(badgeCol), card: r(card),
        overflowsRight: card ? +(card.getBoundingClientRect().right - vw).toFixed(1) : null,
      };
    });
  }, WIDTH);

  await page.screenshot({ path: `${OUTDIR}/gpc-925-states-${WIDTH}.png`, fullPage: true });
  await browser.close();

  const problems = [];
  for (let i = 0; i < measured.length; i++) {
    const m = measured[i], want = STATES[i].expectAge;
    if (want && !m.ageText) problems.push(`${m.state}: expected an age line, none rendered`);
    if (!want && m.ageText) problems.push(`${m.state}: age line on an exact readout (${m.ageText})`);
    if (m.overflowsRight > 0) problems.push(`${m.state}: card overflows ${m.overflowsRight}px past ${WIDTH}px`);
  }
  const out = { width: WIDTH, screenshot: `${OUTDIR}/gpc-925-states-${WIDTH}.png`,
                measured, problems };
  console.log(JSON.stringify(out, null, 2));
  process.exit(problems.length ? 1 : 0);
})().catch((e) => { console.error(String(e?.stack || e)); process.exit(2); });
