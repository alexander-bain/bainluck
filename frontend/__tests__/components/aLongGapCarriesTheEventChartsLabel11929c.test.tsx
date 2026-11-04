/**
 * #11929 cause C — A FUTURES CHART'S LONG GAP CARRIES THE EVENT CHART'S LABEL,
 * NOT A DASHED LINE.
 *
 * Alex, 2026-11-03: "The 2-hour gaps carry a label — the event chart already
 * prints 'No numbers for 37 hours in this stretch'; the futures chart uses the
 * same component instead of a dashed line that implies movement."
 *
 * Production 2026-11-04 after #11929 B: `/futures/65536371` (Denver December
 * snow, a venue-bank board) drew 6 pieces, 5 faint dotted connectors across its
 * 15–19 h holes and 2 lone dots; the capture-only US Open board (34277822) drew
 * 33 connectors and 22 dots. The fixtures below are those shapes.
 *
 * Pinned, every case a pair:
 *   • a hole renders the caption's own sentence over the gap and no connector;
 *   • a sub-threshold gap draws one continuous line and no label;
 *   • several holes → several labels, each over its own hole;
 *   • lone real points stay dots;
 *   • a settled line still ends at its last real observation, with its result
 *     mark there, and its settlement point never opens a labelled hole;
 *   • control: a dense series renders exactly as on B's branch.
 *
 * This file imports nothing that #11929 C adds, so on the base every
 * assertion below runs and the label assertions fail on their own.
 * Fixed anchors throughout — never Date.now() (gotcha #44).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "../../lib/types";

const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const NOW = Date.UTC(2026, 10, 4, 6, 0, 0);
const START = NOW - 168 * HOUR;

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => jest.useRealTimers());

function pt(at: number, p: number, extra: Partial<FuturesHistoryPoint> = {}): FuturesHistoryPoint {
  return {
    timestamp: new Date(at).toISOString(),
    probability: p,
    american_odds: null,
    bookmaker: "consensus",
    ...extra,
  };
}

/** Points at the given hour offsets from START. */
function at(hours: readonly number[], p: (i: number) => number, extra: Partial<FuturesHistoryPoint> = {}) {
  return hours.map((h, i) => pt(START + h * HOUR, p(i), extra));
}

/** Hourly offsets `from` … `to` inclusive. */
const hourly = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, i) => from + i);

const one = (history: FuturesHistoryPoint[], name = "Yes"): FuturesOutcomeHistory[] => [
  { outcome_id: 1, name, history },
];

function render(data: FuturesOutcomeHistory[], props: Record<string, unknown> = {}) {
  return renderToStaticMarkup(<FuturesChart historyData={data} showAxes fixedYAxis {...props} />);
}

interface DrawnPath {
  d: string;
  dash: string | null;
}
function seriesPaths(html: string): DrawnPath[] {
  return (html.match(/<path[^>]*\bd="M [^"]*"[^>]*>/g) ?? []).map((tag) => ({
    d: /\bd="([^"]*)"/.exec(tag)![1],
    dash: /stroke-dasharray="([^"]*)"/.exec(tag)?.[1] ?? null,
  }));
}
/** Solid series strokes only — not the eliminated "4 3", not a bridge. */
const solid = (html: string) => seriesPaths(html).filter((p) => p.dash === null);
const connectors = (html: string) => seriesPaths(html).filter((p) => p.dash === "1 5");
const dots = (html: string) => html.match(/<circle[^>]*\br="3"[^>]*>/g) ?? [];

interface Label {
  text: string;
  x: number;
  y: number;
  fromX: number;
  toX: number;
  from: string;
  to: string;
  className: string;
}
function labels(html: string): Label[] {
  return [
    ...html.matchAll(/<text[^>]*data-testid="futures-chart-gap-label"[^>]*>([^<]*)<\/text>/g),
  ].map((m) => {
    // `\s` before the name, not `\b`: `\bx=` would match `data-gap-from-x=`.
    const attr = (name: string) => new RegExp(`\\s${name}="([^"]*)"`).exec(m[0])?.[1] ?? "";
    return {
      text: m[1],
      x: Number(attr("x")),
      y: Number(attr("y")),
      fromX: Number(attr("data-gap-from-x")),
      toX: Number(attr("data-gap-to-x")),
      from: attr("data-gap-from"),
      to: attr("data-gap-to"),
      className: attr("class"),
    };
  });
}
const caption = (html: string) =>
  /data-testid="futures-chart-freshness"[^>]*>([^<]*)</.exec(html)?.[1] ?? null;

/** The x coordinates a path visits. */
const xs = (d: string) => [...d.matchAll(/[MLH] (-?[\d.]+)/g)].map((m) => Number(m[1]));
function widestStride(d: string): number {
  const seq = xs(d);
  let w = 0;
  for (let i = 1; i < seq.length; i += 1) w = Math.max(w, Math.abs(seq[i] - seq[i - 1]));
  return w;
}

