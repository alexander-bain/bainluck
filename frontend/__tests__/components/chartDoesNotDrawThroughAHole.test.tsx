/**
 * #3659 → #11929 — THE WIRING: the chart that ships draws a solid line through
 * unobserved time.
 *
 * ═══ SUPERSEDED CONTRACT ═══
 *
 * #3659 pinned the opposite: the holed series broke into runs, a faint dotted
 * bridge (`stroke-dasharray="1 5"`) spanned the hole, and the caption named it
 * ("No numbers for 15 days in this stretch"). Alex ruled that away on
 * 2026-11-04 12:09 PM PT (#11929):
 *
 *   "A solid line through unobserved time. A hole between two observations is
 *    drawn like any other segment of that line (the chart's normal
 *    interpolation): no bridge, no dotted treatment, no label, and the
 *    caption's 'No numbers for N hours' sentence goes with it — nothing on the
 *    chart calls the reader's attention to a gap."
 *
 * The gaps are the bug, closed at the source; the chart does not confess them.
 * The file keeps its name and its specimen so the history of the contract
 * stays readable in one place; every assertion below is the new contract.
 *
 * `FuturesChart` is the kernel behind `/futures/[id]`, `/categories/golf`,
 * `/sport/[sport]/[league]`, `TeamSeasonJourney`, `WinnerEvolutionChart`,
 * `SettledPathChart` and `RaceToTitleChart`.
 *
 * ═══ THE FIXTURE ═══
 *
 * `/api/futures/16630403/history` ("Hantavirus pandemic in 2026?"), outcome
 * "Yes", re-read from production 2026-09-06 ~23:0xZ: median gap 1.00h, one
 * interior hole of 345.6h, then a day of hourly readings. The rendered window
 * puts ~93% of the chart's horizontal space inside that hole.
 *
 * ═══ WHAT IS ASSERTED ═══
 *
 *   • the holed series is ONE solid stroke, read out of the rendered `d` by
 *     coordinate: it visits every observation, and the hole is one ordinary
 *     segment of it (`L`, or `H … V` under `stepInterpolation`);
 *   • nothing dotted, nothing faint, no "No numbers for" anywhere;
 *   • controls: the stale "Last number …" caption (the line's right-hand end,
 *     not a gap) still prints, and a healthy chart is unchanged.
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

/** The observations a path visits: `M x y`, then `L x y` or `H x V y` each. */
function vertices(d: string): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  const re = /(?:([ML]) (-?[\d.]+) (-?[\d.]+))|(?:H (-?[\d.]+) V (-?[\d.]+))/g;
  for (const m of d.matchAll(re)) {
    out.push(m[1] ? [Number(m[2]), Number(m[3])] : [Number(m[4]), Number(m[5])]);
  }
  return out;
}

const HOLED_N = HOLED[0].history.length;

describe("#11929 FuturesChart — a solid line through the hole (supersedes #3659)", () => {
  test("the holed series is drawn as ONE stroke", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);
    expect(seriesPaths(html)).toHaveLength(1);
  });

  test("the stroke that spans the hole is the solid line itself — not faint, not dotted", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);
    const [line] = seriesPaths(html);

    expect(line.opacity).toBe(1);
    expect(line.dash).toBeNull();
    // The hole is ~95% of the plot; it is crossed by this same path.
    expect(widestStride(line.d)).toBeGreaterThan(0.9 * 730);
    expect(html).not.toContain('stroke-dasharray="1 5"');
  });

  test("the observation stranded on the far side of the hole is still painted, as part of the line", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);
    const [line] = seriesPaths(html);
    const v = vertices(line.d);

    // Every observation is a vertex of the one path, the stranded Aug 22
    // reading first — at the left padding (50), the x the oldest point scales to.
    expect(v).toHaveLength(HOLED_N);
    expect(v[0][0]).toBeCloseTo(50, 5);
    // …and the next vertex is the far side of the hole, joined by a plain `L`.
    expect(line.d).toMatch(/^M 50 [\d.]+ L [\d.]+ [\d.]+ L /);
    expect(v[1][0] - v[0][0]).toBeGreaterThan(0.9 * 730);
    // It is a line vertex now, not a lone dot.
    expect(html).not.toMatch(/<circle[^>]*\br="3"/);
  });

  test("no caption names the hole — the line is current, so no caption at all", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);

    expect(html).not.toContain("No numbers for");
    expect(html).not.toContain('data-series-state="gapped"');
    expect(html).not.toContain('data-testid="futures-chart-freshness"');
  });

  test("control: a line behind NOW still says how old its last number is, and is still one stroke", () => {
    // Run through the real cached payload the page rendered on 2026-09-06, the
    // 16630403 series comes out `stale` — n=358, median 1.00h, age 6.37h. That
    // caption is about the line's right-hand end, not a gap, and the ruling
    // leaves it alone. Move the CLOCK forward 6h rather than the points back,
    // so the cadence is untouched.
    jest.setSystemTime(NOW + 6 * HOUR);
    const html = renderToStaticMarkup(<FuturesChart historyData={HOLED} showAxes />);
    jest.setSystemTime(NOW);

    expect(html).toContain('data-series-state="stale"');
    expect(html).toContain("Last number 6 hours ago");
    expect(html).not.toContain("No numbers for");
    expect(seriesPaths(html)).toHaveLength(1);
    expect(seriesPaths(html).filter((p) => p.dash === "1 5")).toHaveLength(0);
  });

  test("under step interpolation the hole is an ordinary step of the same stroke", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={HOLED} showAxes stepInterpolation fixedYAxis />,
    );
    const drawn = seriesPaths(html);
    expect(drawn).toHaveLength(1);
    const [line] = drawn;
    expect(line.dash).toBeNull();
    // Hold, then riser — `H x V y` — exactly like every other step on the line.
    expect(line.d).toMatch(/^M 50 [\d.]+ H [\d.]+ V [\d.]+ H /);
    expect(line.d).not.toMatch(/ L /);
    const v = vertices(line.d);
    expect(v).toHaveLength(HOLED_N);
    expect(v[1][0] - v[0][0]).toBeGreaterThan(0.9 * 730);
    expect(html).not.toContain("No numbers for");
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
