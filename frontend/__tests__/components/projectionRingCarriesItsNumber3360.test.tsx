/**
 * #3360 — THE PROJECTION RING CARRIES ITS OWN NUMBER, AND THAT NUMBER FITS.
 *
 * From a production LOOK of `/events/15304847` (Paul v Alcaraz, pre-game) at
 * 390px, re-shot for this fix on 2026-09-06:
 *
 *   Games map                                    Projected 37
 *   Two lines quoted
 *   (        ◯                                              )
 *   33                    39                             44+
 *
 * The `◯` is the Projection marker. `MarketMap` renders `m.logoFallback` inside
 * a `proj` dot; the PRE-GAME totals marker sets `hideTile: true` and supplied no
 * `logoFallback`, so the ring was empty — and because `hideTile` suppresses the
 * tile underneath, the empty ring was the marker's ONLY mark. It reads as a
 * missing value rather than as a pointer at 37.
 *
 * ── THE INVARIANT ────────────────────────────────────────────────────────────
 *
 * Both arms that draw a projection also print one in the headline, so the honest
 * assertion is AGREEMENT rather than a pinned literal:
 *
 *   the number inside the projection ring == the number in "Projected N"
 *
 * That is one rule covering the pre-game arm (`Math.round(ouVal)`) and the live
 * arm (`Math.round(projected)`), and it cannot be satisfied by hard-coding —
 * both sides are read out of the rendered markup.
 *
 * ── WHY THE LIVE ARM MOVED TOO, THOUGH THE ISSUE ONLY NAMED THE PRE-GAME ONE ─
 *
 * The issue asked whether the number would fit before committing to it, and
 * flagged that the live arm's one-decimal string had never been photographed.
 * It was measured on the real production dot with the real styles (Inter, 8px,
 * font-weight 950, 26px ring = 22px inner box), by writing candidates into the
 * live span and reading `getBoundingClientRect().width` back:
 *
 *     "37"      11.13px   FITS      slack  10.87px
 *     "36"      11.77px   FITS      slack  10.23px
 *     "108"     16.80px   FITS      slack   5.20px
 *     "36.4"    20.72px   FITS      slack   1.28px   <- the live arm as shipped
 *     "108.5"   25.36px   OVERFLOWS slack  -3.36px
 *
 * So `toFixed(1)` was already broken for every three-digit total — basketball,
 * NFL — and tennis simply never reaches three digits. Rounding fixes the empty
 * ring and that overflow with one rule, and the decimal is not lost: the live
 * arm's tile still carries it through `displayValue`.
 *
 * Hence the width arm below. It is a proxy for the measurement (jsdom has no
 * text metrics), and it is pinned at the threshold the measurement established:
 * three characters fit, a four-character decimal string is the one that did not.
 *
 * ── THE CONTROLS ─────────────────────────────────────────────────────────────
 *
 * Deleting the ring entirely, or stamping a constant, would satisfy a naive
 * "the ring is not empty" check. So the suite also asserts the ring tracks a
 * DIFFERENT fixture to a different number, and that the settled arm — which
 * draws no projection at all — still draws none.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

type TotalRow = { threshold: number; over: number };

function totalRow(t: TotalRow) {
  return {
    threshold: t.threshold,
    over_probability: t.over,
    source: "kalshi",
    market_type: "game_total",
    market_name: `Total Games O/U ${t.threshold}`,
    outcome_name: "Over",
    is_winner: null,
    resolution_source: null,
    movement: 0,
    period: null,
  };
}

const SPREADS = [
  { market_name: "Game Spread", outcome_name: "Tommy Paul -2.5", threshold: 2.5, probability: 0.31, source: "kalshi", is_winner: null, resolution_source: null },
  { market_name: "Game Spread", outcome_name: "Carlos Alcaraz -2.5", threshold: 2.5, probability: 0.69, source: "kalshi", is_winner: null, resolution_source: null },
];

function markets(totals: TotalRow[], overrides: Record<string, unknown> = {}) {
  return {
    event_id: 15304847,
    home_team: "Tommy Paul",
    away_team: "Carlos Alcaraz",
    home_score: null,
    away_score: null,
    status: "scheduled",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: SPREADS,
    totals: totals.map(totalRow),
    ...overrides,
  };
}

function render(
  totals: TotalRow[],
  eventStatus = "scheduled",
  linescore: object | null = null,
  overrides: Record<string, unknown> = {},
  sportKey = "tennis_atp_us_open"
): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={markets(totals, overrides) as never}
      eventStatus={eventStatus}
      homeTeam="Tommy Paul"
      awayTeam="Carlos Alcaraz"
      homeAbbr="PAU"
      awayAbbr="ALC"
      homeWinProb={0.31}
      awayWinProb={0.69}
      homeSpread={-2.5}
      sportKey={sportKey}
      linescore={linescore as never}
    />
  );
}

/**
 * The section draws a MARGIN map before the totals map, and that one has a
 * projection dot too — carrying a team abbreviation ("ALC"), by design and not
 * in scope here. So every assertion has to be scoped to the totals card first,
 * or it reads the wrong ring and the suite is about the wrong component.
 */
