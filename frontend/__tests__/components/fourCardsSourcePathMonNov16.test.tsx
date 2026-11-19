/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

let swrMap: Record<string, unknown> = {};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: string) => ({
    data: swrMap[key],
    error: undefined,
    isLoading: swrMap[key] === undefined,
  }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  usePathname: () => "/economics",
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

import RainForecast from "@/components/weather/RainForecast";
import EconomicsPage from "@/app/economics/page";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("Item 3: four cards on /weather and /economics link directly to /futures/[id]", () => {
  let host: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    swrMap = {};
    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
  });

  it("1. /weather RainForecast links daily rain tiles and monthly city rows to /futures/[id] and never /futures/undefined", () => {
    swrMap["weather-rain"] = {
      daily: [
        {
          day: "Mon",
          date: "Nov 16",
          iso: "2026-11-16",
          prob: 45,
          probability: 0.45,
          icon: "🌦️",
          market_id: 70101,
        },
        {
          day: "Tue",
          date: "Nov 17",
          iso: "2026-11-17",
          prob: 20,
          probability: 0.2,
          icon: "⛅",
          market_id: null, // cached fallback with no id renders plain div
        },
      ],
      monthly: [
        {
          city: "New York",
          period: "Nov 2026",
          prob: 78,
          probability: 0.78,
          settled: false,
          src: "kalshi",
          delta24h: 3,
          market_id: 70201,
        },
        {
          city: "Seattle",
          period: "Nov 2026",
          prob: 92,
          probability: 0.92,
          settled: false,
          src: "kalshi",
          delta24h: 0,
        },
      ],
    };

    act(() => {
      root.render(React.createElement(RainForecast));
    });

    const dailyTiles = host.querySelectorAll('[data-testid="rain-day-tile"]');
    expect(dailyTiles).toHaveLength(2);
    expect(dailyTiles[0].tagName).toBe("A");
    expect(dailyTiles[0].getAttribute("href")).toBe("/futures/70101");
    expect(dailyTiles[1].tagName).toBe("DIV");

    const monthlyRows = host.querySelectorAll('[data-testid="monthly-rain-row"]');
    expect(monthlyRows).toHaveLength(2);
    expect(monthlyRows[0].tagName).toBe("A");
    expect(monthlyRows[0].getAttribute("href")).toBe("/futures/70201");
    expect(monthlyRows[1].tagName).toBe("DIV");

    expect(host.innerHTML).not.toContain("/futures/undefined");
    expect(host.innerHTML).not.toContain("/futures/null");
  });

  it("2–4. /economics FedHeatmap, RateCutsChart card, and DistributionCard each open /futures/[id] on one tap", () => {
    swrMap["economics-data"] = {
      total_markets: 12,
      updated_at: "2026-11-16T15:00:00Z",
      cross_source: [],
      by_source: { kalshi: 8, polymarket: 4 },
      themes: {
        fed: {
          count: 4,
          fomc_meetings: [
            {
              date: "Dec 2026",
              mo: "Dec",
              dist: [
                [62, "3.75–4.00%"],
                [38, "4.00–4.25%"],
              ],
              resolved: false,
              market_id: 80101,
            },
            {
              date: "Jan 2027",
              mo: "Jan",
              dist: [
                [54, "3.50–3.75%"],
                [46, "3.75–4.00%"],
              ],
              resolved: false,
              market_id: 80102,
            },
          ],
          rate_cuts: [
            [24, "1 cut"],
            [51, "2 cuts"],
            [25, "3 cuts"],
          ],
          rate_cuts_market_id: 80201,
          side_markets: [],
        },
        inflation: { count: 0, cpi_releases: [], side_markets: [] },
        jobs: { count: 0, markets: [] },
        recession: {
          count: 0,
          main_prob: null,
          main_q: null,
          main_market_id: null,
          gdp_quarters: [],
          side_markets: [],
        },
        markets: { count: 0, today: [], stocks: [], side_markets: [] },
        energy: { count: 0, gas: [], oil: [], side_markets: [] },
        metals: { count: 0, cards: [], markets: [] },
        housing: {
          count: 1,
          mortgage_dist: {
            q: "30-year mortgage rate at year-end 2026?",
            kind: "ladder",
            rows: [
              [84, "Above 5.5%"],
              [52, "Above 6.0%"],
              [19, "Above 6.5%"],
            ],
            src: "kalshi",
            market_id: 80301,
          },
          markets: [],
        },
        trade: { count: 0, markets: [] },
        government: {
          count: 1,
          markets: [],
          distributions: [
            {
              q: "FY2026 federal deficit bracket?",
              kind: "brackets",
              rows: [
                [35, "$1.5T–$1.8T"],
                [45, "$1.8T–$2.1T"],
                [20, "Above $2.1T"],
              ],
              src: "polymarket",
              market_id: 80401,
            },
          ],
        },
      },
    };

    act(() => {
      root.render(React.createElement(EconomicsPage));
    });

    // FedHeatmap headers + cells link to each FOMC meeting's market page
    const fedHeaderLinks = Array.from(
      host.querySelectorAll('[data-testid="fed-heatmap-meeting-link"]'),
    ).map((el) => el.getAttribute("href"));
    expect(fedHeaderLinks).toEqual(["/futures/80101", "/futures/80102"]);

    const fedCellLinks = Array.from(
      host.querySelectorAll('[data-testid="fed-heatmap-cell-link"]'),
    ).map((el) => el.getAttribute("href"));
    expect(fedCellLinks).toContain("/futures/80101");
    expect(fedCellLinks).toContain("/futures/80102");

    // RateCutsChart card links to /futures/80201
    const rateCutsLink = host.querySelector('[data-testid="econ-rate-cuts-card-link"]');
    expect(rateCutsLink?.getAttribute("href")).toBe("/futures/80201");

    // DistributionCards (housing ladder + government brackets) link to /futures/80301 and /futures/80401
    const distLinks = Array.from(
      host.querySelectorAll('[data-testid="econ-distribution-card-link"]'),
    ).map((el) => el.getAttribute("href"));
    expect(distLinks).toEqual(["/futures/80301", "/futures/80401"]);

    expect(host.innerHTML).not.toContain("/futures/undefined");
  });
});
