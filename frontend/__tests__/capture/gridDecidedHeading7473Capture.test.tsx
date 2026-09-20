/**
 * #7473 CAPTURE — the grid heading, before and after the trophy, side by side.
 *
 * Jest has no layout engine, so the guard test beside this one can prove the
 * WORDS and not the LINE they sit on. This renders the shipped component
 * against the app's own compiled Tailwind into a `file://` page at a 390px
 * phone width, which is where the defect was seen.
 *
 * Both grids are real production output for the same slug, five weeks apart.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import { readPlayoffGrid, type PlayoffGrid as GridModel } from "@/lib/playoffGrid";

const MOCKS = path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open");

/** The app's real compiled Tailwind, so the capture is not a lookalike. */
function appStylesheet(): string {
  const dir = path.join(__dirname, "..", "..", ".next", "static", "css");
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".css"))
      .map((f) => fs.readFileSync(path.join(dir, f), "utf8"))
      .join("\n");
  } catch {
    return "";
  }
}

function gridFor(file: string, draw: string): GridModel {
  const payload = JSON.parse(fs.readFileSync(path.join(MOCKS, file), "utf8"));
  const grid = readPlayoffGrid(payload.grids?.[draw]);
  if (!grid) throw new Error(`${file}/${draw} missing`);
  return grid;
}

const LIVE_MEN = gridFor("payload-2026-08-27.json", "mens-singles");
const DONE_MEN = gridFor("payload-decided-2026-09-20.json", "mens-singles");
const DONE_WOMEN = gridFor("payload-decided-2026-09-20.json", "womens-singles");

describe("#7473 capture", () => {
  it("writes the before/after page", () => {
    const css = appStylesheet();
    expect(css.length).toBeGreaterThan(1000);

    const phone = (caption: string, note: string, body: React.ReactElement) => `
  <div class="col">
    <div class="cap">${caption}</div>
    <div class="phone"><div class="pad">${renderToStaticMarkup(body)}</div></div>
    <div class="sub">${note}</div>
  </div>`;

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>#7473 — the grid heading follows the draw</title>
<style>${css}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .rail{display:flex;gap:22px;justify-content:center;align-items:flex-start;flex-wrap:wrap;padding:20px 16px 40px;max-width:1400px;margin:0 auto}
  .col{width:390px}
  .phone{width:390px;background:#F5F5F7;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;max-height:760px;overflow-y:auto}
  .cap{font:700 11.5px inherit;letter-spacing:.07em;text-transform:uppercase;color:#6B7280;padding:0 2px 7px}
  .sub{padding:9px 2px 0;font-size:11.5px;line-height:1.5;color:#6B7280}
  .pad{padding:16px}
</style></head>
<body>
<div class="rail">
${phone(
  "BEFORE THE FINAL &mdash; 27 August",
  "Nobody has won. The heading is unchanged: a table of percentages headed as a forecast.",
  <PlayoffGrid grid={LIVE_MEN} drawLabel={LIVE_MEN.label} />
)}
${phone(
  "AFTER &mdash; men's, 20 September",
  "Zverev's title cell is settled and noted won, so the same component heads the same table in the past tense.",
  <PlayoffGrid grid={DONE_MEN} drawLabel={DONE_MEN.label} />
)}
${phone(
  "AFTER &mdash; women's, 20 September",
  "A different field, same switch.",
  <PlayoffGrid grid={DONE_WOMEN} drawLabel={DONE_WOMEN.label} />
)}
</div>
</body></html>`;

    const out = path.join(MOCKS, "..", "..", "..", "artifacts", "ux-7473");
    fs.mkdirSync(out, { recursive: true });
    const file = path.join(out, "grid-heading-7473.html");
    fs.writeFileSync(file, html);
    expect(fs.statSync(file).size).toBeGreaterThan(20000);
  });
});
