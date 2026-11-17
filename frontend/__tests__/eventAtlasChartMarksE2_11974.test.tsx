/** @jest-environment jsdom */

import React, { act } from "react";
import { createRoot } from "react-dom/client";

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

function renderHtml(element: React.ReactElement): string {
  const container = document.createElement("div");
  const root = createRoot(container);
  act(() => {
    root.render(element);
  });
  const html = container.innerHTML;
  act(() => {
    root.unmount();
  });
  return html;
}

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

import OddsChart from "@/components/OddsChart";
import ProjectedFinalPointsChart from "@/components/event/ProjectedFinalPointsChart";
import type { ProjectedFinalPointsInput } from "@/lib/projectedFinalPointsSeries";
import type { OddsHistoryPoint } from "@/lib/types";

const START = Date.UTC(2026, 10, 6, 0, 0, 0);

const SAMPLE_POINTS: OddsHistoryPoint[] = [
  {
    timestamp: new Date(START - 30 * 60_000 + 14_000).toISOString(),
    home_probability: 0.56,
    away_probability: 0.44,
    over_under: null,
    projected_home_score: null,
    projected_away_score: null,
    bookmaker: "blend",
  },
  {
    timestamp: new Date(START + 15 * 60_000 + 27_000).toISOString(),
    home_probability: 0.64,
    away_probability: 0.36,
    over_under: null,
    projected_home_score: null,
    projected_away_score: null,
    bookmaker: "blend",
  },
  {
    timestamp: new Date(START + 45 * 60_000 + 52_000).toISOString(),
    home_probability: 0.72,
    away_probability: 0.28,
    over_under: null,
    projected_home_score: null,
    projected_away_score: null,
    bookmaker: "blend",
  },
];

