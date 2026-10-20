/**
 * #2920 / #9483 — a LIVE game card shows its actual score and, beneath it, a
 * supported projected final that means the same thing on the event page.
 *
 * The failure this guards: the cards printed no forecast once a game started,
 * and simply un-gating them would have shown TWO different finals for one game
 * — the list routes' sportsbook pair on the card, the prediction-market
 * ladders' pair on the page — or a PREGAME pair wearing a live label, because
 * detail and search serve the bare `current_odds.projected_*` through a stale
 * filter that falls back to every book when none has quoted since the start.
 *
 * So both cards and the page read one marked in-play object,
 * `current_odds.live_projection` (release-root dependency D3, 2026-10-20). It
 * is NOT served yet. The positives below wrap REAL retained production values
 * in that contract shape (`fixtures/liveCardProjectedFinal2920.json`, sources
 * and hashes in its `_captured` block):
 *
 *   - NCAAF 14870008, Oklahoma @ Georgia, LIVE 21 – 0 (2nd quarter): the
 *     sportsbooks' pair 36.9 / 10.7 at 20:36Z; every book carrying a pair was
 *     captured from 19:35Z, after the 19:30Z kickoff.
 *   - K League 15306856, Gangwon @ Sangju Sangmu, LIVE 1 – 0 (~31'): 1.8 / 1.0,
 *     bovada's 08:02Z quote alone — the stale filter had already dropped the two
 *     books still at their pregame 1.2 / 1.2.
 *
 * And the negatives are the cases already on the issue:
 *
 *   - 49ers v Commanders 14780563: the PREGAME pair 29.6 / 22.3 (22:20Z, before
 *     the 00:15Z kickoff) under the halftime 20 – 3 the page photographed.
 *     It is reachable from that score, so only the in-play marker refuses it.
 *   - MLS 15291065: the cached league pair 2.1 / 1.3 recorded 2026-09-06 over a
 *     detail body with no pair — it must not become a current forecast.
 */

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
import FeedCard from "@/components/FeedCard";
import {
  admittedLiveProjection,
  eventPageProjectedPair,
  liveCardProjectedFinal,
  projectedFinalPeriod,
  type LiveProjection,
} from "@/lib/projectedFinalPair";
import { teamShortNames } from "@/lib/teamShortName";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";
import FIXTURE from "./fixtures/liveCardProjectedFinal2920.json";
import PREGAME_FIXTURE from "./fixtures/webProjectedFinal2920.json";

const F = FIXTURE as unknown as Record<string, Event>;
const P = PREGAME_FIXTURE as unknown as Record<string, unknown>;

/** A real retained in-play reading, in the D3 shape. */
function inPlay(e: Event, earliestConfirmedAt: string, patch: Partial<LiveProjection> = {}): LiveProjection {
  const odds = e.current_odds!;
  const format = (e.sport ?? "").startsWith("soccer_") ? "goals" : "points";
  return {
    projected_home_score: odds.projected_home_score as number,
    projected_away_score: odds.projected_away_score as number,
    kind: "in_play",
    boundary: "commence_time",
    boundary_at: e.commence_time,
    earliest_confirmed_at: earliestConfirmedAt,
    latest_captured_at: odds.captured_at,
    source: "sportsbooks",
    basis: "consensus_spread_total",
    bookmaker_count: odds.bookmaker_count ?? 1,
    unit: format,
    period: format === "goals" ? "regulation" : "full_game",
    ...patch,
  };
}

const UGA = F.event_14870008_live;
const UGA_IN_PLAY = inPlay(UGA, "2026-09-26T19:35:32.134948+00:00");
const KLEAGUE = F.event_15306856_live;
const KLEAGUE_IN_PLAY = inPlay(KLEAGUE, "2026-09-13T08:02:03.508636+00:00");

function withOdds(e: Event, odds: Record<string, unknown>, patch: Partial<Event> = {}): Event {
  return { ...e, ...patch, current_odds: { ...e.current_odds, ...odds } as Event["current_odds"] };
}

