/**
 * #3769 — A SETTLED GAMES MAP SAID THE *PREGAME* CHANCE OF CLEARING 36.5 GAMES
 * WAS 0%, TWO ROWS UNDER ITS OWN "PRE-GAME 33" TILE.
 *
 * Seen on production at 390px on 2026-09-06:
 *
 *   `/events/15304847` — Paul d. by Alcaraz, 6-4 6-3 6-4, 29 games, completed
 *
 *     GAMES MAP · Total: expected vs final
 *        FINAL 29 games        PRE-GAME 33
 *     PREGAME CHANCE OF GOING OVER
 *        Over 36.5 ........ 0%
 *        Over 40.5 ........ 0%
 *
 * The card contradicted itself two rows apart: a total 3.5 games above its own
 * stated expectation is not a 0% proposition, and a book had hung a 36.5 line
 * (`bookmaker_odds`: betrivers 36.5, betus 36.0, betonlineag 35.5) — no book
 * hangs a line at 0%.
 *
 * `/api/events/{id}/game-markets`, `totals[].over_probability`, measured the
 * same minute:
 *
 *   15304847  completed   36.5 -> 0.0005   40.5 -> 0.0005
 *   15305016  completed   36.5 -> 0.0045   38.5 -> 0.001   40.5 -> 0.0005
 *   15305580  SCHEDULED   21.5 -> 0.445    22.5 -> 0.445     <- the control arm
 *
 * The field is read LIVE and collapses on settlement. Only the heading claimed
 * it was pregame, and `done` was the ONE branch in which the word appeared.
 *
 * ## What makes this suite non-vacuous
 *
 * Handing `outcome: "missed"` to `MarketMap` and asserting it renders "not
 * cleared" proves the renderer branches and proves nothing about whether the
 * page derives the grade — the same shape that let this ship. So the decisive
 * test (`derives the grade from the payload the page actually gets`) renders
 * the REAL `MarketMapSection` over Paul–Alcaraz's real numbers and reads the
 * words off the markup. The `MarketMap`-level cases below it cover the heading
 * branches, including the popover home #3210 gave this ladder — a heading fixed
 * inline is not fixed behind the hover.
 *
 * The collapsed 0.0005 is kept verbatim in every settled fixture on purpose:
 * the fix is not "get a better number", it is "stop describing this one as
 * something it is not".
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMap, { ladderGraded, type MarketMapLadderRow } from "@/components/MarketMap";
import MarketMapSection from "@/components/MarketMapSection";

/** Strip tags so an assertion reads the words a fan reads, not the markup. */
function visibleText(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

// ── The real payload ────────────────────────────────────────────────────────

/** Paul–Alcaraz's two rungs, at the resolved prices production served. */
const ALCARAZ_TOTALS = [
  {
    threshold: 36.5,
    over_probability: 0.0005,
    source: "kalshi",
    market_type: "game_total",
    market_name: "Paul vs Alcaraz: Total Games",
    outcome_name: "Over 36.5 games",
    is_winner: null,
    resolution_source: null,
    movement: 0,
    period: null,
  },
  {
    threshold: 40.5,
    over_probability: 0.0005,
    source: "kalshi",
    market_type: "game_total",
    market_name: "Paul vs Alcaraz: Total Games",
    outcome_name: "Over 40.5 games",
    is_winner: null,
    resolution_source: null,
    movement: 0,
    period: null,
  },
];

/** 6-4 6-3 6-4 = 29 games; the FINAL tile reads 29 off this same `pace`. */
const ALCARAZ_PACE = { total_scored: 29, projected_total: null };

function alcarazMarkets(over: Record<string, unknown> = {}) {
  return {
    event_id: 15304847,
    home_team: "Tommy Paul",
    away_team: "Carlos Alcaraz",
    home_score: 0,
    away_score: 3,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: ALCARAZ_PACE,
    props_script: [],
    spreads: [],
    totals: ALCARAZ_TOTALS,
    ...over,
  };
}

function renderSection(gameMarkets: ReturnType<typeof alcarazMarkets>, eventStatus: string) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={gameMarkets as never}
        eventStatus={eventStatus as never}
        homeTeam="Tommy Paul"
        awayTeam="Carlos Alcaraz"
        homeAbbr="PAU"
        awayAbbr="ALC"
        homeWinProb={0.03}
        awayWinProb={0.97}
        homeSpread={5.8}
        overUnder={33.4}
        sportKey="tennis_atp_us_open"
        linescore={{
          sets: [
            [4, 6],
            [3, 6],
            [4, 6],
          ] as [number, number][],
          home_games: 11,
          away_games: 18,
          source: "espn",
        }}
      />
    )
  );
}

// ── The decisive test ───────────────────────────────────────────────────────

describe("#3769 the page derives the grade, it is not handed one", () => {
  it("derives the grade from the payload the page actually gets", () => {
    const text = renderSection(alcarazMarkets(), "completed");

    // The defect, in the reader's own words.
    expect(text.toLowerCase()).not.toContain("pregame chance");
    // 0% was the resolved price wearing a pregame label. A settled rung has a
    // result, so there is no percentage over it at all.
    expect(text).not.toMatch(/Over 36\.5\s+0%/);

    // ...and what it says instead: 29 games cleared neither line.
    expect(text).toContain("Over 36.5");
    expect(text).toContain("not cleared");
  });

  it("still quotes the same rungs while the match is live", () => {
    // Same collapsed numbers, unsettled card: the page has no final to grade
    // against, so it must keep asking rather than start asserting.
    const text = renderSection(alcarazMarkets({ status: "live" }), "live");
    expect(text).not.toContain("not cleared");
    expect(text).not.toContain("Each line vs the final");
  });
});

