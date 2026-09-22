// #8066 — a single-source live chart labels its legend "Bain Luck" while the
// line spanning the match is the unnamed source line.
//
// THE DEFECT. The backend emits `aggregate_line` only when it blended two or
// more sources, so a Kalshi-only match is served none. The live stream is not
// bound by that rule: it publishes the event's blend `p` for single-source
// events too, and #920's `mergeLiveChartHistory` puts those frames into the
// SAME `aggregate_line` array. `OddsChart` then asks only "are there aggregate
// points", so two pushed frames — five seconds of an open tab — flip the whole
// chart:
//
//   • a 2-vertex emerald series appears at strokeWidth 3 under the name
//     "Bain Luck", and
//   • `primarySeriesKey` moves to it, which demotes the 319-vertex line the
//     reader actually reads the match off from 2.5px/opacity 1 to
//     1px/opacity 0.28 — #3151/#3111's "a correct 852px path nobody can see",
//     reintroduced by a delivery change rather than a renderer one.
//
// Measured by live/514 on production `15317096` at 19:27Z: Kalshi 72 vertices
// at width 1, "Bain Luck" 2 vertices at width 3.
//
// THE SECOND HALF, which the issue names and which is visible with no pushed
// frames at all: the legend's collapse-behind-"+ N sources" is gated on
// `isMultiSource`, but it exists so that THE BLEND may dominate. With no blend
// drawn there is nothing to defer to, and the collapse was hiding the name of
// the only line on the plot — a legend whose entire content was "+ 1 source".
//
// THE SHIP: the blend line and the blend's name belong to the backend's blend.
// Where there is none, the one real measured line is drawn at full weight and
// is labelled as itself (#1003's own stated fallback).
//
// These go through the REAL component and read the SVG recharts emitted, plus
// the legend's own markup — the two things that disagreed. Same rig as
// chartStopsDrawingAcrossAHoleNobodyObserved7878.test.tsx.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

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
import { computeSharedChartDomain } from "@/lib/eventKeyStats";
import type { EventHistoryResponse } from "@/lib/types";

// ── SVG + legend readers ────────────────────────────────────────────────────

interface Curve {
  stroke: string;
  width: number;
  opacity: number;
  dash: string | null;
  vertices: number;
}

function curves(html: string): Curve[] {
  return (html.match(/<path[^>]*recharts-line-curve[^>]*>/g) ?? []).map((tag) => {
    const d = /\sd="([^"]*)"/.exec(tag)?.[1] ?? "";
    return {
      stroke: /stroke="([^"]+)"/.exec(tag)?.[1] ?? "",
      width: Number(/stroke-width="([^"]+)"/.exec(tag)?.[1] ?? "0"),
      opacity: Number(/stroke-opacity="([^"]+)"/.exec(tag)?.[1] ?? "1"),
      dash: /stroke-dasharray="([^"]+)"/.exec(tag)?.[1] ?? null,
      vertices: (d.match(/-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?/g) ?? []).length,
    };
  }).filter((c) => c.vertices > 0);
}

const KALSHI_GREEN = "#22c55e";
const BLEND_EMERALD = "#059669";
/** The gap connector #7878 draws; not a series. */
const isConnector = (c: Curve) => c.dash === "2 5";

const blendCurve = (html: string) => curves(html).find((c) => c.stroke === BLEND_EMERALD && !isConnector(c));
const kalshiCurve = (html: string) => curves(html).find((c) => c.stroke === KALSHI_GREEN && !isConnector(c));

/** The legend is the block of source swatches under the plot. */
function legendNames(html: string): string[] {
  return (html.match(/<span class="text-xs[^"]*"[^>]*>([^<]+)<\/span>/g) ?? [])
    .map((s) => /<span[^>]*>([^<]+)<\/span>/.exec(s)?.[1] ?? "")
    .filter(Boolean);
}
const hasExpander = (html: string) => /\+\s*\d+\s*source/.test(html);
/**
 * The swatch drawn beside a legend name, as `width/opacity`. The dasharray
 * sits between the two on a source that has one and is absent on one that does
 * not, so the reader must not assume adjacency (it did, and reported `null`
 * about a swatch that was there).
 */
function legendSwatch(html: string, name: string): string | null {
  const block = new RegExp(
    `<line[^>]*?stroke-width="([^"]+)"[^>]*?stroke-opacity="([^"]+)"[^>]*></line></svg><span class="text-xs[^"]*">${name}</span>`,
  ).exec(html);
  return block ? `${block[1]}/${block[2]}` : null;
}
/** The current-probability callout, read from the attribute the chart emits for it. */
function callout(html: string): string | null {
  return /data-callout-label="([^"]*)"/.exec(html)?.[1] ?? null;
}
/**
 * recharts numbers each instance's clipPaths from a module-global counter, in
 * three id forms (`recharts8-clip`, `clipPath-recharts-line-12`, `clipPath-recharts-scatter-42`), so two renders
 * of identical trees differ in those ids and — as this comparison proves —
 * nothing else. Normalising that counter is not normalising an answer: it
 * removes the render ORDER from a comparison about render OUTPUT. Nothing here
 * touches a coordinate, a colour, a width or a word.
 */
