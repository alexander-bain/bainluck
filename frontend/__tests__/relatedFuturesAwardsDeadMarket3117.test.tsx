/**
 * PLAYER AWARDS: THE RIGHT TEAM'S NOMINEES, AND NO PRICE THE VENUE CAN NO LONGER MOVE.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/15304746` (Seahawks v Cowboys) at 390px, 2026-09-18 — re-shot 13
 * days after #3117 was filed, and unchanged. Both team cards printed ONE
 * identical six-row list:
 *
 *     WS  Will Sam Darn…    MVP 45%
 *     WJ  Will Jaxon Sm…    MVP 14%
 *     DP  Dak Prescott      MVP  2%
 *     WR  Will Rashid Sh…   MVP  2%
 *     JS  Jaxon Smith-…     MVP  1%
 *     CL  CeeDee Lamb       MVP  1%
 *
 * Dak Prescott and CeeDee Lamb are listed as Seahawks; Sam Darnold as a Cowboy.
 *
 * ═══ MECHANISM 1: THE PARTITION KEY WAS A COLOUR ═══
 *
 * The payload arrives already split — `home_team_futures` / `away_team_futures`
 * — and the component threw that split away: it concatenated both sides into
 * one `mergedAwards`, tagged each row with its side's `teamColor`, and split it
 * back apart with `mergedAwards.filter(a => a.teamColor === hColor)`. A round
 * trip that returns what went in, EXCEPT when the two colours are equal.
 *
 * This page serves `primary_color: "#002a5c"` for the Seahawks AND for the
 * Cowboys. Both filters then match all six rows. `relatedFuturesEmptyTeamCard`
 * had already spotted the hazard and passed distinct colours to work around it,
 * saying so in a note at `HOME_COLOR`: *"That collision is a real defect in its
 * own right; it is not this ship's."* It is this ship's.
 *
 * Measured 2026-09-18: of 16 sampled pages drawing both award cards, 1
 * collapses (this one). Over all 1,305 future events, 586 have `hColor ===
 * aColor` — 9 sharing a real colour, 577 because both teams' colours are null
 * and fall to DEFAULT_COLOR together; most of those draw no awards at all.
 *
 * ═══ MECHANISM 2: A DEAD MARKET'S FEBRUARY PRICES ═══
 *
 * Four of those six rows are market 479, Kalshi `KXNFLSBMVP-26`, last priced
 * **2026-02-04** — 226 days before the shot, with `opening_probability`
 * still equal to `probability`. The venue serves that event with ZERO markets
 * (gotcha #35: Kalshi market data purges at ≥74/<86 days), so the prices can
 * never move again. The stored field sums to 1,967% across 79 nominees with 37
 * at exactly 0.500, which is why eight other NFL pages show a player as a coin
 * flip to win MVP. Full measurements: `lib/awardPriceAge.ts`.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "The stale rows vanish" is passed perfectly by a block that never draws, and
 * "the cards differ" by a card that is always empty. So every suppression case
 * below is paired with a control that changes exactly ONE thing — the price
 * stamp, or the colours — and asserts the row comes back.
 *
 * ═══ THE STAMPS ARE OFFSETS, NOT THE LITERAL PRODUCTION DATES (gotcha #44) ═══
 *
 * Every other field here is verbatim from the served payload. `last_updated` is
 * expressed as `daysAgo(n)` because a literal `2026-02-04` only tests "is 90
 * days ago before February" — true today, and it would drift into testing
 * nothing at all. `daysAgo` offsets first and never branches on the clock. The
 * real production stamps were `2026-02-04T04:45:07Z` for market 479 and
 * `2026-09-18T06:56:07Z` / `2026-09-18T08:50:27Z` for the live rows.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";
import { AWARD_PRICE_MAX_AGE_DAYS } from "@/lib/awardPriceAge";

const EVENT_ID = 15304746;
const HOME = "Seattle Seahawks";
const AWAY = "Dallas Cowboys";

/** The colour production serves for BOTH of these teams. */
const SHARED_COLOR = "#002a5c";
/** Dallas's real navy, used only by the controls that separate the two cards. */
const DISTINCT_AWAY_COLOR = "#003594";

function daysAgo(n: number): string {
  return new Date(Date.now() - n * 86_400_000).toISOString();
}

/** Older than any award price may be — market 479 was 226 days stale. */
const DEAD = daysAgo(AWARD_PRICE_MAX_AGE_DAYS + 136);
/** The oldest row anybody is still repricing, in the sample, was 20.7 days. */
const LIVE = daysAgo(0.1);

