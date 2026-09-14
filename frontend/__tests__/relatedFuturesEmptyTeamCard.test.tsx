/**
 * "BIGGER PICTURE" NEVER DRAWS A TEAM CARD WITH NOTHING IN IT.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/15312489` (FC Porto v Partizan) at 09:05Z on 2026-09-14, phone
 * width: the section drew Porto's card with a `CHAMPIONSHIP PATH` — `Liga
 * Portugal Champion 52%` — and beside it a **Partizan card containing a crest,
 * the word "Partizan", and nothing else**. No path, no awards, not even a
 * record: an empty rounded rectangle taking a phone screen's worth of height.
 *
 * ═══ THE MECHANISM ═══
 *
 * This is #3775 one level down, and the file already carries that lesson for
 * the SECTION. The section gate was a single `seasonCount`, summed over BOTH
 * teams, gating a grid of TWO cards:
 *
 *     gate   seasonCount = homePlayoff + awayPlayoff + awards + … (one number)
 *     body   two cards, each drawing only from ITS OWN side's rows
 *
 * So one side's season context was sufficient to draw the other side's card.
 * Nothing inside a card is gated on that card having content: its whole body is
 * `AdvancementPath` (which returns null on zero stages) and a `PLAYER AWARDS`
 * block (gated on `length > 0`), and its header's record line renders as an
 * empty div when there are no standings.
 *
 * Measured before the repair, 2026-09-14, over 30 sampled live/next-36h events
 * (27 whose section opens): **4 drew an empty card, in BOTH directions** —
 * away-empty on Porto–Partizan and Toulouse–Montpellier, home-empty on Örebro
 * SK–Nordic United and Dundalk–St Patricks.
 *
 * ═══ WHY THE SECTION GATE MOVED IN THE SAME COMMIT ═══
 *
 * Suppressing the empty card is exactly what RE-CREATES #3775 when the other
 * card is empty too: the header and the `N related futures` caption would be
 * left with nothing between them. So the gate is no longer a row count at all —
 * it is the OR of the blocks that actually render. That also drops four terms
 * that no renderer reads (`seasonStats`, `mergedNovelty`, the bolted-on
 * standings term, and `hasGridProgression`, whose renderer was deleted in
 * UX-P152). The last two cases below are the ones that pin that.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * A test that only proved "the empty card disappears" is passed perfectly by
 * never drawing a second card again — which would delete the side-by-side
 * comparison that IS this section. Every suppression case here is paired with a
 * control that changes ONE thing and asserts the card comes back.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15312489;
const HOME = "FC Porto";
const AWAY = "Partizan";

/**
 * Distinct colours are passed on purpose. `hColor`/`aColor` both fall back to
 * one `DEFAULT_COLOR`, and the awards split is `mergedAwards.filter(a =>
 * a.teamColor === hColor)` — so with colours unset an away award is attributed
 * to BOTH cards and the awards cases below would prove nothing about which side
 * drew. (That collision is a real defect in its own right; it is not this
 * ship's, and pinning it here would be pinning it at the wrong address.)
 */
const HOME_COLOR = "#004494";
const AWAY_COLOR = "#000000";

/** A related-futures row, defaulted to the reported page's championship shape. */
function row(over: Partial<RelatedFuture> = {}): RelatedFuture {
  return {
    market_id: 59164821,
    market_name: "Liga Portugal Champion",
    clean_label: "Liga Portugal Champion",
    display_category: "playoff_path",
    market_tier: 1,
    category: "championship",
    source: "kalshi",
    outcome_id: 219749915,
    outcome_name: "Porto",
    probability: 0.515,
    american_odds: -106,
    probability_change_24h: null,
    opening_probability: null,
    rank: 1,
    relevance_score: 51.1,
    relevance_reason: "near 50/50",
    last_updated: null,
    next_update_expected: "",
    resolution_date: null,
    ...over,
  };
}

type Standings = NonNullable<
  React.ComponentProps<typeof RelatedFutures>["homeStandings"]
>;

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

