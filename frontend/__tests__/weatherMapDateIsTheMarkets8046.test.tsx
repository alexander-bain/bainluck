/**
 * #8046 Half B — the /weather temperature map dates itself from its markets,
 * never from the reader's clock.
 *
 * WHAT A READER SAW, production 2026-09-28 01:1xZ at 390px: the map chip read
 * "HIGH · SEP 28, 2026" and every city panel "Tomorrow's high temperature ·
 * Sep 28, 2026" — `new Date() + 1` on the reader's machine. The 48 markets
 * behind the pins were on THREE days: 6 Kalshi cities on Sep 27, 2 on Sep 28,
 * 40 Polymarket cities on Sep 29 (New York's panel said Sep 28 over market
 * 62721466, "Highest temperature in NYC on September 29?").
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherMapDateIsTheMarkets8046
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import DistributionPanel from "@/components/weather/DistributionPanel";
import MapCanvas from "@/components/weather/MapCanvas";
import { isoDayLabel, sharedDayLabel } from "@/components/weather/data";
import type { CityData } from "@/components/weather/data";

function city(id: string, name: string, iso?: string | null): CityData {
  return {
    id,
    name,
    preferredX: 28.6,
    preferredY: 37.8,
    x: 28.6,
    y: 37.8,
    region: "Americas",
    srcs: ["polymarket"],
    iso,
    high: {
      unit: "F",
      mode: 72.5,
      dist: [
        { label: "70-71°F", prob: 36, probability: 0.36 },
        { label: "72-73°F", prob: 64, probability: 0.64 },
      ],
    },
  };
}

const text = (html: string) => html.replace(/<[^>]+>/g, "").replace(/&#x27;/g, "'");

function panel(c: CityData): string {
  return text(renderToStaticMarkup(<DistributionPanel city={c} />));
}

function chip(cities: CityData[]): string {
  const html = text(
    renderToStaticMarkup(
      <MapCanvas cities={cities} selected="" hover={null} onHover={() => {}} onSelect={() => {}} />,
    ),
  );
  return /HIGH(?:\s*·\s*[A-Z]{3} \d{1,2}, \d{4})?/.exec(html)?.[0] ?? "";
}

describe("the city panel prints its own market's day", () => {
  test("New York's Sep 29 market reads Sep 29, whatever the reader's clock says", () => {
    const seen = panel(city("nyc", "New York", "2026-09-29"));
    expect(seen).toContain("High temperature · Sep 29, 2026");
    expect(seen).not.toContain("Tomorrow");
  });

  test("a city that cannot say its day prints no date at all", () => {
    const seen = panel(city("nyc", "New York", null));
    expect(seen).toContain("High temperature");
    expect(seen).not.toMatch(/High temperature · /);
    expect(seen).not.toMatch(/[A-Z][a-z]{2} \d{1,2}, \d{4}/);
  });
});

describe("the map chip asserts one date only when every city shares it", () => {
  test("48 cities on three days: the chip names none", () => {
    const cities = [
      city("boston", "Boston", "2026-09-27"),
      city("denver", "Denver", "2026-09-28"),
      city("nyc", "New York", "2026-09-29"),
    ];
    expect(chip(cities)).toBe("HIGH");
  });

  test("every city on one day: the chip names it", () => {
    const cities = [city("nyc", "New York", "2026-09-29"), city("chicago", "Chicago", "2026-09-29")];
    expect(chip(cities)).toBe("HIGH · SEP 29, 2026");
  });

  test("one city without a day withholds the shared date", () => {
    const cities = [city("nyc", "New York", "2026-09-29"), city("chicago", "Chicago")];
    expect(chip(cities)).toBe("HIGH");
  });
});

describe("the day is read as a calendar day, not through the reader's zone", () => {
  test("isoDayLabel", () => {
    expect(isoDayLabel("2026-09-29")).toBe("Sep 29, 2026");
    expect(isoDayLabel("2026-01-01")).toBe("Jan 1, 2026");
    expect(isoDayLabel("2026-13-01")).toBeNull();
    expect(isoDayLabel("Sep 29")).toBeNull();
    expect(isoDayLabel(undefined)).toBeNull();
  });

  test("sharedDayLabel", () => {
    expect(sharedDayLabel([])).toBeNull();
    expect(sharedDayLabel([city("a", "A", "2026-09-29"), city("b", "B", "2026-09-29")])).toBe("Sep 29, 2026");
  });
});
