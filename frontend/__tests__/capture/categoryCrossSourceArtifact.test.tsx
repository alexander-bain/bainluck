/**
 * UX-P194 artifact rig — renders
 * `artifacts-ux-p194/category-cross-source-states.html`.
 *
 * Two pages, two panels each, all from the real shipped component and one
 * verbatim production payload (`backend/tests/fixtures/uxp194_category_cross_source.json`):
 *
 *   BEFORE  what `/economics` and `/entertainment` actually showed: nothing.
 *           The panel lists the eight rows each route SERVED and the page
 *           discarded, annotated with whether the pair survives UX-P187's
 *           alignment — i.e. whether the number was ever a disagreement.
 *   AFTER   the shipped `CrossSourceSpotlight`, fed the rows that survive.
 *
 * The rig asserts its own output. An artifact that silently captured the wrong
 * thing is worse than no artifact.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import type { CrossSourceMatch } from "@/lib/api";

/* eslint-disable @typescript-eslint/no-var-requires */
const { CrossSourceSpotlight } = require("@/components/crossSource/CrossSourceSpotlight");
/* eslint-enable @typescript-eslint/no-var-requires */

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const OUT = path.join(REPO, "artifacts-ux-p194");

const banked = JSON.parse(
  fs.readFileSync(
    path.join(REPO, "backend", "tests", "fixtures", "uxp194_category_cross_source.json"),
    "utf8",
  ),
);

type Aligned = { outcome: string; kalshi: number; poly: number; delta: number };
type BankedRow = CrossSourceMatch & { _aligned: Aligned | null };

const esc = (v: string): string =>
  v.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function rowsFor(page: string): BankedRow[] {
  return banked.pages[page].rows as BankedRow[];
}

function alignedFor(page: string): CrossSourceMatch[] {
  return rowsFor(page)
    .filter((r) => r._aligned)
    .map((r) => ({ ...r, ...r._aligned! }));
}

function beforePanel(page: string): string {
  const items = rowsFor(page)
    .map((r) => {
      const note = r._aligned
        ? `<span class="ok">real — both sides price <b>${esc(r._aligned.outcome)}</b>,
           and the gap is ${r._aligned.delta.toFixed(1)}pp</span>`
        : `<span class="bad">not a disagreement — the two sources share no outcome,
           so the served ${r.delta.toFixed(1)}pp is arithmetic on unrelated quantities</span>`;
      return `<li><b>${esc(r.q)}</b> — served Kalshi ${r.kalshi}% / Polymarket
        ${r.poly}%<br>${note}</li>`;
    })
    .join("");
  return `<section><h2>Before — /${esc(page)} showed none of this</h2>
    <p class="blurb">The route computed all eight rows on every precompute.
    <code>${esc(page === "economics" ? "EconData" : "EntertainmentData")}</code>
    never declared <code>cross_source</code>, so the field could not reach the
    page even in principle.</p>
    <ol class="served">${items}</ol></section>`;
}

function afterPanel(page: string): string {
  const matches = alignedFor(page);
  return `<section><h2>After — /${esc(page)} renders the rows that are real</h2>
    <p class="blurb">The shipped component, fed the
    <b>${matches.length}</b> of eight that survive UX-P187's alignment. Each
    card names the one outcome both numbers price.</p>
    <div class="grid">${renderToStaticMarkup(
      React.createElement(CrossSourceSpotlight, { matches }),
    )}</div></section>`;
}

describe("UX-P194 artifact — the card reaches economics and entertainment", () => {
  let html = "";

  beforeAll(() => {
    html = `<!doctype html><meta charset="utf-8">
<title>UX-P194 — cross-source on the other two category pages</title>
<style>
 body{font:14px/1.5 -apple-system,system-ui,sans-serif;margin:32px;background:#FAFAFC;color:#111827}
 h1{font-size:20px} h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:#6B7280}
 .blurb{max-width:78ch;color:#374151}
 .served{max-width:78ch;color:#374151;font-size:13px} .served li{margin-bottom:8px}
 .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:12px 0 32px}
 .section{margin:12px 0 32px} .sectionTitle{font-size:15px}
 .crossCard{background:#fff;border:1px solid #E5E7EB;border-radius:10px;padding:12px 14px;
            display:flex;flex-direction:column;gap:10px}
 .sourceCellKalshi,.sourceCellPoly{background:#F5F5F7;border-radius:8px;padding:8px 10px;
            display:flex;flex-direction:column;gap:4px;border-left:3px solid transparent}
 .sourceCellKalshi{border-left-color:#22C55E} .sourceCellPoly{border-left-color:#3B82F6}
 .spreadBadge{background:rgba(245,158,11,.15);color:#B45309;padding:2px 6px;border-radius:4px;
            font-size:10px;font-weight:600}
 .probNum{font-family:ui-monospace,monospace;font-weight:700}
 .srcBoth{display:inline-flex;align-items:center;gap:3px}
 .srcDot{width:6px;height:6px;border-radius:50%;display:inline-block}
 .bad{color:#B45309} .ok{color:#047857}
</style>
<h1>UX-P194 — the cross-source card reaches the other two category pages</h1>
<p class="blurb">Read live ${esc(String(banked.read_at).slice(0, 10))}.
<code>/api/economics</code> and <code>/api/entertainment</code> each serve
<b>eight</b> cross-source rows off the same shared matcher that feeds
<code>/politics</code>, and neither page rendered one. Across all three pages
<b>21 of the 24</b> served rows were two sources pricing different outcomes —
which is why this is worth wiring only now that UX-P187 drops them.</p>
${beforePanel("economics")}
${afterPanel("economics")}
${beforePanel("entertainment")}
${afterPanel("entertainment")}`;

    fs.mkdirSync(OUT, { recursive: true });
    fs.writeFileSync(path.join(OUT, "category-cross-source-states.html"), html);
  });

  test("both AFTER panels rendered real cards, not an empty section", () => {
    // CrossSourceSpotlight returns null on an empty list, so an empty panel
    // would silently produce a header and no grid — exactly the failure this
    // artifact exists to rule out.
    expect(html).toContain("Cross-source spotlight");
    expect(html).toContain("Which bank will lead Anthropic's IPO?");
    expect(html).toContain("Beauty in Black: Season 3");
  });

  test("the BEFORE panels name the discard, and the numbers are the banked ones", () => {
    expect(html).toContain("never declared");
    expect(html).toContain("not a disagreement");
    for (const page of ["economics", "entertainment"]) {
      expect(banked.pages[page].served).toBe(8);
      expect(banked.pages[page].rendered_by_page).toBe(false);
    }
  });

  test("every served row is accounted for in a BEFORE panel", () => {
    for (const page of ["economics", "entertainment"]) {
      for (const r of rowsFor(page)) expect(html).toContain(esc(r.q));
    }
  });
});