const TOTALS_TITLES = ["Games map", "Points map", "Total: expected vs final"];

function totalsCard(html: string): string | null {
  for (const t of TOTALS_TITLES) {
    const i = html.indexOf(t);
    if (i !== -1) return html.slice(i);
  }
  return null;
}

/**
 * The text rendered INSIDE the totals map's projection dot — what the ring
 * shows. Returns null when that card draws no projection dot at all, so "no
 * ring" and "an empty ring" stay distinguishable: they are different bugs.
 */
function ringText(html: string): string | null {
  const card = totalsCard(html);
  if (card === null) return null;
  const at = card.indexOf('data-dot="proj"');
  if (at === -1) return null;
  // The dot is a single <div> whose only child is the <span> holding the label.
  const span = card.slice(at).match(/<span[^>]*>([^<]*)<\/span>/);
  if (!span) return "";
  return span[1].trim();
}

/** The number the totals card states in its own headline: "Projected 37" -> "37". */
function headlineProjection(html: string): string | null {
  const card = totalsCard(html);
  if (card === null) return null;
  const text = card.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  const m = text.match(/Projected\s+([\d.]+)/);
  return m ? m[1] : null;
}

/** `/events/15304847`, as production served it. Headline reads "Projected 37". */
const PAUL_ALCARAZ: TotalRow[] = [
  { threshold: 36.5, over: 0.485 },
  { threshold: 40.5, over: 0.395 },
];

/** A DIFFERENT book, so a hard-coded "37" cannot pass the tracking arm. */
const LOWER_LINE: TotalRow[] = [
  { threshold: 28.5, over: 0.52 },
  { threshold: 30.5, over: 0.44 },
];

/** A basketball book, where the live ring actually renders and totals hit 3 digits. */
const NBA_TOTALS: TotalRow[] = [
  { threshold: 219.5, over: 0.52 },
  { threshold: 224.5, over: 0.41 },
];

const BERGS_LINE = {
  sets: [
    [6, 3],
    [1, 4],
  ] as [number, number][],
  home_games: 7,
  away_games: 7,
  source: "espn",
};

describe("#3360 — the projection ring carries its own number", () => {
  it("a PRE-GAME totals map draws its projection number inside the ring", () => {
    const html = render(PAUL_ALCARAZ);
    const ring = ringText(html);

    expect(ring).not.toBeNull(); // the marker exists at all
    expect(ring).not.toBe(""); // <- the defect: a 26px ring with nothing in it
    expect(ring).toMatch(/^\d+$/);
  });

  it("the ring states the SAME number the card's headline states", () => {
    const html = render(PAUL_ALCARAZ);

    // Agreement, not a pinned literal — the card may not point at 37 and say 38.
    expect(headlineProjection(html)).toBe("37");
    expect(ringText(html)).toBe(headlineProjection(html));
  });

  it("the ring TRACKS the book rather than stamping a constant", () => {
    const lower = render(LOWER_LINE);
    const higher = render(PAUL_ALCARAZ);

    expect(ringText(lower)).toBe(headlineProjection(lower));
    expect(ringText(higher)).toBe(headlineProjection(higher));
    // A constant would make these equal; the two books quote different totals.
    expect(ringText(lower)).not.toBe(ringText(higher));
  });

  /**
   * The LIVE ring only ever renders where `scoreboardCountsTheUnit` is true —
   * tennis nulls `pace` outright (ux/1034 B5: its scoreboard counts sets while
   * the rail counts games), so a tennis page has no live projection at all.
   * Which sharpens the overflow: the live ring appears on exactly the sports
   * whose totals reach three digits.
   */
  it("a LIVE map's ring is rounded rather than carrying a decimal", () => {
    const html = render(NBA_TOTALS, "live", null, {
      pace: { projected_total: 108.5, total_scored: 60 },
    }, "basketball_nba");
    const ring = ringText(html);

    expect(ring).not.toBeNull();
    expect(ring).not.toBe("");
    // "108.5" measured 25.36px against a 22px inner box — it OVERFLOWED. This
    // is the case that was already broken before #3360 touched anything.
    expect(ring).toBe("109"); // NOT "108.5"
    expect(ring).not.toContain(".");
    expect(ring).toBe(headlineProjection(html));
  });

  it("a live ring stays within the 3 chars the ring was measured to hold", () => {
    for (const projected_total of [98.4, 108.5, 224.6]) {
      const html = render(NBA_TOTALS, "live", null, {
        pace: { projected_total, total_scored: 60 },
      }, "basketball_nba");
      const ring = ringText(html) as string;

      expect(ring).not.toContain(".");
      expect(ring.length).toBeLessThanOrEqual(3);
    }
  });

  it("CONTROL — a settled map still draws no projection ring", () => {
    const settled = render(PAUL_ALCARAZ, "completed", {
      ...BERGS_LINE,
      sets: [
        [6, 3],
        [6, 4],
      ] as [number, number][],
      home_games: 12,
      away_games: 7,
    });

    // Nothing here should have grown a projection: a finished match has a final,
    // not a forecast. This is what fails if the fix is applied indiscriminately.
    expect(ringText(settled)).toBeNull();
  });
});
