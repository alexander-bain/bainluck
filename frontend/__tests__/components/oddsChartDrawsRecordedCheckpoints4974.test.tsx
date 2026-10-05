/**
 * #4974 slice 1 (web, #10487) — on a finished game, inside the recorded window
 * the blend is drawn as one dot per recorded checkpoint and nothing joins them.
 * Boundary: `4974-UX-READER-SLICE-1-BOUNDARY.md`, section B.
 *
 * This renders the real chart and reads the emitted SVG, because every claim
 * here is about ink: (iv) no path joins two checkpoints, the legacy blend is
 * withdrawn inside the window and is drawn as two lines, one each side of it,
 * so no segment can cross any part of it — including a window inside one
 * minute, which has no row of its own to break on — the callout labels the last
 * checkpoint when the window runs to the end, disconnected checkpoints never
 * count as an odds flip, and every control — no response, live, truncated,
 * empty, single-source — is byte-identical to today's chart.
 *
 * 🪤 recharts draws nothing inside a `ResponsiveContainer` without a viewport,
 * so it is mocked to a fixed 390×300 (same device as
 * `periodMarkersPaintAboveTheSeries6964`), and the first arm proves the chart
 * and the dots are really in the markup before anything is asserted about them.
 *
 * The scrub rules (i)–(iii), (vi) are pure and pinned in
 * `__tests__/publicationJourney4974.test.ts`; static markup cannot move a cursor.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OddsChart from "@/components/OddsChart";
import { AnalyticsProvider } from "@/components/Analytics";
import { sourceHex } from "@/lib/sourceColors";
import type { EventPublicationsResponse, PublicationVertex } from "@/lib/types";

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

/** Fixed anchor — never `Date.now()` (gotcha #44). */
const KICKOFF = Date.UTC(2026, 9, 4, 20, 0, 0);
const MIN = 60_000;
const iso = (offsetMin: number) => new Date(KICKOFF + offsetMin * MIN).toISOString();
const FINAL_MIN = 180;

const series = (stepMin: number, f: (m: number) => number) => {
  const out: Array<{ timestamp: string; home_probability: number; away_probability: number }> = [];
  for (let m = 0; m <= FINAL_MIN; m += stepMin) {
    const p = f(m);
    out.push({ timestamp: iso(m), home_probability: p, away_probability: 1 - p });
  }
  return out;
};

const legacy = (m: number) => 0.55 + 0.25 * Math.sin(m / 40);
const AGGREGATE = series(1, legacy);
const ESPN = series(5, (m) => legacy(m) + 0.01);
const KALSHI = series(5, (m) => legacy(m) - 0.01);
const BOOKS = series(10, legacy);

/** Interior window [60, 120] in rev order with a non-monotonic `t` (rev 5 → 63 min). */
const INTERIOR: PublicationVertex[] = [
  { rev: 1, t: iso(60), p: 0.3 },
  { rev: 2, t: iso(61), p: 0.31 },
  { rev: 3, t: iso(62), p: 0.33 },
  { rev: 4, t: iso(90), p: 0.45 },
  { rev: 5, t: iso(63), p: 0.34 },
  { rev: 6, t: iso(120), p: 0.88 },
];

/** A window that runs to the final whistle, ending on a value the legacy line never had. */
const TO_THE_END: PublicationVertex[] = [
  { rev: 1, t: iso(150), p: 0.5 },
  { rev: 2, t: iso(170), p: 0.6 },
  { rev: 3, t: iso(FINAL_MIN), p: 0.93 },
];

const body = (vertices: PublicationVertex[], over: Partial<EventPublicationsResponse> = {}): EventPublicationsResponse => ({
  event_id: 1,
  schema_version: 1,
  time_basis: "recorded_at_insert_before_commit",
  truncated: false,
  vertices,
  ...over,
});

type Props = Partial<React.ComponentProps<typeof OddsChart>>;

/**
 * recharts numbers its clip-path ids from module counters, so two renders of
 * one chart differ only there; those counters are normalised and nothing else.
 */
function draw(over: Props = {}): string {
  return drawRaw(over)
    .replace(/recharts\d+-clip/g, "recharts#-clip")
    .replace(/recharts-(line|scatter)-\d+/g, "recharts-$1-#");
}

