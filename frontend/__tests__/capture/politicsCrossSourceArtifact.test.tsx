/**
 * UX-P187 artifact rig — renders
 * `artifacts-ux-p187/cross-source-spotlight-states.html`.
 *
 * Two panels, both from real components and one verbatim production payload:
 *
 *   BEFORE  `__tests__/fixtures/uxp187CrossSourceCardLegacy.tsx` — the verbatim
 *           pre-fix card, extracted with
 *           `git show e6719c91:frontend/app/politics/page.tsx`, fed the four
 *           rows `/api/politics` actually served on 2026-08-30. A render of the
 *           code that shipped, NOT a drawing of it.
 *   AFTER   the shipped `components/politics/CrossSourceSpotlight.tsx`, fed the
 *           four rows the fixed matcher produces from the same production
 *           market data.
 *
 * The BEFORE panel annotates each card with the two outcomes its numbers were
 * really the price of — that annotation is the whole point, and it comes from
 * the fixture, not from this file.
 *
 * No timezone gate: nothing here renders a date, so a zone guard would buy
 * nothing and imply a dependency that does not exist. The rig asserts its own
 * output instead — an artifact that silently captured the wrong thing is worse
 * than no artifact.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import type { CrossSourceMatch } from "@/lib/api";

/* eslint-disable @typescript-eslint/no-var-requires */
const { CrossSourceCard } = require("@/components/politics/CrossSourceSpotlight");
const LegacyCard = require("../fixtures/uxp187CrossSourceCardLegacy").default;
/* eslint-enable @typescript-eslint/no-var-requires */

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const OUT = path.join(REPO, "artifacts-ux-p187");
const banked = JSON.parse(
  fs.readFileSync(
    path.join(
      REPO,
      "backend",
      "tests",
      "fixtures",
      "uxp187_politics_cross_source.json",
    ),
    "utf8",
  ),
);

type BankedRow = CrossSourceMatch & {
  _kalshi_leader: string | null;
  _poly_leader: string | null;
  _leaders_agree: boolean;
};

const BEFORE = (banked.served_before as BankedRow[]).slice(0, 4);
const AFTER = (
  banked.after_top8 as {
    q: string;
    outcome: string;
    k: number;
    p: number;
    delta: number;
  }[]
).slice(0, 4);

const esc = (v: string): string =>
  v.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function panel(title: string, blurb: string, cards: string[]): string {
  return `<section><h2>${esc(title)}</h2><p class="blurb">${blurb}</p>
  <div class="grid">${cards.join("")}</div></section>`;
}

