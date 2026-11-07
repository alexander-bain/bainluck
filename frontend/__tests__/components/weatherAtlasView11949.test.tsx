import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

jest.mock("@/components/weather/MapCanvas", () => {
  const R = jest.requireActual<typeof import("react")>("react");
  return {
    __esModule: true,
    default: () => R.createElement("div", { "data-testid": "map-canvas" }, "MAP"),
  };
});

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: string) => {
    if (key === "weather-featured") {
      return {
        data: [
          {
            q: "Where will it rain this weekend?",
            leader: "Miami",
            prob: 78,
            probability: 0.78,
            src: "kalshi",
            tag: "Rain",
            closes: "Nov 8, 2026",
            market_id: 501,
          },
        ],
      };
    }
    if (key === "weather-rain") {
      return {
        data: {
          daily: [],
          monthly: [
            {
              city: "Austin",
              period: "Nov 2026",
              prob: 100,
              probability: 1.0,
              src: "kalshi",
              status: "settled",
              result: "yes",
            },
            {
              city: "New York",
              period: "Nov 2026",
              prob: 42,
              probability: 0.42,
              src: "kalshi",
              status: "closed",
              result: null,
            },
            {
              city: "Seattle",
              period: "Oct 2026",
              prob: 100,
              probability: 1.0,
              src: "kalshi",
              status: "settled",
              result: null,
            },
          ],
        },
      };
    }
    if (key === "weather-cities") {
      return {
        data: [
          {
            id: "nyc",
            name: "New York",
            preferredX: 100,
            preferredY: 100,
            x: 100,
            y: 100,
            region: "Americas",
            srcs: ["kalshi"],
            iso: "2026-11-06",
            high: {
              unit: "F",
              mode: 55,
              dist: [
                { label: "52°–53°F", prob: 25, probability: 0.25 },
                { label: "54°–55°F", prob: 50, probability: 0.50 },
                { label: "56°–57°F", prob: 25, probability: 0.25 },
              ],
            },
          },
        ],
      };
    }
    if (key === "weather-events") {
      return {
        data: {
          hurricane: [
            {
              q: "Atlantic named storms > 14",
              prob: 100,
              probability: 1.0,
              src: "kalshi",
              closes: "Nov 30, 2026",
              status: "settled",
              result: "yes",
            },
          ],
          earthquake: [
            {
              q: "7.0+ earthquake in California in 2026?",
              prob: 12,
              probability: 0.12,
              src: "polymarket",
              closes: "Dec 31, 2026",
            },
          ],
          tornadoes: [],
        },
      };
    }
    if (key === "weather-climate") {
      return {
        data: [
          {
            q: "2026 warmest year on record?",
            prob: 38,
            probability: 0.38,
            src: "kalshi",
            scale: "2026",
          },
        ],
      };
    }
    if (key === "weather-wildcards") {
      return {
        data: [
          {
            q: "White Christmas in NYC?",
            prob: 18,
            probability: 0.18,
            src: "kalshi",
            tag: "Winter",
          },
        ],
      };
    }
    return { data: undefined };
  },
}));

import WeatherPage from "@/app/weather/page";
import { findBannedCopy, JARGON_BANS, visibleTextFromHtml } from "@/lib/copyBans";

describe("/weather?atlas=1 (#11949 Order 11)", () => {
  afterEach(() => {
    delete (globalThis as { window?: unknown }).window;
  });

  it("renders probability-first hero, ThresholdLadderCard for monthly rain with ✓ Won, and BucketDistribution for city highs without venue or verdict pills", () => {
    (globalThis as { window?: unknown }).window = {
      location: { search: "?atlas=1" },
    };
    const html = renderToStaticMarkup(React.createElement(WeatherPage));
    expect(html).toContain("data-testid=\"weather-atlas-view\"");
    expect(html).toContain("What is the chance it rains tomorrow?");
    expect(html).not.toContain("What are the odds it rains tomorrow?");
    // Monthly rain settled row shows ✓ Won instead of 100%
    expect(html).toContain("Austin (Nov 2026)");
    expect(html).toContain("✓ Won");
    // 'closed' without a result stays unsettled and prints its live probability
    expect(html).toContain("New York (Nov 2026)");
    expect(html).toContain("42%");
    // 'settled' without a result prints 'Result unavailable' (never 100% or blank)
    expect(html).toContain("Seattle (Oct 2026)");
    expect(html).toContain("Result unavailable");
    expect(html).not.toContain(">100%<");
    // Temperature BucketDistribution
    expect(html).toContain("data-testid=\"atlas-bucket-distribution\"");
    expect(html).toContain("New York daily high");
    // No verdict pills ("Likely" / "Toss-up" / "Unlikely")
    expect(html).not.toContain(">Unlikely<");
    expect(html).not.toContain(">Likely<");
    expect(html).not.toContain(">Toss-up<");
    // No banned copy ("blend", etc.)
    expect(findBannedCopy(visibleTextFromHtml(html), JARGON_BANS)).toEqual([]);
  });
});
