/**
 * #6325 — A SETTLED BOARD PRINTED TWO ROWS BADGED `1`, AND THEN KEPT MOVING THEM.
 *
 * ── WHAT A READER SAW ────────────────────────────────────────────────────────
 *
 * `bainluck.com/futures/58675941` ("Vuelta a Espana 2026: Winner", resolved) at
 * 390px, under the heading **Final Results**:
 *
 *     1   Other              WON     100%
 *     1   Tadej Pogacar      LOST      0%
 *     27  Sam Welsford       LOST      0%
 *     28  Mauro Schmid       LOST      0%
 *     17  Pello Bilbao       LOST      0%
 *
 * Two rows badged `1`, and beneath them a column reading 27, 28, 17, 10, 25 —
 * #4416's sentence word for word: a column that carries no ordering at all while
 * looking exactly like one.
 *
 * ── THE MECHANISM ────────────────────────────────────────────────────────────
 *
 * `rank` is a PRICE rank — where an outcome sat in the field while the market was
 * being made. `app/futures/[id]/page.tsx` hands the row `outcome.rank ?? index + 1`,
 * so a leg with no price history takes its DISPLAY POSITION instead. #6110 mints the
 * graded champion (here the venue's `Other` bucket) with `rank` NULL, the settled
 * sort hoists it to the top, and it lands on `1` — the badge Tadej Pogacar is
 * already wearing as the pre-race favourite who lost.
 *
 * Neither number is a lie about the row it sits on. The column they share is the
 * lie: after settlement the rows are ordered winner-first and then by frozen price,
 * and the badges are still speaking about a market being made.
 *
 * ── THE POPULATION, MEASURED RATHER THAN ASSUMED (production, 2026-09-15) ────
 *
 *   · **677** markets resolved in the last 45 days hold a NULL-ranked GRADED WINNER
 *     beside a sibling with stored rank 1 — the exact collision above, guaranteed,
 *     because the settled sort puts that winner at display position 1.
 *   · **1,960** resolved markets in that window mix ranked and unranked legs at all.
 *   · **180,626** settled outcome rows across **20,904** resolved markets still carry
 *     a non-zero `rank_change_24h`, and the API serves it: `/api/futures/57780365`
 *     ("Who will be Trump's next Attorney General?", resolved) serves Lee Zeldin
 *     `rank_change_24h: 5`, so a finished board prints **↓5** — "moved five places in
 *     the last 24 hours" about a question that is over.
 *   · Zero OPEN markets can collide: all 15 open markets holding NULL ranks (2,365
 *     rows, three golf fields) are NULL on EVERY leg, so nothing falls back into a
 *     sibling's number. The defect is settled-only, which is why the fix is too.
 *
 * ── NOT THE FIX ──────────────────────────────────────────────────────────────
 *
 * Renumbering the settled rows by display position. It makes the column coherent by
 * asserting something we do not know — that the second row FINISHED second. Only the
 * winner is graded; everyone else merely lost, and their order on the page is the
 * order their prices froze in. So the cell says nothing at all on a settled board:
 * the verdict chip (#4788) already crowns the winner, and there is nothing else true
 * left for a number to say.
 *
 * ── HOW THIS FILE IS AIMED ───────────────────────────────────────────────────
 *
 * The rule lives in `OutcomeRow` and is keyed on `isResolved`, the MARKET-level
 * fact — so the renders below are the component's own, at the two states that
 * matter. Every settled assertion has an OPEN sibling (gotcha #43), because the
 * cheapest way to pass "no badge renders" is to delete the badge, and that is a
 * different bug on the 2,148-row live boards. The fixtures are the real served rows
 * of the two markets named above, read from the production payload on 2026-09-15,
 * not invented rows that happen to collide.
 */

import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";

import OutcomeRow from "@/components/futures/OutcomeRow";
import type { FuturesOutcome } from "@/lib/types";

const REPO = path.join(__dirname, "..", "..");

/** `[name, rank, is_winner, rank_change_24h]`, as `/api/futures/58675941` serves them. */
const VUELTA: [string, number | null, boolean, number | null][] = [
  ["Other", null, true, null],
  ["Tadej Pogacar", 1, false, 0],
  ["Sam Welsford", 27, false, 0],
  ["Mauro Schmid", 28, false, 0],
  ["Pello Bilbao", 17, false, 0],
  ["Florian Lipowitz", 10, false, 0],
  ["Christophe Laporte", 25, false, 0],
  ["Jonas Vingegaard", 26, false, 0],
  ["Richard Carapaz", 12, false, 0],
  ["Ben Tulett", 29, false, 0],
];

/** Three rows of `/api/futures/57780365`, the arrows a settled board still prints. */
const ATTORNEY_GENERAL: [string, number | null, boolean, number | null][] = [
  ["Todd Blanche", 1, true, 0],
  ["Lee Zeldin", 5, false, 5],
  ["Harmeet Dhillon", 8, false, -4],
];

function outcome(
  [name, rank, isWinner, rankChange]: [string, number | null, boolean, number | null],
  id: number,
): FuturesOutcome {
  return {
    id,
    name,
    probability: isWinner ? 1 : 0,
    opening_probability: null,
    probability_change_24h: null,
    rank,
    rank_change_24h: rankChange,
    is_winner: isWinner,
    // Both specimens settled through `api_settlement`, so the verdict chips print.
    resolution_source: "api_settlement",
    last_updated: "2026-09-14T07:29:00+00:00",
  } as FuturesOutcome;
}

