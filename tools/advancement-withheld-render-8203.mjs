// advancement-withheld-render-8203.mjs — what a CHAMPIONSHIP PATH ladder LOOKS LIKE once a
// rung nobody priced stops printing `0%`. (ux, #8203)
//
// ── WHY A RENDER AND NOT ONLY THE UNIT SUITE ────────────────────────────────────────────────
// `advancementPathWithheldPriceIsNotZero8203.test.tsx` proves the STRINGS and the absence of a
// bar. It renders to static markup, so it is blind to the thing a reader actually meets: a row
// that has lost its number and its bar still occupies a line in a list, and whether that line
// reads as "we don't have this" or as a broken card is a layout fact. It also cannot show that
// a MIXED ladder still lines its labels up, which is the reason the withheld row keeps
// `w-36 shrink-0` instead of #8067's `flex-1`.
//
// Real component, real production CSS: each ladder is server-rendered through the REAL
// `AdvancementPath` and dropped into a page that loads the built stylesheet from
// `.next/static/css`, so the classes resolve to the rules the site ships. It is NOT a
// production page — production is the separate `advancement-rung-price-8203.mjs` run against a
// live event, which answers the DATA question. This answers the layout one.
//
// The controls are in the frame on purpose: a shot of the withheld row alone cannot show that
// a genuine 0% and a 1% still print, and those are the two values this fix must not swallow.
//
// Usage: node tools/advancement-withheld-render-8203.mjs [frontendDir] [outDir]
//        SHOT_W=390 viewport width.
// Exit:  0 rendered and measured, every expectation met · 1 an expectation failed · 2 setup
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
const OUTDIR = process.argv[3] || `${process.env.HOME}/bainluck-dev/ux/artifacts/ux-1458`;
const WIDTH = Number(process.env.SHOT_W || 390);

// `expectNumbered` = how many of the ladder's rungs should print a percentage.
const STATES = [
  {
    name: "the-A's-specimen-withheld-only",
    expectNumbered: 0,
    stages: [{ label: "World Series Champion", prob: null, change: null, resolved: false }],
  },
  {
    name: "mixed-ladder-one-withheld-one-priced",
    expectNumbered: 1,
    stages: [
      { label: "World Series Champion", prob: null, change: null, resolved: false },
      { label: "NL Champion", prob: 0.23, change: 0.021, resolved: false },
    ],
  },
  {
    name: "CONTROL-genuine-zero-still-prints",
    expectNumbered: 1,
    stages: [{ label: "World Series Champion", prob: 0, change: null, resolved: false }],
  },
  {
    name: "CONTROL-one-percent-still-draws-a-bar",
    expectNumbered: 1,
    stages: [{ label: "World Series Champion", prob: 0.01, change: null, resolved: false }],
  },
  {
    name: "CONTROL-clinched-outranks-an-absent-price",
    expectNumbered: 0,
    stages: [{ label: "Make Playoffs", prob: null, change: null, resolved: true }],
  },
  {
    name: "the-full-ladder-a-league-can-serve",
    expectNumbered: 3,
    stages: [
      { label: "Make Playoffs", prob: 0.9972, change: 0.004, resolved: false },
      { label: "Division", prob: null, change: null, resolved: false },
      { label: "AL / NL Champ", prob: 0.1207, change: -0.018, resolved: false },
      { label: "World Series", prob: 0.0545, change: null, resolved: false },
    ],
  },
];

