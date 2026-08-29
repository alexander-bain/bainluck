/**
 * UX-P158 — THE ILLIQUIDITY MARK, ACTUALLY GRADED, FOR ALEX'S EYEBALL.
 *
 * ═══ WHAT HE ASKED FOR, AND WHAT HE WOULD HAVE GOT ═══
 *
 * *"A really clean, universal signal for illiquidity"* — graded (at least two
 * levels, because illiquidity is not uniform), with a reveal that says
 * **precisely when the probability was last updated**, and a **non-hover
 * equivalent for native designed at the same time, not later**. #2256 is his
 * issue in his own words; #2257 is the presentation question it answers.
 *
 * UX-P157 built all of that and shipped a page with **one** reachable level.
 * The fact behind the second is "did anybody trade it in the last day", and
 * Gamma answers that question by omitting the field rather than serving a zero,
 * so it was unreadable on 264 of the 328 markets this surface is made of. The
 * previous version of this rig rendered two levels anyway, because its legend
 * is hand-written — so the artifact looked graded and the page was not. That is
 * the failure this rig now exists to make impossible: **panels 1, 2 and 3 are
 * the same real bracket graded three ways, and the assertions at the bottom
 * check the hollow mark against the corpus rather than the legend.**
 *
 * ═══ WHAT THIS RENDERS, AND HOW FAITHFUL EACH PANEL IS ═══
 *
 * Every panel is the SHIPPED component with the app's own compiled stylesheet:
 *
 *   • the grid rows come from `payload-2026-08-28.json`, which
 *     `capture_tournament_payload.py` read from production through the route's
 *     own `build_grids`;
 *   • the books come from `ladder-books-2026-08-29.json` — all 336 US Open
 *     ladder markets, pulled by `backend/scripts/pull_ladder_books.py`: the
 *     STORED book, volume and volume STAMP out of production Postgres, Gamma's
 *     LIVE book and volume fields, and the Polymarket TRADE TAPE beside both;
 *   • the grade on every cell is `market_liquidity.grade_liquidity`'s rule
 *     applied to those books.
 *
 * SYNTHETIC, and captioned as such on the page: the questions panel and the
 * phone mock, whose LEVELS are hand-set because those cards' markets are not in
 * the ladder fixture. Every grid cell in panels 1-3 is measured.
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
const BOOKS_PATH = path.join(MOCKS, "ladder-books-2026-08-29.json");

/** UX-P158's window, mirroring `market_liquidity.VOLUME_OBSERVATION_MAX_AGE_HOURS`. */
const VOLUME_WINDOW_HOURS = 24;

interface Book {
  stored_bid: number | null;
  stored_ask: number | null;
  stored_volume_24h: number | null;
  /** `null` on every ladder row today — see the PRODUCTION TODAY panel. */
  stored_volume_updated_at?: string | null;
  live_bid: number | null;
  live_ask: number | null;
  live_volume_24h: number | null;
  live_present?: boolean;
}

interface BooksMeta {
  pulled_at_utc: string;
  condition_ids: number;
  live_served: number;
}

function loadBooks(): { books: Record<string, Book>; meta: BooksMeta } {
  const raw = JSON.parse(fs.readFileSync(BOOKS_PATH, "utf8")) as Record<string, unknown>;
  const meta = raw._meta as unknown as BooksMeta;
  const books: Record<string, Book> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (key !== "_meta") books[key] = value as Book;
  }
  return { books, meta };
}

/**
 * `market_liquidity.grade_liquidity`, restated for the rig ONLY.
 *
 * Deliberately not imported: the rule is Python and lives in the backend,
 * where 53 tests guard it. This is a fixture-stamping helper, and the tests
 * below assert it agrees with the shipped constants on the specimens that
 * matter — a rig that silently disagreed with the route would render a
 * beautiful, wrong picture.
 *
 * `ageHours` is UX-P158's addition and it is the whole point of this queue: an
 * ABSENT volume figure is a measured zero when we know we asked recently, and
 * nothing at all when we do not. `undefined` means "no observation" and is how
 * the PRODUCTION TODAY panel below is graded.
 */
