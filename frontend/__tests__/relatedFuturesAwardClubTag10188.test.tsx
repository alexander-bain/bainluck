/**
 * PLAYER AWARDS: A VENUE'S "(LAD)" NAMESAKE TAG IS NOT A SECOND PERSON — #10188.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/15323083` (Braves @ Dodgers, NLDS) at 390px, 2026-10-02 10:45Z. The
 * Dodgers card's PLAYER AWARDS listed one player twice:
 *
 *     MM  Max Muncy (LAD)   MVP Finalist 4%   NLCS MVP 3%   Championship MVP 2%
 *     MM  Max Muncy         MVP 1%
 *
 * Both rows are Kalshi, verbatim from `/api/events/15323083/related-futures`:
 * `KXMLBAWARDFIN-26NLMVP-MMUNCY13` writes "Max Muncy (LAD)", `KXMLBNLMVP-26-MMUN`
 * writes "Max Muncy". Every one is a National League market, so every one is
 * the Dodgers' Muncy. #8360's accent fold could not see it: the tag is not an
 * accent.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "One Muncy row" is passed by a key that drops ANY trailing tag — which would
 * fold the Dodgers' Muncy into the Athletics' namesake (#8072) on the A's card.
 * So: a tag naming a different club stays as written and stays its own row, a
 * card with no club tag to compare against changes nothing, and each card
 * (home and away are two copies of the block) is asserted on its own.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { LeagueContextData, RelatedFuture, RelatedFuturesResponse } from "@/lib/types";
import { groupAwardsByPlayer, withoutOwnClubTag } from "@/lib/playerAwardRows";

const EVENT_ID = 15323083;
const HOME = "Los Angeles Dodgers";
const AWAY = "Atlanta Braves";
const LIVE = new Date(Date.now() - 0.1 * 86_400_000).toISOString();

function award(over: Partial<RelatedFuture>): RelatedFuture {
  return {
    market_id: 58728331,
    market_name: "National League MVP Finalists",
    clean_label: "National League MVP Finalists",
    display_category: "award",
    merge_group: null,
    market_tier: 2,
    category: "championship",
    source: "kalshi",
    outcome_id: 237400013,
    outcome_name: "Max Muncy (LAD)",
    probability: 0.04,
    american_odds: null,
    probability_change_24h: null,
    opening_probability: null,
    rank: 6,
    relevance_score: 26.8,
    relevance_reason: "conference context",
    last_updated: LIVE,
    next_update_expected: "",
    resolution_date: "2026-11-10T15:00:00+00:00",
    ...over,
  };
}

const MUNCY_FINALIST = award({});
const MUNCY_NLCS = award({
  market_id: 62952890,
  market_name: "NLCS MVP Winner",
  clean_label: "NLCS MVP",
  outcome_id: 237492300,
  probability: 0.0275,
  relevance_reason: "award watch",
});
const MUNCY_MVP = award({
  market_id: 209,
  market_name: "NL MVP Winner?",
  clean_label: "NL MVP",
  merge_group: "nl_mvp",
  outcome_id: 1395,
  outcome_name: "Max Muncy",
  probability: 0.01,
  relevance_reason: "award watch",
});
const OHTANI = award({ outcome_id: 237400001, outcome_name: "Shohei Ohtani", probability: 0.98 });

const DODGERS = [OHTANI, MUNCY_FINALIST, MUNCY_NLCS, MUNCY_MVP];
/** The other card needs a nominee of its own or neither card draws. */
const BRAVES = [award({ outcome_id: 237400050, outcome_name: "Matt Olson", probability: 0.12 })];

function ctx(home: string | null, away: string | null): LeagueContextData {
  const side = (short: string | null) => ({
    cells: {},
    changes_24h: {},
    conference: "National League",
    short_name: short,
  });
  return {
    league_slug: "mlb",
    league_name: "MLB Playoffs 2026",
    columns: [],
    league_page_url: "/baseball/mlb",
    home_team: side(home),
    away_team: side(away),
  };
}

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

function render(
  home: RelatedFuture[],
  away: RelatedFuture[],
  leagueContext: LeagueContextData | null,
): string {
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
    league_context: leagueContext,
  } as RelatedFuturesResponse;
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: EVENT_ID,
      homeTeam: HOME,
      awayTeam: AWAY,
      homeTeamColor: "#005A9C",
      awayTeamColor: "#13274F",
    }),
  );
}

function card(html: string, side: "home" | "away"): string {
  const h = html.indexOf('data-testid="home-team-card"');
  const a = html.indexOf('data-testid="away-team-card"');
  expect(h).toBeGreaterThanOrEqual(0);
  expect(a).toBeGreaterThan(h);
  return side === "home" ? html.slice(h, a) : html.slice(a);
}