/**
 * The page's own rank expression (`app/futures/[id]/page.tsx`, the `OutcomeRow`
 * call): the stored price rank, or the row's display position when it has none.
 * Mirrored here rather than imported because it is written inline in a `page.tsx`,
 * which exports nothing — so the last `describe` in this file reads the page's
 * source and fails if that expression, or the `isResolved` it travels with, moves.
 */
function pageRank(o: FuturesOutcome, index: number): number {
  return o.rank ?? index + 1;
}

function renderBoard(
  rows: [string, number | null, boolean, number | null][],
  isResolved: boolean,
): string {
  const outcomes = rows.map((r, i) => outcome(r, 100 + i));
  return outcomes
    .map((o, index) =>
      renderToStaticMarkup(
        <OutcomeRow
          outcome={o}
          rank={pageRank(o, index)}
          isLeader={index === 0}
          isSelected={false}
          onToggleSelect={() => {}}
          hasHistory={false}
          marketCategory="cycling"
          marketName="Vuelta a Espana 2026: Winner"
          isResolved={isResolved}
          rendered={null}
          renderedOpening={null}
          showLastMove={false}
          showEntityImage={false}
        />,
      ),
    )
    .join("");
}

/**
 * The contents of every rank badge, in render order.
 *
 * Read off the badge's own class signature — the `w-8 h-8 … rounded-full` disc —
 * and NOT off the `data-testid` this ship added, so the guard cannot be satisfied
 * by the attribute the fix introduced. Returning `[]` is a real answer here (that is
 * the settled case), so the strawman protection is the OPEN sibling of every
 * assertion: if this extractor ever goes blind, those fail loudly.
 */
function rankBadges(html: string): string[] {
  return [
    ...html.matchAll(
      /<span[^>]*class="w-8 h-8 flex items-center justify-center text-sm rounded-full[^"]*"[^>]*>([^<]*)<\/span>/g,
    ),
  ].map((m) => m[1].trim());
}

/** Every rank-change arrow drawn, e.g. `↓5`, `↑4`. */
function rankArrows(html: string): string[] {
  return [...html.matchAll(/>([↑↓]\d+)</g)].map((m) => m[1]);
}

describe("#6325 — the rank cell is silent on a settled board", () => {
  it("THE DEFECT: the Vuelta's settled field draws no rank badge at all", () => {
    // RED BEFORE THIS SHIP: `["1", "1", "27", "28", "17", "10", "25", "26", "12", "29"]`
    // — the champion's display position colliding with the favourite's stored rank,
    // and eight unordered numbers under them.
    expect(rankBadges(renderBoard(VUELTA, true))).toEqual([]);
  });

  it("draws no duplicate badge, stated as the reader's complaint", () => {
    // The same fact from the angle the issue was filed at, so a future change that
    // brings numbering back has to keep it collision-free to pass.
    const badges = rankBadges(renderBoard(VUELTA, true));
    expect(new Set(badges).size).toBe(badges.length);
  });

  it("stops printing 24-hour rank moves on a question that is over", () => {
    expect(rankArrows(renderBoard(ATTORNEY_GENERAL, true))).toEqual([]);
  });

  it("keeps the names and the verdicts — it suppresses a number, not a row", () => {
    // The badge is inside the row, so "no badge" must not have been bought by
    // rendering nothing. Every rider is still on the page, and the champion is
    // still crowned.
    const html = renderBoard(VUELTA, true);
    for (const [name] of VUELTA) {
      expect(html).toContain(`data-outcome-name="${name}"`);
    }
    expect(html).toContain("Won");
    expect(html).toContain("Lost");
  });

  // ── THE OTHER DIRECTION (gotcha #43) ──────────────────────────────────────

  it("a LIVE board keeps every badge, in the order the page passes them", () => {
    expect(rankBadges(renderBoard(VUELTA, false))).toEqual([
      "1",
      "1",
      "27",
      "28",
      "17",
      "10",
      "25",
      "26",
      "12",
      "29",
    ]);
  });

  it("a LIVE board keeps its rank-change arrows", () => {
    expect(rankArrows(renderBoard(ATTORNEY_GENERAL, false))).toEqual(["↓5", "↑4"]);
  });

  it("a settled LEG on an OPEN market keeps its badge (#6082)", () => {
    // `isResolved` is the MARKET's status, never the leg's. A graded leg on a board
    // that is still being priced keeps a rank that still means something — the
    // #6082 case, pinned here so this ship cannot quietly take it away.
    const html = renderBoard([["Todd Blanche", 1, true, 0]], false);
    expect(rankBadges(html)).toEqual(["1"]);
  });
});

// ════════════════════════════════════════════════════════════════════════════
// THE PAGE'S HALF — a SOURCE SCAN, strictly weaker than a render, and said so.
// The rule above is the component's; what the page owes is to keep telling it
// which board this is. If `isResolved` stops reaching the row, every assertion
// above still passes while the reader sees two `1`s again.
// ════════════════════════════════════════════════════════════════════════════

/** Source with comments removed — this file's own prose quotes every identifier. */
function codeOf(rel: string): string {
  return fs
    .readFileSync(path.join(REPO, rel), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
}

describe("#6325 — the futures detail page (SOURCE SCAN)", () => {
  const page = codeOf("app/futures/[id]/page.tsx");

  it("still routes the market's settled state into every outcome row", () => {
    expect(page).toContain("<OutcomeRow");
    expect(page).toMatch(/isResolved=\{isResolved\}/);
    expect(page).toMatch(/const isResolved = market\.status === "resolved"/);
  });

  it("still passes the rank expression `pageRank` mirrors", () => {
    expect(page).toMatch(/rank=\{outcome\.rank \?\? index \+ 1\}/);
  });
});
