/**
 * #11929 — A SOLID LINE THROUGH UNOBSERVED TIME.
 *
 * Alex, 2026-11-04 12:09 PM PT (#11929):
 *
 *   "A solid line through unobserved time. A hole between two observations is
 *    drawn like any other segment of that line (the chart's normal
 *    interpolation): no bridge, no dotted treatment, no label, and the
 *    caption's 'No numbers for N hours' sentence goes with it — nothing on the
 *    chart calls the reader's attention to a gap."
 *
 * This supersedes #3659 (the dotted bridge) and the hole half of #2961/#6331
 * (the "No numbers for …" caption). The gaps themselves are the bug, closed at
 * the source; the chart does not confess them.
 *
 * ═══ THE SPECIMENS (shapes, constructed — labelled as such) ═══
 *
 *   • 34277822-shaped: two lines; one has a 37-day hole between readings, the
 *     other is observed straight through.
 *   • 108629-shaped: ten lines, each an hourly run, then a multi-day hole, then
 *     an hourly run up to now.
 *
 * Each renders with zero bridges, zero "No numbers for" text, and each line as
 * ONE path whose vertices are every observation, in time order, at the x its
 * timestamp scales to — the hole is just one more segment.
 *
 * ═══ CONTROLS (what the ruling does not touch) ═══
 *
 *   • a line behind NOW still prints "Last number …" (its right-hand end, not a
 *     gap);
 *   • a lone single-point series is still a dot;
 *   • settled result marks are still drawn at their leg's last real reading;
 *   • step interpolation steps across the hole like everywhere else.
 *
 * Fixed anchors throughout — never Date.now() (gotcha #44).
 */

import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "../../lib/types";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const NOW = Date.UTC(2026, 10, 4, 19, 0, 0);

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => {
  jest.useRealTimers();
});

function pt(at: number, p: number, bookmaker = "blend"): FuturesHistoryPoint {
  return { timestamp: new Date(at).toISOString(), probability: p, american_odds: null, bookmaker };
}

const range = (n: number) => Array.from({ length: n }, (_, i) => i);

// ─── specimens ──────────────────────────────────────────────────────────────

/** 34277822-shaped: line A holes for 37 days; line B is observed throughout. */
function specimen34277822(end = NOW - 30 * 60 * 1000): FuturesOutcomeHistory[] {
  const start = end - 60 * DAY;
  const before = range(11).map((d) => pt(start + d * DAY, 0.22 + d * 0.002));
  const holeEnd = start + 10 * DAY + 37 * DAY;
  const after = range(53).map((k) => pt(holeEnd + k * 6 * HOUR, 0.41 - k * 0.001));
  const through = range(241).map((k) => pt(start + k * 6 * HOUR, 0.6 + (k % 7) / 200));
  return [
    { outcome_id: 1, name: "Holed", history: [...before, ...after] },
    { outcome_id: 2, name: "Observed", history: through },
  ];
}

/** 108629-shaped: ten lines, 48 hourly readings, a 5-day hole, 24 more to now. */
function specimen108629(): FuturesOutcomeHistory[] {
  const lastRunStart = NOW - 23 * HOUR;
  const firstRunEnd = lastRunStart - 5 * DAY;
  const firstRunStart = firstRunEnd - 47 * HOUR;
  return range(10).map((i) => ({
    outcome_id: 100 + i,
    name: `Candidate ${i + 1}`,
    history: [
      ...range(48).map((h) => pt(firstRunStart + h * HOUR, 0.05 + i * 0.06)),
      ...range(24).map((h) => pt(lastRunStart + h * HOUR, 0.08 + i * 0.06)),
    ],
  }));
}

// ─── markup readers ─────────────────────────────────────────────────────────

const MARK_RE = /<g data-testid="futures-chart-result-mark"[\s\S]*?<\/g>/g;

interface DrawnPath {
  d: string;
  dash: string | null;
  stroke: string | null;
}

/** Every stroked series path (result-mark glyphs removed first). */
function seriesPaths(html: string): DrawnPath[] {
  const tags = html.replace(MARK_RE, "").match(/<path[^>]*\bd="M [^"]*"[^>]*>/g) ?? [];
  return tags.map((tag) => ({
    d: /\bd="([^"]*)"/.exec(tag)![1],
    dash: /stroke-dasharray="([^"]*)"/.exec(tag)?.[1] ?? null,
    stroke: /\bstroke="([^"]*)"/.exec(tag)?.[1] ?? null,
  }));
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