/** Printed name spans — `>Max Muncy<` — counted, not merely found. */
const MUNCY = />(Max Muncy(?: \([A-Z]+\))?)</g;
function muncyRows(markup: string): string[] {
  return [...markup.matchAll(MUNCY)].map((m) => m[1]);
}

describe("#10188 — a venue's own-club namesake tag folds into one PLAYER AWARDS row", () => {
  it("THE REPORTED PAGE: 'Max Muncy (LAD)' and 'Max Muncy' print as ONE untagged row carrying every award", () => {
    const dodgers = card(render(DODGERS, BRAVES, ctx("LAD", "ATL")), "home");
    expect(muncyRows(dodgers)).toEqual(["Max Muncy"]);
    const row = dodgers.slice(dodgers.indexOf(">Max Muncy<"));
    expect(row).toContain("MVP Finalist");
    expect(row).toContain("NLCS MVP");
    expect(row).toContain(">4%<");
    expect(row).toContain(">3%<");
    expect(row).toContain(">1%<");
  });

  it("the away card's copy of the block folds the same way", () => {
    const dodgers = card(render(BRAVES, DODGERS, ctx("ATL", "LAD")), "away");
    expect(muncyRows(dodgers)).toEqual(["Max Muncy"]);
  });

  it("CONTROL — a tag naming a DIFFERENT club is kept as written and stays its own row (#8072's namesake)", () => {
    const aMuncy = award({ ...MUNCY_MVP, outcome_id: 9001, market_name: "AL MVP Winner?", clean_label: "AL MVP", merge_group: "al_mvp" });
    const athletics = card(render([MUNCY_FINALIST, aMuncy, OHTANI], BRAVES, ctx("ATH", "ATL")), "home");
    expect(muncyRows(athletics).sort()).toEqual(["Max Muncy", "Max Muncy (LAD)"]);
  });

  it("CONTROL — with no league_context to name the club, nothing is folded (the old rendering)", () => {
    const dodgers = card(render(DODGERS, BRAVES, null), "home");
    expect(muncyRows(dodgers).sort()).toEqual(["Max Muncy", "Max Muncy (LAD)"]);
  });

  it("CONTROL — the other nominee still draws; nothing is suppressed to win the case above", () => {
    const dodgers = card(render(DODGERS, BRAVES, ctx("LAD", "ATL")), "home");
    expect(dodgers).toContain("PLAYER AWARDS");
    expect(dodgers).toContain(">Shohei Ohtani<");
  });

  it("the same award under both spellings collapses to one entry, not 'NLCS MVP 3% NLCS MVP 2%'", () => {
    const polyNlcs = award({ ...MUNCY_NLCS, source: "polymarket", outcome_id: 40281999, outcome_name: "Max Muncy", probability: 0.02 });
    const dodgers = card(render([MUNCY_NLCS, polyNlcs, OHTANI], BRAVES, ctx("LAD", "ATL")), "home");
    expect(muncyRows(dodgers)).toEqual(["Max Muncy"]);
    const row = dodgers.slice(dodgers.indexOf(">Max Muncy<"));
    expect(row.split("NLCS MVP").length - 1).toBe(1);
  });
});

describe("withoutOwnClubTag", () => {
  it("drops a trailing tag only when it is the card's own club, case-insensitively on the club side", () => {
    expect(withoutOwnClubTag("Max Muncy (LAD)", "LAD")).toBe("Max Muncy");
    expect(withoutOwnClubTag("Max Muncy (LAD)", "lad")).toBe("Max Muncy");
    expect(withoutOwnClubTag("Max Muncy (LAD)", "ATH")).toBe("Max Muncy (LAD)");
    expect(withoutOwnClubTag("Max Muncy (LAD)", null)).toBe("Max Muncy (LAD)");
    expect(withoutOwnClubTag("Max Muncy (LAD)", "")).toBe("Max Muncy (LAD)");
  });

  it("leaves a parenthesis that is not a trailing club tag alone", () => {
    expect(withoutOwnClubTag("Will Smith (Pitcher)", "LAD")).toBe("Will Smith (Pitcher)");
    expect(withoutOwnClubTag("(LAD) Max Muncy", "LAD")).toBe("(LAD) Max Muncy");
  });

  it("groupAwardsByPlayer folds the tagged and bare spellings under the own club, and only then", () => {
    const entries = [
      { name: "Max Muncy (LAD)", label: "MVP Finalist", prob: 0.04 },
      { name: "Max Muncy", label: "MVP", prob: 0.01 },
    ];
    expect(groupAwardsByPlayer(entries, "LAD")).toEqual([
      { name: "Max Muncy", awards: [{ label: "MVP Finalist", prob: 0.04 }, { label: "MVP", prob: 0.01 }] },
    ]);
    expect(groupAwardsByPlayer(entries).map((r) => r.name)).toEqual(["Max Muncy (LAD)", "Max Muncy"]);
  });
});
