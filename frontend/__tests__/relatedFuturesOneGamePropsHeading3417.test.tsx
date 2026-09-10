/**
 * #3417 — "BIGGER PICTURE" PRINTS ITS HEADING STACK ONCE, NOT ONCE PER SIDE.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/events/15309061` (Zverev–Khachanov, US Open men's semi-final) at 390px on
 * 2026-09-10, verbatim:
 *
 *     Bigger Picture · Season context            cross-source aggregated
 *       GAME PROPS
 *         EXACT MATCH SCORE (3)   [AZ 3-1 25%] [AZ 3-0 23%] [AZ 3-2 14%]
 *         OTHER (1)               [Alexander Zv…  82%]
 *       GAME PROPS
 *         EXACT MATCH SCORE (3)   [KK 3-2  9%] [KK 3-1  7%] [KK 3-0  4%]
 *         OTHER (1)               [Karen Khacha…  19%]
 *
 * Every heading appears twice, and NOTHING in the heading stack says the first
 * block is Zverev and the second is Khachanov — the only cue is the two-letter
 * initial inside each tile. Originally filed from a women's semi-final on
 * 2026-09-06 and still reproducing on the men's four days later.
 *
 * ═══ THE MECHANISM ═══
 *
 * `StatPropsSection` emitted the `Game props` eyebrow itself, and the rail calls
 * it once per side. So the eyebrow — which names the SECTION — was rendered by
 * the thing being sectioned, and appeared as many times as there were sides with
 * props. This is the same grammar error as #4460, where a map-column eyebrow that
 * names a GROUP was printed above a single card that already carried the name.
 *
 * The repair moves the eyebrow up to the pair. It is deliberately placed on the
 * SAME gate as the wrapper it now lives in — the #3775 gate, computed from the
 * DRAWING rows rather than the payload rows — so a heading still cannot open over
 * a section whose bodies all return `null`. That invariant is #3775's and is
 * guarded there; this file must not be read as re-proving it.
 *
 * ═══ WHY A RENDER TEST, AND WHY A COUNT ═══
 *
 * The defect is a COUNT, not a presence: "Game props" was in the markup before
 * the fix and is in the markup after it. Every `toContain("Game props")`
 * assertion is green ON THE BUG. Only counting occurrences separates the two
 * states, so these assertions are `toBe(1)` on a global match.
 *
 * `toBe(1)` is also the both-directions guard (gotcha #43) in a single
 * assertion: re-inlining the eyebrue into the per-side component takes it to 2,
 * and deleting the eyebrow altogether takes it to 0. Both fail. A test written as
 * `not.toBe(2)` would have been passed perfectly by deleting the heading, which
 * is the worse bug — Bigger Picture would then open with an unlabelled grid.
 *
 * The live/finished label variants are pinned on `gamePropsHeading` directly
 * rather than through a render, because reaching them needs a box score AND a
 * matching event status: a render test written at one clock would quietly assert
 * only the scheduled string and report full coverage.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures, { gamePropsHeading } from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15309061;
const HOME = "Zverev";
const AWAY = "Khachanov";

/** A related-futures row, defaulted to the reported page's shape. */
function row(over: Partial<RelatedFuture> = {}): RelatedFuture {
  return {
    market_id: 7001,
    market_name: "Zverev vs Khachanov",
    display_category: "game_prop",
    market_tier: 5,
    category: "game",
    source: "kalshi",
    outcome_id: 9001,
    outcome_name: HOME,
    probability: 0.62,
    american_odds: null,
    probability_change_24h: null,
    opening_probability: null,
    rank: null,
    relevance_score: 1,
    relevance_reason: "same match",
    last_updated: null,
    next_update_expected: "",
    resolution_date: null,
    ...over,
  };
}

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

/**
 * Render the section for one payload.
 *
 * `homeStandings` / `awayStandings` are omitted and `teamProgression` is unset
 * for the same reason as #3775: either would open the section on its own and
 * mask what these cases are measuring.
 */