/** The same real game in `/api/feed`'s row shape. */
function feedOf(e: Event): FeedItem {
  const data: FeedEventData = {
    id: e.id,
    sport: e.sport,
    home_team: e.home_team,
    away_team: e.away_team,
    commence_time: e.commence_time,
    status: e.status,
    home_score: e.home_score,
    away_score: e.away_score,
    home_team_data: e.home_team_data,
    away_team_data: e.away_team_data,
    current_odds: e.current_odds as FeedEventData["current_odds"],
    opening_odds: e.opening_odds as FeedEventData["opening_odds"],
  } as FeedEventData;
  return { type: "event", score: 60, reason: "", data } as unknown as FeedItem;
}

const card = (e: Event) => renderToStaticMarkup(<EventCard event={e} />);
const feed = (e: Event) => renderToStaticMarkup(<FeedCard item={feedOf(e)} />);

function stamp(html: string, testId: string): string | null {
  const m = html.match(new RegExp(`data-testid="${testId}" data-projected-final="(\\d+)-(\\d+)" data-projected-order="([a-z-]+)"`));
  return m ? `${m[1]}-${m[2]} ${m[3]}` : null;
}
const BAND_CARD = "event-card-projected-final";
const BAND_FEED = "feed-card-projected-final";
const withoutBand = (html: string) => html.replace(/<div role="group"[^]*?<\/div>/, "");

describe("the fixtures are the readings they claim", () => {
  it("Georgia 21 – 0 live, the in-play pair dated after kickoff", () => {
    expect(UGA.status).toBe("live");
    expect([UGA.home_score, UGA.away_score]).toEqual([21, 0]);
    expect([UGA.current_odds?.projected_home_score, UGA.current_odds?.projected_away_score]).toEqual([36.9, 10.7]);
    expect(Date.parse(UGA_IN_PLAY.earliest_confirmed_at)).toBeGreaterThan(Date.parse(UGA.commence_time));
  });

  it("Sangju 1 – 0 live, one live book's 1.8 / 1.0 after kickoff", () => {
    expect([KLEAGUE.home_score, KLEAGUE.away_score]).toEqual([1, 0]);
    expect(Date.parse(KLEAGUE.current_odds!.captured_at)).toBeGreaterThan(Date.parse(KLEAGUE.commence_time));
  });

  it("14780563's pair was read before its kickoff", () => {
    const e = P.event_14780563 as Event;
    expect(Date.parse(e.current_odds!.captured_at)).toBeLessThan(Date.parse(e.commence_time));
  });
});

describe("a live card prints the in-play pair under the score, named per team", () => {
  const live = withOdds(UGA, { live_projection: UGA_IN_PLAY });
  const names = teamShortNames(
    { name: UGA.home_team, abbreviation: UGA.home_team_data?.abbreviation },
    { name: UGA.away_team, abbreviation: UGA.away_team_data?.abbreviation },
    UGA.sport,
  );

  it("EventCard: home first, like its rows", () => {
    const html = card(live);
    expect(stamp(html, BAND_CARD)).toBe("37-11 home-away");
    expect(html).toContain(`aria-label="Projected final: ${names.home} 37, ${names.away} 11"`);
    expect(html).toContain(`${names.home} <span class="font-mono">37</span>`);
    expect(html).toContain(`${names.away} <span class="font-mono">11</span>`);
  });

  it("FeedCard: away first, like its rows — the same pairing, reversed", () => {
    const html = feed(live);
    expect(stamp(html, BAND_FEED)).toBe("37-11 away-home");
    expect(html).toContain(`aria-label="Projected final: ${names.away} 11, ${names.home} 37"`);
    expect(html.indexOf(`${names.away} <span`)).toBeLessThan(html.indexOf(`${names.home} <span`));
  });

  it("the actual score is still printed, and ahead of the forecast", () => {
    const c = card(live);
    const scoreAt = c.indexOf(`aria-label="${UGA.home_team} score: 21"`);
    expect(scoreAt).toBeGreaterThan(-1);
    expect(scoreAt).toBeLessThan(c.indexOf(BAND_CARD));
    const f = feed(live);
    const liveAt = f.indexOf(`aria-label="${UGA.away_team} 0, ${UGA.home_team} 21"`);
    expect(liveAt).toBeGreaterThan(-1);
    expect(f).toContain('data-testid="feed-card-live-score"');
    expect(liveAt).toBeLessThan(f.indexOf(BAND_FEED));
  });

  it("nothing else on either card moves: score, chances and bar are byte-identical", () => {
    expect(withoutBand(card(live))).toBe(card(UGA));
    expect(withoutBand(feed(live))).toBe(feed(UGA));
  });

  it("the event page reads the SAME pair, not the ladders', and rounds it to the card's numbers", () => {
    const ladder = { home_score: 41.4, away_score: 6.2 };
    const page = eventPageProjectedPair({ odds: live.current_odds, sportKey: UGA.sport, commenceTime: UGA.commence_time, isLive: true, ladderPair: ladder });
    expect(page).toEqual({ home_score: 36.9, away_score: 10.7 });
    expect(`${Math.round(page!.home_score)}-${Math.round(page!.away_score)}`).toBe(
      stamp(card(live), BAND_CARD)!.split(" ")[0],
    );
  });
});

