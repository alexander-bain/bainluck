/**
 * Regression guards for #12750 (Rulings 201 & 202-A) and Ruling 211-A:
 *   - Two-team games fit from the very first reading (min span 20 pts).
 *   - Soccer (draw-priced 3-way) stays 0 to 100 and draws all three lines:
 *     Home (home club colour), Draw (#94A3B8 — lighter grey from headline),
 *     and Away (away club colour, disambiguated via Ruling 197).
 *   - Golf, futures, TeamSeasonJourney, SettledPathChart, and /politics scale
 *     0 to the stepped top value shown.
 */

import { readFileSync } from "fs";
import { join } from "path";
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

import EventCard183A, { extractDiscoverChartPointsFromHistory } from "@/components/EventCard183A";
import { FuturesChart } from "@/components/FuturesChart";
import OddsChart from "@/components/OddsChart";
import {
  extractThreeWaySample,
  gameChartYAxis,
  manyWayChartCeiling,
  manyWayChartYTicks,
  normalizeSoccerThreeWayPercents,
  SOCCER_DRAW_LINE_HEX,
} from "@/lib/chartScaleRule201";
import { HEADLINE_STYLE_199 } from "@/lib/headlineModel199";

const T0 = Date.UTC(2026, 10, 16, 14, 0, 0);
const isoAt = (minOffset: number) => new Date(T0 + minOffset * 60_000).toISOString();