function award(over: Partial<RelatedFuture>): RelatedFuture {
  return {
    market_id: 479,
    market_name: "Pro Football Championship MVP?",
    clean_label: "NFL Championship MVP?",
    display_category: "award",
    merge_group: null,
    market_tier: 3,
    category: "championship",
    source: "kalshi",
    outcome_id: 6958,
    outcome_name: "Will Sam Darnold win the Pro Football Championship Game MVP?",
    probability: 0.445,
    american_odds: 125,
    probability_change_24h: null,
    opening_probability: 0.445,
    rank: 43,
    relevance_score: 30.1,
    relevance_reason: "award watch",
    last_updated: DEAD,
    next_update_expected: "",
    resolution_date: "2027-02-10T15:00:00+00:00",
    ...over,
  };
}

// ── The six rows the reported page actually rendered, verbatim but for the
//    stamps. Three of the four Seahawks rows and none of the Cowboys rows are
//    market 479; the two Dak Prescott rows dedupe to one, which is why the
//    screenshot shows six and the payload holds seven.
const SEAHAWKS_ROWS: RelatedFuture[] = [
  award({}),
  award({
    outcome_id: 6971,
    outcome_name: "Will Jaxon Smith-Njigba win the Pro Football Championship Game MVP?",
    probability: 0.145,
  }),
  award({
    outcome_id: 6952,
    outcome_name: "Will Rashid Shaheed win the Pro Football Championship Game MVP?",
    probability: 0.015,
  }),
  award({
    market_id: 40532,
    market_name: "MVP Winner?",
    clean_label: "MVP",
    merge_group: "mvp",
    outcome_id: 643797,
    outcome_name: "Jaxon Smith-Njigba",
    probability: 0.01,
    last_updated: LIVE,
  }),
];

const COWBOYS_ROWS: RelatedFuture[] = [
  award({
    market_id: 7585490,
    market_name: "Pro Football: 2026 MVP Winner",
    clean_label: "MVP",
    merge_group: "mvp",
    source: "polymarket",
    outcome_id: 40281027,
    outcome_name: "Dak Prescott",
    probability: 0.0195,
    last_updated: LIVE,
  }),
  award({
    market_id: 59164988,
    market_name: "MVP Finalists",
    clean_label: "MVP Finalists",
    outcome_id: 222322891,
    outcome_name: "Dak Prescott",
    probability: 0.01,
    last_updated: LIVE,
  }),
  award({
    market_id: 40532,
    market_name: "MVP Winner?",
    clean_label: "MVP",
    merge_group: "mvp",
    outcome_id: 643818,
    outcome_name: "CeeDee Lamb",
    probability: 0.01,
    last_updated: LIVE,
  }),
];

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
  awayColor?: string;
} = {}): string {
  const home = opts.home ?? SEAHAWKS_ROWS;
  const away = opts.away ?? COWBOYS_ROWS;
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
      homeTeamColor: SHARED_COLOR,
      awayTeamColor: opts.awayColor ?? SHARED_COLOR,
    }),
  );
}

/**
 * The markup of one card only.
 *
 * Asserting on the whole page cannot tell "Dak Prescott is under the Cowboys
 * crest" from "Dak Prescott is under both crests" — which is the entire defect.
 * The away card is the tail after its own testid; the home card is what lies
 * between the two.
 */
function card(html: string, side: "home" | "away"): string {
  const h = html.indexOf('data-testid="home-team-card"');
  const a = html.indexOf('data-testid="away-team-card"');
  expect(h).toBeGreaterThanOrEqual(0);
  expect(a).toBeGreaterThan(h);
  return side === "home" ? html.slice(h, a) : html.slice(a);
}

describe("#3117 — a crest shows its own team's nominees", () => {
  it("THE REPORTED PAGE: with one colour served for both teams, each card draws only its own side", () => {
    const html = render();

    expect(card(html, "home")).toContain("Jaxon Smith-");
    expect(card(html, "home")).not.toContain("Dak Prescott");
    expect(card(html, "home")).not.toContain("CeeDee Lamb");

    expect(card(html, "away")).toContain("Dak Prescott");
    expect(card(html, "away")).toContain("CeeDee Lamb");
    expect(card(html, "away")).not.toContain("Jaxon Smith-");
  });

  it("CONTROL — the split is not an artefact of the shared colour: distinct colours give the same answer", () => {
    const html = render({ awayColor: DISTINCT_AWAY_COLOR });

    expect(card(html, "home")).not.toContain("Dak Prescott");
    expect(card(html, "away")).toContain("Dak Prescott");
    expect(card(html, "away")).not.toContain("Jaxon Smith-");
  });

  it("CONTROL — both cards still draw their own awards; nothing is suppressed to win the case above", () => {
    const html = render();
    expect(html).toContain("PLAYER AWARDS");
    // One PLAYER AWARDS heading per card, not one shared list.
    expect(html.split("PLAYER AWARDS").length - 1).toBe(2);
  });

  it("an away-only award never appears under the home crest, even sharing a colour", () => {
    const html = render({ home: [], away: COWBOYS_ROWS });
    expect(html).toContain("Dak Prescott");
    const h = html.indexOf('data-testid="home-team-card"');
    const a = html.indexOf('data-testid="away-team-card"');
    if (h >= 0 && a > h) expect(html.slice(h, a)).not.toContain("Dak Prescott");
  });
});