function render(opts: {
  home?: RelatedFuture[];
  away?: RelatedFuture[];
  homeStandings?: Standings;
  awayStandings?: Standings;
  total?: number;
}): string {
  const home = opts.home ?? [];
  const away = opts.away ?? [];
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: home,
    away_team_futures: away,
    series_markets: [],
    total_count: opts.total ?? home.length + away.length,
    summary: null,
    event_status: "live",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;

  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: EVENT_ID,
      homeTeam: HOME,
      awayTeam: AWAY,
      homeTeamColor: HOME_COLOR,
      awayTeamColor: AWAY_COLOR,
      homeStandings: opts.homeStandings,
      awayStandings: opts.awayStandings,
    }),
  );
}

const HOME_CARD = 'data-testid="home-team-card"';
const AWAY_CARD = 'data-testid="away-team-card"';
const CAPTION = /related futures from multiple sources/;

describe("a team card is drawn only when that team has something to show", () => {
  it("THE REPORTED PAGE: Porto has a championship path, Partizan has nothing — only Porto's card draws", () => {
    const html = render({ home: [row()], total: 2 });

    // The section is still here: Porto's context is real and is the point.
    expect(html).toContain("Bigger Picture");
    expect(html).toContain(HOME_CARD);
    expect(html).toContain("Liga Portugal Champion");

    // …and the empty rectangle beside it is gone.
    expect(html).not.toContain(AWAY_CARD);
  });

  it("CONTROL: give Partizan a path of its own and its card comes back", () => {
    // One thing differs from the case above — the away side now has a row.
    const html = render({
      home: [row()],
      away: [
        row({
          market_id: 31834253,
          market_name: "Serbian SuperLiga Champion",
          clean_label: "Serbian SuperLiga Champion",
          outcome_id: 149462883,
          outcome_name: "Partizan",
          probability: 0.31,
        }),
      ],
      total: 2,
    });

    expect(html).toContain(HOME_CARD);
    expect(html).toContain(AWAY_CARD);
    expect(html).toContain("Liga Portugal Champion");
    expect(html).toContain("Serbian SuperLiga Champion");
  });

  it("MIRROR: the home card is suppressed on the same rule — this is not 'the away card is special'", () => {
    // Örebro SK–Nordic United was the home-empty shape in the measured sample.
    const html = render({
      away: [row({ outcome_name: "Partizan", probability: 0.31 })],
      total: 1,
    });

    expect(html).toContain(AWAY_CARD);
    expect(html).not.toContain(HOME_CARD);
  });

  it("A RECORD IS CONTENT: standings alone keep a card that has no futures", () => {
    // The header's record line is the one thing a card can say without any
    // related futures at all, so it must not be suppressed with the rest.
    const html = render({
      home: [row()],
      awayStandings: { wins: 3, losses: 1 } as Standings,
      total: 1,
    });

    expect(html).toContain(HOME_CARD);
    expect(html).toContain(AWAY_CARD);
    expect(html).toContain("3-1");
  });

  it("NEITHER SIDE DRAWS: the whole section goes, rather than a header over nothing (#3775)", () => {
    // This is the case the repair itself could have created: hide both cards
    // and leave "Bigger Picture" above "N related futures from multiple
    // sources" with empty space between them.
    const html = render({ total: 4 });

    expect(html).toBe("");
    expect(html).not.toContain("Bigger Picture");
    expect(html).not.toMatch(CAPTION);
  });

  it("PHANTOM TERM — season_stat rows are counted by no renderer, so they cannot open the section", () => {
    // `seasonStats` is filtered in `categorizeFutures`, was summed into the old
    // gate, and is passed to no component anywhere in the file.
    const html = render({
      home: [
        row({
          display_category: "season_stat",
          market_name: "Porto total points",
          clean_label: "Porto total points",
          probability: 0.5,
        }),
      ],
      total: 1,
    });

    expect(html).toBe("");
  });

  it("PHANTOM TERM — novelty rows likewise: NoveltyScroll is declared and never called", () => {
    const html = render({
      home: [
        row({
          display_category: "novelty",
          market_name: "Will the match go to extra time?",
          clean_label: "Extra time",
          probability: 0.4,
        }),
      ],
      total: 1,
    });

    expect(html).toBe("");
  });
});
