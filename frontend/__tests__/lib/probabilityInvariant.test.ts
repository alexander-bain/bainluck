// Cross-surface probability invariant (#1003 durable guard).
//
// The standing ruling: "the hero and the chart must show the SAME number" (the
// blend is the product). #1003 was a scale slip (0–1 fraction vs 0–100 axis) at
// the chart boundary that made the live tooltip show ~81% while the headline
// fallback showed ~1%. This suite locks the whole class down at the unit level —
// no live game required — by driving every EVENT-DETAIL surface through the same
// functions the page uses and asserting they reduce to ONE displayed integer %:
//
//   hero (resolveProbability)  ==  at-rest readout (computeLastChartPoint)
//     ==  chart plot/tooltip (homeProbToChartAxis)  ==  scrub-out round-trip
//     (chartAxisToHomeProb) .
//
// A regression — an added/removed *100 or /100, or an orientation flip — fails a
// test here instead of only surfacing as a live visual mismatch.

import {
  chartAxisToHomeProb,
  computeLastChartPoint,
  homeProbToChartAxis,
  latestBlendPoint,
  resolveProbability,
} from "../../lib/eventKeyStats";
import type {
  EventHistoryResponse,
  EventDetailResponse,
} from "../../lib/types";

function hist(partial: Partial<EventHistoryResponse>): EventHistoryResponse {
  return { event_id: 1, history: [], ...partial } as unknown as EventHistoryResponse;
}

function evt(partial: Partial<EventDetailResponse>): EventDetailResponse {
  return {
    id: 1,
    home_team: "Home",
    away_team: "Away",
    status: "live",
    commence_time: "2026-07-23T00:00:00Z",
    ...partial,
  } as unknown as EventDetailResponse;
}

const pct = (frac: number | null): number | null =>
  frac === null ? null : Math.round(frac * 100);

/**
 * The integer home-% each event-detail surface would DISPLAY for one payload,
 * computed through the real functions + the real chart-axis conversion. The page
 * wires computeLastChartPoint(...) into resolveProbability(...) as the fallback
 * chart point, so we mirror that exactly.
 */
function surfaces(
  event: EventDetailResponse,
  historyData: EventHistoryResponse,
  isLive: boolean,
  isFinished: boolean,
) {
  const lastChartPoint = computeLastChartPoint(historyData, null, null);
  const hero = resolveProbability(event, historyData, lastChartPoint, isLive, isFinished);

  // The chart's last plotted home value (0–100 axis): the blend when present,
  // else the same at-rest home the readout resolves to (chart's homeDelta path).
  const blend = latestBlendPoint(historyData.aggregate_line);
  const chartHomeFrac = blend ?? lastChartPoint?.homeProb ?? null;
  const chartAxis = chartHomeFrac === null ? null : homeProbToChartAxis(chartHomeFrac);
  // Tooltip renders the axis value directly; scrub hands it back /100.
  const tooltipHome = chartAxis; // already 0–100
  const scrubHomeFrac = chartAxis === null ? null : chartAxisToHomeProb(chartAxis);

  return {
    hero: pct(hero.homeProb),
    atRest: pct(lastChartPoint?.homeProb ?? null),
    chartPlot: chartAxis === null ? null : Math.round(chartAxis),
    tooltip: tooltipHome === null ? null : Math.round(tooltipHome),
    scrub: pct(scrubHomeFrac),
    heroAway: pct(hero.awayProb),
  };
}

describe("chart-axis conversion is an exact round-trip (the #1003 boundary)", () => {
  test.each([0, 0.0081, 0.01, 0.2, 0.5, 0.62, 0.81, 0.99, 1])(
    "chartAxisToHomeProb(homeProbToChartAxis(%p)) === input",
    (p) => {
      expect(chartAxisToHomeProb(homeProbToChartAxis(p))).toBeCloseTo(p, 10);
    },
  );

  test("a 0–1 fraction becomes a 0–100 axis value, not left as a fraction", () => {
    expect(homeProbToChartAxis(0.81)).toBeCloseTo(81); // NOT 0.81
    expect(chartAxisToHomeProb(81)).toBeCloseTo(0.81); // NOT 0.0081
  });
});

describe("cross-surface invariant: hero == readout == chart == tooltip == scrub", () => {
  test("live with blend — every surface shows the blend %", () => {
    const s = surfaces(
      evt({
        status: "live",
        // A lagging sportsbook consensus that must NOT win over the blend.
        current_odds: { home_probability: 0.57, away_probability: 0.43, bookmaker_count: 9 } as never,
      }),
      hist({
        aggregate_line: [
          { timestamp: "2026-07-23T00:10:00Z", home_probability: 0.24 },
          { timestamp: "2026-07-23T00:17:00Z", home_probability: 0.2 },
        ],
      }),
      true,
      false,
    );
    expect(new Set([s.hero, s.atRest, s.chartPlot, s.tooltip, s.scrub])).toEqual(
      new Set([20]),
    );
  });

  test("#1003 case — no blend, no win_prob_history: history FRACTION shows as 81, never 1", () => {
    // The exact reported bug: cricket/soccer live, win_prob_history empty. The
    // headline fallback used to divide the 0–1 history by 100 (→ ~1%) while the
    // chart multiplied it by 100 (→ 81%). Now every surface agrees on 81.
    const s = surfaces(
      evt({ status: "live", current_odds: undefined as never }),
      hist({
        win_prob_history: {},
        history: [
          { timestamp: "2026-07-09T10:00:00Z", home_probability: 0.54 },
          { timestamp: "2026-07-09T16:00:00Z", home_probability: 0.81 },
        ] as never,
      }),
      true,
      false,
    );
    expect(s.hero).toBe(81);
    expect(new Set([s.hero, s.atRest, s.chartPlot, s.tooltip, s.scrub])).toEqual(
      new Set([81]),
    );
    expect(s.hero).not.toBe(1); // the #1003 regression value
  });

  test("orientation holds — an asymmetric blend can't silently 1-x flip", () => {
    const s = surfaces(
      evt({ status: "live" }),
      hist({
        aggregate_line: [{ timestamp: "2026-07-23T02:00:00Z", home_probability: 0.01 }],
        // An oppositely-oriented single source must NOT override the blend.
        win_prob_history: {
          espn: [{ timestamp: "2026-07-23T03:00:00Z", home_probability: 0.99 }],
        } as never,
      }),
      true,
      false,
    );
    expect(new Set([s.hero, s.atRest, s.chartPlot, s.tooltip, s.scrub])).toEqual(
      new Set([1]),
    );
    expect(s.heroAway).toBe(99); // away = 1 - home, consistently
  });

  test("finished — hero shows pregame opening; readout/chart agree on the frozen blend", () => {
    // Different surfaces legitimately answer different questions when finished
    // (hero = pregame expectation), so we assert each surface is internally
    // scale-correct rather than mutually equal here.
    const s = surfaces(
      evt({
        status: "completed",
        opening_odds: { home_probability: 0.35, away_probability: 0.65 } as never,
      }),
      hist({ aggregate_line: [{ timestamp: "t", home_probability: 0.98 }] }),
      false,
      true,
    );
    expect(s.hero).toBe(35); // pregame opening, scale-correct (not 0 or 3500)
    // The chart/readout still round-trip the frozen blend cleanly.
    expect(s.chartPlot).toBe(s.tooltip);
    expect(s.chartPlot).toBe(s.scrub);
    expect(s.scrub).toBe(98);
  });
});
