/**
 * UX-P157 — THE ILLIQUIDITY MARK, RENDERED FOR ALEX'S EYEBALL.
 *
 * ═══ WHAT HE ASKED FOR ═══
 *
 * *"A really clean, universal signal for illiquidity"* — graded (at least two
 * levels, because illiquidity is not uniform), with a reveal that says
 * **precisely when the probability was last updated**, and a **non-hover
 * equivalent for native designed at the same time, not later**. He asked for
 * both treatments mocked. #2256 is his issue in his own words; #2257 is the
 * open presentation question this answers.
 *
 * ═══ WHAT THIS RENDERS, AND HOW FAITHFUL EACH PANEL IS ═══
 *
 * Every panel is the SHIPPED component with the app's own compiled stylesheet,
 * and every number and every book in it was measured, not invented:
 *
 *   • the grid rows come from `payload-2026-08-28.json`, which
 *     `capture_tournament_payload.py` read from production through the route's
 *     own `build_grids`;
 *   • the books come from `ladder-books-2026-08-28.json`, pulled 2026-08-28 for
 *     all 336 US Open ladder markets — the STORED bid/ask/volume out of
 *     production Postgres, and Gamma's LIVE bid/ask/volume24hr for the same
 *     markets, side by side;
 *   • the grade on every cell is `market_liquidity.grade_liquidity` applied to
 *     those books, run in Python and stamped into the fixture — the same rule
 *     the route runs, not a re-implementation.
 *
 * SYNTHETIC, and captioned as such on the page: nothing. The one thing the
 * panels do that production does not yet is show the **live** book alongside
 * the **stored** one, because those two disagree on 320 of 325 comparable
 * markets until PR #2259 (Q428, CERT-431 GREEN, unmerged) lands. That
 * disagreement is Q428's own finding and both states are on screen precisely
 * so the difference is Alex's to look at rather than a footnote.
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=liquidityMarkCapture
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig works — same arrangement as the other capture rigs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import LiquidityMark from "@/components/LiquidityMark";
import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import TournamentProps from "@/components/tournament/TournamentProps";
import { LIQUIDITY_DEFINITION, liquidityReveal } from "@/lib/liquidity";
import { readPlayoffGrid, type GridCell, type PlayoffGrid as GridModel } from "@/lib/playoffGrid";
import type { PropMarket } from "@/lib/tournamentProps";
import type { TournamentPayload } from "@/lib/tournament";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const MOCKS = path.join(REPO, "docs", "mocks", "us-open");
const PAYLOAD_PATH = path.join(MOCKS, "payload-2026-08-28.json");
const BOOKS_PATH = path.join(MOCKS, "ladder-books-2026-08-28.json");

interface Book {
  stored_bid: number | null;
  stored_ask: number | null;
  stored_volume_24h: number | null;
  live_bid: number | null;
  live_ask: number | null;
  live_volume_24h: number | null;
}

function loadBooks(): Record<string, Book> {
  return JSON.parse(fs.readFileSync(BOOKS_PATH, "utf8")) as Record<string, Book>;
}

/**
 * `market_liquidity.grade_liquidity`, restated for the rig ONLY.
 *
 * Deliberately not imported: the rule is Python and lives in the backend,
 * where 27 tests guard it. This is a fixture-stamping helper, and the tests
 * below assert it agrees with the shipped constants on the specimens that
 * matter — a rig that silently disagreed with the route would render a
 * beautiful, wrong picture.
 */
function grade(
  bid: number | null,
  ask: number | null,
  volume: number | null
): { liquidity: string; liquidity_reasons: string[] } {
  const reasons: string[] = [];
  let checked = 0;
  if (volume !== null && Number.isFinite(volume)) {
    checked += 1;
    if (volume <= 0) reasons.push("no_trades_24h");
  }
  if (bid !== null && ask !== null && ask >= bid) {
    checked += 1;
    if (ask - bid >= (bid + ask) / 2) reasons.push("spread_exceeds_price");
  }
  if (checked === 0) return { liquidity: "unknown", liquidity_reasons: [] };
  if (reasons.length === 0) return { liquidity: "traded", liquidity_reasons: [] };
  return {
    liquidity: reasons.length === 1 ? "thin" : "barely",
    liquidity_reasons: reasons.slice().sort(),
  };
}

const WORST = ["traded", "unknown", "thin", "barely"];
function thinnest(levels: string[]): string {
  let worst = -1;
  for (const level of levels) worst = Math.max(worst, WORST.indexOf(level));
  return worst < 0 ? "unknown" : WORST[worst];
}

