// #3973 — the win-probability chart spends its height on the market's movement.
//
// LOOKED at production `/events/15306813` (Shelton v Alcaraz, US Open QF) and
// `/events/15306225` (Tiafoe v Michelsen) at 390px on 2026-09-08. Both Win
// Probability cards drew a full 0–100 axis, a vertical cliff in the first pixel
// column, and then a horizontal line for the entire remaining width. 98% of
// 15306813's 1,588 plotted samples sit between 21.5% and 27.8%, so on a fixed
// axis every move a reader opened the page for was 6.8% of the plot's height.
//
// The filing (#3973) blamed the early outlier for "stretching the axis to
// 0–100". It did not: `yDomain` was the literal `[0, 100]`, so the outlier
// stretched nothing and removing it would have changed nothing. What the
// outlier does do is defeat the obvious repair — a min/max domain here is
// [21, 92], as flat as what it replaces. That is why the axis is percentile-led
// and why THIS guard is about height used, not about the domain's numbers:
// pinning [20, 60] would go green on a future restyle that flattened the plot
// again at different constants.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// recharts draws NOTHING inside a ResponsiveContainer without a viewport, so a
// test that rendered the component as-is would assert over an empty string and
// pass on both arms (same reason as `chartDrawsALineYouCanSee`).
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

const START = Date.UTC(2026, 8, 7, 1, 26, 0); // fixed anchor — never Date.now()

/**
 * A market that wanders inside [lo, hi] deterministically. Real prices are not
 * a ramp: a monotone fixture would let a chart that plotted only the endpoints
 * satisfy every extent assertion below.
 */
function wander(n: number, lo: number, hi: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = (Math.sin(i * 0.7) + Math.sin(i * 0.13) + 2) / 4; // 0..1, no RNG
    out.push(lo + (hi - lo) * t);
  }
  return out;
}

function points(probs: number[]) {
  return probs.map((p, i) => ({
    timestamp: new Date(START + i * 60_000).toISOString(),
    home_probability: p / 100,
    away_probability: 1 - p / 100,
  }));
}

function render(probs: number[]) {
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Ben Shelton"
      awayTeam="Carlos Alcaraz"
      commenceTime="2026-09-09T00:30:00+00:00"
      isLive={false}
      eventStatus="scheduled"
      externalTimeRange="all"
      winProbHistory={{ kalshi: points(probs) }}
      winProbSources={{
        kalshi: {
          display_name: "Kalshi",
          color: "#22c55e",
          type: "market",
          snapshot_count: probs.length,
        },
      }}
    />,
  );
}

/** The plot rectangle recharts actually laid out, read off its own clip rect. */
function plotRect(html: string): { top: number; height: number } {
  const rect = /<clipPath id="recharts\d+-clip"><rect x="[\d.-]+" y="([\d.-]+)" height="([\d.-]+)"/.exec(html);
  if (!rect) throw new Error("no plot clip rect — the chart did not lay out");
  return { top: Number(rect[1]), height: Number(rect[2]) };
}

/** The `<path>` recharts stroked for the line, tag and all. */
function curveTag(html: string): string {
  const curves = html.match(/<path[^>]*recharts-line-curve[^>]*>/g) ?? [];
  if (curves.length !== 1) throw new Error(`expected one curve, drew ${curves.length}`);
  return curves[0];
}

function curvePoints(tag: string): Array<{ x: number; y: number }> {
  const d = /\sd="([^"]+)"/.exec(tag)?.[1] ?? "";
  return [...d.matchAll(/([ML])([\d.eE+-]+),([\d.eE+-]+)/g)].map((m) => ({
    x: Number(m[2]),
    y: Number(m[3]),
  }));
}

// Production's shape: 200 samples inside 21.0–27.8, preceded by the four-sample
// early spike that reaches 92. Ratio-faithful to the 1,588/10 measured live.
const SHELTON = [46.5, 76, 77, 92, ...wander(200, 21.0, 27.8)];

