/**
 * #5502 — A SETTLED HALF TOTALS MAP STOPS CALLING A SETTLEMENT LEFTOVER A LINE.
 *
 * #5143 taught this card that a ladder with NO rung between 0.15 and 0.85 has
 * stopped quoting and cannot carry a Pre-game tile. It did not ask what ONE
 * rung in there means after the whistle. Mystery-shopped on production at
 * 390px, 2026-09-11 21:36 PT, `/events/15303008` (Stade Rennais 1-0 Olympique
 * Marseille, Ligue 1, settled):
 *
 *   1st half goals map    (no tile — #5143 working)
 *   2nd half goals map    PRE-GAME 2
 *
 * The match produced one goal, in the second half. Read the same minute from
 * `/api/events/15303008/game-markets`, the payload the page reads:
 *
 *   Over 0.5 → 0.99     Over 1.5 → 0.20     Over 2.5 → 0.01
 *
 * The ends are graded correctly against a one-goal half. The 0.20 is Over 1.5
 * resolved FALSE and still wearing a tradeable-looking price — settlement does
 * not land on every rung at once. It is the only rung inside the band, so
 * `ladderQuotesALine` passes, `ouLine` elects it as closest to a coin flip, and
 * `Math.round(1.5)` prints 2 under a label claiming somebody expected it.
 *
 * ═══ WHY THE COUNT, AND WHY TWO ═══
 *
 * Measured (lane1/260) over every event with `status='completed'` and
 * `commence_time > NOW() - 3 days`, read from `/api/events/<id>/game-markets`
 * and selected with the page's own `selectHalfTotalRungs`: 170 events, 87 with
 * period markets, **76 half cards that render**.
 *
 *   0 interior rungs   72   no tile today, already correct
 *   exactly 1           2   the defect — both are settlement leftovers
 *   2 or more           2   genuine, a real line passing through the middle
 *
 * The four cards that print a tile are the four fixtures below. The count
 * splits that population exactly and is decidable from the ladder alone. The
 * other live candidate — "the interior rung must be monotone with its
 * neighbours" — reaches the same two rows but needs a second tuned constant to
 * say how big a step is a step, and this sample gives it nothing to tune
 * against. Dropping the tile on `isDone` outright stays rejected: it inverts
 * #5143's own control and would take the two genuine cards with it.
 *
 * ═══ WHAT MAKES THIS SUITE NON-VACUOUS ═══
 *
 * "No Pre-game tile" is also what a card that never rendered looks like, so
 * every arm renders the REAL `MarketMapSection` and each defect arm asserts its
 * card is STILL THERE by title and still naming its rungs underneath. The
 * controls differ from the defect arms only in the probabilities on the ladder,
 * or only in the event status. Each arm kills a different wrong fix: the
 * genuine controls kill `isDone` and kill a required count of three, the
 * unfinished control kills a rule that forgot to scope itself to settled cards,
 * and the zero-interior arm kills one that suppressed the card whole.
 *
 * Tiles are asserted through `data-tile`, not through the words: "Pre-game"
 * appears on other cards in this section and the digit 2 appears inside ladder
 * labels like "Over 2.5".
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import {
  LADDER_INTERIOR_MAX,
  LADDER_INTERIOR_MIN,
  SETTLED_INTERIOR_RUNGS_REQUIRED,
  countInteriorRungs,
  ladderQuotesALine,
  probabilitiesQuoteALine,
  probabilitiesQuoteASettledLine,
  settledLadderQuotesALine,
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

type Rung = [threshold: number, overProbability: number];

/**
 * The four ladders production served, each `[threshold, over_probability]`,
 * exactly as the census read them.
 */

/** `/events/15303008` 2H — Ligue 1, Rennes 1-0 Marseille. One goal all match. */
const RENNES_2H: Rung[] = [
  [0.5, 0.99],
  [1.5, 0.2],
  [2.5, 0.01],
];

/** `/events/15296764` 2H — UCL, Man Utd 4-0 Sabah. `1.00` is a resolved rung. */
const UNITED_2H: Rung[] = [
  [0.5, 1.0],
  [1.5, 0.79],
];

/** `/events/15296863` 1H — UCL, Como 4-1 Leipzig. A real line through the middle. */
const COMO_1H: Rung[] = [
  [0.5, 0.785],
  [2.5, 0.185],
];

/** `/events/15296762` 1H — UCL, PSV 1-1 Shakhtar. The same shape. */
const PSV_1H: Rung[] = [
  [0.5, 0.785],
  [2.5, 0.195],
];

