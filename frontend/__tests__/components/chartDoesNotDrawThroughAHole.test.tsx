/**
 * #3659 — THE WIRING: the chart that ships stops drawing through its holes.
 *
 * `chartSeriesPath.test.ts` proves the geometry. This proves that
 * `FuturesChart` — the kernel behind `/futures/[id]`, `/categories/golf`,
 * `/sport/[sport]/[league]`, `TeamSeasonJourney`, `WinnerEvolutionChart`,
 * `SettledPathChart` and `RaceToTitleChart` — actually calls it, and that the
 * six of those seven which plot healthy series see nothing change.
 *
 * The lesson #2961 wrote into this pair still holds: a green rule says nothing
 * about a render. UX-P145 and UX-P146 both swept copy that was never on
 * production.
 *
 * ═══ THE FIXTURE ═══
 *
 * `/api/futures/16630403/history` ("Hantavirus pandemic in 2026?"), outcome
 * "Yes", re-read from production 2026-09-06 ~23:0xZ: median gap 1.00h, one
 * interior hole of 345.6h, then a day of hourly readings. The rendered window
 * puts ~93% of the chart's horizontal space inside that hole.
 *
 * ═══ WHAT IS ASSERTED, AND WHY IT IS NOT THE CONSTANTS ═══
 *
 * The reader's property, twice over:
 *
 *   • the SOLID stroke — the thing a reader reads as data — never spans the
 *     hole. Read out of the rendered `d` attributes by coordinate, so a
 *     restyle that changed the dash pattern or the opacity cannot make it pass;
 *   • a series with no hole draws ONE path per outcome and nothing faint at
 *     all, so the dotted treatment can never leak onto a healthy chart.
 *
 * Every case is a pair, for the reason #2961 gave: a chart that always breaks
 * its line has moved the problem, not fixed it.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesOutcomeHistory } from "../../lib/types";

const HOUR = 60 * 60 * 1000;
const NOW = Date.UTC(2026, 8, 6, 19, 15, 0);
const START = Date.UTC(2026, 7, 22, 15, 15, 0); // fixed anchor — never Date.now()

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => {
  jest.useRealTimers();
});

function pointsAt(hours: readonly number[], prob = 0.03): FuturesOutcomeHistory["history"] {
  return hours.map((h) => ({
    timestamp: new Date(START + h * HOUR).toISOString(),
    probability: prob,
    american_odds: null,
    bookmaker: "blend",
  }));
}

/** The production shape: one point, a 345.6h hole, then 19 hourly readings. */
const HOLED: FuturesOutcomeHistory[] = [
  {
    outcome_id: 1,
    name: "Yes",
    history: pointsAt([0, 345.6, ...Array.from({ length: 18 }, (_, i) => 346.6 + i)]),
  },
];

/** The same span, observed the whole way through. */
const HEALTHY: FuturesOutcomeHistory[] = [
  {
    outcome_id: 1,
    name: "Yes",
    history: pointsAt(Array.from({ length: 40 }, (_, i) => i * 9)),
  },
];

interface DrawnPath {
  d: string;
  dash: string | null;
  opacity: number;
}

/** Every stroked series path the chart emitted, with how it stroked it. */
function seriesPaths(html: string): DrawnPath[] {
  const tags = html.match(/<path[^>]*\bd="M [^"]*"[^>]*>/g) ?? [];
  return tags.map((tag) => ({
    d: /\bd="([^"]*)"/.exec(tag)![1],
    dash: /stroke-dasharray="([^"]*)"/.exec(tag)?.[1] ?? null,
    // React omits the attribute at full opacity.
    opacity: Number(/stroke-opacity="([^"]*)"/.exec(tag)?.[1] ?? "1"),
  }));
}

/** The x coordinates a path visits, in order. */
function xs(d: string): number[] {
  return [...d.matchAll(/[MLH] (-?[\d.]+)/g)].map((m) => Number(m[1]));
}

/** The widest jump between consecutive x's on a single path. */
function widestStride(d: string): number {
  const seq = xs(d);
  let widest = 0;
  for (let i = 1; i < seq.length; i += 1) {
    widest = Math.max(widest, Math.abs(seq[i] - seq[i - 1]));
  }
  return widest;
}