describe("Step E2 — Game chart marks on OddsChart (#11974)", () => {
  it("keeps default OddsChart markup unchanged when atlasMode is omitted", () => {
    const html = renderHtml(
      <OddsChart
        history={SAMPLE_POINTS}
        homeTeam="Denver Nuggets"
        awayTeam="Miami Heat"
        commenceTime={new Date(START).toISOString()}
        isLive
        eventStatus="live"
        externalTimeRange="all"
      />,
    );

    expect(html).not.toContain('data-testid="atlas-chart-mark-key"');
    expect(html).not.toContain('data-testid="atlas-chart-opening-mark"');
    expect(html).not.toContain('data-testid="atlas-chart-recorded-mark"');
    expect(html).not.toContain('data-testid="atlas-chart-result-word"');
  });

  it("draws hollow Pregame mark without solid reading marks on All, and legend says only what is true in All (#12615)", () => {
    const html = renderHtml(
      <OddsChart
        history={SAMPLE_POINTS}
        homeTeam="Denver Nuggets"
        awayTeam="Miami Heat"
        commenceTime={new Date(START).toISOString()}
        isLive
        eventStatus="live"
        externalTimeRange="all"
        atlasMode
      />,
    );

    expect(html).toContain('data-testid="atlas-chart-mark-key"');
    expect(html).toContain(">Pregame<");
    expect(html).not.toContain(">Recorded reading<");
    expect(html).toContain(">Change<");
    expect(html).toContain("Tap any reading for exact time (PT)");

    const openingMatches = html.match(/data-testid="atlas-chart-opening-mark"/g) ?? [];
    const recordedMatches = html.match(/data-testid="atlas-chart-recorded-mark"/g) ?? [];
    const hitMatches = html.match(/data-testid="atlas-chart-reading-hit"/g) ?? [];
    expect(openingMatches).toHaveLength(1);
    expect(recordedMatches).toHaveLength(0);
    // Every real reading remains tappable in All even when solid dots are suppressed
    expect(hitMatches).toHaveLength(3);
  });

  it("omits the hollow Pregame mark on Since Start (live window) and shows Recorded reading in legend (#12615)", () => {
    const html = renderHtml(
      <OddsChart
        history={SAMPLE_POINTS}
        homeTeam="Denver Nuggets"
        awayTeam="Miami Heat"
        commenceTime={new Date(START).toISOString()}
        isLive
        eventStatus="live"
        externalTimeRange="live"
        atlasMode
      />,
    );

    expect(html).toContain('data-testid="atlas-chart-mark-key"');
    expect(html).not.toContain(">Pregame<");
    expect(html).toContain(">Recorded reading<");
    expect(html).not.toContain('data-testid="atlas-chart-opening-mark"');
    const recordedMatches = html.match(/data-testid="atlas-chart-recorded-mark"/g) ?? [];
    expect(recordedMatches).toHaveLength(2);
  });

  it("shows a solid mark for every recorded reading during a 146-minute game in Since Start without thinning (#12615)", () => {
    const gameReadings: OddsHistoryPoint[] = Array.from({ length: 146 }, (_, idx) => ({
      timestamp: new Date(START + idx * 60_000).toISOString(),
      home_probability: Math.min(0.99, Math.max(0.01, 0.42 + Math.sin(idx / 9) * 0.28)),
      away_probability: Math.min(0.99, Math.max(0.01, 0.58 - Math.sin(idx / 9) * 0.28)),
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
      bookmaker: "blend",
    }));

    const html = renderHtml(
      <OddsChart
        history={gameReadings}
        homeTeam="Philadelphia 76ers"
        awayTeam="Boston Celtics"
        commenceTime={new Date(START).toISOString()}
        isLive={false}
        eventStatus="completed"
        externalTimeRange="live"
        atlasMode
        settledWinnerSide="home"
      />,
    );

    const recordedMatches = html.match(/data-testid="atlas-chart-recorded-mark"/g) ?? [];
    expect(recordedMatches).toHaveLength(146);
    expect(html).toContain('data-testid="event-atlas-how-to-read"');
    expect(html).toContain(">How to read this<");
    expect(html).toContain(">Recorded reading<");
    expect(html).not.toContain(">Pregame<");
  });

  it("thins solid reading marks and hit targets above the 300-mark ceiling on a 2,000-reading match and keeps the key truthful (#12615)", () => {
    const marathonReadings: OddsHistoryPoint[] = Array.from({ length: 2000 }, (_, idx) => ({
      timestamp: new Date(START + idx * 60_000).toISOString(),
      home_probability: Math.min(0.99, Math.max(0.01, 0.5 + Math.sin(idx / 40) * 0.3)),
      away_probability: Math.min(0.99, Math.max(0.01, 0.5 - Math.sin(idx / 40) * 0.3)),
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
      bookmaker: "blend",
    }));

    const html = renderHtml(
      <OddsChart
        history={marathonReadings}
        homeTeam="England"
        awayTeam="Australia"
        commenceTime={new Date(START).toISOString()}
        isLive={false}
        eventStatus="completed"
        externalTimeRange="live"
        atlasMode
        settledWinnerSide="home"
      />,
    );

    const recordedMatches = html.match(/data-testid="atlas-chart-recorded-mark"/g) ?? [];
    const hitMatches = html.match(/data-testid="atlas-chart-reading-hit"/g) ?? [];
    expect(recordedMatches.length).toBeGreaterThan(250);
    expect(recordedMatches.length).toBeLessThanOrEqual(300);
    expect(hitMatches.length).toBeLessThanOrEqual(300);
    expect(html).toContain("Recorded readings (sampled above 300)");
    expect(html).not.toContain(">Recorded reading<");

    const allHtml = renderHtml(
      <OddsChart
        history={marathonReadings}
        homeTeam="England"
        awayTeam="Australia"
        commenceTime={new Date(START + 500 * 60_000).toISOString()}
        isLive={false}
        eventStatus="completed"
        externalTimeRange="all"
        atlasMode
        settledWinnerSide="home"
      />,
    );
    const allRecordedMatches = allHtml.match(/data-testid="atlas-chart-recorded-mark"/g) ?? [];
    const allHitMatches = allHtml.match(/data-testid="atlas-chart-reading-hit"/g) ?? [];
    expect(allRecordedMatches.length).toBe(0);
    expect(allHitMatches.length).toBeGreaterThan(250);
    expect(allHitMatches.length).toBeLessThanOrEqual(300);
  });

  it("draws one data-forecast-mark per point on multi-point segments in ProjectedFinalPointsChart and leaves single-point segments unchanged (#12615)", () => {
    const input: ProjectedFinalPointsInput = {
      sportKey: "basketball_nba",
      sourceKey: "draftkings",
      basis: "same_book_same_capture_full_game_spread_and_total",
      pairs: [
        // 3-point segment before a withheld gap
        { timestamp: "2026-11-11T00:05:00Z", home: 112.5, away: 108.0, homeProbability: 0.62 },
        { timestamp: "2026-11-11T00:25:00Z", home: 114.0, away: 106.5, homeProbability: 0.70 },
        { timestamp: "2026-11-11T00:45:00Z", home: 111.0, away: 109.5, homeProbability: 0.55 },
        { timestamp: "2026-11-11T01:00:00Z", home: null, away: null },
        // 1-point segment isolated between two withheld gaps
        { timestamp: "2026-11-11T01:15:00Z", home: 116.0, away: 110.0, homeProbability: 0.68 },
        { timestamp: "2026-11-11T01:30:00Z", home: null, away: null },
        // 2-point segment before the final
        { timestamp: "2026-11-11T01:50:00Z", home: 118.0, away: 115.0, homeProbability: 0.60 },
        { timestamp: "2026-11-11T02:10:00Z", home: 119.5, away: 120.5, homeProbability: 0.45 },
      ],
      actuals: [
        { timestamp: "2026-11-11T00:10:00Z", home_score: 4, away_score: 2 },
        { timestamp: "2026-11-11T02:15:00Z", home_score: 119, away_score: 121 },
      ],
      kickoffAt: "2026-11-11T00:00:00Z",
      finalAt: "2026-11-11T02:20:00Z",
      asOf: "2026-11-11T02:30:00Z",
    };

    const html = renderHtml(
      <ProjectedFinalPointsChart
        input={input}
        homeTeam="Philadelphia 76ers"
        awayTeam="Boston Celtics"
        finalScore={{ home: 119, away: 121 }}
      />,
    );

    // Multi-point segments have 3 + 2 = 5 points per team -> 5 home marks and 5 away marks
    const homeForecastMarks = html.match(/data-forecast-mark="home"/g) ?? [];
    const awayForecastMarks = html.match(/data-forecast-mark="away"/g) ?? [];
    expect(homeForecastMarks).toHaveLength(5);
    expect(awayForecastMarks).toHaveLength(5);

    // Single-point segment (1 isolated point + 1 final pre-completion capture = 2 single-point segments per team = 4 total) stays on data-single-point="true" without data-forecast-mark
    const singlePointCircles = html.match(/data-single-point="true"/g) ?? [];
    expect(singlePointCircles.length).toBeGreaterThanOrEqual(2);
  });

  it("renders settled result word (✓ Won / ✗ Lost) beside the final reading when settled", () => {
    const wonHtml = renderHtml(
      <OddsChart
        history={SAMPLE_POINTS}
        homeTeam="Denver Nuggets"
        awayTeam="Miami Heat"
        commenceTime={new Date(START).toISOString()}
        isLive={false}
        eventStatus="completed"
        externalTimeRange="all"
        atlasMode
        settledWinnerSide="home"
      />,
    );

    expect(wonHtml).toContain('data-testid="atlas-chart-key-result-word"');
    expect(wonHtml).toContain('data-testid="atlas-chart-result-word"');
    expect(wonHtml).toContain('data-result="won"');
    expect(wonHtml).toContain("✓ Won");

    const awayPolePoints: OddsHistoryPoint[] = [
      {
        timestamp: new Date(START - 30 * 60_000).toISOString(),
        home_probability: 0.44,
        away_probability: 0.56,
        over_under: null,
        projected_home_score: null,
        projected_away_score: null,
        bookmaker: "blend",
      },
      {
        timestamp: new Date(START + 45 * 60_000).toISOString(),
        home_probability: 0.02,
        away_probability: 0.98,
        over_under: null,
        projected_home_score: null,
        projected_away_score: null,
        bookmaker: "blend",
      },
    ];
    const awayWonHtml = renderHtml(
      <OddsChart
        history={awayPolePoints}
        homeTeam="Washington Wizards"
        awayTeam="Atlanta Hawks"
        commenceTime={new Date(START).toISOString()}
        isLive={false}
        eventStatus="completed"
        externalTimeRange="all"
        atlasMode
        settledWinnerSide="away"
      />,
    );
    expect(awayWonHtml).toContain('data-testid="atlas-chart-result-word"');
    expect(awayWonHtml).toContain('data-result="won"');
    expect(awayWonHtml).toContain("✓ Won");

    const lostHtml = renderHtml(
      <OddsChart
        history={SAMPLE_POINTS}
        homeTeam="Denver Nuggets"
        awayTeam="Miami Heat"
        commenceTime={new Date(START).toISOString()}
        isLive={false}
        eventStatus="completed"
        externalTimeRange="all"
        atlasMode
        settledWinnerSide="away"
      />,
    );

    expect(lostHtml).toContain('data-testid="atlas-chart-result-word"');
    expect(lostHtml).toContain('data-result="lost"');
    expect(lostHtml).toContain("✗ Lost");
  });

  it("displays exact PT timestamp and probability when a reading mark is tapped", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(
        <OddsChart
          history={SAMPLE_POINTS}
          homeTeam="Denver Nuggets"
          awayTeam="Miami Heat"
          commenceTime={new Date(START).toISOString()}
          isLive
          eventStatus="live"
          externalTimeRange="all"
          atlasMode
        />,
      );
    });

    const hits = container.querySelectorAll('[data-testid="atlas-chart-reading-hit"]');
    expect(hits.length).toBe(3);

    act(() => {
      hits[1].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    const readout = container.querySelector('[data-testid="atlas-chart-selected-reading"]');
    expect(readout).not.toBeNull();
    expect(readout?.textContent).toContain("Denver Nuggets");
    expect(readout?.textContent).toContain("Recorded");
    expect(readout?.textContent).toContain("64%");
    expect(readout?.textContent).toContain("PT");

    const clearBtn = container.querySelector('[data-testid="atlas-chart-reading-clear"]');
    expect(clearBtn).not.toBeNull();
    act(() => {
      clearBtn?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(container.querySelector('[data-testid="atlas-chart-selected-reading"]')).toBeNull();

    act(() => {
      root.unmount();
    });
    container.remove();
  });
});