// ── The heading branches ────────────────────────────────────────────────────

function renderMap(overrides: {
  ladder: MarketMapLadderRow[];
  status: "pre" | "live" | "done";
  variant?: "margin" | "total";
  bandDrawsShape?: boolean;
}) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMap
        variant={overrides.variant ?? "total"}
        title="Total: expected vs final"
        subtitle="Where it landed vs what was expected"
        headline=""
        rangeMin={26}
        rangeMax={44}
        density={[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}
        accentRgb="139,92,246"
        axisLabels={{ left: "26", mid: "35", right: "44+" }}
        markers={[]}
        ladder={overrides.ladder}
        status={overrides.status}
        // Paul–Alcaraz: two rungs both at ~0 draw no shape, which is the only
        // reason the ladder was on the card rather than behind a hover.
        bandDrawsShape={overrides.bandDrawsShape ?? false}
      />
    )
  );
}

const settledLadder = (): MarketMapLadderRow[] =>
  [36.5, 40.5].map((threshold) => ({
    label: `Over ${threshold}`,
    probability: 0, // Math.round(0.0005 * 100)
    side: "right" as const,
    outcome: "missed" as const,
  }));

describe("#3769 a settled ladder grades rather than quotes", () => {
  it("never says 'pregame' — the one branch where the word appeared", () => {
    expect(renderMap({ ladder: settledLadder(), status: "done" }).toLowerCase()).not.toContain(
      "pregame"
    );
  });

  it("says how each line finished", () => {
    const text = renderMap({ ladder: settledLadder(), status: "done" });
    expect(text).toContain("Each line vs the final");
    expect(text).toContain("not cleared");
    expect(text).not.toContain("0%");
  });

  it("says 'cleared' for a line the final actually beat", () => {
    const text = renderMap({
      status: "done",
      ladder: [
        { label: "Over 24.5", probability: 100, side: "right", outcome: "cleared" },
        { label: "Over 36.5", probability: 0, side: "right", outcome: "missed" },
      ],
    });
    expect(text).toContain("cleared");
    expect(text).toContain("not cleared");
  });

  it("grades in the popover home too, not just the inline one (#3210 gave it two)", () => {
    const text = renderMap({ ladder: settledLadder(), status: "done", bandDrawsShape: true });
    expect(text.toLowerCase()).not.toContain("pregame");
    expect(text).toContain("Each line vs the final");
  });
});

describe("#3769 the branches that were already true stay true", () => {
  const quoted: MarketMapLadderRow[] = [
    { label: "Over 21.5", probability: 45, side: "right" },
    { label: "Over 22.5", probability: 44, side: "right" },
  ];

  it("still asks about the chance, with its bars, before the match", () => {
    const text = renderMap({ ladder: quoted, status: "pre" });
    expect(text).toContain("Chance of going over");
    expect(text).toContain("45%");
  });

  it("still asks about the chance while the match is live", () => {
    expect(renderMap({ ladder: quoted, status: "live" })).toContain("Chance of going over");
  });

  it("keeps the margin variant's own verb", () => {
    expect(renderMap({ ladder: quoted, status: "pre", variant: "margin" })).toContain(
      "Chance of winning by"
    );
  });
});

describe("#3769 a settled ladder with nothing to grade against says what it has", () => {
  // A card can be `done` and hold no final — an abandoned match, or a sport
  // whose scoreboard does not count this market's unit. The rung is then
  // genuinely a last quote, and saying so is #3645's shipped vocabulary.
  const ungraded: MarketMapLadderRow[] = [{ label: "Over 36.5", probability: 0, side: "right" }];

  it("calls the number a last quote rather than a pregame chance", () => {
    const text = renderMap({ ladder: ungraded, status: "done" });
    expect(text).toContain("Last quote for going over");
    expect(text.toLowerCase()).not.toContain("pregame");
  });

  it("uses the margin verb in the same breath", () => {
    expect(renderMap({ ladder: ungraded, status: "done", variant: "margin" })).toContain(
      "Last quote for winning by"
    );
  });
});

describe("#3769 ladderGraded is all-or-nothing", () => {
  const halfGraded: MarketMapLadderRow[] = [
    { label: "Over 36.5", probability: 0, side: "right", outcome: "missed" },
    { label: "Over 40.5", probability: 0, side: "right" },
  ];

  it("refuses a ladder where only some rungs know how they finished", () => {
    // A half-graded ladder prints "cleared" beside "0%" and invites the reader
    // to read the 0% as the odds of the thing next to it.
    expect(ladderGraded(halfGraded)).toBe(false);
  });

  it("is false for an empty ladder", () => {
    expect(ladderGraded([])).toBe(false);
  });

  it("is true only when every rung carries an outcome", () => {
    expect(ladderGraded(settledLadder())).toBe(true);
  });

  it("falls back to quoting, and the heading follows it", () => {
    const text = renderMap({ status: "done", ladder: halfGraded });
    expect(text).toContain("Last quote for going over");
    expect(text).not.toContain("Each line vs the final");
  });
});