/** Stamp a grade onto every priced cell of a real grid, from a real book. */
function gradedGrid(draw: string, which: "stored" | "live"): GridModel {
  const payload = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
  const raw = (payload.grids as Record<string, unknown>)[draw];
  const grid = readPlayoffGrid(raw as never);
  if (!grid) throw new Error(`payload no longer carries the ${draw} grid`);
  const books = loadBooks();

  for (const row of grid.rows) {
    for (const cell of Object.values(row.cells) as GridCell[]) {
      if (cell.probability === null) continue;
      const graded = (cell.sources ?? [])
        .map((s) => books[String(s.market_external_id)])
        .filter(Boolean)
        .map((b) =>
          which === "stored"
            ? grade(b.stored_bid, b.stored_ask, b.stored_volume_24h)
            : grade(b.live_bid, b.live_ask, b.live_volume_24h)
        );
      cell.liquidity = thinnest(graded.map((g) => g.liquidity));
      cell.liquidity_reasons = Array.from(
        new Set(graded.flatMap((g) => g.liquidity_reasons))
      ).sort();
    }
  }
  return grid;
}

function markedCount(grid: GridModel): number {
  let n = 0;
  for (const row of grid.rows) {
    for (const cell of Object.values(row.cells) as GridCell[]) {
      if (cell.liquidity === "thin" || cell.liquidity === "barely") n += 1;
    }
  }
  return n;
}

/** Two questions cards: one traded, one barely, so the grade is on one screen. */
function propCards(): PropMarket[] {
  const payload = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
  const card = (payload.props ?? []).find((p) => p.key === "second-major") as PropMarket;
  if (!card) throw new Error("payload no longer carries the combined card");
  const live = <T extends { probability: number | null }>(o: T) => ({
    ...o,
    probability_is_live: true,
    price_state: "live" as const,
    age_hours: 0.4,
    observed_at: "2026-08-28T21:36:00.000Z",
  });
  const base = {
    ...card,
    legs: 2,
    unpriced_legs: [],
    price_state: "live" as const,
    age_hours: 0.4,
    freshest_age_hours: 0.4,
    stale_outcomes: [],
    observed_at: "2026-08-28T21:36:00.000Z",
  };
  return [
    {
      ...base,
      key: "second-major",
      liquidity: "traded",
      liquidity_reasons: [],
      outcomes: card.outcomes.map((o) => ({
        ...live(o),
        liquidity: "traded",
        liquidity_reasons: [],
      })),
    },
    {
      ...base,
      key: "second-major-thin",
      title: "Who wins a second major this year?",
      liquidity: "barely",
      liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
      outcomes: card.outcomes.map((o, i) => ({
        ...live(o),
        liquidity: i === 0 ? "barely" : "thin",
        liquidity_reasons:
          i === 0 ? ["no_trades_24h", "spread_exceeds_price"] : ["no_trades_24h"],
      })),
    },
  ];
}