function grade(
  bid: number | null,
  ask: number | null,
  volume: number | null,
  ageHours?: number
): { liquidity: string; liquidity_reasons: string[] } {
  const reasons: string[] = [];
  let checked = 0;
  const observed =
    ageHours !== undefined &&
    Number.isFinite(ageHours) &&
    ageHours >= 0 &&
    ageHours <= VOLUME_WINDOW_HOURS;
  if (observed) {
    checked += 1;
    if (volume === null || !Number.isFinite(volume) || volume <= 0) {
      reasons.push("no_trades_24h");
    }
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

/**
 * The three ways the same real grid can be graded, and why each is a PANEL
 * rather than a variant:
 *
 *   `today`   — the stored book and the stored volume STAMP. Production, right
 *               now. Every ladder row's stamp is null, so the volume fact is
 *               never checked and the second grade cannot appear.
 *   `shipped` — the live book with a fresh observation beside it, which is what
 *               the 10-minute refresh rail writes once this queue deploys. The
 *               page Alex will see.
 *   `p157`    — the live book graded the way UX-P157 graded it, with an absent
 *               figure unreadable. The counterfactual, so the change is a
 *               comparison rather than a claim.
 */
type Reading = "today" | "shipped" | "p157";

/** Stamp a grade onto every priced cell of a real grid, from a real book. */
function gradedGrid(draw: string, which: Reading): GridModel {
  const payload = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
  const raw = (payload.grids as Record<string, unknown>)[draw];
  const grid = readPlayoffGrid(raw as never);
  if (!grid) throw new Error(`payload no longer carries the ${draw} grid`);
  const { books, meta } = loadBooks();
  const pulledAt = new Date(meta.pulled_at_utc).getTime();
  const storedAge = (b: Book): number | undefined =>
    b.stored_volume_updated_at
      ? (pulledAt - new Date(b.stored_volume_updated_at).getTime()) / 3_600_000
      : undefined;

  for (const row of grid.rows) {
    for (const cell of Object.values(row.cells) as GridCell[]) {
      if (cell.probability === null) continue;
      const graded = (cell.sources ?? [])
        .map((s) => books[String(s.market_external_id)])
        .filter(Boolean)
        .map((b) => {
          if (which === "today") {
            return grade(b.stored_bid, b.stored_ask, b.stored_volume_24h, storedAge(b));
          }
          if (which === "p157") {
            // UX-P157 read a figure and never a stamp: a present figure was
            // checked, an absent one was not.
            return grade(
              b.live_bid,
              b.live_ask,
              b.live_volume_24h,
              b.live_volume_24h === null ? undefined : 0
            );
          }
          // The live half IS the observation — read from Gamma seconds before
          // it was written into the fixture.
          return grade(b.live_bid, b.live_ask, b.live_volume_24h, 0);
        });
      cell.liquidity = thinnest(graded.map((g) => g.liquidity));
      cell.liquidity_reasons = Array.from(
        new Set(graded.flatMap((g) => g.liquidity_reasons))
      ).sort();
    }
  }
  return grid;
}

function levelCount(grid: GridModel, level: string): number {
  let n = 0;
  for (const row of grid.rows) {
    for (const cell of Object.values(row.cells) as GridCell[]) {
      if (cell.liquidity === level) n += 1;
    }
  }
  return n;
}

function markedCount(grid: GridModel): number {
  return levelCount(grid, "thin") + levelCount(grid, "barely");
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

describe("UX-P158 — the illiquidity mark, graded on the surfaces it was built for", () => {
  it("the rig's grade agrees with the shipped rule on the specimens", () => {
    // #2257's shape: a book eight cents wide under a four-cent number.
    expect(grade(0.0, 0.08, 0, 0.5)).toEqual({
      liquidity: "barely",
      liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
    });
    // Ben Shelton's cell — one of the sixteen, and deliberately unmarked.
    expect(grade(0.69, 0.71, 7, 0.5)).toEqual({
      liquidity: "traded",
      liquidity_reasons: [],
    });
    // Nothing to check is never a clean bill of health.
    expect(grade(null, null, null).liquidity).toBe("unknown");
  });

  it("UX-P158: an OBSERVED absence is the second grade; an unobserved one is silence", () => {
    // The ship, in the rig's own mirror of the rule. Same book, same absent
    // figure; the only difference is whether we know when we last asked.
    expect(grade(0.0, 0.08, null, 0.5).liquidity).toBe("barely");
    expect(grade(0.0, 0.08, null).liquidity).toBe("thin");
    // And the observation stops being evidence past the window it describes.
    expect(grade(0.0, 0.08, null, 83).liquidity).toBe("thin");
  });

  it("THE SECOND GRADE REACHES THE REAL GRID — the defect UX-P157 shipped", () => {
    /**
     * UX-P157's mark was graded and its page was not: on these same real books
     * every marked cell could only be `thin`, because the fact behind the
     * second level was uncheckable. This is that, asserted as a count on the
     * production payload rather than described in a report.
     */
    const before = gradedGrid("womens-singles", "p157");
    const after = gradedGrid("womens-singles", "shipped");
    expect(levelCount(before, "barely")).toBe(0);
    expect(levelCount(after, "barely")).toBeGreaterThan(0);
    // And it is a GRADE, not a repaint: both levels have to be on the page at
    // once or the reader has nothing to compare.
    expect(levelCount(after, "thin")).toBeGreaterThan(0);
    // The mark still has to be able to say nothing.
    expect(levelCount(after, "traded")).toBeGreaterThan(0);
  });

  it("the grid draws the mark, and the key only when there is one to explain", () => {
    const grid = gradedGrid("womens-singles", "shipped");
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
    const grid = gradedGrid("womens-singles", "shipped");
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
    const thin = gradedGrid("womens-singles", "shipped");
    const clean = gradedGrid("womens-singles", "shipped");
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
    const today = gradedGrid("womens-singles", "today");
    const p157 = gradedGrid("womens-singles", "p157");
    const live = gradedGrid("womens-singles", "shipped");
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
<title>UX-P158 — the illiquidity mark, actually graded</title>
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
  <span class="tag mark">UX-P158</span> <b>The illiquidity mark stops having one grade.</b>
  <br><br>
  Alex's ruling, 2026-08-28, asked for a symbol that <b>grades</b> — at least two levels.
  UX-P157 built two, and only one of them could ever appear on the page: the fact behind the second
  is "did anybody trade it in the last day", and Gamma answers that by <b>omitting</b> the field
  rather than serving a zero, so on 264 of these 328 markets it was unreadable. The three panels
  below are the same real bracket under the same real books, graded three ways, so the change is
  something to look at rather than something to take my word for.
  <ul class="key">${specimens}</ul>
  <b>How the absence was made readable, and why it is a measurement and not an assumption:</b>
  every one of the 328 markets Gamma still serves was cross-checked against the Polymarket
  <b>trade tape</b> — a different endpoint, listing trades rather than computing an aggregate.
  <b>64</b> carry a 24h figure and <b>64 of 64</b> traded in the last day; <b>133</b> carry only a
  lifetime figure and <b>0 of 133</b> traded in the last day; <b>131</b> carry neither and
  <b>131 of 131</b> have never traded at all. Three cohorts, 328 of 328, no exceptions. So an
  absence <i>we know we asked for recently</i> is a zero. An absence with no record of asking is
  still nothing, and still draws nothing.
  <br><br>
  Every number and book below is production's own: the grid is
  <code>payload-2026-08-28.json</code>, the books are all 336 US Open ladder markets in
  <code>ladder-books-2026-08-29.json</code>.
  <b>The one place levels are hand-set is the questions panel and the phone mock at the bottom</b>,
  which are there to show the component rather than the corpus — captioned as such where they sit.
</div>
${panel(
  "pending",
  "1 · WHAT THE PAGE SHOWS RIGHT NOW — " + markedCount(today) + " cells marked, of which " + levelCount(today, "barely") + " are hollow",
  "Production, this minute, from the stored book and the stored volume stamp. Every ladder row's volume stamp is <b>null</b> — the hourly Polymarket scan last touched these markets on <b>2026-08-25</b>, and the 10-minute refresh rail wrote the price and the book but never the volume — so the trading fact is never checked and the hollow mark cannot appear. This is the gap between the artifact UX-P157 shipped and the page it shipped. The <b>115</b> rows whose book is still four days old are not a coverage gap: 8 are markets Gamma no longer serves and <b>107 are the ones Q428 declines to price</b>, which is to say the deadest books on the board had the oldest data about them.",
  renderToStaticMarkup(<PlayoffGrid grid={today} initialExpanded />)
)}
${panel(
  "control",
  "2 · THE SAME GRID ON TODAY'S LIVE BOOK, GRADED THE OLD WAY — " + markedCount(p157) + " marked, " + levelCount(p157, "barely") + " hollow",
  "The counterfactual, and the control for panel 3. Same books, same rule, one difference: an absent volume figure is treated as unreadable, exactly as UX-P157 treated it. The count of hollow marks is <b>zero</b>, and it is zero for a reason no amount of fresher data would fix.",
  renderToStaticMarkup(<PlayoffGrid grid={p157} initialExpanded />)
)}
${panel(
  "mark",
  "3 · WHAT IT SHOWS ONCE THIS DEPLOYS — " + markedCount(live) + " of " + live.rows.length * live.columns.length + " cells marked, " + levelCount(live, "barely") + " of them hollow",
  "The live book with a volume observation beside it, which is what the 10-minute refresh rail writes from now on — the figure and the price come off <b>one</b> Gamma response, so the mark is never grading a book from a different observation than the number it sits next to. Venus Williams' 0.8% to reach the quarter-final still sits above a 3.6% semi-final; both are still printed, unchanged, and the reader can now see how little either is worth.",
  renderToStaticMarkup(<PlayoffGrid grid={live} initialExpanded />)
)}
${panel(
  "mark",
  "4 · THE QUESTIONS SECTION — the card is marked, and so is each row",
  "A field card's leader can be heavily traded while the tail it is printed above is quoted by nobody, so the mark is on both. The definition is printed once, under the section, and only when something on screen needs it. <b>Levels here are hand-set</b>: these cards' markets are not in the ladder fixture, so this panel demonstrates the component, not a measurement.",
  renderToStaticMarkup(<TournamentProps markets={propCards()} draw="mens-singles" />)
)}
<div class="panel">
  <div class="panel-head"><span class="tag native">NATIVE</span> <b>THE NON-HOVER EQUIVALENT</b><br>
  A phone has no mouse, so the mark is a tap target and the reveal opens inline UNDER the row rather
  than in a popover — a popover covers the number the reader just asked about, and the sentence is
  only meaningful while that number is on screen. Long-press does the same thing without moving
  focus. The Swift component is <code>LiquidityMarkView.swift</code>; it draws the same two glyphs
  from the same two levels and reads the same sentence. <b>Hand-set, like panel 4</b> — this is the
  interaction, not a measurement.</div>
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

    const out = path.join(dir, "p158-illiquidity-mark.html");
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

    // UX-P158's OWN CLAIM, asserted against the file that will be looked at
    // rather than against the model behind it. The failure this catches is the
    // exact one UX-P157 hit: a page whose second grade appears only in a
    // hand-written legend. Panel 3 must carry hollow marks drawn from measured
    // books, and panel 2 must carry none.
    expect(levelCount(live, "barely")).toBeGreaterThan(0);
    expect(levelCount(p157, "barely")).toBe(0);
    expect(levelCount(today, "barely")).toBe(0);
    expect(written).toContain("3 · WHAT IT SHOWS ONCE THIS DEPLOYS");
    expect(written).toContain("1 · WHAT THE PAGE SHOWS RIGHT NOW");
  });
});