/** No bridge, no dotted treatment, no hole label — anywhere in the markup. */
function expectNothingCallsOutAGap(html: string) {
  expect(html).not.toContain('stroke-dasharray="1 5"');
  expect(html).not.toContain("No numbers for");
  expect(html).not.toContain('data-series-state="gapped"');
}

/**
 * Each outcome is exactly one path, and that path visits every observation in
 * order at the x its own timestamp scales to (linear in time, read off the
 * path's own first and last vertex) — so the segment across the hole joins the
 * two real observations either side of it, like every other segment.
 */
function expectOnePathThroughEveryObservation(html: string, field: FuturesOutcomeHistory[]) {
  const drawn = seriesPaths(html);
  expect(drawn).toHaveLength(field.length);
  field.forEach((o, idx) => {
    const line = drawn[idx];
    expect(line.dash).toBeNull();
    const v = vertices(line.d);
    const ts = o.history.map((p) => Date.parse(p.timestamp));
    expect(v).toHaveLength(ts.length);
    const t0 = ts[0];
    const scale = (v[v.length - 1][0] - v[0][0]) / (ts[ts.length - 1] - t0);
    v.forEach(([x], k) => expect(x).toBeCloseTo(v[0][0] + (ts[k] - t0) * scale, 2));
  });
}

/** The index of the widest gap in a series — the hole. */
function holeIndex(history: FuturesHistoryPoint[]): number {
  let at = 0;
  let widest = -1;
  for (let k = 1; k < history.length; k += 1) {
    const g = Date.parse(history[k].timestamp) - Date.parse(history[k - 1].timestamp);
    if (g > widest) {
      widest = g;
      at = k;
    }
  }
  return at;
}

// ─── the ship ───────────────────────────────────────────────────────────────

describe("#11929 the 34277822 shape — a 37-day hole is one segment of a solid line", () => {
  const field = specimen34277822();

  test("full chart: zero bridges, no hole label, one path per line through every observation", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={field} showAxes />);
    expectNothingCallsOutAGap(html);
    expectOnePathThroughEveryObservation(html, field);
  });

  test("the hole segment is a plain `L` joining the observations either side of it", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={field} showAxes />);
    const holed = seriesPaths(html)[0];
    const v = vertices(holed.d);
    const k = holeIndex(field[0].history);
    // 37 of 60 days: the segment covers well over half the plot's 730px.
    expect(v[k][0] - v[k - 1][0]).toBeGreaterThan(0.55 * 730);
    // The two observations differ in price, so the segment is a real join, not
    // a coincidence of two equal y's.
    expect(v[k][1]).not.toBeCloseTo(v[k - 1][1], 1);
    expect(holed.d).toContain(`L ${v[k][0]} ${v[k][1]}`);
  });

  test("mini chart: zero bridges, one path per line", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={field} mini />);
    expectNothingCallsOutAGap(html);
    expectOnePathThroughEveryObservation(html, field);
  });

  test("step interpolation steps across the hole like everywhere else", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={field} showAxes stepInterpolation fixedYAxis />,
    );
    expectNothingCallsOutAGap(html);
    expectOnePathThroughEveryObservation(html, field);
    for (const p of seriesPaths(html)) expect(p.d).not.toMatch(/ L /);
  });
});

describe("#11929 the 108629 shape — ten lines, an hourly run, then a multi-day hole", () => {
  const field = specimen108629();
  // All ten selected: with none selected the chart draws only its first few
  // lines (`visibleChartOutcomes`), and every one of the ten must be checked.
  const all = new Set(field.map((o) => o.outcome_id));

  test("full chart: zero bridges, no hole label, ten paths each through every observation", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={field} selectedOutcomes={all} showAxes />);
    expectNothingCallsOutAGap(html);
    expectOnePathThroughEveryObservation(html, field);
    // A hole is not a lone observation: nothing is marked.
    expect(html).not.toMatch(/<circle[^>]*\br="3"/);
  });

  test("mini chart: zero bridges, ten paths", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={field} selectedOutcomes={all} mini />);
    expectNothingCallsOutAGap(html);
    expectOnePathThroughEveryObservation(html, field);
  });
});