describe("the band prints the in-play object's pair, never the row's plain pair", () => {
  // The positives above copy the plain `projected_*` keys into the object, so
  // they cannot tell "printed the object" from "printed the plain pair once the
  // object was accepted". On detail and search the plain pair can be pregame:
  // here it is 14780563's 29.6 / 22.3 — reachable from 21 – 0 — under UGA's
  // in-play 36.9 / 10.7.
  const ladder = { home_score: 41.4, away_score: 6.2 };

  it.each([
    ["a different pregame plain pair", { projected_home_score: 29.6, projected_away_score: 22.3 }],
    ["no plain pair at all (the feed serves none)", { projected_home_score: null, projected_away_score: null }],
  ])("%s: both cards print 37-11 and the page reads 36.9 / 10.7", (_l, plain) => {
    const e = withOdds(UGA, { ...plain, live_projection: UGA_IN_PLAY });
    expect(stamp(card(e), BAND_CARD)).toBe("37-11 home-away");
    expect(stamp(feed(e), BAND_FEED)).toBe("37-11 away-home");
    expect(
      eventPageProjectedPair({ odds: e.current_odds, sportKey: UGA.sport, commenceTime: UGA.commence_time, isLive: true, ladderPair: ladder }),
    ).toEqual({ home_score: 36.9, away_score: 10.7 });
  });
});

describe("the in-play object must be measured from the start this row carries", () => {
  // Georgia's row starts 19:30Z. An object measured from 18:30Z (cached, or a
  // start that moved later) with its earliest confirmation at 19:00Z passes its
  // own boundary check, yet that confirmation is pregame for this row.
  const early = withOdds(UGA, {
    live_projection: { ...UGA_IN_PLAY, boundary_at: "2026-09-26T18:30:00+00:00", earliest_confirmed_at: "2026-09-26T19:00:00+00:00" },
  });

  it("an earlier boundary: no band on either card, and the page withholds", () => {
    expect(stamp(card(early), BAND_CARD)).toBeNull();
    expect(stamp(feed(early), BAND_FEED)).toBeNull();
    expect(
      eventPageProjectedPair({ odds: early.current_odds, sportKey: UGA.sport, commenceTime: UGA.commence_time, isLive: true, ladderPair: { home_score: 41.4, away_score: 6.2 } }),
    ).toBeNull();
  });

  it("the times are compared as instants: `Z` and `+00:00` name the same start", () => {
    const z = { live_projection: { ...UGA_IN_PLAY, boundary_at: "2026-09-26T19:30:00Z" } };
    expect(UGA.commence_time).toBe("2026-09-26T19:30:00+00:00");
    expect(admittedLiveProjection(z, UGA.sport, UGA.commence_time)).toEqual({ home: 36.9, away: 10.7 });
    expect(admittedLiveProjection({ live_projection: UGA_IN_PLAY }, UGA.sport, "2026-09-26T19:30:00Z")).toEqual({ home: 36.9, away: 10.7 });
  });

  it.each([
    ["no row start", null],
    ["an unparseable row start", "soon"],
    ["a row start one second after the boundary", "2026-09-26T19:30:01+00:00"],
  ])("%s is refused", (_l, commence) => {
    expect(admittedLiveProjection({ live_projection: UGA_IN_PLAY }, UGA.sport, commence)).toBeNull();
  });
});

