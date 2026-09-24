/**
 * PLAYER AWARDS: ONE ROW PER PERSON, HOWEVER THE VENUES SPELL THEM — #8360.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/15318167` (Royals v White Sox) at 390px, 2026-09-23. The Royals
 * card's PLAYER AWARDS listed one player twice:
 *
 *     BW  Bobby Witt Jr.   MVP Finalist 60%   MVP 1%
 *     MG  Maikel Garcia    MVP Finalist 5%
 *     MG  Maikel García    MVP 1%
 *
 * Both rows are Kalshi, verbatim from `/api/events/15318167/related-futures`:
 * `KXMLBAWARDFIN-26ALMVP-MGARCIA11` (outcome 219813635) writes "Garcia",
 * `KXMLBALMVP-26-MGAR` (outcome 1607) writes "García". The card grouped on
 * the raw `outcome_name`, so an accent became a second person.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "One Maikel row" is passed by a card that draws nobody, and by a key so loose
 * it merges two different Garcias. So: the other nominee still draws, a
 * different player with the same surname stays a separate row, and each card
 * (home and away are two copies of the block) is asserted on its own.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";
import { groupAwardsByPlayer } from "@/lib/playerAwardRows";

const EVENT_ID = 15318167;
const HOME = "Chicago White Sox";
const AWAY = "Kansas City Royals";
const LIVE = new Date(Date.now() - 0.1 * 86_400_000).toISOString();

function award(over: Partial<RelatedFuture>): RelatedFuture {
  return {
    market_id: 59164000,
    market_name: "American League MVP Finalists",
    clean_label: "American League MVP Finalists",
    display_category: "award",
    merge_group: null,
    market_tier: 2,
    category: "championship",
    source: "kalshi",
    outcome_id: 219813635,
    outcome_name: "Maikel Garcia",
    probability: 0.05,
    american_odds: 1900,
    probability_change_24h: null,
    opening_probability: null,
    rank: 8,
    relevance_score: 26.8,
    relevance_reason: "conference context",
    last_updated: LIVE,
    next_update_expected: "",
    resolution_date: "2026-12-01T15:00:00+00:00",
    ...over,
  };
}

const GARCIA_FINALIST = award({});
const GARCIA_MVP = award({
  market_id: 216,
  market_name: "AL MVP Winner?",
  clean_label: "AL MVP",
  merge_group: "al_mvp",
  outcome_id: 1607,
  outcome_name: "Maikel García",
  probability: 0.01,
  american_odds: 9900,
});
const WITT_FINALIST = award({ outcome_id: 219813600, outcome_name: "Bobby Witt Jr.", probability: 0.6 });
const WITT_MVP = award({ ...GARCIA_MVP, outcome_id: 1600, outcome_name: "Bobby Witt Jr.", probability: 0.01 });

const ROYALS = [WITT_FINALIST, WITT_MVP, GARCIA_FINALIST, GARCIA_MVP];
/** The other card needs a nominee of its own or neither card draws. */
const SOX = [award({ outcome_id: 219813800, outcome_name: "Miguel Vargas" })];

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

function render(home: RelatedFuture[], away: RelatedFuture[]): string {
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
      homeTeamColor: "#27251F",
      awayTeamColor: "#004687",
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

/** Printed name spans — `>Maikel García<` — counted, not merely found. */
function nameRows(markup: string, re: RegExp): string[] {
  return [...markup.matchAll(re)].map((m) => m[1]);
}

const MAIKEL = />(Maikel Garc[ií]a)</g;

describe("#8360 — one PLAYER AWARDS row per person", () => {
  it("THE REPORTED PAGE: 'Maikel Garcia' and 'Maikel García' print as ONE row carrying both awards, accented", () => {
    const royals = card(render(SOX, ROYALS), "away");
    expect(nameRows(royals, MAIKEL)).toEqual(["Maikel García"]);
    const i = royals.indexOf(">Maikel García<");
    const row = royals.slice(i, royals.indexOf(">Bobby Witt Jr.<") > i ? royals.indexOf(">Bobby Witt Jr.<") : undefined);
    expect(row).toContain("MVP Finalist");
    expect(row).toContain(">5%<");
    expect(row).toContain(">1%<");
  });

  it("the home card's copy of the block folds the same way", () => {
    const sox = card(render(ROYALS, SOX), "home");
    expect(nameRows(sox, MAIKEL)).toEqual(["Maikel García"]);
  });

  it("CONTROL — the other nominee still draws; nothing is suppressed to win the case above", () => {
    const royals = card(render(SOX, ROYALS), "away");
    expect(royals).toContain("PLAYER AWARDS");
    expect(nameRows(royals, />(Bobby Witt Jr\.)</g)).toEqual(["Bobby Witt Jr."]);
  });

  it("CONTROL — a different player with the same surname stays his own row", () => {
    const luis = award({ outcome_id: 219813700, outcome_name: "Luis García", probability: 0.03 });
    const royals = card(render(SOX, [...ROYALS, luis]), "away");
    expect(nameRows(royals, />((?:Maikel|Luis) Garc[ií]a)</g).sort()).toEqual(["Luis García", "Maikel García"]);
  });

  it("the same award under both spellings collapses to one entry, not 'MVP 1% MVP 1%'", () => {
    const polyMvp = award({ ...GARCIA_MVP, source: "polymarket", outcome_id: 40281999, outcome_name: "Maikel Garcia" });
    const royals = card(render(SOX, [GARCIA_MVP, polyMvp, WITT_FINALIST]), "away");
    expect(nameRows(royals, MAIKEL)).toEqual(["Maikel García"]);
    const i = royals.indexOf(">Maikel García<");
    expect(royals.slice(i).split(">MVP <").length - 1).toBe(1);
  });
});

describe("groupAwardsByPlayer", () => {
  it("prefers the accented spelling whichever order the rows arrive in", () => {
    for (const names of [["Maikel Garcia", "Maikel García"], ["Maikel García", "Maikel Garcia"]]) {
      const rows = groupAwardsByPlayer(names.map((name, i) => ({ name, label: `A${i}`, prob: 0.1 * (i + 1) })));
      expect(rows.map((r) => r.name)).toEqual(["Maikel García"]);
      expect(rows[0].awards.map((a) => a.label)).toEqual(["A1", "A0"]);
    }
  });

  it("folds letters that are their own codepoints (ø), which a bare NFD strip leaves alone", () => {
    const rows = groupAwardsByPlayer([
      { name: "Rasmus Sorensen", label: "X", prob: 0.2 },
      { name: "Rasmus Sørensen", label: "Y", prob: 0.1 },
    ]);
    expect(rows.map((r) => r.name)).toEqual(["Rasmus Sørensen"]);
  });

  it("orders players by their best award", () => {
    const rows = groupAwardsByPlayer([
      { name: "B", label: "x", prob: 0.05 },
      { name: "A", label: "x", prob: 0.6 },
    ]);
    expect(rows.map((r) => r.name)).toEqual(["A", "B"]);
  });
});