// ── fixtures ────────────────────────────────────────────────────────────────

/** Hourly captures with ONE 37 h hole in the middle — Alex's own example. */
const ONE_HOLE = one(at([...hourly(0, 60), ...hourly(97, 167)], (i) => 0.4 + (i % 4) / 100));

/** The same week with a 90 min skipped beat instead — under the 2 h floor. */
const SKIPPED_BEAT = one(
  at([...hourly(0, 60), 61.5, ...hourly(63, 167)], (i) => 0.4 + (i % 4) / 100),
);

/**
 * Denver December snow, "Above 8 inches": a venue-bank line (the 12 h floor
 * applies, #11929 B) with four holes of 15.6 / 18 / 19 / 18 h, one of them
 * leaving a single reading alone between two holes.
 */
const DENVER_HOURS: number[] = (() => {
  const out: number[] = [];
  let h = 0;
  const step = (n: number, gap: number) => {
    for (let i = 0; i < n; i += 1) {
      out.push(h);
      h += gap;
    }
  };
  step(8, 2); // a run
  h += 15.6 - 2;
  step(1, 2); // a reading alone between two holes
  h += 18 - 2;
  step(8, 2);
  h += 19 - 2;
  step(6, 2);
  h += 18 - 2;
  step(8, 2);
  return out;
})();
const DENVER = one(
  at(DENVER_HOURS, (i) => 0.2 + (i % 5) / 50, { bookmaker: "kalshi", provenance: "venue_history" }),
  "Above 8 inches",
);

/** Three holes, far apart on a long window, each wide enough to label. */
const THREE_HOLES = one(
  at(
    [...hourly(0, 20), ...hourly(60, 80), ...hourly(120, 140), ...hourly(180, 200)],
    (i) => 0.5 + (i % 3) / 100,
  ),
);

/** A dense hourly week — the healthy shape every surface plots most days. */
const DENSE = one(at(hourly(0, 167), (i) => 0.4 + (i % 5) / 100));

// ── a hole ──────────────────────────────────────────────────────────────────

