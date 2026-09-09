/**
 * #4259 — THE GOLF CONTENDER CHART USES ITS PLOT.
 *
 * Measured on production before the fix, at 1280px on `/categories/golf`:
 *
 *   plot box 240px · 8 series · whole field spans 22.96px = 9.57% of plot height
 *   leader (McIlroy 11.9%) at 12.22% of plot height · y labels 0/25/50/75/100%
 *
 * So the eight lines read as four or five near-touching strokes at the axis, and the
 * top three gridlines label empty space. This is #2451 word for word — Alex, on the
 * title chart: *"all visually flat and indistinguishable … fix the scale, do not
 * smooth the line"* — on the one field chart that never received #2451's fix.
 *
 * These tests measure the SAME quantity the production probe measures (y values off
 * the rendered `d` attributes, against the plot box), so the guard and the live read
 * cannot disagree about what "flat" means.
 *
 * NOTE ON WHAT IS *NOT* ASSERTED: no pixel width or font metric. This is SSR markup,
 * there is no layout engine here, and any px claim would be invented. The pixel claim
 * lives in the production probe, where it can be true.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesOutcomeHistory } from "../../lib/types";

/** The live Amgen Irish Open field from the issue, to the tenth of a point. */
const FIELD: { name: string; p: number }[] = [
  { name: "Rory McIlroy", p: 0.119 },
  { name: "Jon Rahm", p: 0.068 },
  { name: "Joaquin Niemann", p: 0.043 },
  { name: "Tyrrell Hatton", p: 0.04 },
  { name: "Robert MacIntyre", p: 0.04 },
  { name: "Matt Wallace", p: 0.031 },
  { name: "Alex Fitzpatrick", p: 0.027 },
  { name: "Shane Lowry", p: 0.027 },
];

const HISTORY: FuturesOutcomeHistory[] = FIELD.map((g, i) => ({
  outcome_id: i + 1,
  name: g.name,
  history: [
    { timestamp: "2026-09-01T00:00:00Z", probability: g.p },
    { timestamp: "2026-09-05T00:00:00Z", probability: g.p },
    { timestamp: "2026-09-09T00:00:00Z", probability: g.p },
  ],
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
})) as any;

const ALL = new Set(FIELD.map((_, i) => i + 1));

/** The plot box for a non-mini chart: padding.top, and top + innerHeight. */
const PLOT_TOP = 20;
const PLOT_BOTTOM = 20 + (200 - 20 - 40); // default non-mini height 200

/** Every y value in every drawn series path — the same read as the live probe. */
function seriesYs(html: string): number[] {
  const ys: number[] = [];
  for (const m of html.matchAll(/ d="([^"]+)"/g)) {
    const d = m[1];
    if (!/^[ML]/.test(d.trim())) continue; // skip the icon <path>
    for (const pt of d.matchAll(/[ML]\s*[-\d.]+\s+([-\d.]+)/g)) {
      const y = parseFloat(pt[1]);
      if (Number.isFinite(y)) ys.push(y);
    }
  }
  return ys;
}

/** How high the leader sits, as a fraction of plot height. 0 = welded to the floor. */
function leaderHeight(html: string): number {
  const ys = seriesYs(html);
  const top = Math.min(...ys);
  return (PLOT_BOTTOM - top) / (PLOT_BOTTOM - PLOT_TOP);
}