function drawRaw(over: Props = {}): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={BOOKS as never}
        homeTeam="Dodgers"
        awayTeam="Braves"
        commenceTime={iso(0)}
        eventStatus="completed"
        completedAt={iso(FINAL_MIN)}
        winProbHistory={{ espn: ESPN, kalshi: KALSHI } as never}
        aggregateLine={AGGREGATE}
        externalTimeRange="all"
        {...over}
      />,
    ),
  );
}

const BLEND = sourceHex("blend");

function checkpointLayer(markup: string): string | null {
  const m = markup.match(/<g class="[^"]*publication-checkpoints[^"]*"[^>]*>([\s\S]*?)<\/g>/);
  return m ? m[1] : null;
}

function dots(markup: string): Array<{ rev: number; cx: number; r: string; stroke: string | null }> {
  const layer = checkpointLayer(markup) ?? "";
  return Array.from(layer.matchAll(/<circle[^>]*>/g)).map(([tag]) => ({
    rev: Number(tag.match(/data-checkpoint-rev="([^"]*)"/)?.[1]),
    cx: Number(tag.match(/ cx="([^"]*)"/)?.[1]),
    r: tag.match(/ r="([^"]*)"/)?.[1] ?? "",
    stroke: tag.match(/ stroke="([^"]*)"/)?.[1] ?? null,
  }));
}

/** Every drawn blend line's `d`, in document order (empty paths dropped). */
function blendPaths(markup: string): string[] {
  return Array.from(markup.matchAll(/<path[^>]*>/g))
    .map(([tag]) => tag)
    .filter((tag) => tag.includes(`stroke="${BLEND}"`) && tag.includes('stroke-width="3"') && tag.includes("recharts-line-curve"))
    .map((tag) => tag.match(/ d="([^"]*)"/)?.[1] ?? "")
    .filter((d) => d.length > 0);
}

function blendPath(markup: string): string {
  const paths = blendPaths(markup);
  if (paths.length !== 1) throw new Error(`expected one blend path, found ${paths.length}`);
  return paths[0];
}

const lineCurves = (markup: string) => (markup.match(/recharts-line-curve/g) ?? []).length;
const subpaths = (d: string) => (d.match(/M/g) ?? []).length;
const pathXs = (d: string) => Array.from(d.matchAll(/[ML](-?[\d.]+),(-?[\d.]+)/g)).map((m) => Number(m[1]));

const attr = (markup: string, name: string) => markup.match(new RegExp(`${name}="([^"]*)"`))?.[1] ?? null;