/** `/events/15303008` 1H as served — no interior at all, the #5143 population. */
const RENNES_1H_DEAD: Rung[] = [
  [0.5, 0.99],
  [1.5, 0.01],
];

const HOME = "Stade Rennais";
const AWAY = "Marseille";

function half(period: "1H" | "2H", rungs: Rung[]) {
  const label = period === "1H" ? "First" : "Second";
  return rungs.map(([threshold, over]) => ({
    market_name: `${HOME} vs ${AWAY}: ${label} Half Total`,
    outcome_name: `Over ${threshold} ${period} goals scored`,
    threshold,
    probability: null,
    market_type: "half_total",
    over_probability: over,
    period,
    source: "kalshi",
    is_winner: null,
    resolution_source: "api_settlement",
    movement: 0,
  }));
}

function markets(period: "1H" | "2H", rungs: Rung[]) {
  return {
    event_id: 15303008,
    home_team: HOME,
    away_team: AWAY,
    home_score: 1,
    away_score: 0,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: half(period, rungs),
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [],
    totals: [],
  };
}

/**
 * The section as the finished event page mounts it, holding ONE half's ladder.
 * No `spreads` and no `totals`, so the only card in the markup is that half's
 * goals map and every `data-tile` below belongs to it.
 */
function renderMap(
  period: "1H" | "2H",
  rungs: Rung[],
  eventStatus: "completed" | "scheduled" = "completed"
): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={markets(period, rungs) as never}
      eventStatus={eventStatus}
      homeTeam={HOME}
      awayTeam={AWAY}
      homeAbbr="REN"
      awayAbbr="OLM"
      sportKey="soccer_france_ligue_one"
    />
  );
}

const cardTitle = (period: "1H" | "2H") =>
  period === "1H" ? "1st half goals map" : "2nd half goals map";

describe("#5502 a settled half totals card drops the rung settlement left behind", () => {
  it("prints no Pre-game tile on the page Alex would have read", () => {
    const html = renderMap("2H", RENNES_2H);
    const text = visibleText(html);

    // The card is still here: its title, the subtitle it earns by drawing a
    // real shape, and all three rungs. This is what makes the assertion below
    // an assertion rather than a description of a card that vanished.
    //
    // The rungs are in the markup rather than on the face of the card — a band
    // that draws a shape moves its ladder into the tap popover (`MarketMap`,
    // #3210), which is what the production shot shows. Presence is still the
    // point: the card and its data survive, only the tile goes.
    expect(text).toContain(cardTitle("2H"));
    expect(text).toContain("2nd half goals distribution");
    expect(text).toContain("Over 0.5");
    expect(text).toContain("Over 1.5");
    expect(text).toContain("Over 2.5");

    // And `PRE-GAME 2` is gone. Note "Over 1.5" SURVIVES above, in the ladder,
    // where 20% is printed beside it and it reads as the settled quote it is.
    // What goes is the tile that lifted it out and called it expected.
    expect(tileCount(html, "pre")).toBe(0);
  });

  it("prints no Pre-game tile on the second card the census found", () => {
    // `/events/15296764` — a two-rung ladder whose lower rung has already
    // resolved to exactly 1.00, leaving 0.79 alone in the band.
    const html = renderMap("2H", UNITED_2H);

    expect(visibleText(html)).toContain(cardTitle("2H"));
    expect(tileCount(html, "pre")).toBe(0);
  });

  it("CONTROL: a finished card with a real line through the middle keeps it", () => {
    // `/events/15296863`. Same status, same everything — only the
    // probabilities differ, and neither rung here is a settled one. A fix
    // keyed on `isDone` deletes this tile and fails, which is the answer #5143
    // already rejected and pinned its own control against.
    const html = renderMap("1H", COMO_1H);

    expect(tileCount(html, "pre")).toBe(1);
    expect(visibleText(html)).toContain(cardTitle("1H"));
  });

  it("CONTROL: and so does the fourth card, the other genuine one", () => {
    // `/events/15296762`. Two interior rungs, so a rule that demanded three
    // would take a tile this card has earned. That is the upper side of the
    // constant, pinned on a production row rather than on an invented one.
    const html = renderMap("1H", PSV_1H);

    expect(tileCount(html, "pre")).toBe(1);
  });

  it("CONTROL: before the whistle one interior rung is still a line", () => {
    // The side of the rule this ship makes no claim about. A live ladder with
    // a single rung in the band is quoting, and the census measured settled
    // cards only. A fix written without the `isDone` scoping passes every
    // assertion above and fails here.
    const html = renderMap("2H", RENNES_2H, "scheduled");

    expect(tileCount(html, "pre")).toBe(1);
    expect(visibleText(html)).toContain(cardTitle("2H"));
  });

  it("CONTROL: #5013 is intact — a finished dead ladder keeps its card", () => {
    // Zero interior rungs: no tile before this ship and none after, but the
    // CARD survives, because after the whistle it carries the half's real
    // shape. A fix that suppressed the finished card whole fails here.
    const html = renderMap("1H", RENNES_1H_DEAD);

    expect(visibleText(html)).toContain(cardTitle("1H"));
    expect(tileCount(html, "pre")).toBe(0);
  });
});

