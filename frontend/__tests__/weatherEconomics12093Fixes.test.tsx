import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RainForecast from "@/components/weather/RainForecast";
import EconomicsPage from "@/app/economics/page";
import {
  filterMonotoneLadderRows,
  formatFedHeatmapCell,
} from "@/components/economics/atoms";

let mockRainData: unknown = undefined;
let mockEconData: unknown = undefined;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: string) => {
    if (key === "weather-rain") return { data: mockRainData, error: undefined };
    if (key === "economics-data") return { data: mockEconData, error: undefined };
    return { data: undefined, error: undefined };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

describe("#12093 follow-up fixes on /weather and /economics", () => {
  beforeEach(() => {
    mockRainData = undefined;
    mockEconData = undefined;
  });

  it("formats Fed heat map cells as whole percents with % sign and boundary clamps", () => {
    expect(formatFedHeatmapCell(0)).toBe("");
    expect(formatFedHeatmapCell(55.5)).toBe("56%");
    expect(formatFedHeatmapCell(58.5)).toBe("59%");
    expect(formatFedHeatmapCell(7.5)).toBe("8%");
    expect(formatFedHeatmapCell(1.5)).toBe("2%");
    expect(formatFedHeatmapCell(0.5)).toBe("1%");
    expect(formatFedHeatmapCell(0.3)).toBe("<1%");
    expect(formatFedHeatmapCell(99.8, false)).toBe(">99%");
    expect(formatFedHeatmapCell(100, true)).toBe("100%");
  });

  it("filters out-of-order live ladder rungs while keeping reached rungs intact", () => {
    const reached = new Set(["Above 6.2%", "Above 6.3%", "Above 7.3%"]);
    const rows: [number, string][] = [
      [100, "Above 6.2%"],
      [100, "Above 6.3%"],
      [100, "Above 7.3%"],
      [52.5, "Above 7.4%"],
      [30.5, "Above 7.5%"],
      [9.0, "Above 7.6%"],
      [9.0, "Above 7.8%"],
      [2.0, "Above 7.9%"],
      [4.5, "Above 8.0%"], // backwards tail rung -> dropped
    ];
    expect(filterMonotoneLadderRows(rows, reached)).toEqual([
      [100, "Above 6.2%"],
      [100, "Above 6.3%"],
      [100, "Above 7.3%"],
      [52.5, "Above 7.4%"],
      [30.5, "Above 7.5%"],
      [9.0, "Above 7.6%"],
      [9.0, "Above 7.8%"],
      [2.0, "Above 7.9%"],
    ]);
  });

  it("renders mortgage card with ✓ Reached on settled rungs, >99% on extreme live rungs, and whole % on Fed heat map", () => {
    mockEconData = {
      total_markets: 42,
      themes: {
        fed: {
          count: 2,
          fomc_meetings: [
            {
              date: "Jan 2027 meeting",
              mo: "Jan",
              resolved: false,
              dist: [
                [55.5, "4.25%"],
                [7.5, "4.50%"],
                [1.5, "3.50%"],
              ],
            },
          ],
          rate_cuts: [],
          side_markets: [],
        },
        housing: {
          count: 1,
          mortgage_dist: {
            q: "How high will the 30-year mortgage rate get in 2026?",
            kind: "ladder",
            src: "kalshi",
            market_id: 109321,
            reached_labels: ["Above 6.2%", "Above 6.5%"],
            rows: [
              [100.0, "Above 6.2%"],
              [100.0, "Above 6.5%"],
              [99.8, "Above 7.3%"], // live unreached extreme rung -> >99%, NEVER 100%
              [52.5, "Above 7.4%"],
              [2.0, "Above 7.9%"],
              [4.5, "Above 8.0%"], // backwards -> dropped
            ],
          },
          markets: [],
        },
      },
    };

    const html = renderToStaticMarkup(<EconomicsPage />);
    // Fed heat map prints whole percents with % sign, never bare halves
    expect(html).toContain(">56%<");
    expect(html).toContain(">8%<");
    expect(html).toContain(">2%<");
    expect(html).not.toContain(">55.5<");
    expect(html).not.toContain(">7.5<");
    expect(html).not.toContain(">1.5<");

    // Mortgage card prints ✓ Reached on settled rungs, >99% on live 99.8, never 100%, and omits backwards 8.0%
    expect(html).toContain("✓ Reached");
    expect(html).toContain("&gt;99%");
    expect(html).not.toContain(">100%<");
    expect(html).toContain("Above 7.9%");
    expect(html).not.toContain("Above 8.0%");
  });

  it("drops Monthly rainfall 24h-change column and footer when rows have no 24h changes, and shows ✓ Won only on settled rows", () => {
    mockRainData = {
      daily: [],
      monthly: [
        { city: "Austin", period: "Nov 2026", prob: 100, probability: 1.0, settled: true, src: "kalshi", delta24h: 0 },
        { city: "Seattle", period: "Nov 2026", prob: 100, probability: 0.995, settled: false, src: "kalshi", delta24h: 0 },
        { city: "Chicago", period: "Nov 2026", prob: 79, probability: 0.79, settled: false, src: "kalshi", delta24h: 0 },
      ],
    };
    const html = renderToStaticMarkup(<RainForecast />);
    expect(html).toContain("✓ Won");
    expect(html).toContain("&gt;99%");
    expect(html).not.toContain(">100%<");
    expect(html).not.toContain("24h change shown at right");
  });
});
