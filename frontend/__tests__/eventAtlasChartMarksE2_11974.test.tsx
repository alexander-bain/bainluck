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

  it("draws hollow Pregame mark and solid recorded reading marks on All when atlasMode is enabled", () => {
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
    expect(html).toContain(">Recorded reading<");
    expect(html).toContain(">Change<");
    expect(html).toContain("Tap any reading for exact time (PT)");

    const openingMatches = html.match(/data-testid="atlas-chart-opening-mark"/g) ?? [];
    const recordedMatches = html.match(/data-testid="atlas-chart-recorded-mark"/g) ?? [];
    expect(openingMatches).toHaveLength(1);
    // Only the two subsequent real readings get recorded marks, not the 75 gap-filled minutes
    expect(recordedMatches).toHaveLength(2);
  });

  it("omits the hollow Pregame mark on Since Start (live window) when atlasMode is enabled", () => {
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
    expect(html).not.toContain('data-testid="atlas-chart-opening-mark"');
    const recordedMatches = html.match(/data-testid="atlas-chart-recorded-mark"/g) ?? [];
    expect(recordedMatches).toHaveLength(2);
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
