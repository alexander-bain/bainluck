// #11576 — AN UPCOMING NFL GAME'S CARD ON ITS LEAGUE PAGE PRINTS THE SAME
// "PROJECTED FINAL" AS THE SAME CARD ON /sports AND IN SEARCH.
//
// #11295 made `/api/leagues/{key}` → `upcoming_games[].current_odds` carry the
// admitted pair (`projected_home_score`, `projected_away_score`,
// `projection_captured_at`, and `live_projection` once a game is in play), added
// by the same `attach_card_projected_pair` the feed uses. The rail renders the
// shared `EventCard`, but through `leagueGameToEvent`, which rebuilt
// `current_odds` with the pair nulled. So `/sports/americanfootball_nfl` printed
// "Projected final · Bears 27, Patriots 24" (#11295's 390px look, 10/20 01:47Z)
// and the league page printed nothing for the same game.
//
// Specimen: no retained `/api/leagues` payload carries the pair (searched
// /Users/bain/bainluck/artifacts, 2026-10-24). Each brief below is a CONTROLLED
// PLACEMENT: a retained served row copied into the league brief's own fields —
//   - scheduled: `/api/events/14780563` Commanders @ 49ers, 2026-10-19 22:20Z
//     (`fixtures/webProjectedFinal2920.json`), pair 29.6 / 22.3;
//   - live: the served Georgia–Oklahoma row (`fixtures/liveCardProjectedFinal2920.json`)
//     with the in-play object the producer serves, built as that file's test builds it.
// It proves what the mapper hands the card, not what production serves today.
//
// The clock is pinned to each specimen's own capture instant (gotcha #44): the
// card reads `Date.now()` to decide upcoming vs started, and a served row read
// days later is a different card.
//
// Every arm runs the rail's own path (`LeagueGameRail` → `leagueGameToEvent` →
// `EventCard`), and every "prints nothing" arm has a sibling where the same
// probe finds the line.

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
import SCHEDULED from "./fixtures/webProjectedFinal2920.json";
import LIVE from "./fixtures/liveCardProjectedFinal2920.json";

const NFL = (SCHEDULED as unknown as Record<string, Event>).event_14780563;
const UGA = (LIVE as unknown as Record<string, Event>).event_14870008_live;
const CAPTURED = "2026-10-19T22:20:24.725508+00:00";

const UGA_IN_PLAY = {
  projected_home_score: 36.9,
  projected_away_score: 10.7,
  kind: "in_play",
  boundary: "commence_time",
  boundary_at: UGA.commence_time,
  earliest_confirmed_at: "2026-09-26T19:35:32.134948+00:00",
  latest_captured_at: UGA.current_odds!.captured_at,
  source: "sportsbooks",
  basis: "consensus_spread_total",
  bookmaker_count: UGA.current_odds!.bookmaker_count ?? 1,
  unit: "points",
  period: "full_game",
};

type BriefOdds = NonNullable<LeagueGameBrief["current_odds"]>;

/** The served row's fields under the league brief's names, with the
 *  `current_odds` keys the league producer serves. Nothing else added. */
function briefFrom(row: Event, odds: Partial<BriefOdds>, patch: Partial<LeagueGameBrief> = {}): LeagueGameBrief {
  return {
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
    current_odds: {
      home_probability: row.current_odds?.home_probability ?? null,
      away_probability: row.current_odds?.away_probability ?? null,
      ...odds,
    },
    ...patch,
  };
}

const pinClock = (iso: string) => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date(iso));
  });
  afterEach(() => jest.useRealTimers());
};

const SERVED_PAIR = { projected_home_score: 29.6, projected_away_score: 22.3, projection_captured_at: CAPTURED };
const scheduled = (odds: Partial<BriefOdds> = SERVED_PAIR) => briefFrom(NFL, odds);

const rail = (games: LeagueGameBrief[]) =>
  renderToStaticMarkup(React.createElement(LeagueGameRail, { title: "Upcoming", games }));
const card = (e: Event) => renderToStaticMarkup(React.createElement(EventCard, { event: e }));

const LINE = "event-card-projected-final";
function stamp(html: string): string | null {
  const m = html.match(
    new RegExp(`data-testid="${LINE}" data-projected-final="(\\d+)-(\\d+)" data-projected-order="([a-z-]+)"`),
  );
  return m ? `${m[1]}-${m[2]} ${m[3]}` : null;
}

describe("the upcoming rail prints the served projected final", () => {
  pinClock(CAPTURED);
  it("Commanders @ 49ers: 30 – 22, home first, labelled as the event page labels it", () => {
    const html = rail([scheduled()]);
    expect(stamp(html)).toBe("30-22 home-away");
    expect(html).toContain(">Projected final<");
    expect(html).not.toContain("NaN");
  });

  it("is the same pair, in the same order, as the search/detail card for the same game", () => {
    expect(stamp(card(NFL))).toBe("30-22 home-away");
    expect(stamp(rail([scheduled()]))).toBe(stamp(card(NFL)));
  });
});