function buildHtml() {
  // Server-render through jest, whose `moduleNameMapper` is the only resolver in this repo
  // that understands the `@/` alias — so the module graph here is the one the suite and the
  // app compile against. Written, run and deleted, and it lives OUTSIDE `__tests__/` so a
  // crash that leaves it behind cannot move the committed test count.
  const harness = `${FRONTEND}/ap8203harness.test.tsx`;
  const dump = `${FRONTEND}/.ap8203-rendered.json`;
  writeFileSync(
    harness,
    `
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { writeFileSync } from "fs";
import AdvancementPath from "@/components/event/AdvancementPath";
const STATES: any[] = ${JSON.stringify(STATES)};
test("render the #8203 ladder states for the layout probe", () => {
  const out = STATES.map((s) => ({
    name: s.name,
    html: renderToStaticMarkup(
      React.createElement(AdvancementPath, { stages: s.stages } as any),
    ),
  }));
  writeFileSync(${JSON.stringify(dump)}, JSON.stringify(out));
  expect(out.length).toBe(STATES.length);
});
`,
  );
  let rendered;
  try {
    execFileSync(
      "npx",
      ["jest", "--silent", "--rootDir", ".", "--testMatch", "**/ap8203harness.test.tsx"],
      { cwd: FRONTEND, encoding: "utf8", stdio: "pipe", maxBuffer: 1 << 24 },
    );
    rendered = JSON.parse(readFileSync(dump, "utf8"));
  } finally {
    try {
      execFileSync("rm", ["-f", harness, dump]);
    } catch {}
  }

  const cssDir = `${FRONTEND}/.next/static/css`;
  const css = readdirSync(cssDir)
    .map((f) => `<link rel="stylesheet" href="file://${cssDir}/${f}">`)
    .join("\n");

  const cards = rendered
    .map(
      (r) =>
        `<section data-state="${r.name}" style="padding:10px 14px;border-bottom:1px solid #eee">
       <div style="font:600 10px system-ui;color:#999;margin-bottom:6px">${r.name}</div>
       <div data-ladder>${r.html}</div>
     </section>`,
    )
    .join("\n");

  return `<!doctype html><html><head><meta charset="utf-8">${css}
    <style>body{margin:0;background:#fff;width:${WIDTH}px}</style></head>
    <body>${cards}</body></html>`;
}

(async () => {
  mkdirSync(OUTDIR, { recursive: true });
  const html = buildHtml();
  const page404 = `${OUTDIR}/.ap8203.html`;
  writeFileSync(page404, html);

  // `--single-process` is the load-bearing flag in this sandbox (ux/1457 §5), and a file://
  // target must NOT get the proxy args or the page renders an SSL error as text.
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--single-process", "--disable-gpu", "--disable-crashpad"],
  });
  const page = await browser.newPage({
    viewport: { width: WIDTH, height: 900 },
    deviceScaleFactor: 2,
  });
  await page.goto(`file://${page404}`, { waitUntil: "load" });
  await page.waitForTimeout(300);

  const out = { width: WIDTH, states: [], problems: [] };
  for (const s of STATES) {
    const m = await page.evaluate((name) => {
      const sec = document.querySelector(`[data-state="${name}"]`);
      const rows = [...sec.querySelectorAll('[data-testid="advancement-stage"]')];
      return {
        rows: rows.map((r) => {
          const label = r.querySelector("div");
          const fill = r.querySelector('div[style*="width"]');
          const text = (r.textContent || "").trim();
          const stage = r.getAttribute("data-stage") || "";
          return {
            stage,
            readout: text.startsWith(stage) ? text.slice(stage.length).trim() : text,
            labelWidth: Math.round(label.getBoundingClientRect().width),
            hasBar: !!fill,
            barWidth: fill ? Math.round(fill.getBoundingClientRect().width) : null,
            right: Math.round(r.getBoundingClientRect().right),
          };
        }),
        heading: (sec.querySelector("div[class*=uppercase]") || {}).textContent || null,
      };
    }, s.name);

    const numbered = m.rows.filter((r) => /\d\s*%/.test(r.readout)).length;
    const entry = { name: s.name, expectNumbered: s.expectNumbered, numbered, ...m };
    out.states.push(entry);

    if (numbered !== s.expectNumbered) {
      out.problems.push(`${s.name}: ${numbered} rungs print a percentage, expected ${s.expectNumbered}`);
    }
    // Every row must stay inside the viewport — a label that widened on the unpriced rows
    // would show up here first.
    for (const r of m.rows) {
      if (r.right > WIDTH) out.problems.push(`${s.name}/${r.stage}: row crosses ${WIDTH}px (right ${r.right})`);
    }
    // The alignment claim: within one ladder, every label column is the same width.
    const widths = new Set(m.rows.map((r) => r.labelWidth));
    if (widths.size > 1) {
      out.problems.push(`${s.name}: label columns disagree (${[...widths].join(", ")}px) — a mixed ladder is ragged`);
    }
  }

  // The 1% control must draw a bar a reader can SEE, not a hairline rounded to nothing.
  const onePct = out.states.find((s) => s.name === "CONTROL-one-percent-still-draws-a-bar");
  if (!onePct.rows[0].hasBar || onePct.rows[0].barWidth < 1) {
    out.problems.push("the 1% control draws no visible bar");
  }

  const shot = `${OUTDIR}/AFTER-advancement-withheld-390.png`;
  await page.screenshot({ path: shot, fullPage: true });
  out.shot = shot;

  console.log(JSON.stringify(out, null, 2));
  await browser.close();
  process.exit(out.problems.length ? 1 : 0);
})();
