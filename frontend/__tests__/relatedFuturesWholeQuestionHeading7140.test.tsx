/**
 * #7140 (arm 2, render half) — a Yes/No market whose whole name IS the question is headed by
 * that question, never by "OTHER".
 *
 * WHAT THE READER SAW. `/events/15315787` (Ottawa Senators @ Montreal Canadiens, preseason,
 * 2026-09-24) at 390px, Bigger Picture:
 *
 *   GAME PROPS
 *   OTHER (2)   [No 73%]  [Yes 28%]
 *   OTHER (2)   [No 77%]  [Yes 24%]
 *
 * Two answers each to two questions, and neither question anywhere on the page. #8344 made a
 * question PREFIX ("Will there be a run…?: A vs. B") the heading; these names have no colon at
 * all, so `extractStatCategory` fell through to "other".
 *
 * A second loss rode the same fall-through: every colonless question shared the one "other"
 * group, and the group's per-name dedup keeps one "Yes" and one "No", so two questions on the
 * same side printed as a single pair.
 *
 * Why these markets are on a game page at all (a season question served as `game_prop`) is the
 * backend half of #7140 and is not touched here — this file pins only what the rail prints for
 * whatever it is handed. Fixtures are the served rows from
 * `GET /api/events/15315787/related-futures`, 2026-09-24 21:50Z.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15315787;
const HOME = "Montreal Canadiens";
const AWAY = "Ottawa Senators";
const MTL_Q = "Will Montreal Canadiens advance to the Second Round of the 2027 Stanley Cup Playoffs?";
const OTT_Q = "Will Ottawa Senators advance to the Second Round of the 2027 Stanley Cup Playoffs?";

function row(over: Partial<RelatedFuture>): RelatedFuture {
  return {
    market_id: 61380678,
    market_name: MTL_Q,
    display_category: "game_prop",
    market_tier: 2,
    category: "game_prop",
    source: "polymarket",
    outcome_id: 1,
    outcome_name: "No",
    probability: 0.725,
    american_odds: null,
    probability_change_24h: null,
    opening_probability: null,
    rank: null,
    relevance_score: 40,
    relevance_reason: "shifting",
    last_updated: null,
    next_update_expected: "",
    resolution_date: "2027-06-01T00:00:00+00:00",
    ...over,
  };
}

const MTL_NO = row({});
const MTL_YES = row({ outcome_id: 2, outcome_name: "Yes", probability: 0.275 });
const OTT_NO = row({ market_id: 61380679, market_name: OTT_Q, outcome_id: 3, probability: 0.765 });
const OTT_YES = row({
  market_id: 61380679,
  market_name: OTT_Q,
  outcome_id: 4,
  outcome_name: "Yes",
  probability: 0.235,
});

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
    React.createElement(RelatedFutures, { eventId: EVENT_ID, homeTeam: HOME, awayTeam: AWAY }),
  );
}

// The heading is set in CSS uppercase, so its DOM text is the lower-cased group key (as #8344's).
const text = (html: string) => html.replace(/<[^>]+>/g, "|");
const heading = (q: string) => `|${q.charAt(0)}${q.slice(1).toLowerCase()}|`;
const count = (hay: string, needle: string) => hay.split(needle).length - 1;

describe("#7140 the rail, rendered from the specimen rows", () => {
  const shown = text(render([MTL_NO, MTL_YES], [OTT_NO, OTT_YES]));

  it("heads each pair of legs with its own question", () => {
    expect(shown).toContain(heading(MTL_Q));
    expect(shown).toContain(heading(OTT_Q));
  });

  it("prints no OTHER heading over a question", () => {
    expect(shown).not.toMatch(/\|Other\|/i);
  });

  it("still labels the legs Yes and No, with their numbers", () => {
    expect(count(shown, "|Yes|")).toBe(2);
    expect(count(shown, "|No|")).toBe(2);
    for (const pct of ["73%", "28%", "77%", "24%"]) expect(shown).toContain(`|${pct}|`);
  });
});

describe("#7140 two questions on ONE side keep both pairs", () => {
  it("draws four legs under two headings, not one pair under OTHER", () => {
    const shown = text(render([MTL_NO, MTL_YES, OTT_NO, OTT_YES], []));
    expect(shown).toContain(heading(MTL_Q));
    expect(shown).toContain(heading(OTT_Q));
    expect(count(shown, "|Yes|")).toBe(2);
    expect(count(shown, "|No|")).toBe(2);
  });
});

describe("#7140 CONTROLS — what the rule must not move", () => {
  it("a colonless name that asks nothing is still grouped under Other", () => {
    const plain = row({ market_name: "Montreal Canadiens Specials", outcome_name: "Nick Suzuki", probability: 0.4 });
    expect(text(render([plain], []))).toMatch(/\|Other\|/);
  });

  it("a colon stat market keeps its stat heading", () => {
    const shots = row({
      market_name: "Ottawa at Montreal: Shots on Goal",
      outcome_name: "Over 58.5",
      probability: 0.55,
    });
    const shown = text(render([shots], []));
    expect(shown).not.toMatch(/\|Other\|/);
    expect(shown).not.toContain("Ottawa at Montreal");
  });

  it("#8344's question-prefix heading is unchanged", () => {
    const q = "Will there be a goal in the first period?: Ottawa Senators vs. Montreal Canadiens";
    const shown = text(
      render([row({ market_name: q, outcome_name: "Yes" }), row({ market_name: q, outcome_id: 9 })], []),
    );
    expect(shown).toContain("|Will there be a goal in the first period?|");
  });
});

describe("#7140 a leg that restates its question stays with #2788's rule", () => {
  it("a Kalshi binary (outcome name == question) is not headed by itself", () => {
    const q = "Will Nick Suzuki score a goal?";
    const shown = text(render([row({ market_name: q, outcome_name: q, probability: 0.3 })], []));
    expect(shown).toMatch(/\|Other\|/);
    expect(shown).not.toContain(heading(q));
  });
});