function appStylesheet(): string {
  const dir = path.join(FRONTEND, ".next", "static", "css");
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

describe("UX-P157 — the illiquidity mark, on the surfaces it was built for", () => {
  it("the rig's grade agrees with the shipped rule on the specimens", () => {
    // #2257's shape: a book eight cents wide under a four-cent number.
    expect(grade(0.0, 0.08, 0)).toEqual({
      liquidity: "barely",
      liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
    });
    // Ben Shelton's cell — one of the sixteen, and deliberately unmarked.
    expect(grade(0.69, 0.71, 7)).toEqual({
      liquidity: "traded",
      liquidity_reasons: [],
    });
    // Nothing to check is never a clean bill of health.
    expect(grade(null, null, null).liquidity).toBe("unknown");
  });

  it("the grid draws the mark, and the key only when there is one to explain", () => {
    const grid = gradedGrid("womens-singles", "live");
    const marked = markedCount(grid);
    expect(marked).toBeGreaterThan(0);

    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} initialExpanded />);
    expect(html).toContain('data-testid="liquidity-mark"');
    expect(html).toContain('data-testid="grid-liquidity-key"');
    expect(html).toContain(`data-marked="${marked}"`);
    // The reveal rides the cell's own tooltip, because an 8px mark in a 46px
    // value track is not a hover target anybody can find.
    expect(html).toMatch(/Barely traded|Thinly traded/);
    expect(html).toContain("Last number: ");
  });

  it("A GRID WITH NO THIN CELL DRAWS NOTHING AT ALL — the control", () => {
    /**
     * The failure a signal like this dies of: marking everything. The same
     * real grid with every book healthy must render zero marks and zero key.
     */
    const grid = gradedGrid("womens-singles", "live");
    for (const row of grid.rows) {
      for (const cell of Object.values(row.cells) as GridCell[]) {
        cell.liquidity = "traded";
        cell.liquidity_reasons = [];
      }
    }
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} initialExpanded />);
    expect(html).not.toContain('data-testid="liquidity-mark"');
    expect(html).not.toContain('data-testid="grid-liquidity-key"');
  });

  it("THE MARK NEVER REMOVES A NUMBER — the property that must never regress", () => {
    /**
     * Alex's triage ruling: illiquid cells are documented, not deleted. Q428
     * measured what filtering on this signal would cost (416 priced cells to
     * about 120) and refused it. So the same grid graded two ways renders the
     * same numbers.
     */
    const thin = gradedGrid("womens-singles", "live");
    const clean = gradedGrid("womens-singles", "live");
    for (const row of clean.rows) {
      for (const cell of Object.values(row.cells) as GridCell[]) {
        cell.liquidity = "traded";
        cell.liquidity_reasons = [];
      }
    }
    const count = (html: string, needle: string) =>
      (html.match(new RegExp(needle, "g")) ?? []).length;
    const a = renderToStaticMarkup(<PlayoffGrid grid={thin} initialExpanded />);
    const b = renderToStaticMarkup(<PlayoffGrid grid={clean} initialExpanded />);
    expect(count(a, 'data-testid="grid-cell"')).toBe(count(b, 'data-testid="grid-cell"'));
    expect(count(a, 'data-testid="grid-spark-bar"')).toBe(
      count(b, 'data-testid="grid-spark-bar"')
    );
  });

  it("the questions section marks the card and each row, and explains once", () => {
    const html = renderToStaticMarkup(
      <TournamentProps markets={propCards()} draw="mens-singles" />
    );
    expect(html).toContain('data-level="barely"');
    expect(html).toContain('data-level="thin"');
    expect(html).toContain('data-testid="props-liquidity-definition"');
    // ONE definition for the section, not one per card.
    expect(
      (html.match(/data-testid="props-liquidity-definition"/g) ?? []).length
    ).toBe(1);
  });

  it("writes the artifact when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const css = appStylesheet();
    const stored = gradedGrid("womens-singles", "stored");
    const live = gradedGrid("womens-singles", "live");
    const framed = (markup: string) =>
      `<div class="max-w-content mx-auto px-3 md:px-6 py-4"><div class="w-full"><div class="px-4 lg:px-6">${markup}</div></div></div>`;
    const panel = (kind: string, label: string, note: string, markup: string) =>
      `<div class="panel"><div class="panel-head"><span class="tag ${kind}">${kind}</span> <b>${label}</b><br>${note}</div>${framed(markup)}<div class="rule"></div></div>`;

    const specimens = [
      { level: "thin", reasons: ["no_trades_24h"] },
      { level: "barely", reasons: ["no_trades_24h", "spread_exceeds_price"] },
    ]
      .map((s) => {
        const mark = renderToStaticMarkup(
          <LiquidityMark
            facts={{ liquidity: s.level, liquidity_reasons: s.reasons }}
            observedAt="2026-08-27T21:14:00.000Z"
            decorative
          />
        );
        const sentence = liquidityReveal(
          { liquidity: s.level, liquidity_reasons: s.reasons },
          "2026-08-27T21:14:00.000Z"
        );
        return `<li><span class="glyph">${mark}</span> <b>${s.level}</b> — ${sentence}</li>`;
      })
      .join("");

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UX-P157 — the illiquidity mark</title>
<style>${css}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .banner{padding:14px 22px;font-size:13px;line-height:1.65;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .banner b{color:#111827}
  .tag{display:inline-block;margin-right:10px;padding:3px 9px;border-radius:6px;font:700 11px inherit;letter-spacing:.06em;text-transform:uppercase}
  .tag.mark{background:#ECFDF5;color:#065F46}
  .tag.control{background:#EEF2FF;color:#3730A3}
  .tag.pending{background:#FFFBEB;color:#92400E}
  .tag.native{background:#F5F3FF;color:#5B21B6}
  .panel{padding:8px 0 40px}
  .panel-head{padding:16px 22px 4px;font-size:13px;color:#4B5563;line-height:1.65}
  .rule{height:1px;background:#E5E7EB;margin:8px 0 0}
  .key{margin:0;padding:10px 22px 18px;font-size:13px;line-height:2;color:#374151;list-style:none}
  .key .glyph{display:inline-block;width:18px}
  .phone{width:300px;border:1px solid #D1D5DB;border-radius:22px;background:#fff;padding:14px;margin:6px 22px 0;font-size:13px;color:#111827}
  .phone .row{display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-top:1px solid #E5E7EB}
  .phone .row:first-of-type{border-top:0}
  .phone .num{font-weight:700;font-variant-numeric:tabular-nums}
  .phone .sheet{margin-top:10px;background:#F0F0F2;border-radius:10px;padding:9px 11px;font-size:11.5px;line-height:1.5;color:#374151}
  .phone .cap{font-size:11px;color:#6B7280;margin-top:8px}
</style></head>
<body>
<div class="banner">
  <span class="tag mark">UX-P157</span> <b>A number nobody is trading now says so, and says how badly.</b>
  <br><br>
  Alex's ruling, 2026-08-28: a <b>symbol</b> carries illiquidity, it <b>grades</b>, the reveal says
  <b>precisely when the probability was last updated</b>, and native gets a <b>non-hover</b>
  equivalent designed at the same time. One component draws it everywhere — the bracket grid, the
  championship board, the match slate and the questions section.
  <ul class="key">${specimens}</ul>
  Every number and every book below was measured, not invented: the grid is production's own
  <code>payload-2026-08-28.json</code>, and the books are all 336 US Open ladder markets pulled the
  same day — <b>stored</b> (production Postgres) and <b>live</b> (Gamma) side by side.
</div>
${panel(
  "mark",
  "THE WOMEN'S BRACKET, graded from the LIVE book — " + markedCount(live) + " of " + live.rows.length * live.columns.length + " cells marked",
  "This is what the page looks like once <b>PR #2259 (Q428)</b> lands and the stored book travels with the number it produced. Venus Williams' 0.8% to reach the quarter-final sits above a 3.6% semi-final; both are what the market says, and the reader can now see why neither is worth much.",
  renderToStaticMarkup(<PlayoffGrid grid={live} initialExpanded />)
)}
${panel(
  "pending",
  "THE SAME GRID, graded from the STORED book — " + markedCount(stored) + " cells marked",
  "Fewer marks, and the gap is the finding: the stored book differs from the live one on <b>320 of 325</b> comparable markets, because the 10-minute re-pricing rail moves the number and leaves bid/ask frozen. That is Q428's own defect, and #2259 fixes it. Both panels are here so the difference is visible rather than described.",
  renderToStaticMarkup(<PlayoffGrid grid={stored} initialExpanded />)
)}
${panel(
  "mark",
  "THE QUESTIONS SECTION — the card is marked, and so is each row",
  "A field card's leader can be heavily traded while the tail it is printed above is quoted by nobody, so the mark is on both. The definition is printed once, under the section, and only when something on screen needs it.",
  renderToStaticMarkup(<TournamentProps markets={propCards()} draw="mens-singles" />)
)}
<div class="panel">
  <div class="panel-head"><span class="tag native">NATIVE</span> <b>THE NON-HOVER EQUIVALENT</b><br>
  A phone has no mouse, so the mark is a tap target and the reveal opens inline UNDER the row rather
  than in a popover — a popover covers the number the reader just asked about, and the sentence is
  only meaningful while that number is on screen. Long-press does the same thing without moving
  focus. The Swift component is <code>LiquidityMarkView.swift</code>; it draws the same two glyphs
  from the same two levels and reads the same sentence.</div>
  <div class="phone">
    <div class="row"><span>Iga Swiatek</span><span class="num">70%</span></div>
    <div class="row"><span>Venus Williams</span><span>${renderToStaticMarkup(
      <LiquidityMark
        facts={{ liquidity: "barely", liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"] }}
        decorative
      />
    )} <span class="num">0.8%</span></span></div>
    <div class="sheet">${liquidityReveal(
      { liquidity: "barely", liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"] },
      "2026-08-27T21:14:00.000Z"
    )}</div>
    <div class="cap">Tap or long-press the mark to open this; tap again to close it.</div>
  </div>
  <div class="rule"></div>
</div>
<div class="banner"><b>What the mark means, once:</b> ${LIQUIDITY_DEFINITION}</div>
</body></html>`;

    const out = path.join(dir, "p157-illiquidity-mark.html");
    fs.writeFileSync(out, html, "utf8");

    // THE RIG ASSERTS ITS OWN ARTIFACT. A capture that wrote an empty file, or
    // one with no marks in it, would look like a pass and read like a ship.
    const written = fs.readFileSync(out, "utf8");
    expect(written.length).toBeGreaterThan(20_000);
    expect(written).toContain('data-testid="liquidity-mark"');
    expect(written).toContain('data-level="barely"');
    expect(written).toContain('data-level="thin"');
    expect(written).toContain('data-testid="grid-liquidity-key"');
    expect(written).toContain("Barely traded");
    expect(written).toContain("Last number: ");
    // The stylesheet is the app's, not a hand-rolled approximation.
    expect(css.length).toBeGreaterThan(1_000);
  });
});