const withoutInstanceIds = (html: string) =>
  html
    .replace(/recharts\d+-clip/g, "recharts-clip")
    .replace(/clipPath-recharts-([a-z]+)-\d+/g, "clipPath-recharts-$1-N");

// ── The specimen ────────────────────────────────────────────────────────────

// A real single-source Kalshi match, served with `aggregate_line: null` — the
// exact payload shape #8066 was measured on. (Saved for #7878; its 73.6-minute
// interior hole is irrelevant here and is what the "2 5" connector is.)
const SPECIMEN: EventHistoryResponse & { status: string; commence_time: string } = JSON.parse(
  readFileSync(join(__dirname, "..", "fixtures", "event-15315912-history-7878.json"), "utf8"),
);

const LAST_REAL_READING = 0.42;

/**
 * The frames the page accumulates from the live stream, as
 * `mergeLiveChartHistory` would deposit them in `aggregate_line`.
 *
 * 🔴 Their values DISAGREE with the source's last reading on purpose, and that
 * disagreement is CONSTRUCTED. On a real single-source event the blend is
 * computed over one source, so `p` and the source's own value agree and no
 * reader sees a wrong percentage today. The disagreement here is the
 * discriminator — the only way to ask WHICH series the callout and the plot
 * are reading — not a claim about production.
 */
const PUSHED_FRAMES = (() => {
  const base = Date.parse(SPECIMEN.win_prob_history!.kalshi.at(-1)!.timestamp);
  return [
    { timestamp: new Date(base + 60_000).toISOString(), home_probability: 0.43 },
    { timestamp: new Date(base + 180_000).toISOString(), home_probability: 0.44 },
  ];
})();

function render(props: Record<string, unknown>, history = SPECIMEN) {
  const domain = computeSharedChartDomain(
    history as EventHistoryResponse, "live", SPECIMEN.status, SPECIMEN.commence_time, "tennis_wta",
  );
  expect(domain).not.toBeNull();
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Home"
      awayTeam="Away"
      isLive
      eventStatus="live"
      externalTimeRange="live"
      winProbSources={history.win_prob_sources}
      winProbHistory={history.win_prob_history}
      commenceTime={SPECIMEN.commence_time}
      chartStartTime={domain!.start}
      chartEndTime={domain!.end}
      sharedTicks={domain!.ticks}
      chartLabelFormat={domain!.labelFormat}
      {...props}
    />,
  );
}

describe("#8066 — the specimen is a single-source event the backend served no blend for", () => {
  test("the fixture is that shape, so every assertion below is about it", () => {
    expect(SPECIMEN.aggregate_line).toBeNull();
    expect(Object.keys(SPECIMEN.win_prob_history!)).toEqual(["kalshi"]);
    expect(SPECIMEN.win_prob_history!.kalshi).toHaveLength(199);
    expect(SPECIMEN.win_prob_history!.kalshi.at(-1)!.home_probability).toBe(LAST_REAL_READING);
    expect(SPECIMEN.history).toHaveLength(0);
  });
});

describe("#8066 — pushed live frames do not become a blend line", () => {
  test("no emerald blend series is drawn, and the legend does not say Bain Luck", () => {
    const html = render({ aggregateLine: PUSHED_FRAMES, backendBlendServed: false });
    expect(blendCurve(html)).toBeUndefined();
    expect(html).not.toContain("Bain Luck");
  });

  test("the match-spanning source line keeps full weight — it is not demoted to 1px at 0.28", () => {
    const html = render({ aggregateLine: PUSHED_FRAMES, backendBlendServed: false });
    const kalshi = kalshiCurve(html);
    expect(kalshi).toBeDefined();
    expect(kalshi!.vertices).toBeGreaterThan(300);
    expect(kalshi!.width).toBe(2.5);
    expect(kalshi!.opacity).toBe(1);
  });

  test("the only line on the plot is named in the legend, not hidden behind '+ 1 source'", () => {
    const html = render({ aggregateLine: PUSHED_FRAMES, backendBlendServed: false });
    expect(legendNames(html)).toContain("Kalshi");
    expect(hasExpander(html)).toBe(false);
    // The swatch is drawn at the weight the plot gave the line, so the legend
    // cannot describe a line the chart did not draw.
    expect(legendSwatch(html, "Kalshi")).toBe("2.5/1");
  });

  test("the callout reads off the match-spanning line, not the pushed stub", () => {
    // See PUSHED_FRAMES: the 42 vs 44 disagreement is constructed to make
    // "which series is this number from" answerable at all.
    expect(callout(render({ aggregateLine: PUSHED_FRAMES, backendBlendServed: false }))).toBe("42%");
  });

  test("the pushed frames change nothing: the chart is what it is with no stream at all", () => {
    const withFrames = render({ aggregateLine: PUSHED_FRAMES, backendBlendServed: false });
    const withoutFrames = render({ aggregateLine: undefined, backendBlendServed: false });
    expect(withoutInstanceIds(withFrames)).toBe(withoutInstanceIds(withoutFrames));
  });
});

