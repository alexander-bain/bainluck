import {
  ladderQuotesALine,
  selectHalfTotalRungs,
  LADDER_INTERIOR_MIN,
  LADDER_INTERIOR_MAX,
  type PeriodTotalRow,
} from "@/lib/marketMapUtils";

/**
 * #5013 — the half points maps stop printing a line off a book that has stopped.
 *
 * On the SF@LAR opener (2026-09-10, `/events/14632820`, shot pre-kickoff at
 * 5:32pm PT) three cards sat one screen apart: "Projected 48", "1st half O/U
 * 25", "2nd half O/U 11". 25 + 11 = 36 — the halves were twelve points short of
 * their own game — and the 2nd half marker was jammed against the left edge of
 * a 2 → 48+ axis with the darkest bucket leftmost.
 *
 * What the venue actually held is not in dispute. `futures_odds_snapshots` for
 * market 60075113 at 00:33:31Z — one minute AFTER the screenshot — is
 * `LIVE_2H_ROWS` below: thirteen monotone rungs crossing 50% between 21.5
 * (0.58) and 24.5 (0.43). The honest headline was 25, the same as the first
 * half. The page printed 11.
 *
 * The line is picked by the rung CLOSEST to 50%, and closest is not crossing.
 * `DEAD_2H_ROWS` is what a ladder looks like once its book empties and pricing
 * falls through to the last trade — ~0.99 under the step, ~0.01 over it. Every
 * rung is 49 points from a coin flip, so the reduce returns whichever rung the
 * step sits on. The tests below show that ladder is INDISTINGUISHABLE from the
 * live one by every signal the card has: it is monotone, it spans the same
 * thresholds, and it therefore paints the same 2 → 48+ axis. Only the interior
 * separates them, which is what `ladderQuotesALine` reads.
 */

function row(threshold: number, overProbability: number): PeriodTotalRow {
  return {
    market_name: "SF 49ers vs LA Rams: 2nd Half Total",
    outcome_name: `Over ${threshold} 2H points scored`,
    threshold,
    probability: null,
    market_type: "half_total",
    over_probability: overProbability,
    period: "2H",
  };
}

/**
 * VERBATIM: `futures_odds_snapshots` for market 60075113 (SF@LAR "2nd Half
 * Total"), captured 2026-09-11 00:33:31.957610Z. The 00:20:00Z snapshot either
 * side of it agrees to within 0.01 on every rung.
 */
const LIVE_2H_ROWS: PeriodTotalRow[] = [
  row(3.5, 0.98),
  row(7.5, 0.93),
  row(10.5, 0.91),
  row(14.5, 0.83),
  row(17.5, 0.72),
  row(20.5, 0.62),
  row(21.5, 0.58),
  row(24.5, 0.43),
  row(28.5, 0.3),
  row(31.5, 0.23),
  row(35.5, 0.15),
  row(38.5, 0.14),
  row(42.5, 0.12),
];

/**
 * The same thresholds priced by an empty book. `7.5` and `10.5` are just under
 * the pin so the reduce has a strict winner — which is how the card came to
 * print 11 rather than 8.
 */
const DEAD_2H_ROWS: PeriodTotalRow[] = [
  row(7.5, 0.99),
  row(10.5, 0.98),
  row(14.5, 0.01),
  row(17.5, 0.01),
  row(20.5, 0.01),
  row(21.5, 0.01),
  row(24.5, 0.01),
  row(28.5, 0.01),
  row(31.5, 0.01),
  row(35.5, 0.01),
  row(38.5, 0.01),
  row(42.5, 0.01),
];

/**
 * Denver @ Kansas City, `GET /api/events/14638896/game-markets` read
 * 2026-09-11 03:5xZ — a second live ladder, from a different game and a
 * different week, so the interior bounds are not fitted to one specimen.
 */
const LIVE_2H_ROWS_DEN_KC = [
  0.755, 0.71, 0.71, 0.665, 0.54, 0.5, 0.475, 0.36, 0.23, 0.23, 0.085, 0.075,
].map((p, i) => row([7.5, 10.5, 14.5, 17.5, 20.5, 21.5, 22.5, 24.5, 28.5, 35.5, 38.5, 42.5][i], p));