describe("#3117 — a price the venue can no longer move is not an award probability", () => {
  it("THE REPORTED PAGE: the four market-479 rows go, and the live 1% row stays", () => {
    const home = card(render(), "home");

    // Gone: the February prices, their question-shaped names, and the "W"
    // initials the badge derived from them.
    expect(home).not.toContain("Will Sam Darnold");
    expect(home).not.toContain("Will Jaxon Smith-Njigba");
    expect(home).not.toContain("Will Rashid Shaheed");
    expect(home).not.toContain("45%");
    expect(home).not.toContain("14%");

    // Still here: the row whose price was written this morning.
    expect(home).toContain("Jaxon Smith-");
    expect(home).toContain("1%");
  });

  it("CONTROL — the rows are dropped for their AGE and nothing else: refresh the stamp and all four return", () => {
    const refreshed = SEAHAWKS_ROWS.map((r) => ({ ...r, last_updated: LIVE }));
    const home = card(render({ home: refreshed }), "home");

    expect(home).toContain("Will Sam Darn");
    expect(home).toContain("45%");
    expect(home).toContain("14%");
  });

  it("CONTROL — the bound is a bound: one day the safe side of it renders, one day past it does not", () => {
    const inside = SEAHAWKS_ROWS.map((r) => ({
      ...r,
      last_updated: daysAgo(AWARD_PRICE_MAX_AGE_DAYS - 1),
    }));
    expect(card(render({ home: inside }), "home")).toContain("45%");

    // Asserted on the whole page, not on a slice: with every home award gone
    // the home card has no path, no awards and no standings, so the #3775 gate
    // correctly stops drawing it at all and there is no slice to take.
    const outside = SEAHAWKS_ROWS.map((r) => ({
      ...r,
      last_updated: daysAgo(AWARD_PRICE_MAX_AGE_DAYS + 1),
    }));
    const html = render({ home: outside });
    expect(html).not.toContain("45%");
    expect(html).not.toContain("Will Sam Darn");
  });

  it("THE MEASURED GAP — 226 days is suppressed and 20.7 days is not, stated without reading the constant", () => {
    // Every other case here builds its stamps from AWARD_PRICE_MAX_AGE_DAYS,
    // so they all move with it and none of them tests its VALUE: a mutation
    // setting the bound to 100,000 days survived the whole suite. These two
    // numbers are the edges of the 206-day empty gap measured on production
    // (market 479 at 226.3 days; the oldest still-repriced row at 20.7), so
    // they are facts about the population rather than about the constant.
    const dead = SEAHAWKS_ROWS.map((r) => ({ ...r, last_updated: daysAgo(226) }));
    const deadHtml = render({ home: dead });
    expect(deadHtml).not.toContain("Will Sam Darn");
    expect(deadHtml).not.toContain("45%");

    const oldestLive = SEAHAWKS_ROWS.map((r) => ({ ...r, last_updated: daysAgo(20.7) }));
    expect(card(render({ home: oldestLive }), "home")).toContain("45%");
  });

  it("FAILS OPEN — a row with no stamp at all is rendered, not hidden", () => {
    const unstamped = SEAHAWKS_ROWS.map((r) => ({ ...r, last_updated: null }));
    const home = card(render({ home: unstamped }), "home");
    expect(home).toContain("Will Sam Darn");
  });

  it("FAILS OPEN — an unparseable stamp is rendered, and so is a stamp in the future", () => {
    const junk = SEAHAWKS_ROWS.map((r) => ({ ...r, last_updated: "not a date" }));
    expect(card(render({ home: junk }), "home")).toContain("Will Sam Darn");

    const ahead = SEAHAWKS_ROWS.map((r) => ({ ...r, last_updated: daysAgo(-5) }));
    expect(card(render({ home: ahead }), "home")).toContain("Will Sam Darn");
  });

  it("the other side is gated too — a stale Cowboys award is dropped from the Cowboys card", () => {
    const stale = COWBOYS_ROWS.map((r) => ({ ...r, last_updated: DEAD }));
    const html = render({ away: stale });
    expect(html).not.toContain("Dak Prescott");
    expect(html).not.toContain("CeeDee Lamb");

    // And the control, so this is not "the away card stopped drawing".
    expect(card(render(), "away")).toContain("Dak Prescott");
  });
});