describe("missing, partial or broken prints nothing — and the same probe finds the served pair", () => {
  pinClock(CAPTURED);
  const cases: [string, Partial<BriefOdds>][] = [
    ["an older cached brief with no pair keys", {}],
    ["explicit nulls", { projected_home_score: null, projected_away_score: null }],
    ["half a pair (home only)", { projected_home_score: 29.6 }],
    ["half a pair (away only)", { projected_away_score: 22.3, projected_home_score: null }],
    ["a non-number half", { projected_home_score: "29.6" as unknown as number, projected_away_score: 22.3 }],
    ["a non-finite half", { projected_home_score: Number.POSITIVE_INFINITY, projected_away_score: 22.3 }],
  ];
  it.each(cases)("%s", (_name, odds) => {
    const html = rail([scheduled(odds)]);
    expect(stamp(html)).toBeNull();
    expect(html).not.toContain(">Projected final<");
    expect(html).not.toContain("NaN");
    expect(stamp(rail([scheduled()]))).not.toBeNull();
  });

  it("the card's own refusals still apply: hockey's pinned puck line prints nothing", () => {
    const nhl = briefFrom(NFL, SERVED_PAIR, { sport: "icehockey_nhl" });
    expect(stamp(rail([nhl]))).toBeNull();
  });

  it("a final on the upcoming rail never prints the pregame pair as its projection", () => {
    const fin = briefFrom(NFL, SERVED_PAIR, { status: "completed", home_score: 24, away_score: 20 });
    expect(stamp(rail([fin]))).toBeNull();
  });
});

describe("live: only the served in-play object prints, exactly as on search", () => {
  pinClock(UGA.current_odds!.captured_at);
  const live = (odds: Partial<BriefOdds>) => briefFrom(UGA, odds);

  it("the served in-play pair travels and prints the same line as the search card", () => {
    const html = rail([live({ projected_home_score: 36.9, projected_away_score: 10.7, live_projection: UGA_IN_PLAY })]);
    const searchRow: Event = { ...UGA, current_odds: { ...UGA.current_odds!, live_projection: UGA_IN_PLAY } as Event["current_odds"] };
    expect(stamp(html)).toBe("37-11 home-away");
    expect(stamp(html)).toBe(stamp(card(searchRow)));
  });

  it("no in-play object served: the bare pair is never shown live", () => {
    expect(stamp(rail([live({ projected_home_score: 36.9, projected_away_score: 10.7 })]))).toBeNull();
  });

  it("a refused in-play object (wrong unit) prints nothing", () => {
    const bad = { ...UGA_IN_PLAY, unit: "goals" };
    expect(stamp(rail([live({ live_projection: bad })]))).toBeNull();
  });
});

describe("the mapper hands the card what the envelope said", () => {
  it("the served pair and its capture time, on the card's current_odds", () => {
    const odds = leagueGameToEvent(scheduled()).current_odds as unknown as Record<string, unknown>;
    expect(odds.projected_home_score).toBe(29.6);
    expect(odds.projected_away_score).toBe(22.3);
    expect(odds.projection_captured_at).toBe(CAPTURED);
    expect("live_projection" in odds).toBe(false);
  });

  it("absence is an explicit null, never undefined, and a partial pair is no pair", () => {
    // Each broken pair still carries the served capture time, so the last
    // assertion tests that the time travels only WITH an accepted pair.
    for (const o of [
      { projection_captured_at: CAPTURED },
      { projected_home_score: 29.6, projection_captured_at: CAPTURED },
      { projected_home_score: Number.NaN, projected_away_score: 22.3, projection_captured_at: CAPTURED },
      { projected_home_score: "29.6", projected_away_score: 22.3, projection_captured_at: CAPTURED },
    ] as unknown as Partial<BriefOdds>[]) {
      const odds = leagueGameToEvent(scheduled(o)).current_odds!;
      expect(odds.projected_home_score).toBeNull();
      expect(odds.projected_away_score).toBeNull();
      expect("projection_captured_at" in odds).toBe(false);
    }
  });

  it("the in-play object only when served, and unchanged", () => {
    const odds = leagueGameToEvent(briefFrom(UGA, { live_projection: UGA_IN_PLAY })).current_odds as unknown as Record<
      string,
      unknown
    >;
    expect(odds.live_projection).toEqual(UGA_IN_PLAY);
  });

  it("no probability, no current_odds: a pair alone does not invent one", () => {
    const e = leagueGameToEvent(
      briefFrom(NFL, SERVED_PAIR, {
        home_win_probability: null,
        current_odds: { home_probability: null, away_probability: null, ...SERVED_PAIR },
      }),
    );
    expect(e.current_odds).toBeUndefined();
  });

  it("#11296's final fields still travel beside it", () => {
    const p = { kind: "last_before_scheduled_start" } as unknown as Event["pregame_projection"];
    const e = leagueGameToEvent(briefFrom(NFL, SERVED_PAIR, { pregame_projection: p, final_score_period: "regulation" }));
    expect(e.pregame_projection).toBe(p);
    expect(e.final_score_period).toBe("regulation");
  });
});
