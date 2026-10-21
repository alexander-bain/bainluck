/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import OddsChart from "@/components/OddsChart";
import { projectedTeamStrokes } from "@/lib/teamLineStrokes";

jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: jest.fn() }) }));
jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return { ...actual, ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
    React.cloneElement(children, { width: 390, height: 300 }) };
});
const start = Date.UTC(2026, 9, 18, 0);
const series = (offset = 0) => Array.from({ length: 31 }, (_, i) => {
  const p = 0.48 + i * 0.016 + offset;
  return { timestamp: new Date(start + i * 60_000).toISOString(), home_probability: p, away_probability: 1 - p };
});
beforeAll(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  window.matchMedia = jest.fn().mockReturnValue({ matches: false, addEventListener: jest.fn(), removeEventListener: jest.fn() });
});
it("Sources reveals providers without changing team paths, colors, axes or gutter; Hide restores the view", () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    act(() => root.render(<OddsChart
      history={series() as never} aggregateLine={series()}
      winProbHistory={{ espn: series(0.01), kalshi: series(-0.01) } as never}
      homeTeam="Green Bay Packers" awayTeam="Dallas Cowboys"
      homeTeamColor="#203731" awayTeamColor="#002244"
      commenceTime={new Date(start).toISOString()}
      eventStatus="completed" externalTimeRange="all"
      backendBlendServed pairedAwayLine eventId={14780562}
    />));
    const read = () => ({
      teams: Array.from(container.querySelectorAll('[data-testid="paired-team-key"]')).map(el => el.outerHTML),
      lines: Array.from(container.querySelectorAll('.recharts-line')).filter(el =>
        el.querySelector('path')?.getAttribute('stroke') === projectedTeamStrokes('#203731', '#002244').home || el.classList.contains('paired-away-line')
      ).map(el => ({ stroke: el.querySelector('path')?.getAttribute('stroke'), path: el.querySelector('path')?.getAttribute('d') })),
      axes: Array.from(container.querySelectorAll('.recharts-xAxis, .recharts-yAxis')).map(el => el.outerHTML),
      poles: container.querySelectorAll('[data-testid="chart-axis-pole"]').length,
    });
    const before = read();
    expect(before.teams).toHaveLength(2);
    expect(before.lines).toHaveLength(2);
    expect(before.lines.every(line => line.path)).toBe(true);
    expect(before.poles).toBe(0);
    expect(container.querySelectorAll('.recharts-line')).toHaveLength(2);
    const sources = Array.from(container.querySelectorAll('button')).find(el => el.textContent?.includes('sources'))!;
    expect(sources).toBeDefined();
    act(() => sources.click());
    expect(read()).toEqual(before);
    expect(container.querySelectorAll('.recharts-line').length).toBeGreaterThan(2);
    expect(Array.from(container.querySelectorAll('a')).map(el => el.textContent)).toEqual(expect.arrayContaining(['Kalshi', 'ESPN']));
    const hide = Array.from(container.querySelectorAll('button')).find(el => el.textContent?.trim() === 'Hide')!;
    expect(hide.getAttribute('aria-expanded')).toBe('true');
    act(() => hide.click());
    expect(read()).toEqual(before);
    expect(container.querySelectorAll('.recharts-line')).toHaveLength(2);
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});
