/**
 * #6218 — A SETTLED TOTALS CARD HEADED "EACH LINE VS THE FINAL" LISTED ONLY THE
 * LINES THAT CLEARED.
 *
 * The RENDER half of #6196; lane1b's backend half is live (v4545, `a83d378d`).
 * Seen on production 2026-09-14 at 390px, `/events/14637256` — Giants 28
 * Cowboys 20, a 48-point game:
 *
 *     TOTAL: EXPECTED VS FINAL          FINAL 48 points   PRE-GAME 48
 *     EACH LINE VS THE FINAL
 *        Over 27.5 ......... cleared
 *        ...
 *        Over 47.5 ......... cleared          <- and then it stops
 *
 * Nine rungs, all cleared, and nothing above 48. `/api/events/14637256/game-markets`
 * served TWENTY at `cache.created_at 20:44:45Z`: nine at 1.0 (27.5–47.5) and
 * eleven at 0.0 (48.5–69.5). A card that promises each line against the final and
 * then prints only the winners is not a ladder, it is a highlight reel — and the
 * axis stopped at 47.5, so the FINAL 48 marker pinned to the right-hand edge of
 * its own band instead of landing inside it.
 *
 * The whole cause is one filter in `selectGameTotalRungs`, which dropped every
 * rung at 0% before the ladder was built. `MarketMapSection` was ALREADY
 * grading correctly — it just never saw the losing rungs.
 *
 * ## The filter is kept for every card that is still quoting
 *
 * It was written for a real defect: a dead book prints ~0.0 above its step, and
 * "Over 60.5 — 0%" on a live game is a stale quote wearing a price. So the
 * zeros survive only when the card GRADES, which is the one state in which a 0
 * is an answer rather than a quote.
 *
 * ## What makes this suite non-vacuous
 *
 * The selector cases below could all pass while the page still drew nine rows,
 * so the decisive test renders the REAL `MarketMapSection` over the REAL
 * twenty-rung payload and reads "not cleared" off the markup — the same standard
 * #3769's suite set for this card.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import {
  selectGameTotalRungs,
  totalsMapRenders,
  marketMapIsGraded,
} from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

/** One `totals[]` row in the shape the endpoint serves. */
function rung(threshold: number, over: number, extra: Record<string, unknown> = {}) {
  return {
    threshold,
    over_probability: over,
    source: "kalshi",
    market_type: "game_total",
    market_name: "Dallas vs New York G: Total Points",
    outcome_name: `Over ${threshold} points`,
    is_winner: over >= 1,
    resolution_source: null,
    movement: 0,
    period: null,
    ...extra,
  };
}

/**
 * The real twenty rungs `/api/events/14637256/game-markets` served, verbatim,
 * including the 52.5 row — see THE TRAP below.
 */
const GIANTS_TOTALS = [
  rung(27.5, 1.0), rung(30.5, 1.0), rung(33.5, 1.0), rung(36.5, 1.0),
  rung(39.5, 1.0), rung(42.5, 1.0), rung(45.5, 1.0), rung(46.5, 1.0),
  rung(47.5, 1.0),
  rung(48.5, 0.0), rung(49.5, 0.0), rung(50.5, 0.0), rung(51.5, 0.0),
  // THE TRAP (lane1b, #6218): a Polymarket row whose `outcome_name` has no
  // colon, so `isGameTotal` accepts it — carrying the UNDER's verdict
  // (`is_winner: true`) in an OVER-oriented slot. Harmless only because the card
  // grades by threshold against the final. Kept verbatim so any future change
  // that pairs `over_probability` with `is_winner` reddens here.
  rung(52.5, 0.0, { source: "polymarket", is_winner: true, outcome_name: "Under" }),
  rung(54.5, 0.0), rung(57.5, 0.0), rung(60.5, 0.0),
  rung(63.5, 0.0), rung(66.5, 0.0), rung(69.5, 0.0),
];

const FINAL_TOTAL = 48; // 28 + 20

function renderSection(totals: unknown[], eventStatus: string) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={
          {
            totals,
            spreads: [],
            period_markets: [],
            // The scoreboard the card grades against lives on the PAYLOAD, not
            // on a prop — `playedUnits` reads `gameMarkets.home_score`.
            home_score: 28,
            away_score: 20,
          } as never
        }
        eventStatus={eventStatus as never}
        homeTeam="New York Giants"
        awayTeam="Dallas Cowboys"
        homeAbbr="NYG"
        awayAbbr="DAL"
        homeWinProb={1}
        awayWinProb={0}
        overUnder={48}
        sportKey="americanfootball_nfl"
      />
    )
  );
}

