/**
 * PLAYER AWARDS: THE PLAYER'S NAME IS NOT CUT TO 96px — #9048.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/14781701` (Chiefs @ Dolphins) at 390px, 2026-09-27 04:23Z. The Chiefs
 * card's PLAYER AWARDS printed "Patrick Maho…" beside `MVP Finalist 84%  MVP 9%`
 * with empty space to the right. The name sat in `w-24 truncate shrink-0` — a
 * fixed 96px column, in both the home and away copies of the block.
 *
 * ═══ WHAT THE GUARD PINS ═══
 *
 * jsdom lays nothing out, so the guard pins the mechanism: the name span has no
 * fixed width, and the rows share ONE grid whose name track sizes to its content
 * (the property that keeps awards aligned across rows, which the fixed width was
 * for). Both cards are asserted on their own — they were two copies before.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import PlayerAwardsList from "@/components/event/PlayerAwardsList";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 14781701;
const HOME = "Miami Dolphins";
const AWAY = "Kansas City Chiefs";
const LIVE = new Date(Date.now() - 0.1 * 86_400_000).toISOString();

function award(over: Partial<RelatedFuture>): RelatedFuture {
  return {
    market_id: 59170000,
    market_name: "NFL MVP Finalists",
    clean_label: "NFL MVP Finalists",
    display_category: "award",
    merge_group: null,
    market_tier: 2,
    category: "championship",
    source: "kalshi",
    outcome_id: 219900001,
    outcome_name: "Patrick Mahomes",
    probability: 0.84,
    american_odds: -525,
    probability_change_24h: null,
    opening_probability: null,
    rank: 1,
    relevance_score: 30,
    relevance_reason: "conference context",
    last_updated: LIVE,
    next_update_expected: "",
    resolution_date: "2027-02-01T15:00:00+00:00",
    ...over,
  };
}

const CHIEFS = [
  award({}),
  award({ market_id: 216, market_name: "NFL MVP", clean_label: "NFL MVP", merge_group: "nfl_mvp", outcome_id: 1700, probability: 0.09 }),
];
const DOLPHINS = [award({ outcome_id: 219900002, outcome_name: "De'Von Achane", probability: 0.04 })];

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

function render(): string {
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: DOLPHINS,
    away_team_futures: CHIEFS,
    series_markets: [],
    total_count: 3,
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
      homeTeamColor: "#008E97",
      awayTeamColor: "#E31837",
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

/** The class attribute of the span that prints `name`. */
function nameSpanClass(markup: string, name: string): string {
  const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/'/g, "(?:'|&#x27;)");
  const m = markup.match(new RegExp(`<span class="([^"]*)"[^>]*>${esc}</span>`));
  expect(m).not.toBeNull();
  return m![1];
}

const FIXED_WIDTH = /(^|\s)(w-\d+|w-\[[^\]]+\]|max-w-\d+)(\s|$)/;

describe("#9048 — the award row's player name takes the room it needs", () => {
  it("THE REPORTED PAGE: the Chiefs card prints 'Patrick Mahomes' in a span with no fixed width, one row carrying both awards", () => {
    const chiefs = card(render(), "away");
    const cls = nameSpanClass(chiefs, "Patrick Mahomes");
    expect(cls).not.toMatch(FIXED_WIDTH);
    expect(cls).toContain("truncate"); // an outlier still truncates rather than pushing the numbers off the card
    expect(chiefs.match(/>Patrick Mahomes</g)).toHaveLength(1);
    expect(chiefs).toContain(">84%<");
    expect(chiefs).toContain(">9%<");
  });

  it("the home card's copy of the block renders through the same component", () => {
    const dolphins = card(render(), "home");
    expect(nameSpanClass(dolphins, "De'Von Achane")).not.toMatch(FIXED_WIDTH);
    expect(dolphins).toContain('data-testid="player-awards-list"');
  });

  it("the rows share ONE grid whose name track sizes to the longest name, so awards still line up", () => {
    const html = renderToStaticMarkup(
      React.createElement(PlayerAwardsList, {
        color: "#E31837",
        rows: [
          { name: "Patrick Mahomes", awards: [{ label: "MVP", prob: 0.09 }] },
          { name: "Travis Kelce", awards: [{ label: "OPOY", prob: 0.02 }] },
        ],
      }),
    );
    const grids = html.match(/data-testid="player-awards-list"/g) ?? [];
    expect(grids).toHaveLength(1);
    expect(html).toMatch(/grid-cols-\[1\.5rem_fit-content\(\d+%\)_minmax\(0,1fr\)\]/);
    // Each row dissolves into the shared grid; a row with its own flex box would re-align per row.
    expect(html.match(/<div class="contents">/g)).toHaveLength(2);
  });

  it("the full name stays readable on hover when an outlier does truncate", () => {
    expect(card(render(), "away")).toMatch(/title="Patrick Mahomes"[^>]*>Patrick Mahomes</);
  });
});