describe("#8066 — the controls: what the gate must NOT change", () => {
  // Without this arm, every assertion above is a fact about a chart I
  // configured rather than a difference the gate creates.
  test("CONTROL — a caller that says nothing is unchanged, and that parent state IS the defect", () => {
    const html = render({ aggregateLine: PUSHED_FRAMES });
    const blend = blendCurve(html);
    expect(blend).toBeDefined();
    expect(blend!.vertices).toBe(2);
    expect(blend!.width).toBe(3);
    expect(html).toContain("Bain Luck");
    // …and the 319-vertex real line demoted underneath it.
    const kalshi = kalshiCurve(html);
    expect(kalshi!.vertices).toBeGreaterThan(300);
    expect(kalshi!.width).toBe(1);
    expect(kalshi!.opacity).toBe(0.28);
    expect(hasExpander(html)).toBe(true);
    expect(callout(html)).toBe("44%");
  });

  test("CONTROL — a real backend blend still dominates: drawn at 3px, named, sources collapsed", () => {
    // Two sources and a served blend — the population #920 and L2-131 are
    // about, and the half a wrong fix would break.
    const kalshi = SPECIMEN.win_prob_history!.kalshi;
    const twoSource = {
      ...SPECIMEN,
      win_prob_history: {
        kalshi,
        polymarket: kalshi.map((p) => ({ ...p, home_probability: (p.home_probability ?? 0.5) + 0.01 })),
      },
      win_prob_sources: {
        ...SPECIMEN.win_prob_sources,
        polymarket: { display_name: "Polymarket", color: "#3b82f6", type: "market" as const, dash_pattern: "4 4", snapshot_count: kalshi.length },
      },
    } as unknown as typeof SPECIMEN;
    const served = kalshi.map((p) => ({ timestamp: p.timestamp, home_probability: (p.home_probability ?? 0.5) + 0.005 }));

    const html = render({ aggregateLine: served, backendBlendServed: true }, twoSource);
    const blend = blendCurve(html);
    expect(blend).toBeDefined();
    expect(blend!.width).toBe(3);
    expect(blend!.vertices).toBeGreaterThan(100);
    expect(html).toContain("Bain Luck");
    // Sources stay collapsed and faint — the blend is what dominates.
    expect(hasExpander(html)).toBe(true);
    expect(kalshiCurve(html)!.width).toBe(1);
    expect(kalshiCurve(html)!.opacity).toBe(0.28);
  });

  test("CONTROL — sportsbooks-only mode is untouched: flat legend, betting at full weight", () => {
    const bookHistory = SPECIMEN.win_prob_history!.kalshi.map((p) => ({
      timestamp: p.timestamp,
      home_win_probability: p.home_probability,
      away_win_probability: p.away_probability,
    }));
    const html = render(
      { history: bookHistory, winProbHistory: undefined, winProbSources: undefined, aggregateLine: undefined },
      { ...SPECIMEN, win_prob_history: undefined, history: bookHistory } as unknown as typeof SPECIMEN,
    );
    expect(html).not.toContain("Bain Luck");
    expect(hasExpander(html)).toBe(false);
    const names = legendNames(html);
    expect(names.length).toBeGreaterThan(0);
    expect(legendSwatch(html, names[0])).toBe("2.5/1");
  });
});

describe("#8066 — the page answers the question from the SERVED response", () => {
  const page = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");

  test("both charts are told, and told the same thing", () => {
    expect(page.match(/backendBlendServed=\{backendBlendServed\}/g)).toHaveLength(2);
  });

  test("the answer is derived from servedHistory, before #920's merge — not from historyData", () => {
    // `historyData` is the merged array; reading it here would make the gate
    // answer "yes" for exactly the pages it exists to protect.
    expect(page).toContain(
      "const backendBlendServed = (servedHistory?.aggregate_line?.length ?? 0) > 0;",
    );
  });
});
