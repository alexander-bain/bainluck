/**
 * #10090 — WITH TENTHS ON, THE HEADLINE AND THE CHART'S END LABEL PRINT ONE
 * DECIMAL, AS ONE PAIR.
 *
 * Tenths are on by default on the event page (`lib/tenthsOptIn.ts`, ALEX-DECISIONS
 * item 39). The OFF half (`?tenths=off`) is `tenthsOptInOffIsMaster10090`; this
 * file pins what every other reader sees:
 *
 *   * the two sides sum to 100.0, the second derived from the first;
 *   * the chart's end label is the same pair's digit at a half-tenth tie
 *     (the preview's first cut printed headline 63.2 under a chart 63.3);
 *   * a `<1` / `>99` band pair renders exactly as OFF (text, size, markup), and
 *     a band is symmetric across a pair (`0.5 | 99.5` both print; nearer the
 *     edge both take the marker);
 *   * a venue-settled hero and a completed chart are byte-identical to OFF;
 *   * one named number (#6238) keeps the full 48px size, and a decimal reserves
 *     two numeral widths so 9.8 → 10.2 does not shift the pair.
 *
 * Layout at 390px is not something markup can show; it was read in a browser
 * against production data (the PR body carries the shots).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock("recharts", () => ({
  __esModule: true,
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
    React.cloneElement(children, { width: 390, height: 300 }),
}));

import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import OddsChart from "@/components/OddsChart";
import { tenthsPair, tenthsSideLabel, tenthsText, type TenthsParts } from "@/lib/tenthsOptIn";

/** Fixed anchor — never `Date.now()` (gotcha #44). */
const START = Date.UTC(2026, 9, 25, 18, 0, 0);
const N = 60;

beforeAll(() => {
  jest.useFakeTimers();
  jest.setSystemTime(START + N * 60_000);
});
afterAll(() => jest.useRealTimers());

type HeroProps = React.ComponentProps<typeof EventHeroProbabilityPair>;

const hero = (props: Partial<HeroProps>) =>
  renderToStaticMarkup(
    <EventHeroProbabilityPair
      homeProb={0.6234}
      awayProb={0.3766}
      homePct={62}
      awayPct={38}
      homeColor="#111827"
      awayColor="#94A3B8"
      started
      {...props}
    />,
  );

/** The pair as a reader reads it: each side's text, `%` included. */
function heroSides(html: string): string[] {
  const text = html
    .replace(/<[^>]+>/g, "|")
    .split("|")
    .map((s) => s.trim())
    .filter(Boolean)
    .join("")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
  return text.match(/[<>]?\d+(\.\d)?%/g) ?? [];
}

function series(endPct: number) {
  return Array.from({ length: N }, (_, i) => {
    const p = i === N - 1 ? endPct : 55 + 8 * Math.sin(i * 0.4);
    return {
      timestamp: new Date(START + i * 60_000).toISOString(),
      home_probability: p / 100,
      away_probability: 1 - p / 100,
    };
  });
}

const chart = (endPct: number, status: "live" | "completed", tenths: boolean) =>
  renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Lens"
      awayTeam="Lyon"
      commenceTime={new Date(START).toISOString()}
      isLive={status === "live"}
      eventStatus={status}
      chartStartTime={new Date(START).toISOString()}
      chartEndTime={new Date(START + (N - 1) * 60_000).toISOString()}
      winProbHistory={{ kalshi: series(endPct) }}
      winProbSources={{
        kalshi: { display_name: "Kalshi", color: "#22c55e", type: "market", snapshot_count: N },
      }}
      tenths={tenths}
    />,
  );
const callout = (html: string) => /data-callout-text="([^"]+)"/.exec(html)?.[1];
const normalise = (html: string) => html.replace(/recharts(-[a-z]+)*-?\d+/g, (m) => m.replace(/\d+$/, "N"));

const tenthsOf = (parts: TenthsParts) => Number(parts.whole) * 10 + Number(parts.decimal.slice(1) || 0);

