/**
 * #3210 — A MAP WITH NO SHAPE NAMES ITS RUNGS INSTEAD OF PROMISING A CURVE.
 *
 * Alex, from a production LOOK of `/events/15304847` (Paul v Alcaraz, pre-game)
 * at 390px on 2026-09-05:
 *
 *   > GAMES MAP
 *   >   Games map
 *   >   Final games distribution                     Projected 37
 *   >   ████████████●███████████████████████████████
 *   >   33                    39                  44+
 *   >
 *   > The band underneath is a single flat purple block — the card promises a
 *   > distribution and draws none.
 *
 * ── WHAT SHIPS ───────────────────────────────────────────────────────────────
 *
 * Alex's option 2, in his words: *"Draw the rungs. The component already builds
 * a `ladder` (`Over 36.5 → 49%`, `Over 40.5 → 40%`) and this card is not showing
 * one at phone width."* Three things move together, and each is asserted below:
 *
 *   1. the rail paints NO segments — an empty track under the markers is a
 *      number line, which is all this card can honestly claim;
 *   2. the ladder is drawn INSIDE the card instead of behind a hover a phone
 *      cannot perform;
 *   3. the subtitle stops saying "distribution" and says what is there, in the
 *      wording from Alex's own issue body: "Two lines quoted".
 *
 * ── WHY THE RULE IS NOT "FEWER THAN THREE RUNGS" ─────────────────────────────
 *
 * Because production disagrees with that proxy. All three events measured on
 * 2026-09-05 are in the fixtures below, and the middle one is the reason
 * `densityDrawsShape` asks the rail what colour it would paint rather than
 * counting rows:
 *
 *   /events/15304847  2 rungs, 36.5@0.485 / 40.5@0.395   → one PDF point, solid
 *   /events/15304419  2 rungs, 36.5@0.560 / 38.5@0.550   → one PDF point, solid
 *   /events/15304420  3 rungs, all three quoted at 0.20  → every dp is 0, flat
 *
 * A count-based test calls the third one a distribution. The reader sees the
 * same uniform block.
 *
 * ── THE CONTROLS ARE THE SUITE ───────────────────────────────────────────────
 *
 * A change that simply deleted the band, or that showed the ladder inline on
 * every card, would satisfy every positive assertion here. So every one of them
 * is paired with a four-rung card that must keep its painted band, keep its
 * "distribution" subtitle, and keep its ladder in the popover — and with the
 * live/settled sentences, which are about the MARKERS and must not move when
 * the band does.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { densityDrawsShape, quotedLinesPhrase } from "@/lib/marketMapUtils";

const TOTAL_ACCENT = "124,58,237";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function countOf(html: string, needle: string): number {
  return html.split(needle).length - 1;
}

type TotalRow = { threshold: number; over: number };

function totalRow(t: TotalRow) {
  return {
    threshold: t.threshold,
    over_probability: t.over,
    source: "polymarket",
    market_type: "game_total",
    market_name: `Total Games O/U ${t.threshold}`,
    outcome_name: "Over",
    is_winner: null,
    resolution_source: null,
    movement: 0,
    period: null,
  };
}

/** The two full-game spread rungs the tennis pages really carry. */
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
  overrides: Record<string, unknown> = {},
  linescore: object | null = null
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
      sportKey="tennis_atp_us_open"
      linescore={linescore as never}
    />
  );
}

/** `/events/15304847`, exactly as production served it on 2026-09-05. */
const PAUL_ALCARAZ: TotalRow[] = [
  { threshold: 36.5, over: 0.485 },
  { threshold: 40.5, over: 0.395 },
];

/** `/events/15304420` — THREE rungs, all quoted at the same price. */
const THREE_EQUAL_RUNGS: TotalRow[] = [
  { threshold: 36.5, over: 0.2 },
  { threshold: 38.5, over: 0.2 },
  { threshold: 40.5, over: 0.2 },
];

