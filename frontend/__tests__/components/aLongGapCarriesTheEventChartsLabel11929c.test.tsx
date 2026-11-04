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
 *   • a hole wide enough for its sentence renders it inside the gap and no
 *     connector;
 *   • a hole too narrow for its sentence renders NO label and keeps its faint
 *     bridge — a label never covers readings (production 2026-11-04: Denver's
 *     3-day hole at the right edge slid its label left over a week of data);
 *   • a sub-threshold gap draws one continuous line and no label;
 *   • several holes → a label inside each hole wide enough, a bridge across
 *     each one that is not;
 *   • lone real points stay dots;
 *   • a settled line still ends at its last real observation, with its result
 *     mark there, and its settlement point never opens a labelled hole;
 *   • control: a dense series renders exactly as on B's branch.
 *
 * Fixed anchors throughout — never Date.now() (gotcha #44).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { FuturesChart } from "../../components/FuturesChart";
import { gapLabelWidth } from "../../lib/chartGapLabels";
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

/**
 * Hourly captures with ONE 37 h hole in the middle — Alex's own example — on a
 * 97 h window, so the hole is 38% of the plot (278 units) and its 250-unit
 * sentence fits inside it. On a full week the same hole is 161 units: too
 * narrow, so it would keep its bridge instead (pinned below).
 */
const ONE_HOLE = one(at([...hourly(70, 100), ...hourly(137, 167)], (i) => 0.4 + (i % 4) / 100));

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

/**
 * Three holes on one line: 70 h, 35 h, 70 h over a 195 h window. The two 70 h
 * holes are 262 units, room for "No numbers for 3 days in this stretch" (237);
 * the 35 h hole between them is 131 units, too narrow for its sentence.
 */
const THREE_HOLES = one(
  at(
    [...hourly(0, 5), ...hourly(75, 80), ...hourly(115, 120), ...hourly(190, 195)],
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
    expect(label.from).toBe(new Date(START + 100 * HOUR).toISOString());
    expect(label.to).toBe(new Date(START + 137 * HOUR).toISOString());
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
  test("three holes: a label inside each wide one, none overlapping; the narrow one keeps its bridge", () => {
    const html = render(THREE_HOLES);
    const ls = labels(html);

    expect(ls.map((l) => l.text)).toEqual([
      "No numbers for 3 days in this stretch",
      "No numbers for 3 days in this stretch",
    ]);
    expect(ls.map((l) => l.from)).toEqual([
      new Date(START + 5 * HOUR).toISOString(),
      new Date(START + 120 * HOUR).toISOString(),
    ]);
    for (const l of ls) {
      const w = gapLabelWidth(l.text);
      expect(l.x - w / 2).toBeGreaterThanOrEqual(l.fromX);
      expect(l.x + w / 2).toBeLessThanOrEqual(l.toX);
    }
    // The 35 h hole (80 → 115) carries no label but its faint bridge.
    const bridged = connectors(html);
    expect(bridged).toHaveLength(1);
    const xAt = (h: number) => 50 + (h / 195) * 730;
    expect(Math.min(...xs(bridged[0].d))).toBeCloseTo(xAt(80), 6);
    expect(Math.max(...xs(bridged[0].d))).toBeCloseTo(xAt(115), 6);
    expect(solid(html)).toHaveLength(4);
  });

  test("Denver snow: every hole is a break; none is wide enough for its sentence, so none is labelled and each keeps its bridge", () => {
    // 15.6–19 h holes on a 123 h window are 93–113 units; the sentence is ~250.
    const html = render(DENVER);

    expect(labels(html)).toEqual([]);
    expect(html).not.toContain("futures-chart-gap-labels");
    expect(connectors(html)).toHaveLength(4);
    // Four holes → five pieces (one of them the lone reading).
    expect(solid(html)).toHaveLength(5);
  });
});

// ── guard: a label never covers readings (production 2026-11-04) ─────────────

/**
 * Denver December snow (`/futures/65536371`) at 390 px after C shipped: a 3-day
 * hole at the RIGHT edge, narrower than its sentence, so centre-then-clamp slid
 * "No numbers for 3 days in this stretch" left over a week of real readings.
 * Another board clamped its label onto the y-axis — the LEFT-edge mirror.
 *
 * Both fixtures: a 30-day venue-bank line ending at NOW (2 h readings, the 12 h floor), one
 * 11-day hole in the middle wide enough for its sentence (268 units vs 243),
 * and one 3-day hole at the edge (73 units) that is not.
 */
const bank = { bookmaker: "kalshi", provenance: "venue_history" } as const;
const every2h = (from: number, to: number) =>
  Array.from({ length: Math.floor((to - from) / 2) + 1 }, (_, i) => from + 2 * i);
/** The 30-day window opens here and closes at NOW. */
const START_30D = NOW - 720 * HOUR;
const on30d = (hours: readonly number[]) =>
  hours.map((h, i) => pt(START_30D + h * HOUR, 0.3 + (i % 7) / 100, bank));
const DENVER_RIGHT_EDGE = one(
  on30d([...every2h(0, 300), ...every2h(564, 640), ...every2h(712, 720)]),
  "Above 8 inches",
);
const DENVER_LEFT_EDGE = one(
  on30d([...every2h(0, 8), ...every2h(80, 156), ...every2h(420, 720)]),
  "Above 8 inches",
);
/** x of an hour offset on the 720 h window. */
const x720 = (h: number) => 50 + (h / 720) * 730;

/** Every x where the chart draws a real reading: solid-run vertices and lone dots. */
function readingXs(html: string): number[] {
  const fromRuns = solid(html).flatMap((p) => xs(p.d));
  const fromDots = dots(html).map((tag) => Number(/\bcx="([^"]*)"/.exec(tag)![1]));
  return [...fromRuns, ...fromDots];
}

describe("#11929 C guard — a label sits inside its own hole, never over readings", () => {
  for (const [name, data, narrow, wide] of [
    ["right edge (Denver 65536371)", DENVER_RIGHT_EDGE, [640, 712], [300, 564]],
    ["left edge (the y-axis clamp)", DENVER_LEFT_EDGE, [8, 80], [156, 420]],
  ] as const) {
    test(`${name}: no "No numbers" text over any reading`, () => {
      const html = render(data);
      const readings = readingXs(html);
      expect(readings.length).toBeGreaterThan(100);
      for (const l of labels(html)) {
        const w = gapLabelWidth(l.text);
        const covered = readings.filter((x) => x > l.x - w / 2 && x < l.x + w / 2);
        expect({ label: l.text, covered }).toEqual({ label: l.text, covered: [] });
      }
    });

    test(`${name}: the narrow hole has no label and draws its faint bridge`, () => {
      const html = render(data);
      const from = new Date(START_30D + narrow[0] * HOUR).toISOString();
      expect(labels(html).filter((l) => l.from === from)).toEqual([]);
      const bridged = connectors(html);
      expect(bridged).toHaveLength(1);
      expect(Math.min(...xs(bridged[0].d))).toBeCloseTo(x720(narrow[0]), 6);
      expect(Math.max(...xs(bridged[0].d))).toBeCloseTo(x720(narrow[1]), 6);
    });

    test(`${name}: the wide hole carries its label, centred within the hole`, () => {
      const html = render(data);
      const [l, ...rest] = labels(html);
      expect(rest).toEqual([]);
      expect(l.text).toBe("No numbers for 11 days in this stretch");
      expect(l.from).toBe(new Date(START_30D + wide[0] * HOUR).toISOString());
      expect(l.to).toBe(new Date(START_30D + wide[1] * HOUR).toISOString());
      expect(l.x).toBeCloseTo((x720(wide[0]) + x720(wide[1])) / 2, 6);
      const w = gapLabelWidth(l.text);
      expect(l.x - w / 2).toBeGreaterThanOrEqual(x720(wide[0]));
      expect(l.x + w / 2).toBeLessThanOrEqual(x720(wide[1]));
      expect(caption(html)).toBe(l.text);
    });
  }
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