describe("a reconfirmed unchanged quote is an honest in-play reading", () => {
  // One book first quoting at 19:20Z and confirming the same value at 19:35Z
  // after the 19:30Z start: the latest capture precedes both the boundary and
  // the earliest confirmation. Capture and confirmation clocks have no required
  // order (authority R3, withdrawn 2026-10-20 23:48Z), so neither is a refusal.
  const reconfirmed = withOdds(UGA, { live_projection: { ...UGA_IN_PLAY, latest_captured_at: "2026-09-26T19:20:00+00:00" } });

  it("both cards print it and the page reads it", () => {
    expect(Date.parse("2026-09-26T19:20:00+00:00")).toBeLessThan(Date.parse(UGA_IN_PLAY.boundary_at));
    expect(Date.parse(UGA_IN_PLAY.earliest_confirmed_at)).toBeGreaterThanOrEqual(Date.parse(UGA_IN_PLAY.boundary_at));
    expect(stamp(card(reconfirmed), BAND_CARD)).toBe("37-11 home-away");
    expect(stamp(feed(reconfirmed), BAND_FEED)).toBe("37-11 away-home");
    expect(
      eventPageProjectedPair({ odds: reconfirmed.current_odds, sportKey: UGA.sport, commenceTime: UGA.commence_time, isLive: true, ladderPair: null }),
    ).toEqual({ home_score: 36.9, away_score: 10.7 });
  });
});

describe("FeedCard's live branch needs the start passed, like the league card and the page", () => {
  it("live by status but starting in 10 minutes by this clock: no FeedCard band", () => {
    const start = new Date(Date.now() + 10 * 60_000).toISOString();
    const early = new Date(Date.now() + 11 * 60_000).toISOString();
    const projection = { ...UGA_IN_PLAY, boundary_at: start, earliest_confirmed_at: early, latest_captured_at: early };
    const e = withOdds(UGA, { projected_home_score: 29.6, projected_away_score: 22.3, live_projection: projection }, { commence_time: start });
    // The object itself is admitted, so only the started check refuses it.
    expect(liveCardProjectedFinal(e.current_odds, UGA.sport, start, { home: 21, away: 0 })).toEqual({ home: 37, away: 11 });
    expect(stamp(feed(e), BAND_FEED)).toBeNull();
  });
});

describe("soccer: goals over 90 minutes, and only that", () => {
  const live = withOdds(KLEAGUE, { live_projection: KLEAGUE_IN_PLAY });

  it("prints the 90-minute label over the in-play goals", () => {
    const html = card(live);
    expect(stamp(html, BAND_CARD)).toBe("2-1 home-away");
    expect(html).toContain(">Projected final (90 min)<");
    expect(stamp(feed(live), BAND_FEED)).toBe("2-1 away-home");
    expect(projectedFinalPeriod(KLEAGUE.sport)).toBe("regulation");
  });

  it("the win-probability chips are untouched by the band", () => {
    expect(withoutBand(card(live))).toBe(card(KLEAGUE));
    expect(withoutBand(feed(live))).toBe(feed(KLEAGUE));
  });

  it.each([
    ["a full-game pair", { period: "full_game" as const }],
    ["a points pair", { unit: "points" as const }],
  ])("%s is refused on both cards, and the page withholds rather than swaps", (_l, patch) => {
    const wrong = withOdds(KLEAGUE, { live_projection: inPlay(KLEAGUE, KLEAGUE_IN_PLAY.earliest_confirmed_at, patch) });
    expect(stamp(card(wrong), BAND_CARD)).toBeNull();
    expect(stamp(feed(wrong), BAND_FEED)).toBeNull();
    expect(
      eventPageProjectedPair({ odds: wrong.current_odds, sportKey: KLEAGUE.sport, commenceTime: KLEAGUE.commence_time, isLive: true, ladderPair: { home_score: 2.2, away_score: 0.4 } }),
    ).toBeNull();
  });
});