/** The "Odds flipped (N)" chip's N; 0 when the chip is absent (it is only offered for N > 0). */
const flips = (markup: string) => Number(markup.match(/Odds flipped \((?:<!-- -->)?(\d+)/)?.[1] ?? 0);

/** No single blend path has ink on both sides of [lo, hi]: nothing crosses the window. */
const nothingCrosses = (paths: string[], lo: number, hi: number) =>
  paths.every((d) => !(pathXs(d).some((x) => x < lo) && pathXs(d).some((x) => x > hi)));

const at = (offsetMin: number, offsetSec: number) => new Date(KICKOFF + offsetMin * MIN + offsetSec * 1000).toISOString();

describe("the rig is not vacuous", () => {
  it("draws the chart, the blend, and one dot per checkpoint", () => {
    const control = draw();
    expect(lineCurves(control)).toBeGreaterThanOrEqual(3);
    expect(subpaths(blendPath(control))).toBe(1);
    expect(checkpointLayer(control)).toBeNull();

    const shown = draw({ publications: body(INTERIOR) });
    expect(dots(shown).map((d) => d.rev).sort()).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("is deterministic, so byte-identity controls can testify", () => {
    expect(draw()).toBe(draw());
  });
});

describe("inside the recorded window: dots only, nothing joining them", () => {
  const markup = draw({ publications: body(INTERIOR) });
  const drawn = dots(markup);

  it("(iv) the checkpoint layer holds circles and no path, and the only new series path is the blend's second side", () => {
    expect(checkpointLayer(markup)).not.toMatch(/<path/);
    expect(lineCurves(markup)).toBe(lineCurves(draw()) + 1);
    expect(blendPaths(markup)).toHaveLength(2);
  });

  it("each dot is small, filled, unstroked", () => {
    for (const d of drawn) {
      expect(d.r).toBe("2");
      expect(d.stroke).toBe("none");
    }
  });

  it("dots sit at their own instants, in time order whatever the rev order", () => {
    const byRev = new Map(drawn.map((d) => [d.rev, d.cx]));
    // 60 < 61 < 62 < 63 (rev 5) < 90 (rev 4) < 120.
    const order = [1, 2, 3, 5, 4, 6].map((rev) => byRev.get(rev)!);
    for (let i = 1; i < order.length; i++) expect(order[i]).toBeGreaterThan(order[i - 1]);
  });

  it("the legacy blend is withdrawn across [min t, max t]: one line each side, nothing crossing", () => {
    const paths = blendPaths(markup);
    const xs = drawn.map((p) => p.cx);
    const lo = Math.min(...xs);
    const hi = Math.max(...xs);
    for (const d of paths) {
      expect(subpaths(d)).toBe(1);
      expect(pathXs(d).filter((x) => x > lo + 0.01 && x < hi - 0.01)).toEqual([]);
    }
    expect(nothingCrosses(paths, lo, hi)).toBe(true);
    // and there is legacy ink on both sides
    expect(Math.max(...pathXs(paths[0]))).toBeLessThan(lo);
    expect(Math.min(...pathXs(paths[1]))).toBeGreaterThan(hi);
  });

  it("the callout stays on the legacy end when legacy ink follows the window", () => {
    expect(attr(markup, "data-callout-at")).toBe(attr(draw(), "data-callout-at"));
  });
});

describe("a hole in the legacy blend right after the window", () => {
  // Legacy readings stop inside the window and resume at minute 140. The blend
  // has no observation bound, so only the carry decides what fills 121–139:
  // nothing may — a carried pre-window value would draw a legacy line the
  // blend never had, straight out of the far end of the window.
  const holed = AGGREGATE.filter((p) => {
    const m = (Date.parse(p.timestamp) - KICKOFF) / MIN;
    return m <= 120 || m >= 140;
  });
  const markup = draw({ publications: body(INTERIOR), aggregateLine: holed });

  it("nothing is carried across the window; the blend resumes on its next reading", () => {
    const byRev = new Map(dots(markup).map((p) => [p.rev, p.cx]));
    const at60 = byRev.get(1)!;
    const at120 = byRev.get(6)!;
    const x140 = at120 + ((at120 - at60) / 60) * 20;
    const after = blendPaths(markup).flatMap(pathXs).filter((x) => x > at120 + 0.01);
    expect(after.length).toBeGreaterThan(0);
    expect(Math.min(...after)).toBeCloseTo(x140, 1);
  });
});

describe("a window that runs to the end", () => {
  const markup = draw({ publications: body(TO_THE_END) });

  it("the callout labels the last checkpoint, at its instant, with its value", () => {
    expect(attr(markup, "data-callout-at")).toBe(iso(FINAL_MIN));
    expect(attr(markup, "data-callout-label")).toBe("93%");
    expect(attr(draw(), "data-callout-label")).not.toBe("93%");
  });

  it("the legacy blend ends before the window and is not drawn after it", () => {
    const d = blendPath(markup);
    expect(subpaths(d)).toBe(1);
    const lo = Math.min(...dots(markup).map((p) => p.cx));
    expect(Math.max(...pathXs(d))).toBeLessThan(lo);
  });
});

describe("controls: today's chart, byte for byte", () => {
  const today = draw();

  it.each([
    ["no response", undefined],
    ["null", null],
    ["truncated", body(INTERIOR, { truncated: true })],
    ["empty (never recorded, or folded)", body([])],
    ["one checkpoint", body(INTERIOR.slice(0, 1))],
    ["unknown schema", body(INTERIOR, { schema_version: 2 })],
  ])("%s", (_name, publications) => {
    expect(draw({ publications: publications as EventPublicationsResponse | null | undefined })).toBe(today);
  });

  it("a live game ignores checkpoints", () => {
    const live = { isLive: true, eventStatus: "live", completedAt: undefined } as Props;
    expect(draw({ ...live, publications: body(INTERIOR) })).toBe(draw(live));
  });

  it("a chart with no backend blend ignores checkpoints", () => {
    const single = { backendBlendServed: false } as Props;
    expect(draw({ ...single, publications: body(INTERIOR) })).toBe(draw(single));
  });
});

describe("a recorded window inside one minute (independent vectors, 20:15:10–20:15:50)", () => {
  // Minute 60 is the 20:15-style row before the window, minute 61 the one
  // after; neither row's own instant is inside [60:10, 60:50], so no row is
  // nulled and only a span test can stop a segment, a carry or a flip
  // reaching across. Both rows stay where they are.
  const SUB: PublicationVertex[] = [
    { rev: 1, t: at(60, 10), p: 0.45 },
    { rev: 2, t: at(60, 50), p: 0.55 },
  ];
  const markup = draw({ publications: body(SUB) });
  const byRev = new Map(dots(markup).map((p) => [p.rev, p.cx]));
  const lo = byRev.get(1)!;
  const hi = byRev.get(2)!;
  /** One minute's width: the 40 s between the dots is two thirds of it. */
  const step = (hi - lo) * 1.5;

  it("both dots are drawn, at their own sub-minute instants", () => {
    expect(byRev.size).toBe(2);
    expect(hi).toBeGreaterThan(lo);
  });

  it("no legacy segment joins the 60 and 61 rows across the window", () => {
    expect(nothingCrosses(blendPaths(markup), lo, hi)).toBe(true);
  });

  it("the outside rows are kept: the line before ends ON the 60 row, the line after starts ON the 61 row", () => {
    const [before, after] = blendPaths(markup);
    expect(Math.max(...pathXs(before))).toBeCloseTo(lo - step / 6, 1);
    expect(Math.min(...pathXs(after))).toBeCloseTo(hi + step / 6, 1);
  });

  it("nothing is carried from the 60 row into a 61 row that has no reading", () => {
    // Legacy readings stop at 60 and resume at 70; 61–69 are seeded rows with
    // no blend. A carry judged on the 61 row alone (outside the window) would
    // fill them with the 60 row's value, bridging the window.
    const holed = AGGREGATE.filter((p) => {
      const m = (Date.parse(p.timestamp) - KICKOFF) / MIN;
      return m <= 60 || m >= 70;
    });
    const paths = blendPaths(draw({ publications: body(SUB), aggregateLine: holed }));
    expect(nothingCrosses(paths, lo, hi)).toBe(true);
    const after = paths.flatMap(pathXs).filter((x) => x > hi);
    expect(after.length).toBeGreaterThan(0);
    expect(Math.min(...after)).toBeCloseTo(hi + step / 6 + 9 * step, 1);
  });

  it("a legacy 40% → 60% pair either side of the window is not an odds flip", () => {
    const stepped = series(1, (m) => (m <= 60 ? 0.4 : 0.6));
    expect(flips(draw({ aggregateLine: stepped }))).toBe(1); // control: joined, it IS one
    expect(flips(draw({ aggregateLine: stepped, publications: body(SUB) }))).toBe(0);
  });
});

describe("odds flips are counted on drawn segments only, never across checkpoints", () => {
  const flat = series(1, () => 0.7);

  it("disconnected 40% and 60% checkpoints make no flip", () => {
    const apart: PublicationVertex[] = [
      { rev: 1, t: iso(60), p: 0.4 },
      { rev: 2, t: iso(120), p: 0.6 },
    ];
    expect(flips(draw({ aggregateLine: flat }))).toBe(0); // control
    const markup = draw({ aggregateLine: flat, publications: body(apart) });
    expect(dots(markup)).toHaveLength(2); // the rig drew them
    expect(flips(markup)).toBe(0);
  });

  it("a genuine connected legacy flip outside the window still counts once", () => {
    const early = series(1, (m) => (m < 30 ? 0.4 : 0.7));
    const window: PublicationVertex[] = [
      { rev: 1, t: iso(60), p: 0.45 },
      { rev: 2, t: iso(120), p: 0.55 },
    ];
    expect(flips(draw({ aggregateLine: early }))).toBe(1);
    expect(flips(draw({ aggregateLine: early, publications: body(window) }))).toBe(1);
  });
});