describe("UX-P187 artifact — the spotlight before and after", () => {
  let html = "";

  beforeAll(() => {
    const beforeCards = BEFORE.map((row) => {
      const note = row._leaders_agree
        ? `<span class="ok">both sides price <b>${esc(row._kalshi_leader ?? "")}</b> — this one was real</span>`
        : `<span class="bad">Kalshi is pricing <b>${esc(row._kalshi_leader ?? "")}</b>;
           Polymarket is pricing <b>${esc(row._poly_leader ?? "")}</b></span>`;
      return `<figure>${renderToStaticMarkup(
        React.createElement(LegacyCard, { market: row }),
      )}<figcaption>${note}</figcaption></figure>`;
    });

    const afterCards = AFTER.map((row) =>
      `<figure>${renderToStaticMarkup(
        React.createElement(CrossSourceCard, {
          market: {
            q: row.q,
            outcome: row.outcome,
            kalshi: row.k,
            poly: row.p,
            delta: row.delta,
            category: "presidential",
            kalshi_market_id: 0,
            poly_market_id: 0,
          } as CrossSourceMatch,
        }),
      )}<figcaption><span class="ok">one outcome, both prices</span></figcaption></figure>`,
    );

    html = `<!doctype html><meta charset="utf-8">
<title>UX-P187 — cross-source spotlight</title>
<style>
 body{font:14px/1.5 -apple-system,system-ui,sans-serif;margin:32px;background:#FAFAFC;color:#111827}
 h1{font-size:20px} h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:#6B7280}
 .blurb{max-width:70ch;color:#374151}
 .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:12px 0 32px}
 figure{margin:0}
 figcaption{font-size:12px;margin-top:6px}
 .bad{color:#B45309} .ok{color:#047857}
 .crossCard{background:#fff;border:1px solid #E5E7EB;border-radius:10px;padding:12px 14px;
            display:flex;flex-direction:column;gap:10px}
 .sourceCell,.sourceCellKalshi,.sourceCellPoly{background:#F5F5F7;border-radius:8px;padding:8px 10px;
            display:flex;flex-direction:column;gap:4px;border-left:3px solid transparent}
 .sourceCellKalshi{border-left-color:#22C55E} .sourceCellPoly{border-left-color:#3B82F6}
 .spreadBadge{background:rgba(245,158,11,.15);color:#B45309;padding:2px 6px;border-radius:4px;
            font-size:10px;font-weight:600}
 .probNum{font-family:ui-monospace,monospace;font-weight:700}
 .srcBoth{display:inline-flex;align-items:center;gap:3px}
 .srcDot{width:6px;height:6px;border-radius:50%;display:inline-block}
</style>
<h1>UX-P187 — the cross-source spotlight compares like with like</h1>
<p class="blurb">Both panels are renders of real components on real production
data (<code>/api/politics</code>, ${esc(String(banked._source).slice(0, 80))}…).
Of the <b>${banked.pair_census.pairs_total}</b> cross-source pairs the route
finds, <b>${banked.pair_census.leaders_differ}</b> priced different outcomes on
the two sides and <b>${banked.pair_census.no_shared_outcome}</b> shared no
outcome at all. <b>${banked.after_available}</b> are comparable, which is still
seven times the four this section shows.</p>
${panel(
  "Before — the four cards a reader saw",
  "Each spread is one market's leading outcome minus another market's, and the ‘Merged’ line averages them.",
  beforeCards,
)}
${panel(
  "After — the four cards the same data now produces",
  "Every card names the single outcome both sources price, and the spread is that outcome’s.",
  afterCards,
)}`;

    fs.mkdirSync(OUT, { recursive: true });
    fs.writeFileSync(
      path.join(OUT, "cross-source-spotlight-states.html"),
      html,
    );
  });

  test("the BEFORE panel is the legacy card, and it names nothing", () => {
    // The whole value of the panel is that it is the shipped code. If the
    // legacy import ever starts rendering the caption, the panel is a lie.
    expect(html).toContain("How many House seats will Democrats win in Louisiana?");
    // The numerals sit inside their own <b>, so match across the tags rather
    // than assuming the rendered string is contiguous.
    expect(html).toMatch(/Merged:\s*<b[^>]*>64\.3%<\/b>/);
    expect(html).toContain("56.5pt spread");
    // The BEFORE panel must carry NO caption element at all.
    const beforePanel = html.slice(
      html.indexOf("Before — the four cards"),
      html.indexOf("After — the four cards"),
    );
    expect(beforePanel).not.toContain("margin-top:-6px");
  });

  test("the BEFORE captions carry the two real outcomes from the fixture", () => {
    expect(html).toContain("Kalshi is pricing");
    expect(html).toContain("Polymarket is pricing");
    // Louisiana's pair, verbatim out of the banked evidence.
    expect(html).toContain("exactly 1 seats");
  });

  test("the AFTER panel is the shipped card, and every one is captioned", () => {
    for (const row of AFTER) expect(html).toContain(row.outcome);
    expect((html.match(/margin-top:-6px/g) || []).length).toBe(4);
  });

  test("the artifact reached disk and is what we just asserted", () => {
    const written = fs.readFileSync(
      path.join(OUT, "cross-source-spotlight-states.html"),
      "utf8",
    );
    expect(written).toBe(html);
    expect(written.length).toBeGreaterThan(3000);
  });
});