/** A card whose band really does describe a shape — the control everywhere. */
const SHAPED: TotalRow[] = [
  { threshold: 36.5, over: 0.72 },
  { threshold: 38.5, over: 0.64 },
  { threshold: 40.5, over: 0.51 },
  { threshold: 42.5, over: 0.33 },
];

describe("#3210 · densityDrawsShape — asked of the colour, not the row count", () => {
  it("two rungs cannot describe a shape, and the rail says so", () => {
    // One PDF point means every segment is assigned the same density, so the
    // whole rail normalises to one colour. This is arithmetic, not a heuristic.
    const flat = new Array(12).fill(96);
    expect(densityDrawsShape(flat, TOTAL_ACCENT)).toBe(false);
  });

  it("THREE rungs at one price are just as shapeless — the count is the wrong test", () => {
    // `/events/15304420`. Every `dp` is zero, so the band normalises to all
    // zeros. A rung count calls this a distribution; the reader sees a block.
    const allZero = new Array(12).fill(0);
    expect(allZero).toHaveLength(3 + 9); // it is a 12-segment rail, not 3 rungs
    expect(densityDrawsShape(allZero, TOTAL_ACCENT)).toBe(false);
  });

  it("a band with two colours in it draws a shape — the control", () => {
    expect(densityDrawsShape([0, 12, 44, 96, 44, 12], TOTAL_ACCENT)).toBe(true);
  });

  it("a one-segment rail has nothing to compare and is not a shape", () => {
    expect(densityDrawsShape([96], TOTAL_ACCENT)).toBe(false);
    expect(densityDrawsShape([], TOTAL_ACCENT)).toBe(false);
  });

  /**
   * The predicate is exact about the pixels, so an intensity difference too
   * small to change the rendered `rgba()` string is correctly NOT a shape —
   * that band paints one colour whatever the numbers behind it say.
   */
  it("intensities that render the same colour are one colour", () => {
    const a = new Array(12).fill(96);
    a[5] = 96.4 as number;
    expect(densityDrawsShape(a, TOTAL_ACCENT)).toBe(false);
  });
});

describe("#3210 · quotedLinesPhrase", () => {
  it("uses Alex's wording, and the count is a word", () => {
    expect(quotedLinesPhrase(2)).toBe("Two lines quoted");
  });

  it("stays grammatical at one", () => {
    expect(quotedLinesPhrase(1)).toBe("One line quoted");
  });

  it("falls back to digits past nine rather than inventing a word", () => {
    expect(quotedLinesPhrase(3)).toBe("Three lines quoted");
    expect(quotedLinesPhrase(12)).toBe("12 lines quoted");
  });
});

describe("#3210 · the card Alex photographed", () => {
  it("does not paint a band it has no shape for", () => {
    const html = render(PAUL_ALCARAZ);
    // The margin card beside it DOES have a shape (two spreads land in
    // different segments), so its 12 segments must survive — a fix that
    // deleted the band everywhere would pass a bare `not.toContain`.
    expect(countOf(html, "data-density-segment")).toBe(12);
  });

  it("names the two lines instead of promising a distribution", () => {
    const text = visibleText(render(PAUL_ALCARAZ));
    expect(text).toContain("Two lines quoted");
    expect(text).not.toContain("Expected games distribution");
  });

  it("draws the rungs inside the card, with the prices Alex quoted", () => {
    const html = render(PAUL_ALCARAZ);
    expect(countOf(html, 'data-inline-ladder="1"')).toBe(1);

    const text = visibleText(html);
    expect(text).toContain("Over 36.5");
    expect(text).toContain("49%");
    expect(text).toContain("Over 40.5");
    expect(text).toContain("40%");
  });

  it("keeps the markers and the axis — the rail is still a number line", () => {
    // The pre-game projection is what the rail is FOR once the band is gone.
    // A card that lost its dots along with its fill would read as broken.
    //
    // These are the exact figures in Alex's shot — `Projected 37` over an axis
    // reading `33 … 39 … 44+`. They are asserted because they are how this
    // fixture proves it is the card he photographed and not one like it.
    const text = visibleText(render(PAUL_ALCARAZ));
    expect(text).toContain("Projected 37");
    expect(text).toContain("33 39 44+");
  });

  it("prints the ladder once, not twice", () => {
    // The popover is suppressed when the inline block renders. Both live in
    // the static markup, so a duplicate would be a real duplicate on screen.
    const html = render(PAUL_ALCARAZ);
    expect(countOf(html, "Over 36.5")).toBe(1);
  });
});