describe("#11929 C — a hole carries the caption's sentence, not a connector", () => {
  test("one label, the caption's own words, over the gap", () => {
    const html = render(ONE_HOLE);
    const [label, ...rest] = labels(html);

    expect(rest).toEqual([]);
    expect(label.text).toBe("No numbers for 37 hours in this stretch");
    // The caption under the plot names the same hole in the same sentence.
    expect(caption(html)).toBe(label.text);

    // Over the gap: centred on the stretch between the two bracketing readings.
    expect(label.from).toBe(new Date(START + 60 * HOUR).toISOString());
    expect(label.to).toBe(new Date(START + 97 * HOUR).toISOString());
    expect(label.toX - label.fromX).toBeGreaterThan(100);
    expect(label.x).toBeCloseTo((label.fromX + label.toX) / 2, 6);
    // Inside the plot frame (top 20, floor 160 at the default height).
    expect(label.y).toBeGreaterThan(20);
    expect(label.y).toBeLessThan(160);
  });

  test("no connector: nothing is stroked across the hole", () => {
    const html = render(ONE_HOLE);
    expect(connectors(html)).toEqual([]);
    expect(solid(html)).toHaveLength(2);
    const [label] = labels(html);
    for (const p of seriesPaths(html)) {
      expect(widestStride(p.d)).toBeLessThan(label.toX - label.fromX);
    }
  });

  test("the label wears the caption's tokens, never a raw colour", () => {
    const [label] = labels(render(ONE_HOLE));
    expect(label.className.split(" ")).toEqual(
      expect.arrayContaining(["text-xs", "fill-text-muted", "stroke-surface-card"]),
    );
    const tag = render(ONE_HOLE).match(/<text[^>]*data-testid="futures-chart-gap-label"[^>]*>/)![0];
    expect(tag).not.toMatch(/#[0-9a-fA-F]{3,6}\b/);
  });

  test("step interpolation: still labelled, still no connector", () => {
    const html = render(ONE_HOLE, { stepInterpolation: true });
    expect(labels(html).map((l) => l.text)).toEqual(["No numbers for 37 hours in this stretch"]);
    expect(connectors(html)).toEqual([]);
  });

  test("two lines sharing one hole carry ONE label, not one each", () => {
    const html = render([
      { outcome_id: 1, name: "A", history: ONE_HOLE[0].history },
      {
        outcome_id: 2,
        name: "B",
        history: ONE_HOLE[0].history.map((p) => ({ ...p, probability: 0.2 })),
      },
    ]);
    expect(labels(html).map((l) => l.text)).toEqual(["No numbers for 37 hours in this stretch"]);
    expect(connectors(html)).toEqual([]);
    expect(solid(html)).toHaveLength(4);
  });
});

describe("#11929 C — a gap under the threshold is one line", () => {
  test("a 90 min skipped beat: one continuous stroke, no label, no caption", () => {
    const html = render(SKIPPED_BEAT);
    expect(solid(html)).toHaveLength(1);
    expect(labels(html)).toEqual([]);
    expect(connectors(html)).toEqual([]);
    expect(html).not.toContain("futures-chart-gap-labels");
    expect(caption(html)).toBeNull();
  });

  test("a venue-bank joint under 12 h is not a hole either", () => {
    const html = render(
      one(at([...hourly(0, 60), ...hourly(71, 167)], () => 0.3, { provenance: "venue_history" })),
    );
    expect(solid(html)).toHaveLength(1);
    expect(labels(html)).toEqual([]);
  });
});

describe("#11929 C — several holes, several labels", () => {
  test("three far-apart holes: three labels, each over its own hole, none overlapping", () => {
    const html = render(THREE_HOLES);
    const ls = labels(html);

    expect(ls.map((l) => l.text)).toEqual([
      "No numbers for 40 hours in this stretch",
      "No numbers for 40 hours in this stretch",
      "No numbers for 40 hours in this stretch",
    ]);
    expect(new Set(ls.map((l) => l.from)).size).toBe(3);
    for (const l of ls) {
      expect(l.x).toBeGreaterThanOrEqual(l.fromX);
      expect(l.x).toBeLessThanOrEqual(l.toX);
    }
    expect(connectors(html)).toEqual([]);
    expect(solid(html)).toHaveLength(4);
  });

  test("Denver snow: every hole is a break, no connector; the largest is labelled", () => {
    const html = render(DENVER);
    const ls = labels(html);

    expect(connectors(html)).toEqual([]);
    // Four holes → five pieces (one of them the lone reading).
    expect(solid(html)).toHaveLength(5);
    expect(ls.length).toBeGreaterThanOrEqual(1);
    expect(ls.length).toBeLessThanOrEqual(4);
    expect(ls.map((l) => l.text)).toContain("No numbers for 19 hours in this stretch");
    // Every label names a distinct hole and sits in the plot.
    expect(new Set(ls.map((l) => l.from)).size).toBe(ls.length);
    for (const l of ls) {
      expect(l.y).toBeGreaterThan(20);
      expect(l.y).toBeLessThan(160);
    }
  });
});

describe("#11929 C — what must not move", () => {
  test("a reading alone between two holes keeps its dot", () => {
    expect(dots(render(DENVER))).toHaveLength(1);
  });

  test("a settled line ends at its last real reading, with its mark there and no extra label", () => {
    const LAST = START + 167 * HOUR;
    const settledAt = LAST + 30 * 24 * HOUR; // a settlement stamp a month later
    const settledField: FuturesOutcomeHistory[] = [
      {
        outcome_id: 1,
        name: "Yes",
        history: [...ONE_HOLE[0].history, pt(settledAt, 1, { bookmaker: "settlement" })],
      },
    ];
    // The result mark's own glyph is a `<path>` too; set the mark aside to
    // compare the series strokes.
    const withoutMarks = (html: string) =>
      html.replace(/<g data-testid="futures-chart-result-mark"[\s\S]*?<\/g>/g, "");
    const fullSettled = render(settledField, { settled: true });
    const settledHtml = withoutMarks(fullSettled);
    const openHtml = render(ONE_HOLE);

    // The same strokes, the same single label — the settlement point opens no hole.
    expect(solid(settledHtml)).toEqual(solid(openHtml));
    expect(labels(settledHtml)).toEqual(labels(openHtml));
    // The result mark sits on the last real reading (right edge, 780).
    expect(fullSettled).toMatch(/data-testid="futures-chart-result-mark"[^>]*data-anchor="last-observation"/);
    expect(fullSettled).toMatch(/<circle cx="780"[^>]*r="6"/);
  });

  test("control: a dense series is one stroke, byte-identical to the old inline path", () => {
    const html = render(DENSE);
    const [run, ...rest] = solid(html);
    expect(rest).toEqual([]);

    // The pre-#3659 inline expression, re-implemented: x across 730 units of
    // plot from 50, y on the fixed 0–100 axis over 140 units from 20.
    const span = 167 * HOUR;
    const old = DENSE[0].history
      .map((p, i) => {
        const t = Date.parse(p.timestamp);
        const x = 50 + ((t - START) / span) * 730;
        const y = 20 + (1 - p.probability!) * 140;
        return `${i === 0 ? "M" : "L"} ${x} ${y}`;
      })
      .join(" ");
    expect(run.d).toBe(old);
    expect(labels(html)).toEqual([]);
    expect(html).not.toContain("futures-chart-gap-labels");
    expect(connectors(html)).toEqual([]);
    expect(dots(html)).toEqual([]);
  });

  test("mini sparklines keep their faint bridge and print no sentence", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={ONE_HOLE} mini />);
    expect(connectors(html)).toHaveLength(1);
    expect(labels(html)).toEqual([]);
  });
});