describe("#4259 the field chart uses its plot", () => {
  // Not a red-first test — it passes on the parent too, deliberately. It pins the
  // BEFORE state so the fix's differential is asserted rather than asserted-about:
  // if someone makes the flat axis stop stranding the field, this tells us the
  // measurement below no longer means what it says. The red-first guard for the
  // actual defect is `fieldChartCallSites4259.test.ts`, which reads the call sites.
  test("the old flat axis strands the whole field on the floor", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={HISTORY} selectedOutcomes={ALL} showAxes />,
    );
    // What production measured: leader at 12.22% of plot height.
    expect(leaderHeight(html)).toBeLessThan(0.15);
  });

  test("fieldCeiling lifts the leader to a height a reader can see", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={HISTORY} selectedOutcomes={ALL} showAxes fieldCeiling />,
    );
    // Ceiling 0.25, so McIlroy at 0.119/0.25 = 47.6% of the plot.
    expect(leaderHeight(html)).toBeGreaterThan(0.4);
    expect(leaderHeight(html)).toBeCloseTo(0.476, 2);
  });

  test("the acceptance in the issue: McIlroy and Lowry are visibly different heights", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={HISTORY} selectedOutcomes={ALL} showAxes fieldCeiling />,
    );
    const ys = seriesYs(html);
    const leaderY = Math.min(...ys); // McIlroy 11.9%
    const tailY = Math.max(...ys); // Lowry / Fitzpatrick 2.7%
    const plotHeight = PLOT_BOTTOM - PLOT_TOP;
    // Was 22.96px of 240 (9.57%) on production; the ladder makes it more than a third.
    expect((tailY - leaderY) / plotHeight).toBeGreaterThan(0.35);
  });

  test("ZERO IS NOT NEGOTIABLE — the baseline is never cropped", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={HISTORY} selectedOutcomes={ALL} showAxes fieldCeiling />,
    );
    // Every line stays inside the box, and the floor is still 0% — a 2.7% player is
    // drawn at 2.7% of the ceiling, not floated up off a fake floor.
    for (const y of seriesYs(html)) {
      expect(y).toBeGreaterThanOrEqual(PLOT_TOP - 0.01);
      expect(y).toBeLessThanOrEqual(PLOT_BOTTOM + 0.01);
    }
    expect(html).toContain("0%");
  });

  test("the moved top is LABELLED — this is the half that makes it honest", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={HISTORY} selectedOutcomes={ALL} showAxes fieldCeiling />,
    );
    // A moving ceiling with no labels would be strictly worse than a fixed one.
    expect(html).toContain("25%");
    expect(html).not.toContain("100%");
  });

  test("a two-sided market is untouched — it keeps the flat 0–100% axis", () => {
    const binary: FuturesOutcomeHistory[] = [
      {
        outcome_id: 1,
        name: "Yes",
        history: [
          { timestamp: "2026-09-01T00:00:00Z", probability: 0.58 },
          { timestamp: "2026-09-09T00:00:00Z", probability: 0.91 },
        ],
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any;
    const html = renderToStaticMarkup(
      <FuturesChart historyData={binary} selectedOutcomes={new Set([1])} showAxes fieldCeiling />,
    );
    // 0.91 * 1.15 > 1, so the ladder returns 1 and nothing moves.
    expect(html).toContain("100%");
  });

  test("a settled field is untouched — the winner at 100% holds the axis open", () => {
    const settledField: FuturesOutcomeHistory[] = [
      {
        outcome_id: 1,
        name: "Winner",
        history: [
          { timestamp: "2026-09-01T00:00:00Z", probability: 0.11 },
          { timestamp: "2026-09-09T00:00:00Z", probability: 1 },
        ],
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any;
    const html = renderToStaticMarkup(
      <FuturesChart historyData={settledField} selectedOutcomes={new Set([1])} showAxes fieldCeiling />,
    );
    expect(html).toContain("100%");
  });

  test("a sparkline is excluded — it has no labels to declare a moved top with", () => {
    const mini = renderToStaticMarkup(
      <FuturesChart historyData={HISTORY} selectedOutcomes={ALL} mini fieldCeiling />,
    );
    const miniFlat = renderToStaticMarkup(
      <FuturesChart historyData={HISTORY} selectedOutcomes={ALL} mini />,
    );
    // Identical geometry: fieldCeiling must be inert at sparkline size.
    expect(seriesYs(mini)).toEqual(seriesYs(miniFlat));
  });
});