describe("#6218 a settled totals ladder serves both halves of its own question", () => {
  it("keeps every losing rung the payload authorised — 9 rungs become 20", () => {
    expect(selectGameTotalRungs(GIANTS_TOTALS as never, "completed")).toHaveLength(20);
  });

  it("stopped at the final before the fix — that is the defect, stated", () => {
    // No status is the pre-change call, still the default for any caller that
    // does not know the lifecycle.
    const before = selectGameTotalRungs(GIANTS_TOTALS as never);
    expect(before).toHaveLength(9);
    expect(Math.max(...before.map((t) => t.threshold))).toBeLessThan(FINAL_TOTAL);
  });

  it("widens the axis past the final, so the FINAL marker lands inside its band", () => {
    const after = selectGameTotalRungs(GIANTS_TOTALS as never, "completed");
    const axisMax = Math.max(...after.map((t) => t.threshold));
    expect(axisMax).toBe(69.5);
    expect(axisMax).toBeGreaterThan(FINAL_TOTAL);
  });

  it("keeps the ladder monotonically non-increasing with the zeros in it", () => {
    const after = selectGameTotalRungs(GIANTS_TOTALS as never, "completed");
    for (let i = 1; i < after.length; i += 1) {
      expect(after[i].over_probability).toBeLessThanOrEqual(after[i - 1].over_probability);
    }
  });
});

describe("#6218 a card that is still quoting keeps dropping dead quotes", () => {
  it.each(["live", "scheduled", "pre", "in_progress", "halftime", undefined])(
    "status %s drops the 0%% rungs",
    (status) => {
      expect(selectGameTotalRungs(GIANTS_TOTALS as never, status)).toHaveLength(9);
    },
  );

  /**
   * DELIBERATELY NARROWER THAN `isSettledStatus`, which also accepts "settled",
   * "final" and "resolved". `MarketMapSection` grades on "completed"/"closed"
   * only, so a status that kept the zeros here but did not grade there would
   * print a bare "0%" with no verdict beside it. The two must agree.
   */
  it.each([
    ["completed", true],
    ["closed", true],
    ["settled", false],
    ["final", false],
    ["resolved", false],
    ["live", false],
    [undefined, false],
  ])("marketMapIsGraded(%s) === %s", (status, expected) => {
    expect(marketMapIsGraded(status as string | undefined)).toBe(expected);
  });
});

describe("#6218 the note and the card cannot disagree (#3240)", () => {
  /**
   * A settled game whose final is below EVERY line — every rung 0%. Before, the
   * card did not render and `totalsMapRenders` agreed. Now the card renders, so
   * the note must be asked with the same argument or it will point a reader at a
   * card it believes is absent.
   */
  const ALL_ZERO = [rung(48.5, 0.0), rung(51.5, 0.0), rung(54.5, 0.0)];

  it("an all-zero settled ladder renders, and the note says so", () => {
    expect(selectGameTotalRungs(ALL_ZERO as never, "completed")).toHaveLength(3);
    expect(totalsMapRenders({ totals: ALL_ZERO, spreads: [] } as never, "completed")).toBe(true);
  });

  it("the same ladder on a live card renders nothing, and the note agrees", () => {
    expect(selectGameTotalRungs(ALL_ZERO as never, "live")).toHaveLength(0);
    expect(totalsMapRenders({ totals: ALL_ZERO, spreads: [] } as never, "live")).toBe(false);
  });
});

describe("#6218 the decisive test — the real section over the real payload", () => {
  it("prints 'not cleared' for the lines the game did not reach", () => {
    const text = renderSection(GIANTS_TOTALS, "completed");
    expect(text).toContain("not cleared");
    expect(text).toContain("Over 69.5");
  });

  it("still prints 'cleared' for the lines it did reach", () => {
    const text = renderSection(GIANTS_TOTALS, "completed");
    expect(text).toContain("Over 27.5");
    expect(text).toContain("cleared");
  });

  /**
   * THE TRAP, asserted at the surface. The 52.5 row carries `is_winner: true`
   * (the UNDER's verdict). A 48-point game did not go over 52.5, so the card
   * must say NOT cleared. If anything ever grades this ladder by `is_winner`
   * instead of threshold-vs-final, this reddens.
   */
  it("grades 52.5 against the final, not against the Under's is_winner", () => {
    const text = renderSection(GIANTS_TOTALS, "completed");
    const at = text.indexOf("Over 52.5");
    expect(at).toBeGreaterThan(-1);
    expect(text.slice(at, at + 40)).toContain("not cleared");
  });

  it("a live card over the same rows draws no losing rung at all", () => {
    const text = renderSection(GIANTS_TOTALS, "live");
    expect(text).not.toContain("Over 69.5");
  });
});