function render(futures: { home?: RelatedFuture[]; away?: RelatedFuture[] }): string {
  const home = futures.home ?? [];
  const away = futures.away ?? [];
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: home,
    away_team_futures: away,
    series_markets: [],
    total_count: home.length + away.length,
    summary: null,
    event_status: "scheduled",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;

  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: EVENT_ID,
      homeTeam: HOME,
      awayTeam: AWAY,
    }),
  );
}

/** How many times the section eyebrow appears in the served markup. */
function headingCount(html: string): number {
  return (html.match(/Game props/g) ?? []).length;
}

describe("#3417 — one 'Game props' eyebrow per section, never one per side", () => {
  it("THE REPORTED PAGE: props on BOTH sides print the eyebrow exactly once", () => {
    // The shape that produced the screenshot: each player's leg of the match
    // arrives as its own `game_prop` row, so both sides render a stat section.
    // Before the repair this markup carried the eyebrow twice.
    const html = render({
      home: [row({ outcome_id: 9001, outcome_name: HOME, probability: 0.62 })],
      away: [
        row({
          market_id: 7002,
          outcome_id: 9002,
          outcome_name: AWAY,
          probability: 0.38,
        }),
      ],
    });

    expect(headingCount(html)).toBe(1);

    // …and the repair removed a HEADING, not the content under it. Both sides'
    // cards must still be on the page, or this passes for the wrong reason.
    expect(html).toContain("Bigger Picture");
    expect(html).toContain(HOME);
    expect(html).toContain(AWAY);
  });

  it("CONTROL: props on ONE side still print the eyebrow exactly once", () => {
    // One field differs from the case above — the away side is empty. This is
    // the direction that fails if the repair hoisted the eyebrow into a branch
    // that only fires for pairs.
    const html = render({
      home: [row({ outcome_id: 9001, outcome_name: HOME, probability: 0.62 })],
    });

    expect(headingCount(html)).toBe(1);
    expect(html).toContain(HOME);
  });

  it("the per-category sub-headings still name their groups", () => {
    // The inner headings are NOT what this issue's first defect is about, and
    // hoisting the outer one must not have taken them with it. `extractStatCategory`
    // reads the text after the colon, so this row heads its group "Exact match score".
    const html = render({
      home: [
        row({
          market_name: "Alexander Zverev vs Karen Khachanov: Exact Match Score",
          outcome_id: 9001,
          outcome_name: "Alexander Zverev wins 3-1",
          probability: 0.25,
        }),
      ],
    });

    expect(headingCount(html)).toBe(1);
    expect(html).toContain("Exact match score");
  });

  it("a section that draws nothing gets no eyebrow at all", () => {
    // The #3775 invariant, restated here only because the eyebrow MOVED onto that
    // gate in this change and a regression would now show up as a heading over an
    // empty section. Both rows are pinned at the rails `visibleStatProps` drops.
    const html = render({
      home: [row({ probability: 0.99, outcome_id: 9001 })],
      away: [row({ probability: 0.01, outcome_id: 9002, market_id: 7002 })],
    });

    expect(headingCount(html)).toBe(0);
    expect(html).toBe("");
  });

  describe("gamePropsHeading pins all three labels", () => {
    // Reached through the helper rather than a render: the live and finished
    // strings need a box score AND the matching status, and a render-only test
    // would silently cover just the scheduled one.
    it("scheduled — no box score", () => {
      expect(gamePropsHeading({})).toBe("Game props");
      expect(gamePropsHeading({ isFinished: true })).toBe("Game props");
      expect(gamePropsHeading({ isLive: true })).toBe("Game props");
    });

    it("finished, with a box score, grades the props", () => {
      expect(gamePropsHeading({ isFinished: true, hasBoxScore: true })).toBe(
        "Game props — results",
      );
    });

    it("live, with a box score, marks them live", () => {
      expect(gamePropsHeading({ isLive: true, hasBoxScore: true })).toBe(
        "Game props — live",
      );
    });

    it("finished wins over live when both are set", () => {
      // Not decoration: `isLive` is not always cleared the instant an event
      // finishes, and "— live" over a settled grid is the worse of the two.
      expect(
        gamePropsHeading({ isFinished: true, isLive: true, hasBoxScore: true }),
      ).toBe("Game props — results");
    });
  });
});
