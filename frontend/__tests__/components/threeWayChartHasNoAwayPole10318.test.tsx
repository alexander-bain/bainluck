// #10318 — a three-way game's chart is not framed two-way.
//
// Specimen: `/events/15321333`, Parma Calcio v Ternana (Kalshi PAR/TER/TIE),
// shopper at 390px, 2026-10-03. The chart drew Parma's win chance on an axis
// whose bottom read "↓ TERNANA", with the screen-reader sentence "the bottom of
// this axis is Ternana at 100%", and offered "Odds flipped (7)". Pre-match
// Parma were 48.5% to Ternana's 24.5% (draw 26.5%): the line sat in "Ternana's
// half" all day while Parma were twice Ternana's price, and every 50% crossing
// was counted as a flip when the favourite never changed.
//
// On a market that prices a draw, the bottom of a home line is "the home side
// does not win" (a draw OR the away side). So with `awayWithheld` (the page's
// one switch, #6238) the gutter keeps the home pole alone and the chart counts
// no flips. Two-sided markets are unchanged: the control arm renders the same
// rows without the switch and must still print both poles and the count.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

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

/** Fixed anchor — never Date.now() (gotcha #44). */
const FIRST_POINT = Date.UTC(2026, 9, 2, 10, 0, 0);

/** Three served legs per row, as `/history` serves Kalshi for this game. The
 *  home line crosses 50 four times; none sits ON 50. */
const THREE_WAY = [
  [0.55, 0.25, 0.2],
  [0.45, 0.27, 0.28],
  [0.55, 0.25, 0.2],
  [0.45, 0.27, 0.28],
  [0.55, 0.25, 0.2],
].map(([home, draw, away], i) => ({
  timestamp: new Date(FIRST_POINT + i * 3_600_000).toISOString(),
  home_probability: home,
  draw_probability: draw,
  away_probability: away,
}));

function render(awayWithheld: boolean) {
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      winProbHistory={{ kalshi: THREE_WAY }}
      winProbSources={{
        kalshi: { display_name: "Kalshi", color: "#22c55e", type: "market", snapshot_count: 5 },
      }}
      homeTeam="Parma Calcio"
      awayTeam="Ternana"
      sportKey="soccer_italy_serie_a"
      commenceTime="2026-10-03T10:30:00+00:00"
      isLive={false}
      eventStatus="scheduled"
      externalTimeRange="all"
      awayWithheld={awayWithheld}
    />,
  );
}

const poles = (html: string) => html.match(/data-pole="(home|away)"/g) ?? [];

describe("#10318 — a draw-priced game's chart has no away pole and counts no flips", () => {
  const html = render(true);

  it("draws the chart (so every absence below is about a rendered chart)", () => {
    expect(html).toContain("recharts-line-curve");
  });

  it("keeps the home pole alone: the line is the home side's chance", () => {
    expect(poles(html)).toEqual(['data-pole="home"']);
    expect(html).not.toMatch(/bottom of this axis is Ternana/);
    expect(html).not.toContain("↓");
  });

  it("offers no 'Odds flipped': a home 50% crossing is not the favourite changing", () => {
    expect(html).not.toContain("Odds flipped");
  });
});

describe("#10318 CONTROL — the same rows on a two-sided market are unchanged", () => {
  const html = render(false);

  it("still prints both poles, the away sentence and the count", () => {
    expect(html).toContain("recharts-line-curve");
    expect(poles(html)).toEqual(['data-pole="home"', 'data-pole="away"']);
    expect(html).toMatch(/bottom of this axis is Ternana at 100%/);
    expect(html).toContain("Odds flipped (4)");
  });
});