/** Mirrors the `ouLine` reduce in `MarketMapSection`'s `halfTotalMaps`. */
function headlineOU(rungs: Array<{ threshold: number; overProbability: number }>): number {
  const ouLine = rungs.reduce((best, t) =>
    Math.abs(t.overProbability - 0.5) < Math.abs(best.overProbability - 0.5) ? t : best
  );
  return Math.round(ouLine.threshold);
}

describe("#5013 the 2nd half card printed a line a dead book could not know", () => {
  it("prints 25 off the ladder the venue actually held at kickoff", () => {
    const cleaned = selectHalfTotalRungs(LIVE_2H_ROWS, "2H");
    expect(cleaned).toHaveLength(13);
    expect(headlineOU(cleaned)).toBe(25);
  });

  it("prints the screenshot's 11 off the same thresholds once the book empties", () => {
    const cleaned = selectHalfTotalRungs(DEAD_2H_ROWS, "2H");
    expect(headlineOU(cleaned)).toBe(11);
  });

  it("gives the reader no tell: full ladder, monotone, and the shop's own axis", () => {
    const dead = selectHalfTotalRungs(DEAD_2H_ROWS, "2H");

    // Not one rung is dropped by the selector's monotonicity pass, so the card
    // has as many rungs as a healthy one.
    expect(dead).toHaveLength(DEAD_2H_ROWS.length);
    expect(dead.map((r) => r.overProbability)).toEqual(
      [...dead.map((r) => r.overProbability)].sort((a, b) => b - a)
    );

    // And the rail it paints is the one photographed under the card: the
    // range arithmetic in `MarketMapSection`'s `halfTotalMaps`, applied to
    // this ladder, is the "2 … 48+" the shop shot at 5:32pm PT.
    const dataMin = dead[0].threshold;
    const dataMax = dead[dead.length - 1].threshold;
    const pad = Math.max((dataMax - dataMin) * 0.15, 3);
    expect(Math.max(0, Math.floor(dataMin - pad))).toBe(2);
    expect(Math.ceil(dataMax + pad)).toBe(48);
  });

  it("is told apart by the interior, which is the one thing that differs", () => {
    expect(ladderQuotesALine(selectHalfTotalRungs(LIVE_2H_ROWS, "2H"))).toBe(true);
    expect(ladderQuotesALine(selectHalfTotalRungs(LIVE_2H_ROWS_DEN_KC, "2H"))).toBe(true);
    expect(ladderQuotesALine(selectHalfTotalRungs(DEAD_2H_ROWS, "2H"))).toBe(false);
  });
});

describe("ladderQuotesALine", () => {
  it("does not refuse a low-total sport, where one rung is the whole ladder's middle", () => {
    // A soccer 1st half: goals, not points, so the rungs are 0.5 apart and the
    // interior is thin. It still has one.
    const soccer = [
      { threshold: 0.5, overProbability: 0.7 },
      { threshold: 1.5, overProbability: 0.34 },
      { threshold: 2.5, overProbability: 0.11 },
    ];
    expect(ladderQuotesALine(soccer)).toBe(true);
  });

  it("reads the bounds inclusively, so a rung sitting exactly on one counts", () => {
    expect(ladderQuotesALine([{ overProbability: LADDER_INTERIOR_MAX }])).toBe(true);
    expect(ladderQuotesALine([{ overProbability: LADDER_INTERIOR_MIN }])).toBe(true);
    expect(ladderQuotesALine([{ overProbability: LADDER_INTERIOR_MAX + 0.001 }])).toBe(false);
    expect(ladderQuotesALine([{ overProbability: LADDER_INTERIOR_MIN - 0.001 }])).toBe(false);
  });

  it("answers false for a ladder with nothing in it rather than throwing", () => {
    expect(ladderQuotesALine([])).toBe(false);
  });
});
