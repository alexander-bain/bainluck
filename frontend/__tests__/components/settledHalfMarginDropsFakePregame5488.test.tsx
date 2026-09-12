/**
 * #5488 — A SETTLED HALF MARGIN MAP STOPS PRINTING A FORECAST IT DOES NOT HAVE.
 *
 * The half TOTALS map learned this in #5143. The half MARGIN map beside it never
 * did, and it is the same defect off the same kind of ladder. Mystery-shopped on
 * production at 390px, 2026-09-11 21:36 PT, `/events/15303008` (Stade Rennais
 * 1-0 Olympique Marseille, Ligue 1, settled):
 *
 *   1st half margin    PRE-GAME  REN by 1.5+
 *   2nd half margin    PRE-GAME  OLM by 1.5+
 *
 * Marseille lost. Neither card carries a FINAL beside it — soccer serves no half
 * scores — so on a finished match the ONLY thing either card said about the
 * halves was a number nobody ever quoted, under a label claiming somebody had.
 *
 * ═══ WHERE THE NUMBER COMES FROM ═══
 *
 * The marker is `closest50`, the rung nearest a coin flip in the ladder AS IT
 * STANDS. After the whistle the rungs are the settled ones. Measured the same
 * minute from `/api/events/15303008/game-markets`, which is what the page reads:
 *
 *   1H  REN by more than 1.5 → 0.01     OLM by more than 1.5 → 0.01
 *   2H  REN by more than 1.5 → 0.005    OLM by more than 1.5 → 0.02
 *
 * Every rung is ~49 points from the middle, so "closest to 50%" returns whichever
 * side settlement happened to leave nearest — 0.02 on the 2nd half, which is why
 * the card named the team that lost, and a tie broken on array order on the 1st.
 * The same read of `/api/events/15304450/game-markets` (Boston College 28-21
 * Rutgers, NCAAF, settled) found 21 rungs on its 1st half of which every single
 * one is 0.99, 0.04 or 0.01. Neither ladder has a rung anywhere near the middle.
 *
 * The full-game rail above these escapes by falling back to the frozen
 * `opening_home_spread` (#5414). There is no `opening_half_spread` column, so a
 * half has no pre-game quantity at all.
 *
 * ═══ WHY THE TEST IS THE LADDER AND NOT `isDone` ═══
 *
 * Because #5143 already ruled that for the sibling card and pinned a control
 * against the other answer (`settledHalfMapDropsFakePregame5143`, "a finished
 * game whose ladders DID quote keeps its Pre-game"). Answering the same question
 * two ways on two cards of one family is the drift that rule exists to stop, so
 * the margin map reaches #5013's bounds through `probabilitiesQuoteALine` — the
 * shared body, not a second copy — and the arms below pin it from BOTH sides:
 * the defect arm fails a fix that does nothing, the finished-and-quoting control
 * fails a fix keyed on `isDone`, and the unfinished-and-dead control fails a fix
 * that dropped the `!isDone` half of the condition and took the live Projection
 * marker with it.
 *
 * ═══ WHAT MAKES THIS SUITE NON-VACUOUS ═══
 *
 * "No Pre-game tile" is also what a card that never rendered looks like. So every
 * arm renders the REAL `MarketMapSection`, and the defect arm asserts both cards
 * are STILL THERE by title and still draw their rungs. The controls differ from
 * it only in the four probabilities, or only in the event status.
 *
 * Tiles are asserted through `data-tile`, not through the words: "Pre-game"
 * appears on other cards in this section.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import {
  LADDER_INTERIOR_MAX,
  LADDER_INTERIOR_MIN,
  ladderQuotesALine,
  probabilitiesQuoteALine,
} from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** How many summary tiles of this kind the section drew. */
function tileCount(html: string, key: string): number {
  return html.split(`data-tile="${key}"`).length - 1;
}

const HOME = "Stade Rennais";
const AWAY = "Marseille";

/** `/events/15303008`'s half spread ladders as production served them, settled. */
const SETTLED_1H = { home: 0.01, away: 0.01 };
const SETTLED_2H = { home: 0.005, away: 0.02 };

/** The same four rungs with an interior — a ladder still quoting a line. */
const QUOTING_1H = { home: 0.42, away: 0.33 };
const QUOTING_2H = { home: 0.55, away: 0.28 };

function half(period: "1H" | "2H", probs: { home: number; away: number }) {
  const label = period === "1H" ? "First" : "Second";
  return [HOME, AWAY].map((team) => ({
    market_name: `${HOME} vs ${AWAY}: ${label} Half Spread`,
    outcome_name: `${team} wins the ${period} by more than 1.5 goals`,
    threshold: period === "1H" ? 1.0 : 2.0,
    probability: team === HOME ? probs.home : probs.away,
    market_type: "half_spread",
    over_probability: null,
    period,
    source: "kalshi",
    is_winner: null,
    resolution_source: "api_settlement",
    movement: 0,
  }));
}