describe("#3659 FuturesChart — the solid line does not cross the hole", () => {
  test("the holed series is drawn as more than one stroke", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);
    expect(seriesPaths(html).length).toBeGreaterThan(1);
  });

  test("no fully-opaque stroke spans the hole", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);
    const drawn = seriesPaths(html);

    // Something has to cross it — the plot is ~93% hole and a void would read
    // as a rendering failure — so the test is not "nothing crosses". It is that
    // whatever crosses is not wearing the clothes of data.
    const crossing = drawn.filter((p) => widestStride(p.d) > 100);
    expect(crossing.length).toBeGreaterThan(0);
    for (const p of crossing) {
      expect(p.opacity).toBeLessThan(0.5);
      expect(p.dash).not.toBeNull();
    }

    const solid = drawn.filter((p) => p.opacity === 1);
    expect(solid.length).toBeGreaterThan(0);
    for (const p of solid) expect(widestStride(p.d)).toBeLessThan(100);
  });

  test("the observation stranded on the far side of the hole is still painted", () => {
    // A bare `M` paints nothing. The Aug 22 reading is alone on its side of the
    // hole and is visible on production today; a break must not delete it.
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);
    const solid = seriesPaths(html).filter((p) => p.opacity === 1);
    const leftmost = Math.min(...solid.flatMap((p) => xs(p.d)));

    // 50 is the chart's left padding — the x the oldest point scales to.
    expect(leftmost).toBeCloseTo(50, 5);
    expect(solid.some((p) => /^M 50 [\d.]+ L 50 [\d.]+$/.test(p.d))).toBe(true);
  });

  test("when the caption names the hole, it names the one the line broke on", () => {
    // One threshold drives both, so they can never describe different
    // intervals — which is why #3659 took the number from
    // `seriesGapThresholdMs` instead of re-deriving one.
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);

    expect(html).toContain('data-series-state="gapped"');
    expect(html).toContain("No numbers for 14 days in this stretch");
    expect(seriesPaths(html).filter((p) => p.dash === "1 5")).toHaveLength(1);
  });

  test("when the caption is talking about something ELSE, the line still breaks", () => {
    // THE PRODUCTION CASE, and the strongest argument for this ship.
    //
    // Run through the real cached payload the page rendered on 2026-09-06, the
    // 16630403 series comes out `stale`, not `gapped` — n=358, median 1.00h,
    // age 6.37h, largest hole 345.6h — because `seriesFreshness` ranks being
    // behind NOW above being holed, deliberately: the right-hand end of the
    // line is where a reader looks first.
    //
    // So the caption on that chart reads "Last number 6 hours ago" and says
    // NOTHING about the fourteen days. #2961's declaration does not cover this
    // case at all. The broken line is the only thing on the page that does.
    const staleAndHoled: FuturesOutcomeHistory[] = [
      {
        outcome_id: 1,
        name: "Yes",
        history: pointsAt([0, 345.6, ...Array.from({ length: 18 }, (_, i) => 346.6 + i)]),
      },
    ];
    // The newest point is ~24 min before NOW. Move the CLOCK forward 6h rather
    // than the points back, so the cadence is untouched and the only thing that
    // changes is how far behind the series has fallen — which is the one
    // variable that flips `gapped` to `stale`.
    jest.setSystemTime(NOW + 6 * HOUR);
    const html = renderToStaticMarkup(<FuturesChart historyData={staleAndHoled} showAxes />);
    jest.setSystemTime(NOW);

    expect(html).toContain('data-series-state="stale"');
    expect(html).not.toContain("No numbers for");
    // The caption has gone quiet about the hole. The line has not.
    expect(seriesPaths(html).filter((p) => p.dash === "1 5")).toHaveLength(1);
  });

  test("the bridge covers the hole the caption measured, not some other gap", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);
    const bridge = seriesPaths(html).find((p) => p.dash === "1 5")!;
    const span = widestStride(bridge.d);

    // 345.6h of a 363.6h domain across 730px of plot: the bridge is ~95% of the
    // drawable width, because the hole very nearly IS this chart.
    expect(span / 730).toBeGreaterThan(0.9);
  });
});

describe("#3659 FuturesChart — a healthy series does not move", () => {
  test("one path per outcome, and nothing faint on it", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={HEALTHY} showAxes />);
    const drawn = seriesPaths(html);

    expect(drawn).toHaveLength(1);
    expect(drawn[0].opacity).toBe(1);
    expect(drawn[0].dash).toBeNull();
  });

  test("the dotted bridge treatment never appears on a healthy chart", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={HEALTHY} showAxes />);
    expect(html).not.toContain('stroke-dasharray="1 5"');
  });

  test("step interpolation is a single stroke too", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={HEALTHY} showAxes stepInterpolation fixedYAxis />,
    );
    expect(seriesPaths(html)).toHaveLength(1);
  });

  test("a multi-outcome healthy chart draws exactly one line each", () => {
    // The season-journey / race-to-title shape. This is the arm that would fail
    // loudest if the threshold were ever taken from the union of the outcomes
    // instead of from each outcome's own cadence.
    const many: FuturesOutcomeHistory[] = [
      { outcome_id: 1, name: "A", history: pointsAt([0, 9, 18, 27, 36, 45], 0.4) },
      { outcome_id: 2, name: "B", history: pointsAt([2, 11, 20, 29, 38, 47], 0.3) },
      { outcome_id: 3, name: "C", history: pointsAt([4, 13, 22, 31, 40, 49], 0.2) },
    ];
    const html = renderToStaticMarkup(<FuturesChart historyData={many} showAxes />);

    expect(seriesPaths(html)).toHaveLength(3);
    expect(html).not.toContain('stroke-dasharray="1 5"');
  });
});
