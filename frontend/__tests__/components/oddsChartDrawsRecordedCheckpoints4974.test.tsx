/**
 * #4974 slice 1 (web, #10487) — on a finished game, inside the recorded window
 * the blend is drawn as one dot per recorded checkpoint and nothing joins them.
 * Boundary: `4974-UX-READER-SLICE-1-BOUNDARY.md`, section B.
 *
 * This renders the real chart and reads the emitted SVG, because every claim
 * here is about ink: (iv) no path joins two checkpoints, the legacy blend is
 * withdrawn inside the window and BREAKS at both ends of it (it carries
 * `connectNulls` everywhere else, which would bridge the window with a straight
 * segment), the callout labels the last checkpoint when the window runs to the
 * end, and every control — no response, live, truncated, empty, single-source —
 * is byte-identical to today's chart.
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

function blendPath(markup: string): string {
  const paths = Array.from(markup.matchAll(/<path[^>]*>/g))
    .map(([tag]) => tag)
    .filter((tag) => tag.includes(`stroke="${BLEND}"`) && tag.includes('stroke-width="3"') && tag.includes("recharts-line-curve"));
  if (paths.length !== 1) throw new Error(`expected one blend path, found ${paths.length}`);
  return paths[0].match(/ d="([^"]*)"/)?.[1] ?? "";
}

const lineCurves = (markup: string) => (markup.match(/recharts-line-curve/g) ?? []).length;
const subpaths = (d: string) => (d.match(/M/g) ?? []).length;
const pathXs = (d: string) => Array.from(d.matchAll(/[ML](-?[\d.]+),(-?[\d.]+)/g)).map((m) => Number(m[1]));

const attr = (markup: string, name: string) => markup.match(new RegExp(`${name}="([^"]*)"`))?.[1] ?? null;

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

  it("(iv) the checkpoint layer holds circles and no path, and no new series path exists", () => {
    expect(checkpointLayer(markup)).not.toMatch(/<path/);
    expect(lineCurves(markup)).toBe(lineCurves(draw()));
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

  it("the legacy blend is withdrawn across [min t, max t] and breaks at both ends", () => {
    const d = blendPath(markup);
    expect(subpaths(d)).toBe(2);
    const xs = drawn.map((p) => p.cx);
    const lo = Math.min(...xs);
    const hi = Math.max(...xs);
    expect(pathXs(d).filter((x) => x > lo + 0.01 && x < hi - 0.01)).toEqual([]);
    // and there is legacy ink on both sides
    expect(pathXs(d).some((x) => x < lo)).toBe(true);
    expect(pathXs(d).some((x) => x > hi)).toBe(true);
  });

  it("the callout stays on the legacy end when legacy ink follows the window", () => {
    expect(attr(markup, "data-callout-at")).toBe(attr(draw(), "data-callout-at"));
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