describe("no in-play marker, no live forecast — whatever pair rides on the row", () => {
  it("the bare live pair (no live_projection) prints nothing; the page keeps its ladders, as today", () => {
    expect(UGA.current_odds).not.toHaveProperty("live_projection");
    expect(stamp(card(UGA), BAND_CARD)).toBeNull();
    expect(stamp(feed(UGA), BAND_FEED)).toBeNull();
    const ladder = { home_score: 41.4, away_score: 6.2 };
    expect(eventPageProjectedPair({ odds: UGA.current_odds, sportKey: UGA.sport, commenceTime: UGA.commence_time, isLive: true, ladderPair: ladder })).toBe(ladder);
  });

  it("the list routes' own marker (`projection_captured_at`) is not the in-play marker", () => {
    const e = withOdds(UGA, { projection_captured_at: UGA.current_odds!.captured_at });
    expect(stamp(card(e), BAND_CARD)).toBeNull();
    expect(stamp(feed(e), BAND_FEED)).toBeNull();
  });

  describe("14780563 at halftime 20 – 3 with its pregame 29.6 / 22.3", () => {
    const pregame = P.event_14780563 as Event;
    const halftime = { status: "live", commence_time: pregame.commence_time, home_score: 20, away_score: 3 } as Partial<Event>;

    it("reachable from the score, yet neither card prints it", () => {
      const e = withOdds(pregame, {}, halftime);
      expect(stamp(card(e), BAND_CARD)).toBeNull();
      expect(stamp(feed(e), BAND_FEED)).toBeNull();
    });

    it("wrapped as 'in play' with its real pregame dates, it is still refused — and the page withholds", () => {
      const seeded = withOdds(pregame, { live_projection: inPlay(pregame, pregame.current_odds!.captured_at) }, halftime);
      expect(stamp(card(seeded), BAND_CARD)).toBeNull();
      expect(stamp(feed(seeded), BAND_FEED)).toBeNull();
      expect(admittedLiveProjection(seeded.current_odds, pregame.sport, pregame.commence_time)).toBeNull();
      expect(
        eventPageProjectedPair({ odds: seeded.current_odds, sportKey: pregame.sport, commenceTime: pregame.commence_time, isLive: true, ladderPair: { home_score: 33.2, away_score: 15.1 } }),
      ).toBeNull();
    });
  });

  describe("MLS 15291065: the old league pair and the pair-less detail body", () => {
    const league = F.league_list_15291065;
    const detail = F.detail_15291065;
    const asLive = { status: "live", home_score: 0, away_score: 0 } as Partial<Event>;

    it("the cached league pair is from September, the detail body has none", () => {
      expect(league.current_odds?.captured_at).toBe("2026-09-06T02:32:31.866068+00:00");
      expect(detail.current_odds?.projected_home_score).toBeNull();
    });

    it("live, the old pair prints on neither card", () => {
      const e = withOdds(league, {}, { ...asLive, commence_time: "2026-09-06T03:00:00+00:00" });
      expect(stamp(card(e), BAND_CARD)).toBeNull();
      expect(stamp(feed(e), BAND_FEED)).toBeNull();
    });

    it("seeding the old pair as 'in play' gives the page no headline either", () => {
      const seed = inPlay(withOdds(league, {}, { commence_time: detail.commence_time }), league.current_odds!.captured_at);
      const odds = { ...detail.current_odds, live_projection: seed };
      expect(admittedLiveProjection(odds, detail.sport, detail.commence_time)).toBeNull();
      expect(eventPageProjectedPair({ odds, sportKey: detail.sport, commenceTime: detail.commence_time, isLive: true, ladderPair: null })).toBeNull();
      expect(eventPageProjectedPair({ odds: detail.current_odds, sportKey: detail.sport, commenceTime: detail.commence_time, isLive: true, ladderPair: null })).toBeNull();
    });
  });
});

