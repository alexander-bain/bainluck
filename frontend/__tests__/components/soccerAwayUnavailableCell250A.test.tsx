/**
 * @jest-environment node
 *
 * Ruling 250: A — On draw-priced (soccer) game headlines where the home row
 * prints a real probability and no draw probability is served, the away cell may
 * never stay blank: print "No probability yet" before the match has started or
 * held a non-complement away reading, and "No recent probability" after.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventPageHeadline199 from "@/components/event/EventPageHeadline199";
import {
  HEADLINE_STYLE_199,
  NO_PROBABILITY_YET_250A,
  NO_RECENT_PROBABILITY_250A,
  resolveEventPageHeadline199,
  resolveWithheldAwayCellLabel250A,
  type HeadlineModel199,
} from "@/lib/eventPageHeadline199";
import type { EventDetailResponse } from "@/lib/types";

type ResolveInput199 = Parameters<typeof resolveEventPageHeadline199>[0];

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/1",
  useSearchParams: () => new URLSearchParams(),
}));

const FIXED_NOW_MS = Date.parse("2026-11-26T19:15:00Z");
const FUTURE_START = "2026-11-27T20:00:00Z";
const LIVE_START = "2026-11-26T18:00:00Z";

function soccerEvent(overrides: Partial<EventDetailResponse> = {}): EventDetailResponse {
  return {
    id: 99001,
    external_id: "epl-forest-chelsea",
    sport: "soccer_epl",
    sport_key: "soccer_epl",
    sport_name: "Premier League",
    away_team: "Chelsea",
    home_team: "Nottingham Forest",
    commence_time: FUTURE_START,
    status: "scheduled",
    away_score: null,
    home_score: null,
    away_team_data: {
      name: "Chelsea",
      abbreviation: "CHE",
      primary_color: "#034694",
      record: "5-1-5",
      logo_large: null,
      logo_small: null,
    },
    home_team_data: {
      name: "Nottingham Forest",
      abbreviation: "NFO",
      primary_color: "#DD0000",
      record: "2-3-6",
      logo_large: null,
      logo_small: null,
    },
    current_odds: {
      home_probability: 0.62,
      away_probability: null,
      home_rendered_percent: 62,
      away_rendered_percent: null,
    } as EventDetailResponse["current_odds"],
    bookmaker_odds: [],
    win_probability_sources: {},
    ...overrides,
  } as EventDetailResponse;
}

function renderHeadline(
  overrides: Partial<EventDetailResponse> = {},
  inputOverrides: Partial<ResolveInput199> = {},
): { event: EventDetailResponse; model: HeadlineModel199; html: string } {
  const event = soccerEvent(overrides);
  const isFinished = event.status === "completed" || event.status === "closed";
  const isLive = event.status === "live";
  const isSuspended = event.status === "suspended";
  const bestHomeScore = event.home_score ?? null;
  const bestAwayScore = event.away_score ?? null;
  const heroScorePairPresent = bestHomeScore !== null && bestAwayScore !== null;

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
    liveClockLabel: isLive ? "67'" : null,
    bestHomeScore,
    bestAwayScore,
    heroScorePairPresent,
    heroScoreIsStoppageFiller: false,
    projectedPairRaw: null,
    projectedPairAdmitted: false,
    homeProb: isFinished ? null : (event.current_odds?.home_probability ?? null),
    servedAwayProb: isFinished ? null : (event.current_odds?.away_probability ?? null),
    homePct: isFinished ? null : (event.current_odds?.home_rendered_percent ?? null),
    servedAwayPct: isFinished ? null : (event.current_odds?.away_rendered_percent ?? null),
    probSourceLabel: "Bain Luck blend",
    tenthsOptIn: isLive,
    settledWinnerSide: null,
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

describe("#13823 follow-up (250: A) — soccer game with home probability and no draw leaves no blank away cell", () => {
  it("prints 'No probability yet' in the scheduled away Chance cell before any away reading existed", () => {
    const { model, html } = renderHeadline();
    const awayRow = model.rows.find((r) => r.role === "away");
    const homeRow = model.rows.find((r) => r.role === "home");

    expect(model.phase).toBe("before");
    expect(awayRow?.cells.at(-1)).toBe(NO_PROBABILITY_YET_250A);
    expect(awayRow?.rawProbability).toBeNull();
    expect(homeRow?.cells.at(-1)).toBe("62%");
    expect(model.bottomBar).toBeNull();
    expect(model.columns.find((c) => c.role === "chance")?.header).toBe("Chance");

    const awayChunk = html.slice(
      html.indexOf('data-testid="headline-12472-away-row"'),
      html.indexOf('data-testid="headline-12472-home-row"'),
    );
    expect(awayChunk).toContain('data-testid="headline-12472-away-unavailable-cell"');
    expect(awayChunk).toContain(NO_PROBABILITY_YET_250A);
    expect(awayChunk).not.toContain("data-hero-digits");
    expect(awayChunk).not.toContain("38%");
  });

  it("prints 'No recent probability' before kickoff when a prior non-complement 3-way away reading existed", () => {
    const { model, html } = renderHeadline({
      opening_odds: {
        home_probability: 0.52,
        away_probability: 0.24,
        draw_probability: 0.24,
      } as unknown as EventDetailResponse["opening_odds"],
    });

    const awayRow = model.rows.find((r) => r.role === "away");
    expect(awayRow?.cells.at(-1)).toBe(NO_RECENT_PROBABILITY_250A);
    expect(awayRow?.rawProbability).toBeNull();
    expect(model.rows.find((r) => r.role === "home")?.cells.at(-1)).toBe("62%");
    expect(html).toContain(NO_RECENT_PROBABILITY_250A);
  });

  it("still prints 'No probability yet' when opening_odds only held a 2-way complement (1 - home)", () => {
    const { model } = renderHeadline({
      opening_odds: {
        home_probability: 0.62,
        away_probability: 0.38,
      } as unknown as EventDetailResponse["opening_odds"],
    });

    expect(model.rows.find((r) => r.role === "away")?.cells.at(-1)).toBe(NO_PROBABILITY_YET_250A);
  });

  it("prints 'No recent probability' in the live Now cell (with tenths and whole percents) while preserving Score alignment", () => {
    for (const tenthsOptIn of [true, false]) {
      const { model, html } = renderHeadline(
        {
          status: "live",
          commence_time: LIVE_START,
          away_score: 0,
          home_score: 1,
          current_odds: {
            home_probability: 0.62,
            away_probability: 0.38, // served complement must still be withheld
            home_rendered_percent: 62,
            away_rendered_percent: 38,
          } as EventDetailResponse["current_odds"],
        },
        { tenthsOptIn },
      );

      const awayRow = model.rows.find((r) => r.role === "away");
      const homeRow = model.rows.find((r) => r.role === "home");
      expect(model.phase).toBe("during");
      expect(model.columns.map((c) => c.header).filter(Boolean)).toEqual(["Score", "Now"]);
      expect(awayRow?.cells[0]).toBe("0");
      expect(awayRow?.cells.at(-1)).toBe(NO_RECENT_PROBABILITY_250A);
      expect(awayRow?.rawProbability).toBeNull();
      expect(homeRow?.cells[0]).toBe("1");
      expect(homeRow?.cells.at(-1)).toBe(tenthsOptIn ? "62.0%" : "62%");
      expect(model.bottomBar).toBeNull();

      const awayChunk = html.slice(
        html.indexOf('data-testid="headline-12472-away-row"'),
        html.indexOf('data-testid="headline-12472-home-row"'),
      );
      expect(awayChunk).toContain('data-score-cell="away"');
      expect(awayChunk).toContain('data-testid="headline-12472-away-unavailable-cell"');
      expect(awayChunk).toContain(NO_RECENT_PROBABILITY_250A);
      expect(awayChunk).not.toContain("38.0%");
      expect(awayChunk).not.toContain("38%");
    }
  });

  it("also prints 'No recent probability' before status flips if scheduled kickoff has already passed", () => {
    const startedEvent = soccerEvent({ commence_time: LIVE_START, status: "scheduled" });
    expect(resolveWithheldAwayCellLabel250A(startedEvent, "before", FIXED_NOW_MS)).toBe(
      NO_RECENT_PROBABILITY_250A,
    );
  });

  it("leaves explicit 3-way soccer and 2-way sports completely untouched", () => {
    const threeWayMarkets = {
      other: [
        {
          market_name: "Match Result",
          outcome_name: "Nottingham Forest",
          probability: 0.48,
          pregame_mark: 0.45,
          source: "blended",
          observed_at: "2026-11-26T19:14:30Z",
          _market_id: 501,
        },
        {
          market_name: "Match Result",
          outcome_name: "Chelsea",
          probability: 0.25,
          pregame_mark: 0.28,
          source: "blended",
          observed_at: "2026-11-26T19:14:30Z",
          _market_id: 501,
        },
        {
          market_name: "Match Result",
          outcome_name: "Draw",
          probability: 0.27,
          pregame_mark: 0.27,
          source: "blended",
          observed_at: "2026-11-26T19:14:30Z",
          _market_id: 501,
        },
      ],
    };
    const threeWay = renderHeadline(
      { status: "live", commence_time: LIVE_START, away_score: 0, home_score: 1 },
      { gameMarkets: threeWayMarkets },
    );
    expect(threeWay.model.rows.map((r) => r.role)).toEqual(["home", "away", "draw"]);
    expect(threeWay.model.colors.drawText).toBe(HEADLINE_STYLE_199.drawTextInk);
    expect(threeWay.html).not.toContain("headline-12472-away-unavailable-cell");

    const twoWay = renderHeadline({
      sport: "americanfootball_nfl",
      sport_key: "americanfootball_nfl",
      sport_name: "NFL",
      away_team: "Green Bay Packers",
      home_team: "Detroit Lions",
      current_odds: {
        home_probability: 0.62,
        away_probability: 0.38,
        home_rendered_percent: 62,
        away_rendered_percent: 38,
      } as EventDetailResponse["current_odds"],
    });
    expect(twoWay.model.rows.find((r) => r.role === "away")?.cells.at(-1)).toBe("38%");
    expect(twoWay.html).not.toContain("headline-12472-away-unavailable-cell");
  });

  it("keeps the Chance / Now column collapsed when neither team has a current probability", () => {
    const noHome = renderHeadline(
      {
        current_odds: {
          home_probability: null,
          away_probability: null,
        } as unknown as EventDetailResponse["current_odds"],
      },
      { homeProb: null, servedAwayProb: null, homePct: null, servedAwayPct: null },
    );
    expect(noHome.model.columns.find((c) => c.role === "chance")?.header).toBe("");
    expect(noHome.html).not.toContain("headline-12472-away-unavailable-cell");
  });
});
