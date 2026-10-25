// #11296 — THE LEAGUE PAGE'S RECENT RESULTS RAIL PRINTS THE SAME FORECAST BAND
// SEARCH AND THE EVENT PAGE PRINT.
//
// The producer serves `pregame_projection` (or its refusal) and
// `final_score_period` on `/api/leagues/{key}` → `recent_results[]`
// (`_attach_pregame_projections` in `routes/league_futures.py`), under the same
// names `/api/events/search` and `/api/events/{id}` use. The rail renders the
// shared `EventCard`, but through `leagueGameToEvent`, which copied a fixed list
// of keys and dropped these three. So a finished NFL game printed
// "Projection before scheduled start" on search and the event page, and nothing
// on its league page.
//
// Specimen: no retained `/api/leagues` payload carries the key (searched
// /Users/bain/bainluck/artifacts, 2026-10-24). The brief below is a CONTROLLED
// PLACEMENT: the retained served search row for Buccaneers 19 – Steelers 26
// (`fixtures/finalForecast11296.json`, `search_14966179`, captured 2026-10-20
// 02:27Z) copied into the league brief's own fields. Its `pregame_projection`
// object is the one `attach_pregame_projection` puts on both envelopes.
//
// Every arm runs the rail's own path (`LeagueGameRail` → `leagueGameToEvent` →
// `EventCard`), never a hand-written `Event`: a consumer fix that the mapper
// drops never reaches the reader, and only the real mapper can see that.
// Every "prints nothing" arm has a sibling where the same probe finds the band.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import LeagueGameRail from "@/components/LeagueGameRail";
import type { LeagueGameBrief } from "@/lib/api";
import { leagueGameToEvent } from "@/lib/leagueCards";
import type { Event } from "@/lib/types";
import FIXTURE from "./fixtures/finalForecast11296.json";

const F = FIXTURE as unknown as Record<string, Event>;
const NFL = F.search_14966179;
const NHL = F.search_15331169;

/** The served row's fields, under the league brief's names. Nothing added. */
function briefFrom(row: Event, patch: Partial<LeagueGameBrief> = {}): LeagueGameBrief {
  const brief: LeagueGameBrief = {
    id: row.id,
    external_id: row.external_id,
    sport: row.sport,
    home_team: row.home_team,
    away_team: row.away_team,
    commence_time: row.commence_time,
    completed_at: row.completed_at ?? null,
    status: row.status,
    home_score: row.home_score ?? null,
    away_score: row.away_score ?? null,
    home_win_probability: row.current_odds?.home_probability ?? null,
  };
  if (row.pregame_projection) brief.pregame_projection = row.pregame_projection;
  if (row.pregame_projection_unavailable) {
    brief.pregame_projection_unavailable = row.pregame_projection_unavailable;
  }
  return { ...brief, ...patch };
}

const rail = (games: LeagueGameBrief[]) =>
  renderToStaticMarkup(
    React.createElement(LeagueGameRail, { title: "Recent Results", games, settled: true }),
  );
const card = (e: Event) => renderToStaticMarkup(React.createElement(EventCard, { event: e }));

const BAND = "event-card-final-forecast";
function stamp(html: string): string | null {
  const m = html.match(
    new RegExp(`data-testid="${BAND}" data-projected-final="(\\d+)-(\\d+)" data-projected-order="([a-z-]+)"`),
  );
  return m ? `${m[1]}-${m[2]} ${m[3]}` : null;
}
const ANY_BAND_LABEL = /before scheduled start/i;

describe("the results rail prints the served final's forecast band", () => {
  it("Buccaneers 19 – Steelers 26: the band, home first, under the actual result", () => {
    const html = rail([briefFrom(NFL)]);
    expect(stamp(html)).toBe("18-20 home-away");
    expect(html).toContain(">Projection before scheduled start<");
    // The actual result still prints, above the band.
    const band = html.indexOf(`data-testid="${BAND}"`);
    expect(html.indexOf(">19<")).toBeGreaterThan(-1);
    expect(html.indexOf(">19<")).toBeLessThan(band);
    expect(html.indexOf(">26<")).toBeLessThan(band);
  });

  it("is the same pair, the same order, as the search card for the same game", () => {
    expect(stamp(rail([briefFrom(NFL)]))).toBe(stamp(card(NFL)));
  });

  it("never prints the in-play 'Projected final' line on a final", () => {
    expect(rail([briefFrom(NFL)])).not.toContain(">Projected final<");
  });
});

describe("absent or refused prints nothing, and the same probe finds it when served", () => {
  it("an older cached brief without the key", () => {
    const { pregame_projection: _drop, ...older } = briefFrom(NFL);
    void _drop;
    const html = rail([older as LeagueGameBrief]);
    expect(stamp(html)).toBeNull();
    expect(html).not.toMatch(ANY_BAND_LABEL);
    expect(stamp(rail([briefFrom(NFL)]))).not.toBeNull();
  });

  it("hockey: the served NHL final carries only its refusal", () => {
    const html = rail([briefFrom(NHL)]);
    expect(stamp(html)).toBeNull();
    expect(html).not.toMatch(ANY_BAND_LABEL);
  });

  it("a projection read after the scheduled start is refused on the rail too", () => {
    const p = NFL.pregame_projection!;
    const late = { ...p, latest_captured_at: p.boundary_at };
    expect(stamp(rail([briefFrom(NFL, { pregame_projection: late })]))).toBeNull();
  });

  it("a game still in play prints no final band, whatever the brief carries", () => {
    expect(stamp(rail([briefFrom(NFL, { status: "live" })]))).toBeNull();
  });
});

describe("the mapper hands the card what the envelope said", () => {
  it("the projection object, unchanged", () => {
    expect(leagueGameToEvent(briefFrom(NFL)).pregame_projection).toEqual(NFL.pregame_projection);
  });

  it("the refusal, and no projection beside it", () => {
    const e = leagueGameToEvent(briefFrom(NHL));
    expect(e.pregame_projection_unavailable).toBe("format_unsupported");
    expect("pregame_projection" in e).toBe(false);
  });

  it("the actual score's period when served, and no key when not", () => {
    expect(leagueGameToEvent(briefFrom(NFL, { final_score_period: "regulation" })).final_score_period).toBe(
      "regulation",
    );
    expect("final_score_period" in leagueGameToEvent(briefFrom(NFL))).toBe(false);
  });

  it("soccer: the 90-minute band only when the brief says the match ended at full time", () => {
    // The served NFL projection placed on a soccer brief with the goals unit and
    // regulation period the soccer producer serves: a CONTROLLED placement that
    // proves the period travels through the rail, not a served soccer specimen.
    const goals = { ...NFL.pregame_projection!, unit: "goals" as const, period: "regulation" as const,
      projected_home_score: 1.6, projected_away_score: 1.1 };
    const soccer = (patch: Partial<LeagueGameBrief>) =>
      briefFrom(NFL, { sport: "soccer_epl", home_score: 2, away_score: 1, pregame_projection: goals, ...patch });
    const full = rail([soccer({ final_score_period: "regulation" })]);
    expect(full).toContain(">Projection (90 min) before scheduled start<");
    expect(stamp(full)).not.toBeNull();
    expect(rail([soccer({})])).not.toMatch(ANY_BAND_LABEL);
  });
});