describe("a broken or impossible in-play pair prints nothing", () => {
  it.each([
    ["null half", { projected_home_score: null }],
    ["NaN", { projected_away_score: Number.NaN }],
    ["Infinity", { projected_home_score: Number.POSITIVE_INFINITY }],
    ["negative half", { projected_away_score: -1.2 }],
    ["zero half", { projected_away_score: 0 }],
    ["another kind", { kind: "latest_before_play" }],
    ["another boundary", { boundary: "scheduled_start" }],
    ["another source", { source: "kalshi" }],
    ["another basis", { basis: "ladder" }],
    ["no books", { bookmaker_count: 0 }],
    ["fractional books", { bookmaker_count: 2.5 }],
    ["unparseable boundary", { boundary_at: "soon" }],
    ["missing latest", { latest_captured_at: "" }],
    ["confirmed before the start", { earliest_confirmed_at: "2026-09-26T19:29:59+00:00" }],
  ])("%s", (_label, patch) => {
    const e = withOdds(UGA, { live_projection: { ...UGA_IN_PLAY, ...(patch as object) } });
    expect(stamp(card(e), BAND_CARD)).toBeNull();
    expect(stamp(feed(e), BAND_FEED)).toBeNull();
    expect(card(e)).not.toContain("NaN");
  });

  it("not an object", () => {
    expect(admittedLiveProjection({ live_projection: "in_play" }, UGA.sport, UGA.commence_time)).toBeNull();
    expect(admittedLiveProjection({ live_projection: [UGA_IN_PLAY] }, UGA.sport, UGA.commence_time)).toBeNull();
  });

  it("below the score already on the board (#4885): Oklahoma projected 11 while holding 14", () => {
    const e = withOdds(UGA, { live_projection: UGA_IN_PLAY }, { away_score: 14 });
    expect(stamp(card(e), BAND_CARD)).toBeNull();
    expect(stamp(feed(e), BAND_FEED)).toBeNull();
    // Equal is reachable: a game with no more scoring.
    expect(liveCardProjectedFinal({ live_projection: UGA_IN_PLAY }, UGA.sport, UGA.commence_time, { home: 37, away: 11 })).toEqual({ home: 37, away: 11 });
    expect(liveCardProjectedFinal({ live_projection: UGA_IN_PLAY }, UGA.sport, UGA.commence_time, { home: 38, away: 11 })).toBeNull();
  });

  it("a level pair in a sport that cannot end level (#8156)", () => {
    const nba = { ...UGA_IN_PLAY, projected_home_score: 110.4, projected_away_score: 110.2 };
    expect(liveCardProjectedFinal({ live_projection: nba }, "basketball_nba", UGA.commence_time, { home: 100, away: 100 })).toBeNull();
    expect(liveCardProjectedFinal({ live_projection: { ...nba, projected_away_score: 104.1 } }, "basketball_nba", UGA.commence_time, { home: 100, away: 100 })).toEqual({ home: 110, away: 104 });
  });
});

describe("the game state decides, not the pair", () => {
  const live = withOdds(UGA, { live_projection: UGA_IN_PLAY });

  it.each([
    ["no home score", { home_score: null }],
    ["no away score", { away_score: null }],
    ["suspended", { status: "suspended" }],
    ["completed", { status: "completed" }],
    ["closed", { status: "closed" }],
  ])("%s: no live band on either card", (_l, patch) => {
    const e = { ...live, ...(patch as Partial<Event>) };
    expect(stamp(card(e), BAND_CARD)).toBeNull();
    expect(stamp(feed(e), BAND_FEED)).toBeNull();
  });

  it("a final prints no current forecast beside its historical one", () => {
    const e = { ...live, status: "completed" } as Event;
    const html = card(e) + feed(e);
    expect(html).not.toContain(BAND_CARD);
    expect(html).not.toContain(BAND_FEED);
  });

  it("before play the in-play object changes nothing: the pregame pair still prints", () => {
    const pregame = P.event_14780563 as Event;
    const future = new Date(Date.now() + 3 * 3600_000).toISOString();
    const e = withOdds(pregame, { live_projection: inPlay(pregame, pregame.current_odds!.captured_at) }, { commence_time: future });
    expect(stamp(card(e), BAND_CARD)).toBe("30-22 home-away");
    expect(
      eventPageProjectedPair({ odds: e.current_odds, sportKey: pregame.sport, commenceTime: e.commence_time, isLive: false, ladderPair: { home_score: 28.1, away_score: 21.0 } }),
    ).toEqual({ home_score: 29.6, away_score: 22.3 });
  });
});

describe("formats that keep their refusal live", () => {
  it.each(["baseball_mlb", "icehockey_nhl", "tennis_atp_shanghai_masters", "cricket_ipl", "mma_mixed_martial_arts", "rugbyleague_nrl", ""])(
    "%s",
    (sport) => {
      expect(admittedLiveProjection({ live_projection: UGA_IN_PLAY }, sport, UGA.commence_time)).toBeNull();
      expect(projectedFinalPeriod(sport)).toBeNull();
    },
  );

  it("football and basketball are full-game points", () => {
    expect(projectedFinalPeriod("americanfootball_ncaaf")).toBe("full_game");
    expect(projectedFinalPeriod("basketball_nba")).toBe("full_game");
  });
});
