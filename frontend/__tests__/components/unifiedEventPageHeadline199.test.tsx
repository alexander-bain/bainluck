/**
 * Direction 199 & Rulings 200-B, 197, 194-A — Unified Website Game Page Headline Guard
 *
 * Mirrors iOS `UnifiedHeadlineContactSheetGuard199Tests.swift` (`#12771`) across
 * every sport (`NFL, NBA, NCAAF, NCAAB, MLB, NHL, Soccer 3-Way, Tennis, MMA, Boxing`)
 * × `before / during / after` + edge cases (`no pregame number`, `no projection`,
 * `no score`, `ended with no result`, `opening-only quote`, `Ruling 197 colour collision`,
 * `Ruling 194-A college school names`).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventPageHeadline199 from "@/components/event/EventPageHeadline199";
import { computeLastChartPoint, resolveProbability } from "@/lib/eventKeyStats";
import {
  HEADLINE_STYLE_199,
  resolveEventPageHeadline199,
  resolveHeadlineTeamHexes199,
  type HeadlineModel199,
} from "@/lib/eventPageHeadline199";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";

type ResolveInput199 = Parameters<typeof resolveEventPageHeadline199>[0];

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/1",
  useSearchParams: () => new URLSearchParams(),
}));

const FIXED_NOW_MS = Date.parse("2026-11-16T19:15:00Z");
const FUTURE_START = "2026-11-16T22:00:00Z";
const LIVE_START = "2026-11-16T18:00:00Z";
const PAST_START = "2026-11-16T01:00:00Z";

describe("a historical opening reading is kept off the live headline", () => {
  const opening = "2026-11-16T16:00:00Z";
  const inPlay = "2026-11-16T19:14:00Z";
  const live = baseEvent({
    status: "live", commence_time: LIVE_START, away_score: 68, home_score: 72,
    hero_probability_source: undefined, hero_probability: undefined, current_odds: undefined,
  });

  it.each([
    ["a real pregame quote", opening, opening, "recorded", false, "", ""],
    ["a pregame quote carried to a live timestamp", opening, inPlay, "synthetic", false, "", ""],
    ["an unpinned blend ending at the opening", opening, opening, "recorded", true, "", ""],
    ["a recorded live quote", inPlay, inPlay, "recorded", false, "42.0%", "58.0%"],
  ])("%s", (_case, observed, stamp, kind, oldBlend, away, home) => {
    const history = {
      blend_edge_pinned: false,
      aggregate_line: oldBlend ? [{ timestamp: opening, home_probability: 0.58 }] : [],
      history: [{ timestamp: stamp, home_probability: 0.58, away_probability: 0.42, bookmaker_count: 1 }],
      bookmaker_history: {
        book: [{ timestamp: stamp, home_probability: 0.58, kind, observed_at: observed }],
      },
    } as unknown as EventHistoryResponse;
    const tail = computeLastChartPoint(history, null, null);
    const picked = resolveProbability(live, history, tail, true, false);
    const { model } = resolveSpecimen(live, {
      homeProb: picked.homeProb,
      servedAwayProb: picked.awayProb,
      homePct: picked.homePct,
      servedAwayPct: picked.awayPct,
      probSourceLabel: picked.probSourceLabel,
      tenthsOptIn: true,
    });

    expect(tail?.homeProb).toBe(0.58);
    expect(model.rows.find(row => row.role === "away")?.cells.at(-1)).toBe(away);
    expect(model.rows.find(row => row.role === "home")?.cells.at(-1)).toBe(home);
  });
});

function baseEvent(overrides: Partial<EventDetailResponse> = {}): EventDetailResponse {
  return {
    id: 9001,
    external_id: "spec-9001",
    sport: "americanfootball_nfl",
    sport_key: "americanfootball_nfl",
    sport_name: "NFL",
    away_team: "Green Bay Packers",
    home_team: "Detroit Lions",
    commence_time: FUTURE_START,
    status: "scheduled",
    away_score: null,
    home_score: null,
    away_team_data: {
      name: "Green Bay Packers",
      abbreviation: "GB",
      primary_color: "#203731",
      record: "7-3",
    },
    home_team_data: {
      name: "Detroit Lions",
      abbreviation: "DET",
      primary_color: "#0076B6",
      record: "8-2",
    },
    current_odds: {
      away_probability: 0.42,
      home_probability: 0.58,
      away_rendered_percent: 42,
      home_rendered_percent: 58,
      projected_away_score: 23.4,
      projected_home_score: 27.1,
    },
    prematch_odds: {
      away_probability: 0.42,
      home_probability: 0.58,
      away_rendered_percent: 42,
      home_rendered_percent: 58,
      source: "kalshi",
    },
    pregame_projection: {
      kind: "last_before_scheduled_start",
      boundary: "scheduled_start",
      boundary_at: LIVE_START,
      earliest_captured_at: "2026-11-16T17:30:00Z",
      latest_captured_at: "2026-11-16T17:58:00Z",
      source: "sportsbooks",
      basis: "consensus_spread_total",
      bookmaker_count: 14,
      unit: "points",
      period: "full_game",
      projected_home_score: 27.1,
      projected_away_score: 23.4,
    },
    bookmaker_odds: [],
    win_probability_sources: {},
    ...overrides,
  } as EventDetailResponse;
}

function resolveSpecimen(
  overrides: Partial<EventDetailResponse>,
  inputOverrides: Partial<ResolveInput199> = {},
): { event: EventDetailResponse; model: HeadlineModel199; html: string } {
  const event = baseEvent(overrides);
  const status = event.status;
  const isFinished = status === "completed" || status === "closed";
  const isLive = status === "live";
  const isSuspended = status === "suspended";
  const bestHomeScore = event.home_score ?? null;
  const bestAwayScore = event.away_score ?? null;
  const heroScorePairPresent = bestHomeScore !== null && bestAwayScore !== null;
  const projRaw =
    event.current_odds?.projected_home_score != null &&
    event.current_odds?.projected_away_score != null
      ? {
          home_score: event.current_odds.projected_home_score,
          away_score: event.current_odds.projected_away_score,
        }
      : null;

  const model = resolveEventPageHeadline199({
    event,
    effectivelyLive: isLive,
    isLive,
    isFinished,
    isSuspended,
    venueVoided: false,
    venueSettledSentence: null,
    stoppageLabel: null,
    startClock: "clock",
    pregameStateLabel: "Pregame",
    liveClockLabel: isLive ? "Q3 · 6:12" : null,
    bestHomeScore,
    bestAwayScore,
    heroScorePairPresent,
    heroScoreIsStoppageFiller: false,
    projectedPairRaw: projRaw,
    projectedPairAdmitted: projRaw !== null && (!isLive || heroScorePairPresent),
    homeProb: isFinished ? null : (event.current_odds?.home_probability ?? null),
    servedAwayProb: isFinished ? null : (event.current_odds?.away_probability ?? null),
    homePct: isFinished ? null : (event.current_odds?.home_rendered_percent ?? null),
    servedAwayPct: isFinished ? null : (event.current_odds?.away_rendered_percent ?? null),
    probSourceLabel: "Bain Luck blend",
    tenthsOptIn: isLive,
    settledWinnerSide:
      isFinished && bestHomeScore !== null && bestAwayScore !== null
        ? bestHomeScore > bestAwayScore
          ? "home"
          : bestAwayScore > bestHomeScore
            ? "away"
            : null
        : null,
    gameMarkets: null,
    nowMs: FIXED_NOW_MS,
    ...inputOverrides,
  });

  const html = renderToStaticMarkup(
    React.createElement(EventPageHeadline199, {
      event,
      model,
      isPinned: false,
      pinDisabled: false,
      onPinToggle: () => {},
    }),
  );

  return { event, model, html };
}

function collectVisibleLabels(model: HeadlineModel199): string[] {
  const out: string[] = [];
  if (model.liveBadgeText) {
    out.push(model.liveBadgeText);
    out.push(model.leagueLabel);
  } else if (model.plainMetaText) {
    out.push(model.plainMetaText);
  }
  for (const c of model.columns) {
    if (c.header) out.push(c.header);
  }
  for (const r of model.rows) {
    if (r.shortName) out.push(r.shortName);
    if (r.record) out.push(r.record);
    for (const cell of r.cells) {
      if (cell) out.push(cell);
    }
  }
  if (model.livePregameSummary) {
    out.push(model.livePregameSummary.leadWord);
    out.push(model.livePregameSummary.bodyText);
  }
  return out;
}

const BANNED_SUBSTRINGS = [
  "opening",
  "opened",
  "stale",
  "settled",
  "by venue",
  "3 venues",
  "current win chance",
  "projection before",
];

describe("Unified Website Game Page Headline (Direction 199 & Rulings 200-B, 197, 194-A)", () => {
  const sportsMatrix: Array<{
    name: string;
    sport: string;
    away: string;
    home: string;
    hasProj: boolean;
    hasScore: boolean;
    unit?: "points" | "goals";
    period?: "full_game" | "regulation";
  }> = [
    { name: "NFL", sport: "americanfootball_nfl", away: "Green Bay Packers", home: "Detroit Lions", hasProj: true, hasScore: true },
    { name: "NBA", sport: "basketball_nba", away: "Boston Celtics", home: "Cleveland Cavaliers", hasProj: true, hasScore: true },
    { name: "NCAAF", sport: "americanfootball_ncaaf", away: "Alabama Crimson Tide", home: "Georgia Bulldogs", hasProj: true, hasScore: true },
    { name: "NCAAB", sport: "basketball_ncaab", away: "Kansas Jayhawks", home: "Duke Blue Devils", hasProj: true, hasScore: true },
    { name: "MLB", sport: "baseball_mlb", away: "San Diego Padres", home: "Los Angeles Dodgers", hasProj: true, hasScore: true },
    { name: "NHL", sport: "icehockey_nhl", away: "Edmonton Oilers", home: "Florida Panthers", hasProj: true, hasScore: true },
    { name: "MMA", sport: "mma_mixed_martial_arts", away: "Alex Pereira", home: "Magomed Ankalaev", hasProj: false, hasScore: false },
    { name: "Boxing", sport: "boxing_boxing", away: "Canelo Alvarez", home: "Terence Crawford", hasProj: false, hasScore: false },
  ];

  it.each(sportsMatrix)(
    "$name renders Before / During / After on EventPageHeadline199 with zero banned words or duplicate labels",
    ({ sport, away, home, hasProj, hasScore }) => {
      const before = resolveSpecimen({
        sport,
        sport_key: sport,
        away_team: away,
        home_team: home,
        status: "scheduled",
        commence_time: FUTURE_START,
      });
      expect(before.model.phase).toBe("before");
      expect(before.html).toContain('data-testid="event-page-headline-199"');
      if (hasProj) {
        expect(before.model.columns.map((c) => c.role)).toEqual(["projected", "chance"]);
      } else {
        expect(before.model.columns.map((c) => c.role)).toEqual(["chance"]);
      }
      expect(before.model.livePregameSummary).toBeNull();
      expect(before.model.bottomBar).not.toBeNull();

      const during = resolveSpecimen({
        sport,
        sport_key: sport,
        away_team: away,
        home_team: home,
        status: "live",
        commence_time: LIVE_START,
        away_score: hasScore ? 17 : null,
        home_score: hasScore ? 21 : null,
      });
      expect(during.model.phase).toBe("during");
      expect(during.model.columns.some((c) => c.role === "pregame")).toBe(false);
      expect(during.model.rows.every((r) => r.record === null)).toBe(true);

      const after = resolveSpecimen(
        {
          sport,
          sport_key: sport,
          away_team: away,
          home_team: home,
          status: "completed",
          commence_time: PAST_START,
          away_score: hasScore ? 20 : null,
          home_score: hasScore ? 27 : null,
        },
        { settledWinnerSide: "home" },
      );
      expect(after.model.phase).toBe("after");
      expect(after.model.columns.map((c) => c.header)).toEqual(["Pregame", "Final"]);
      expect(after.model.bottomBar).toBeNull();
      expect(after.model.livePregameSummary).toBeNull();
      expect(after.html).toContain(">✓<");

      for (const spec of [before, during, after]) {
        const labels = collectVisibleLabels(spec.model);
        const lowerJoined = labels.join(" | ").toLowerCase();
        for (const banned of BANNED_SUBSTRINGS) {
          expect(lowerJoined).not.toContain(banned);
        }
        const alpha = labels.filter((t) => /[A-Za-z]/.test(t));
        expect(new Set(alpha).size).toBe(alpha.length);
      }
    },
  );

  it("College teams print school names (Alabama, Georgia, Kansas, Duke), never mascots (Ruling 194-A)", () => {
    const ncaab = resolveSpecimen({
      sport: "basketball_ncaab",
      sport_key: "basketball_ncaab",
      away_team: "Kansas Jayhawks",
      home_team: "Duke Blue Devils",
    });
    expect(ncaab.model.rows.map((r) => r.shortName)).toEqual(["Kansas", "Duke"]);
  });

  it("Soccer 3-way renders Home · Away · Draw with light cool-grey Draw (#94A3B8 / #CBD5E1)", () => {
    const soccer3WayMarkets = {
      other: [
        {
          market_name: "Match Result",
          outcome_name: "Arsenal",
          probability: 0.52,
          pregame_mark: 0.48,
          source: "blended",
          observed_at: "2026-11-16T19:14:30Z",
          _market_id: 501,
        },
        {
          market_name: "Match Result",
          outcome_name: "Draw",
          probability: 0.26,
          pregame_mark: 0.27,
          source: "blended",
          observed_at: "2026-11-16T19:14:30Z",
          _market_id: 501,
        },
        {
          market_name: "Match Result",
          outcome_name: "Chelsea",
          probability: 0.22,
          pregame_mark: 0.25,
          source: "blended",
          observed_at: "2026-11-16T19:14:30Z",
          _market_id: 501,
        },
      ],
    };

    const during = resolveSpecimen(
      {
        sport: "soccer_epl",
        sport_key: "soccer_epl",
        away_team: "Chelsea",
        home_team: "Arsenal",
        status: "live",
        commence_time: LIVE_START,
        away_score: 0,
        home_score: 1,
        pregame_projection: {
          kind: "last_before_scheduled_start",
          boundary: "scheduled_start",
          boundary_at: LIVE_START,
          earliest_captured_at: "2026-11-16T17:30:00Z",
          latest_captured_at: "2026-11-16T17:58:00Z",
          source: "sportsbooks",
          basis: "consensus_spread_total",
          bookmaker_count: 8,
          unit: "goals",
          period: "regulation",
          projected_home_score: 1.7,
          projected_away_score: 1.1,
        },
      },
      { gameMarkets: soccer3WayMarkets },
    );

    expect(during.model.rows.map((r) => r.role)).toEqual(["home", "away", "draw"]);
    expect(during.model.colors.drawText).toBe(HEADLINE_STYLE_199.drawTextInk);
    expect(during.model.colors.drawBar).toBe(HEADLINE_STYLE_199.drawBarInk);
    expect(during.model.bottomBar?.kind).toBe("threeWay");
    expect(during.model.livePregameSummary?.fullText).toBe("Pregame  Arsenal 48% · projected 2–1");
  });

  it("Tennis renders set-by-set S1/S2/S3 + Pts during play and S1/S2 · Pregame · Final after play (no Proj.)", () => {
    const tennisLive = resolveSpecimen({
      sport: "tennis_atp_finals",
      sport_key: "tennis_atp_finals",
      away_team: "Taylor Fritz",
      home_team: "Jannik Sinner",
      status: "live",
      commence_time: LIVE_START,
      away_score: 0,
      home_score: 1,
      espn: {
        period: "Set 2",
        game_clock: "30-40",
      } as EventDetailResponse["espn"],
      linescore: {
        sets: [
          [6, 4],
          [4, 3],
        ],
      } as EventDetailResponse["linescore"],
    });
    expect(tennisLive.model.columns.map((c) => c.header)).toEqual(["S1", "S2", "Pts", "Now"]);
    expect(tennisLive.model.columns.some((c) => c.role === "projected")).toBe(false);

    const tennisFinal = resolveSpecimen(
      {
        sport: "tennis_atp_finals",
        sport_key: "tennis_atp_finals",
        away_team: "Taylor Fritz",
        home_team: "Jannik Sinner",
        status: "completed",
        commence_time: PAST_START,
        away_score: 0,
        home_score: 2,
        linescore: {
          sets: [
            [6, 4],
            [6, 4],
          ],
        } as EventDetailResponse["linescore"],
      },
      { settledWinnerSide: "home" },
    );
    expect(tennisFinal.model.columns.map((c) => c.header)).toEqual(["S1", "S2", "Pregame", "Final"]);
    expect(tennisFinal.model.bottomBar).toBeNull();
  });

  it("Edge cases: no pregame number (never falls back to opening_odds), no projection, no score, ended with no result", () => {
    // 1. No pregame number (`prematch_odds: undefined`, `opening_odds` present) -> Pregame omitted!
    const noPregameLive = resolveSpecimen({
      status: "live",
      commence_time: LIVE_START,
      away_score: 14,
      home_score: 17,
      prematch_odds: undefined,
      pregame_projection: null,
      opening_odds: {
        away_probability: 0.45,
        home_probability: 0.55,
      } as EventDetailResponse["opening_odds"],
    });
    expect(noPregameLive.model.livePregameSummary).toBeNull();
    expect(noPregameLive.model.bottomBar).toEqual({
      kind: "twoWay",
      awayShare: 0.42,
      homeShare: 0.58,
      pregameAwayMarker: null,
    });

    const noPregameAfter = resolveSpecimen(
      {
        status: "completed",
        commence_time: PAST_START,
        away_score: 20,
        home_score: 27,
        prematch_odds: undefined,
        opening_odds: {
          away_probability: 0.45,
          home_probability: 0.55,
        } as EventDetailResponse["opening_odds"],
      },
      { settledWinnerSide: "home" },
    );
    expect(noPregameAfter.model.columns.map((c) => c.header)).toEqual(["", "Final"]);

    // 2. No projection -> `Proj.` header suppressed (`""`) while Chance stays
    const noProjBefore = resolveSpecimen(
      {
        status: "scheduled",
        commence_time: FUTURE_START,
        current_odds: {
          away_probability: 0.42,
          home_probability: 0.58,
          away_rendered_percent: 42,
          home_rendered_percent: 58,
        } as EventDetailResponse["current_odds"],
      },
      { projectedPairRaw: null, projectedPairAdmitted: false },
    );
    expect(noProjBefore.model.columns.map((c) => c.header)).toEqual(["", "Chance"]);

    // 3. Live with no score -> both `Score` and `Proj.` headers suppressed (`""`), `Now` stays
    const noScoreLive = resolveSpecimen(
      {
        status: "live",
        commence_time: LIVE_START,
        away_score: null,
        home_score: null,
      },
      {
        bestAwayScore: null,
        bestHomeScore: null,
        heroScorePairPresent: false,
        projectedPairAdmitted: false,
      },
    );
    expect(noScoreLive.model.columns.map((c) => c.header)).toEqual(["", "", "Now"]);

    // 4. Ended with no result reported -> `after` phase, `"Ended · no result reported"`, no bar, no blank headers
    const endedNoResult = resolveSpecimen(
      {
        status: "scheduled",
        commence_time: PAST_START,
        away_score: null,
        home_score: null,
        prematch_odds: undefined,
      },
      {
        isLive: false,
        effectivelyLive: false,
        isFinished: false,
        isSuspended: true,
        settledWinnerSide: null,
      },
    );
    expect(endedNoResult.model.phase).toBe("after");
    expect(endedNoResult.model.plainMetaText).toBe("NFL · Ended · no result reported");
    expect(endedNoResult.model.hasAnyColumnValue).toBe(false);
    expect(endedNoResult.model.bottomBar).toBeNull();
  });

  it("Ruling 197: same-colour-family teams switch away to secondary colour or slate grey", () => {
    // Kansas (#0051BA) at Duke (#003087) with Kansas crimson secondary (#E8000D) -> crimson vs blue
    const kansasDuke = resolveHeadlineTeamHexes199({
      homePrimary: "#003087",
      awayPrimary: "#0051BA",
      awaySecondary: "#E8000D",
    });
    expect(kansasDuke.away.toUpperCase()).not.toBe("#0051BA");
    expect(kansasDuke.home.toUpperCase()).toBe("#003087");

    // Gonzaga (#041E42) at Duke (#003087) with no secondary -> slate fallback (#64748B)
    const gonzagaDuke = resolveHeadlineTeamHexes199({
      homePrimary: "#003087",
      awayPrimary: "#041E42",
      awaySecondary: null,
    });
    expect(gonzagaDuke.away.toUpperCase()).toBe("#64748B");
  });

  it("emits event-hero-probability on before/during and event-hero-settled with data-winner on after", () => {
    const before = resolveSpecimen({});
    expect(before.html).toContain('data-testid="event-hero-probability"');
    expect(before.html).toContain('data-probability="0.58"');
    expect(before.html).not.toContain('data-testid="event-hero-settled"');

    const after = resolveSpecimen(
      {
        status: "completed",
        commence_time: PAST_START,
        away_score: 20,
        home_score: 27,
      },
      { settledWinnerSide: "home" },
    );
    expect(after.html).toContain('data-testid="event-hero-settled"');
    expect(after.html).toContain('data-winner="Detroit Lions"');
    expect(after.html).not.toContain('data-testid="event-hero-probability"');
  });
});