// ─── controls ───────────────────────────────────────────────────────────────

describe("#11929 controls — what the ruling leaves alone", () => {
  test("a line behind NOW still says how old its last number is", () => {
    // Both lines end ~9 h before NOW on a 6-hourly cadence → `stale`.
    const field = specimen34277822(NOW - 30 * HOUR);
    const html = renderToStaticMarkup(<FuturesChart historyData={field} showAxes />);
    expect(html).toContain('data-series-state="stale"');
    expect(html).toMatch(/Last number \d+ (hours|day|days) ago/);
    expectNothingCallsOutAGap(html);
    expectOnePathThroughEveryObservation(html, field);
  });

  test("a lone single-point series is still a dot", () => {
    const field = [
      ...specimen34277822(),
      { outcome_id: 3, name: "Alone", history: [pt(NOW - 2 * DAY, 0.1)] },
    ];
    const html = renderToStaticMarkup(<FuturesChart historyData={field} showAxes />);
    expectNothingCallsOutAGap(html);
    const lone = seriesPaths(html)[2];
    expect(lone.d).toMatch(/^M ([\d.]+) ([\d.]+) L \1 \2$/);
    expect(html.match(/<circle[^>]*\br="3"[^>]*>/g) ?? []).toHaveLength(1);
  });

  test("settled result marks are still drawn at each graded leg's last real reading", () => {
    const base = specimen34277822();
    const lastReal = (o: FuturesOutcomeHistory) => Date.parse(o.history[o.history.length - 1].timestamp);
    const field: FuturesOutcomeHistory[] = [
      { ...base[0], history: [...base[0].history, pt(lastReal(base[0]) + HOUR, 1, "settlement")] },
      { ...base[1], history: [...base[1].history, pt(lastReal(base[1]) + HOUR, 0, "settlement")] },
    ];
    const html = renderToStaticMarkup(<FuturesChart historyData={field} showAxes settled />);
    expectNothingCallsOutAGap(html);

    const marks = (html.match(MARK_RE) ?? []).map((g) => ({
      outcome: Number(/data-outcome-id="(\d+)"/.exec(g)?.[1]),
      result: /data-result="([a-z]+)"/.exec(g)?.[1],
      cx: Number(/<circle[^>]*cx="([-\d.]+)"/.exec(g)?.[1]),
      cy: Number(/<circle[^>]*cy="([-\d.]+)"/.exec(g)?.[1]),
    }));
    expect(marks.map((m) => [m.outcome, m.result])).toEqual([
      [1, "won"],
      [2, "lost"],
    ]);
    // The settlement points are not drawn as line vertices; the marks sit on
    // each line's own last real vertex.
    const drawn = seriesPaths(html);
    expect(drawn).toHaveLength(2);
    marks.forEach((m, i) => {
      const v = vertices(drawn[i].d);
      expect(v).toHaveLength(base[i].history.length);
      expect(m.cx).toBeCloseTo(v[v.length - 1][0], 5);
      expect(m.cy).toBeCloseTo(v[v.length - 1][1], 5);
    });
  });
});

describe("#11929 /politics — the trend note names no hole", () => {
  const src = readFileSync(join(__dirname, "../../app/politics/page.tsx"), "utf8");

  test("the 'longest is N days' hole sentence is gone", () => {
    // Read for the COPY, not prose: #7250's comment still quotes the old
    // sentence as history.
    expect(src).not.toContain("the longest is ${");
    expect(src).not.toContain("`Dimmed trend lines have stretches we have no numbers for");
    expect(src).not.toMatch(/\bformatGapSpan\(|\bseriesHasHole\(/);
    // The control sentence for a line behind now survives.
    expect(src).toContain("Dimmed trend lines are missing recent numbers.");
  });

  test("every seriesFreshness call on the page uses the never-a-hole floor", () => {
    const calls = src.match(/seriesFreshness\([^;]*/g) ?? [];
    expect(calls.length).toBeGreaterThanOrEqual(2);
    for (const c of calls) expect(c).toContain("NEVER_A_HOLE_MS");
  });
});