function markets(
  firstHalf: { home: number; away: number },
  secondHalf: { home: number; away: number }
) {
  return {
    event_id: 15303008,
    home_team: HOME,
    away_team: AWAY,
    home_score: 1,
    away_score: 0,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: [...half("1H", firstHalf), ...half("2H", secondHalf)],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [],
    totals: [],
  };
}

/**
 * The section as the finished event page mounts it. No `spreads` and no
 * `totals`, so the only cards in the markup are the two half margin maps and
 * every `data-tile` below belongs to one of them.
 */
function renderMaps(
  firstHalf: { home: number; away: number },
  secondHalf: { home: number; away: number },
  eventStatus: "completed" | "scheduled" = "completed"
): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={markets(firstHalf, secondHalf) as never}
      eventStatus={eventStatus}
      homeTeam={HOME}
      awayTeam={AWAY}
      homeAbbr="REN"
      awayAbbr="OLM"
      sportKey="soccer_france_ligue_one"
    />
  );
}

describe("#5488 a settled half margin card drops the line nobody quoted", () => {
  it("prints no marker on the page Alex would have read", () => {
    const html = renderMaps(SETTLED_1H, SETTLED_2H);
    const text = visibleText(html);

    // Both cards are still here, still drawing their axis and — the point —
    // still naming their rungs underneath. This is what makes the assertion
    // below an assertion rather than a description of two cards that vanished.
    expect(text).toContain("1st half margin");
    expect(text).toContain("2nd half margin");
    expect(text).toContain("REN by 5+");
    expect(text).toContain("OLM by 5+");
    expect(text).toContain("OLM by 1.5+");

    // And the reading that was never a forecast is gone from both. Note the
    // rung strings above SURVIVE, in the ladder, where 1% and 2% are printed
    // beside them and they read as the settled quotes they are. What goes is
    // the tile that lifted one of them out and called it what was expected.
    expect(tileCount(html, "proj")).toBe(0);
    expect(text).not.toContain("Pre-game");
  });

  it("CONTROL: a finished game whose ladders DID quote keeps its marker", () => {
    // Same event, same status, same everything — only the four probabilities
    // differ. A fix keyed on `isDone` rather than on the ladder deletes these
    // two markers as well and fails here, which is the answer #5143 already
    // rejected for the half totals card beside this one.
    const html = renderMaps(QUOTING_1H, QUOTING_2H);
    const text = visibleText(html);

    expect(tileCount(html, "proj")).toBe(2);
    expect(text).toContain("1st half margin");
    expect(text).toContain("2nd half margin");
  });

  it("CONTROL: an unfinished game with a dead ladder keeps its Projection", () => {
    // The side of the rule this ship is NOT making a claim about. Before the
    // whistle the marker is a projection off a live book and the shape test has
    // no business removing it; a fix written as `quotesALine` alone, dropping
    // the `!isDone` arm, passes every assertion above and fails here.
    const html = renderMaps(SETTLED_1H, SETTLED_2H, "scheduled");

    expect(tileCount(html, "proj")).toBe(2);
    expect(visibleText(html)).toContain("2nd half margin");
  });

  it("CONTROL: an unfinished game with live ladders is untouched", () => {
    const html = renderMaps(QUOTING_1H, QUOTING_2H, "scheduled");

    expect(tileCount(html, "proj")).toBe(2);
  });
});

describe("#5488 the two half maps read one set of bounds", () => {
  it("answers the interior question over bare probabilities", () => {
    expect(probabilitiesQuoteALine([LADDER_INTERIOR_MIN])).toBe(true);
    expect(probabilitiesQuoteALine([LADDER_INTERIOR_MAX])).toBe(true);
    expect(probabilitiesQuoteALine([LADDER_INTERIOR_MIN - 0.001])).toBe(false);
    expect(probabilitiesQuoteALine([LADDER_INTERIOR_MAX + 0.001])).toBe(false);
    expect(probabilitiesQuoteALine([])).toBe(false);
  });

  it("answers it identically through the totals wrapper", () => {
    // `ladderQuotesALine` is an adapter over the same body, so the margin map
    // cannot drift from the totals map on where the interior is. A copy of the
    // bounds rather than a call is what this pins against.
    const cases = [
      [0.99, 0.01],
      [0.99, 0.2, 0.01],
      [LADDER_INTERIOR_MIN, LADDER_INTERIOR_MAX],
      [LADDER_INTERIOR_MIN - 0.001],
      [],
    ];
    for (const probs of cases) {
      expect(ladderQuotesALine(probs.map((p) => ({ overProbability: p })))).toBe(
        probabilitiesQuoteALine(probs)
      );
    }
  });

  it("reads the production ladders that produced this ship", () => {
    // `/events/15303008`, both halves, settled — the four rungs above.
    expect(probabilitiesQuoteALine([0.01, 0.01])).toBe(false);
    expect(probabilitiesQuoteALine([0.005, 0.02])).toBe(false);
    // `/events/15304450`'s 1st half, 21 rungs reduced to its three values.
    expect(probabilitiesQuoteALine([0.99, 0.04, 0.01])).toBe(false);
  });
});