describe("#5502 the settled test is the same bounds, counted", () => {
  it("counts rungs inside the band, inclusive of both edges", () => {
    expect(countInteriorRungs([])).toBe(0);
    expect(countInteriorRungs([LADDER_INTERIOR_MIN, LADDER_INTERIOR_MAX])).toBe(2);
    expect(countInteriorRungs([LADDER_INTERIOR_MIN - 0.001])).toBe(0);
    expect(countInteriorRungs([LADDER_INTERIOR_MAX + 0.001])).toBe(0);
    expect(countInteriorRungs([0.99, 0.2, 0.01])).toBe(1);
  });

  it("never disagrees with the live test about where the interior is", () => {
    // Both rules read one body, so the settled one cannot drift onto its own
    // copy of the bounds. A copy rather than a call is what this pins against:
    // wherever the settled test says yes, the live test must already say yes.
    const cases = [
      [],
      [0.99, 0.01],
      [0.99, 0.2, 0.01],
      [0.785, 0.185],
      [LADDER_INTERIOR_MIN, LADDER_INTERIOR_MAX],
      [LADDER_INTERIOR_MIN - 0.001, LADDER_INTERIOR_MAX + 0.001],
    ];
    for (const probs of cases) {
      expect(probabilitiesQuoteASettledLine(probs)).toBe(
        countInteriorRungs(probs) >= SETTLED_INTERIOR_RUNGS_REQUIRED
      );
      if (probabilitiesQuoteASettledLine(probs)) {
        expect(probabilitiesQuoteALine(probs)).toBe(true);
      }
    }
  });

  it("answers it identically through the totals wrapper", () => {
    const cases = [[0.99, 0.2, 0.01], [0.785, 0.185], [1.0, 0.79], []];
    for (const probs of cases) {
      expect(
        settledLadderQuotesALine(probs.map((p) => ({ overProbability: p })))
      ).toBe(probabilitiesQuoteASettledLine(probs));
      expect(ladderQuotesALine(probs.map((p) => ({ overProbability: p })))).toBe(
        probabilitiesQuoteALine(probs)
      );
    }
  });

  it("splits the four production ladders that decided the constant", () => {
    const defects = [RENNES_2H, UNITED_2H];
    const genuine = [COMO_1H, PSV_1H];

    for (const ladder of defects) {
      const probs = ladder.map(([, p]) => p);
      // Both are inside the band for the LIVE test — that is the whole reason
      // the defect reached production — and outside it for the settled one.
      expect(probabilitiesQuoteALine(probs)).toBe(true);
      expect(countInteriorRungs(probs)).toBe(1);
      expect(probabilitiesQuoteASettledLine(probs)).toBe(false);
    }
    for (const ladder of genuine) {
      const probs = ladder.map(([, p]) => p);
      expect(countInteriorRungs(probs)).toBe(2);
      expect(probabilitiesQuoteASettledLine(probs)).toBe(true);
    }
  });

  it("pins the constant from BOTH sides against that population", () => {
    // Lowering it to 1 is today's behaviour and keeps both defects; raising it
    // to 3 drops both genuine cards. 2 is the only value that splits the
    // measured population, and this fails if someone moves it either way.
    expect(SETTLED_INTERIOR_RUNGS_REQUIRED).toBe(2);

    const interior = (l: Rung[]) => countInteriorRungs(l.map(([, p]) => p));
    expect([RENNES_2H, UNITED_2H].every((l) => interior(l) >= 1)).toBe(true);
    expect([COMO_1H, PSV_1H].every((l) => interior(l) >= 3)).toBe(false);
  });
});