describe("#3210 · the three-rung card the row count would have missed", () => {
  it("is treated as the flat band it renders as", () => {
    const text = visibleText(render(THREE_EQUAL_RUNGS));
    expect(text).toContain("Three lines quoted");
    expect(text).not.toContain("Expected games distribution");
  });

  it("paints no totals band either", () => {
    expect(countOf(render(THREE_EQUAL_RUNGS), "data-density-segment")).toBe(12);
  });
});

describe("#3210 · a card that earned its band keeps it — the controls", () => {
  it("paints both rails when both have a shape", () => {
    expect(countOf(render(SHAPED), "data-density-segment")).toBe(24);
  });

  it("still calls itself a distribution", () => {
    const text = visibleText(render(SHAPED));
    expect(text).toContain("Expected games distribution");
    expect(text).not.toContain("lines quoted");
  });

  it("keeps its ladder in the popover, not inline", () => {
    expect(countOf(render(SHAPED), 'data-inline-ladder="1"')).toBe(0);
  });
});

describe("#3210 · the tense sentences are about the markers, not the band", () => {
  const LINE = {
    sets: [[6, 3], [1, 4]] as [number, number][],
    home_games: 7,
    away_games: 7,
    source: "espn",
  };

  /**
   * live/064 shipped three tenses on this subtitle. Those two sentences grade
   * an ACTUAL marker against a PRE-GAME one, and both markers are drawn whether
   * or not the band has a shape — so a shapeless band must not silence them.
   * Getting this wrong would replace a true sentence with a lesser one.
   */
  it("a live match with a shapeless band still says where it's heading", () => {
    const text = visibleText(render(PAUL_ALCARAZ, "live", { status: "live" }, LINE));
    expect(text).toContain("Where it's heading vs what was expected");
    expect(text).not.toContain("Two lines quoted");
  });

  it("a settled match with a shapeless band still says where it landed", () => {
    const text = visibleText(render(PAUL_ALCARAZ, "completed", { status: "completed" }, LINE));
    expect(text).toContain("Where it landed vs what was expected");
    expect(text).not.toContain("Two lines quoted");
  });

  it("...and both of them still draw the rungs, since the band is still flat", () => {
    // The sentence is about the markers; the PICTURE is still shapeless, so
    // the inline ladder is owed on a live card exactly as on a pre-game one.
    const html = render(PAUL_ALCARAZ, "live", { status: "live" }, LINE);
    expect(countOf(html, 'data-inline-ladder="1"')).toBe(1);
    expect(countOf(html, "data-density-segment")).toBe(12);
  });
});

describe("#3210 · the rule is not a tennis rule", () => {
  it("an NBA card with two rungs names them too", () => {
    const html = renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={markets(PAUL_ALCARAZ, { home_score: 58, away_score: 55 }) as never}
        eventStatus="scheduled"
        homeTeam="Boston Celtics"
        awayTeam="Miami Heat"
        homeAbbr="BOS"
        awayAbbr="MIA"
        homeWinProb={0.6}
        awayWinProb={0.4}
        homeSpread={-4.5}
        sportKey="basketball_nba"
      />
    );
    expect(visibleText(html)).toContain("Two lines quoted");
    expect(visibleText(html)).not.toContain("Expected points distribution");
  });
});