describe("Website probability chart scale & soccer 3-line rules (#12750, Rulings 201, 202-A, 211-A)", () => {
  it("uses the exact lighter grey from the unified game headline (#94A3B8) for Draw", () => {
    expect(SOCCER_DRAW_LINE_HEX).toBe(HEADLINE_STYLE_199.drawTextInk);
    expect(SOCCER_DRAW_LINE_HEX.toLowerCase()).toBe("#94a3b8");
  });

  it("fits two-team games from the first reading (min span 20) while keeping 3-way soccer on [0, 100]", () => {
    const earlyNfl = gameChartYAxis([58, 61, 63], [63], { threeWay: false });
    expect(earlyNfl.domain[0]).toBeGreaterThanOrEqual(40);
    expect(earlyNfl.domain[1]).toBeLessThanOrEqual(80);
    expect(earlyNfl.domain[1] - earlyNfl.domain[0]).toBeGreaterThanOrEqual(20);

    const soccerAxis = gameChartYAxis([67.6, 68.4, 69.1, 69.5], [69.5], { threeWay: true });
    expect(soccerAxis.domain).toEqual([0, 100]);
    expect(soccerAxis.ticks).toEqual([0, 25, 50, 75, 100]);
  });

  it("extracts genuine 3-way soccer probabilities from both explicit draw_probability and 3-way sportsbooks, rejecting 2-way complements", () => {
    // Kalshi / Polymarket explicit 3-way
    expect(
      extractThreeWaySample(
        { home_probability: 0.695, draw_probability: 0.175, away_probability: 0.125 },
        "soccer_epl",
      ),
    ).toEqual({ home: 0.695, draw: 0.175, away: 0.125 });

    // Sportsbook 3-way board (home + away < 0.99 -> draw = 1 - home - away)
    const sb = extractThreeWaySample(
      { home_probability: 0.6764, away_probability: 0.1365 },
      "soccer_epl",
    );
    expect(sb).not.toBeNull();
    expect(sb!.home).toBeCloseTo(0.6764, 4);
    expect(sb!.away).toBeCloseTo(0.1365, 4);
    expect(sb!.draw).toBeCloseTo(0.1871, 4);

    // 2-way complement (`home + away === 1.0` with no draw_probability) is rejected
    expect(
      extractThreeWaySample({ home_probability: 0.68, away_probability: 0.32 }, "soccer_epl"),
    ).toBeNull();

    // Non-draw sport is rejected
    expect(
      extractThreeWaySample({ home_probability: 0.68, away_probability: 0.32 }, "americanfootball_nfl"),
    ).toBeNull();
  });

  it("draws all three lines (Home, Draw in #94A3B8, Away with Ruling 197 colour disambiguation) on a 0-to-100 soccer OddsChart", () => {
    // Chelsea (#034694 blue, secondary #DBA111 gold) @ Everton (#003399 blue):
    // Ruling 197 switches Chelsea away from blue so Home and Away lines never share one colour.
    const kalshiPoints = [
      { timestamp: isoAt(0), home_probability: 0.44, draw_probability: 0.28, away_probability: 0.28 },
      { timestamp: isoAt(15), home_probability: 0.49, draw_probability: 0.27, away_probability: 0.24 },
      { timestamp: isoAt(30), home_probability: 0.54, draw_probability: 0.25, away_probability: 0.21 },
    ];
    const html = renderToStaticMarkup(
      <OddsChart
        history={[
          {
            timestamp: isoAt(0),
            home_probability: 0.43,
            away_probability: 0.29,
            over_under: null,
            projected_home_score: null,
            projected_away_score: null,
            bookmaker: "consensus",
          },
          {
            timestamp: isoAt(30),
            home_probability: 0.53,
            away_probability: 0.22,
            over_under: null,
            projected_home_score: null,
            projected_away_score: null,
            bookmaker: "consensus",
          },
        ]}
        winProbHistory={{ kalshi: kalshiPoints }}
        winProbSources={{
          kalshi: { display_name: "Kalshi", color: "#22c55e", type: "market", snapshot_count: 3 },
        }}
        aggregateLine={[
          { timestamp: isoAt(0), home_probability: 0.432 },
          { timestamp: isoAt(15), home_probability: 0.47 },
          { timestamp: isoAt(30), home_probability: 0.532 },
        ]}
        backendBlendServed
        homeTeam="Everton"
        awayTeam="Chelsea"
        homeTeamColor="#003399"
        awayTeamColor="#034694"
        awayTeamSecondaryColor="#C8102E"
        sportKey="soccer_epl"
        commenceTime={isoAt(0)}
        isLive
        eventStatus="live"
        externalTimeRange="all"
        awayWithheld
      />,
    );

    // 1. Scale stays 0 to 100 (ticks 0%, 25%, 50%, 75%, 100%)
    for (const v of [0, 25, 50, 75, 100]) {
      expect(html).toContain(`data-axis-value="${v}"`);
    }

    // 2. Three solid curves drawn: Home (#003399), Draw (#94A3B8), Away (#C8102E via Ruling 197)
    const curves = html.match(/class="recharts-curve recharts-line-curve"/g) ?? [];
    expect(curves).toHaveLength(3);
    expect(html.toLowerCase()).toContain('stroke="#003399"');
    expect(html.toLowerCase()).toContain('stroke="#94a3b8"');
    expect(html.toLowerCase()).toContain('stroke="#c8102e"');

    // 3. Three-line legend labels Home, Draw, and Away
    expect(html).toContain('data-testid="soccer-three-line-legend"');
    expect(html).toContain(">Everton<");
    expect(html).toContain(">Draw<");
    expect(html).toContain(">Chelsea<");
  });

  it("scales TeamSeasonJourney and many-way charts from 0 to stepped ceiling (Ruling 202-A)", () => {
    expect(manyWayChartCeiling(0.11)).toBe(0.15);
    expect(manyWayChartYTicks(0.15)).toEqual([0, 5, 10, 15]);
    expect(manyWayChartCeiling(0.58)).toBe(0.75);
    expect(manyWayChartYTicks(0.75)).toEqual([0, 25, 50, 75]);

    const journeyHtml = renderToStaticMarkup(
      <FuturesChart
        historyData={[
          {
            outcome_id: 1,
            name: "Detroit Lions",
            history: [
              { timestamp: isoAt(-1440), probability: 0.09, american_odds: 1000, bookmaker: "kalshi" },
              { timestamp: isoAt(-720), probability: 0.1, american_odds: 900, bookmaker: "kalshi" },
              { timestamp: isoAt(0), probability: 0.11, american_odds: 800, bookmaker: "kalshi" },
            ],
          },
        ]}
        selectedOutcomes={new Set([1])}
        fixedYAxis
        fieldCeiling
        allowZoom
        showLegend={false}
        height={220}
      />,
    );

    // 11% Super Bowl contender scales 0..15% (`>15%<` top tick, NOT `>100%<`!)
    expect(journeyHtml).toContain(">15%<");
    expect(journeyHtml).not.toContain(">100%<");

    // Verify TeamSeasonJourney and SettledPathChart both pass fieldCeiling
    const teamJourneySrc = readFileSync(
      join(__dirname, "..", "..", "components", "TeamSeasonJourney.tsx"),
      "utf8",
    );
    const settledPathSrc = readFileSync(
      join(__dirname, "..", "..", "components", "event", "SettledPathChart.tsx"),
      "utf8",
    );
    expect(teamJourneySrc).toMatch(/<FuturesChart[\s\S]*?fieldCeiling/);
    expect(settledPathSrc).toMatch(/<FuturesChart[\s\S]*?fieldCeiling/);
  });

  it("draws all three lines (Home, Draw in #94A3B8, Away) on Discover live/settled soccer cards (EventCard183A)", () => {
    const pts = extractDiscoverChartPointsFromHistory(
      {
        win_prob_history: {
          kalshi: [
            { timestamp: isoAt(0), home_probability: 0.49, draw_probability: 0.27, away_probability: 0.24 },
            { timestamp: isoAt(30), home_probability: 0.56, draw_probability: 0.25, away_probability: 0.19 },
            { timestamp: isoAt(60), home_probability: 0.64, draw_probability: 0.22, away_probability: 0.14 },
          ],
        },
      } as never,
      "soccer_epl",
    );
    expect(pts).toHaveLength(3);
    expect(pts?.[0]).toEqual({ t: 0, p: 0.49, draw: 0.27, away: 0.24 });

    const cardHtml = renderToStaticMarkup(
      <EventCard183A
        card={{
          id: 777,
          sport: "soccer_epl",
          sport_name: "Premier League",
          status: "live",
          home_team: "Arsenal",
          away_team: "Chelsea",
          commence_time: isoAt(0),
          home_score: 1,
          away_score: 0,
          home_color: "#EF0107",
          away_color: "#034694",
          home_prob: 0.64,
          draw_prob: 0.22,
          away_prob: 0.14,
          pregame_home_pct: 49,
          pregame_draw_pct: 27,
          pregame_away_pct: 24,
          projected_home: 1.9,
          projected_away: 0.6,
          live_clock_label: "62'",
          chart_points: pts,
        }}
        surface="discover"
      />,
    );

    expect(cardHtml).toContain('data-chart-domain="0-100"');
    expect(cardHtml).toContain('data-testid="discover-soccer-line-home"');
    expect(cardHtml).toContain('data-testid="discover-soccer-line-draw"');
    expect(cardHtml).toContain('data-testid="discover-soccer-line-away"');
    expect(cardHtml.toLowerCase()).toContain('stroke="#ef0107"');
    expect(cardHtml.toLowerCase()).toContain('stroke="#94a3b8"');
    expect(cardHtml.toLowerCase()).toContain('stroke="#034694"');
  });

  it("keeps Discover soccer Home anchored to blended aggregate_line even when a 3-way source disagrees", () => {
    // 1. Coherent disagreement (blend 0.52 vs kalshi 0.48): Home stays 0.52, Draw+Away partition 0.48
    const coherent = extractDiscoverChartPointsFromHistory(
      {
        aggregate_line: [
          { timestamp: isoAt(0), home_probability: 0.52 },
          { timestamp: isoAt(30), home_probability: 0.55 },
          { timestamp: isoAt(60), home_probability: 0.6 },
        ],
        win_prob_history: {
          kalshi: [
            { timestamp: isoAt(0), home_probability: 0.48, draw_probability: 0.26, away_probability: 0.26 },
            { timestamp: isoAt(30), home_probability: 0.51, draw_probability: 0.245, away_probability: 0.245 },
            { timestamp: isoAt(60), home_probability: 0.56, draw_probability: 0.22, away_probability: 0.22 },
          ],
        },
      } as never,
      "soccer_epl",
    );
    expect(coherent).toHaveLength(3);
    expect(coherent![0].p).toBeCloseTo(0.52, 5);
    expect(coherent![0].draw! + coherent![0].away! + coherent![0].p).toBeCloseTo(1.0, 5);
    expect(coherent![2].p).toBeCloseTo(0.6, 5);

    // 2. Large source divergence (blend 0.65 vs stale source 0.35): Home STILL equals blend 0.65,
    // and incoherent 3-way lines are withheld rather than overriding the blend.
    const divergent = extractDiscoverChartPointsFromHistory(
      {
        aggregate_line: [
          { timestamp: isoAt(0), home_probability: 0.65 },
          { timestamp: isoAt(30), home_probability: 0.68 },
          { timestamp: isoAt(60), home_probability: 0.7 },
        ],
        win_prob_history: {
          kalshi: [
            { timestamp: isoAt(0), home_probability: 0.35, draw_probability: 0.33, away_probability: 0.32 },
            { timestamp: isoAt(30), home_probability: 0.36, draw_probability: 0.32, away_probability: 0.32 },
            { timestamp: isoAt(60), home_probability: 0.37, draw_probability: 0.31, away_probability: 0.32 },
          ],
        },
      } as never,
      "soccer_epl",
    );
    expect(divergent).toHaveLength(3);
    expect(divergent![0].p).toBeCloseTo(0.65, 5);
    expect(divergent![2].p).toBeCloseTo(0.7, 5);
    expect(divergent![0].draw).toBeUndefined();
    expect(divergent![0].away).toBeUndefined();
  });

  it("normalizes soccer 3-way triples to 100 in both directions (< 99 and > 100.5 with showBlendLine=false) and keeps 2-way soccer fallback on 0–100", () => {
    // Sum below 99 in blend mode (40 + 20 + 25 = 85 -> preserves 40, scales 20+25 to 60)
    const under99 = normalizeSoccerThreeWayPercents(40, 20, 25, { preserveHome: true });
    expect(under99).not.toBeNull();
    expect(under99!.home).toBeCloseTo(40, 5);
    expect(under99!.home + under99!.draw + under99!.away).toBeCloseTo(100, 5);

    // Sum above 100.5 with showBlendLine=false (52 + 31 + 25 = 108 -> proportional 100)
    const over100NoBlend = normalizeSoccerThreeWayPercents(52, 31, 25, { preserveHome: false });
    expect(over100NoBlend).not.toBeNull();
    expect(over100NoBlend!.home + over100NoBlend!.draw + over100NoBlend!.away).toBeCloseTo(100, 5);
    expect(over100NoBlend!.home).toBeCloseTo((52 / 108) * 100, 5);

    // OddsChart with showBlendLine=false and sum > 100.5 renders 3 normalized curves on 0–100
    const noBlendHtml = renderToStaticMarkup(
      <OddsChart
        history={[]}
        winProbHistory={{
          kalshi: [
            { timestamp: isoAt(0), home_probability: 0.52, draw_probability: 0.31, away_probability: 0.25 },
            { timestamp: isoAt(15), home_probability: 0.54, draw_probability: 0.3, away_probability: 0.24 },
          ],
        }}
        winProbSources={{
          kalshi: { display_name: "Kalshi", color: "#22c55e", type: "market", snapshot_count: 2 },
        }}
        homeTeam="Everton"
        awayTeam="Fulham"
        homeTeamColor="#003399"
        awayTeamColor="#FFFFFF"
        awayTeamSecondaryColor="#CC0000"
        sportKey="soccer_epl"
        commenceTime={isoAt(0)}
        isLive
        eventStatus="live"
        externalTimeRange="all"
        awayWithheld
      />,
    );
    expect(noBlendHtml.match(/class="recharts-curve recharts-line-curve"/g) ?? []).toHaveLength(3);
    expect(noBlendHtml.toLowerCase()).toContain('stroke="#cc0000"');

    // 2-way complement soccer fallback stays cleanly on 0–100 without fabricating Draw/Away lines
    const twoWayFallbackHtml = renderToStaticMarkup(
      <OddsChart
        history={[
          {
            timestamp: isoAt(0),
            home_probability: 0.6,
            away_probability: 0.4,
            over_under: null,
            projected_home_score: null,
            projected_away_score: null,
            bookmaker: "consensus",
          },
          {
            timestamp: isoAt(15),
            home_probability: 0.62,
            away_probability: 0.38,
            over_under: null,
            projected_home_score: null,
            projected_away_score: null,
            bookmaker: "consensus",
          },
        ]}
        homeTeam="Everton"
        awayTeam="Chelsea"
        homeTeamColor="#003399"
        awayTeamColor="#034694"
        sportKey="soccer_epl"
        commenceTime={isoAt(0)}
        isLive
        eventStatus="live"
        externalTimeRange="all"
        awayWithheld
      />,
    );
    for (const v of [0, 25, 50, 75, 100]) {
      expect(twoWayFallbackHtml).toContain(`data-axis-value="${v}"`);
    }
    expect(twoWayFallbackHtml).not.toContain('data-testid="soccer-three-line-legend"');
  });
});