describe("#10090 tenths pair — the pure rule", () => {
  it("sums to 100.0 across the whole printable range, the second side derived", () => {
    for (let k = 1; k < 10_000; k++) {
      const p = k / 10_000;
      const { home, away } = tenthsPair(p, 1 - p);
      expect(home).not.toBeNull();
      expect(away).not.toBeNull();
      if (home!.marker || away!.marker) {
        // a band on one side is a band on the other
        expect(home!.marker && away!.marker).toBeTruthy();
        continue;
      }
      expect(tenthsOf(home!) + tenthsOf(away!)).toBe(1000);
    }
  });

  it("normalises a vigged pair by its total before deriving, as the cards do", () => {
    const { home, away } = tenthsPair(0.62, 0.385);
    expect(tenthsText(home!)).toBe("61.7%");
    expect(tenthsText(away!)).toBe("38.3%");
  });

  it("carries no digit the value does not: 0.6 prints 60.0, not 60", () => {
    expect(tenthsText(tenthsPair(0.6, 0.4).home!)).toBe("60.0%");
  });

  it("bands keep their text, symmetric across the pair", () => {
    const sides = (p: number) => {
      const { home, away } = tenthsPair(p, 1 - p);
      return [tenthsText(home!), tenthsText(away!)];
    };
    expect(sides(0.004)).toEqual(["<1%", ">99%"]);
    expect(sides(0.005)).toEqual(["0.5%", "99.5%"]);
    expect(sides(0.995)).toEqual(["99.5%", "0.5%"]);
    expect(sides(0.996)).toEqual([">99%", "<1%"]);
    expect(sides(1)).toEqual(["100%", "0%"]);
  });

  it("the chart's side label reads the same pair at a half-tenth tie", () => {
    // 0.3675: rounding 1 − p on its own gives 63.3 under a headline 63.2.
    expect(tenthsSideLabel(0.3675, false)).toBe("36.8%");
    expect(tenthsSideLabel(0.3675, true)).toBe("63.2%");
    expect(tenthsSideLabel(0.5125, false)).toBe("51.3%");
    expect(tenthsSideLabel(0.5125, true)).toBe("48.7%");
  });
});

describe("#10090 tenths on — the hero", () => {
  it("prints one decimal per side, summing to 100.0", () => {
    expect(heroSides(hero({ tenths: true }))).toEqual(["62.3%", "37.7%"]);
    expect(heroSides(hero({}))).toEqual(["62%", "38%"]);
  });

  it("the headline and the chart label agree at a half-tenth tie", () => {
    const sides = heroSides(hero({ homeProb: 0.3675, awayProb: 0.6325, tenths: true }));
    expect(sides).toEqual(["36.8%", "63.2%"]);
    // The dot sits on the away side below 50: its label is the away digit.
    expect(callout(chart(36.75, "live", true))).toBe(sides[1]);
    expect(callout(chart(36.75, "live", false))).toBe("63%");

    expect(heroSides(hero({ homeProb: 0.5125, awayProb: 0.4875, tenths: true }))).toEqual([
      "51.3%",
      "48.7%",
    ]);
    expect(callout(chart(51.25, "live", true))).toBe("51.3%");
  });

  it("a band pair is byte-identical to OFF, and so is its chart label", () => {
    const on = hero({ homeProb: 0.996, awayProb: 0.004, homePct: 100, awayPct: 0, tenths: true });
    const off = hero({ homeProb: 0.996, awayProb: 0.004, homePct: 100, awayPct: 0 });
    expect(heroSides(on)).toEqual([">99%", "<1%"]);
    expect(on).toBe(off);
    const withheld = { homeProb: 0.004, awayProb: 0.996, homePct: 0, awayPct: 100, awayWithheld: true };
    expect(hero({ ...withheld, tenths: true })).toBe(hero(withheld));
    expect(callout(chart(99.7, "live", true))).toBe(callout(chart(99.7, "live", false)));
  });

  it("a venue-settled hero is byte-identical to OFF", () => {
    const settled = { homeProb: 0.6234, awayProb: 0.3766, homePct: 62, awayPct: 38, venueSettled: true };
    expect(hero({ ...settled, tenths: true })).toBe(hero(settled));
  });

  it("a completed chart is byte-identical to OFF", () => {
    expect(normalise(chart(36.75, "completed", true))).toBe(normalise(chart(36.75, "completed", false)));
  });

  it("a two-sided pair takes the fit size; one named number keeps 48px", () => {
    const two = hero({ tenths: true });
    expect(two).toContain("min-[390px]:text-[35px]");
    expect(two).not.toContain("min-[390px]:text-[48px]");
    const one = hero({ homeProb: 0.4175, awayProb: 0.5825, awayWithheld: true, tenths: true });
    expect(heroSides(one)).toEqual(["41.8%"]);
    expect(one).toContain("min-[390px]:text-[48px]");
  });

  it("a side today prints as no reading stays no reading", () => {
    const off = hero({ homePct: null });
    const on = hero({ homePct: null, tenths: true });
    expect(on).not.toContain("62.3");
    expect(heroSides(on).length).toBe(heroSides(off).length);
  });

  it("a decimal reserves two numeral widths, so 9.8 → 10.2 does not shift the pair", () => {
    const html = hero({ homeProb: 0.098, awayProb: 0.902, tenths: true });
    expect(heroSides(html)).toEqual(["9.8%", "90.2%"]);
    expect(html.match(/min-width:2ch/g)).toHaveLength(2);
  });
});