describe("#3973 — a narrow market is drawn, not flattened", () => {
  test("the settled band uses a real share of the plot's height", () => {
    const html = render(SHELTON);
    const plot = plotRect(html);
    const pts = curvePoints(curveTag(html));
    expect(pts.length).toBeGreaterThan(100);

    // Measure the settled band only — the right-hand 90% of the width. Taking
    // the whole curve would be vacuous: the clipped spike reaches the top of
    // the plot, so the full extent is ~100% however flat the band is drawn.
    const xs = pts.map((p) => p.x);
    const cut = Math.min(...xs) + 0.1 * (Math.max(...xs) - Math.min(...xs));
    const settled = pts.filter((p) => p.x >= cut).map((p) => p.y);
    const share = (Math.max(...settled) - Math.min(...settled)) / plot.height;

    // On the old fixed 0–100 axis this same 6.8-point band is 6.8% of the plot.
    // The bar is set above anything that axis can produce for it.
    expect(share).toBeGreaterThan(0.12);
  });

  test("the early spike is CLIPPED to the plot, not drawn over the card", () => {
    // The zoom means samples now fall outside the domain, and recharts does not
    // clamp their coordinates — it emits the true y (here, above the plot's top
    // edge) and relies on the axis's `allowDataOverflow` to fit a clip path.
    // Drop that prop and the spike is painted across the card's own chrome.
    const html = render(SHELTON);
    const plot = plotRect(html);
    const tag = curveTag(html);

    // The mechanism: this curve is clipped, and clipped to the PLOT vertically.
    const clipId = /clip-path="url\(#([^)]+)\)"/.exec(tag)?.[1];
    expect(clipId).toBeTruthy();
    const clipRect = new RegExp(
      `<clipPath id="${clipId}"><rect [^>]*y="([\\d.-]+)" width="[\\d.-]+" height="([\\d.-]+)"`,
    ).exec(html);
    expect(clipRect).toBeTruthy();
    expect(Number(clipRect![1])).toBe(plot.top);
    expect(Number(clipRect![2])).toBe(plot.height);

    // And the fixture really does put ink outside it, or the assertion above
    // is guarding nothing.
    const ys = curvePoints(tag).map((p) => p.y);
    expect(Math.min(...ys)).toBeLessThan(plot.top);
  });
});

describe("#3973 — the axis still says what it always said", () => {
  const yTickLabels = (html: string) =>
    [...html.matchAll(/class="recharts-text recharts-cartesian-axis-tick-value"[^>]*text-anchor="end"[^>]*>.*?<tspan[^>]*>([^<]*)<\/tspan>/g)]
      .map((m) => m[1]);

  test("a market that genuinely used the range keeps the 0–100 axis", () => {
    // The control. "Always zoom to the data" passes every test above and fails
    // here, and so does any rule that forgets a blowout is allowed to look like
    // one.
    const html = render(wander(400, 8, 92));
    expect(yTickLabels(html)).toEqual(["0%", "25%", "50%", "75%", "100%"]);
  });

  test("a narrow market's labels read as probabilities, not as a redrawn scale", () => {
    const labels = yTickLabels(render(SHELTON));
    expect(labels.length).toBeGreaterThanOrEqual(3);
    for (const l of labels) expect(l).toMatch(/^\d+%$/);
    // #3525 deleted the 50% line's own label because "the left axis already
    // prints 50% on this exact line". That is a condition, and this series
    // crosses 50, so it has to still hold.
    expect(labels).toContain("50%");
  });

  test("a market nowhere near 50 does not keep a dashed rule at 50", () => {
    // No crossing ⇒ no lead change ⇒ nothing is drawn at 50. Off the axis the
    // dashed line would be pinned to the plot frame, labelling nothing.
    const dashed = (html: string) =>
      (html.match(/<line y="50"[^>]*class="recharts-reference-line-line"/g) ?? []).length;

    expect(dashed(render(SHELTON))).toBeGreaterThan(0);
    expect(dashed(render(wander(400, 78, 86)))).toBe(0);
  });
});
