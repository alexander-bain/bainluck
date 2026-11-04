/**
 * #11929 — once the fuller history arrives, the chart draws a line, not dots
 * joined by dashes.
 *
 * Production 2026-11-04 ~05:1xZ, `/api/futures/109085/history?hours=168`
 * (Kansas Senate) after its venue fill landed: the leading line held 411 points
 * — 388 from the venue's bank, 23 captures — with gaps of 1 min at the median
 * and 2–8 h across the flat joints the bank compacts (up to 12 h,
 * `VENUE_BANK_MAX_JOINT_SECONDS`). Six times a 1-minute median is the 2 h floor,
 * so the chart drew 21 runs, 20 dotted bridges and 8 lone dots over a week the
 * venue observed end to end. The fixture below is that shape.
 *
 * Pinned: a bank line breaks only past the bank's 12 h joint (at / above /
 * below); a bridge never slopes; the caption breaks where the line does; a
 * capture-only line keeps today's rule; a dense series and the fixed 0–100 axis
 * render exactly as before.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { FuturesChart } from "../../components/FuturesChart";
import { chartSeriesPath, type PlottedPoint } from "../../lib/chartSeriesPath";
import { VENUE_BANK_JOINT_MS, venueBankGapFloorMs } from "../../lib/seriesFreshness";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "../../lib/types";

const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const NOW = Date.UTC(2026, 10, 4, 5, 0, 0);
const START = NOW - 168 * HOUR; // fixed anchor — never Date.now()

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => {
  jest.useRealTimers();
});

function pt(at: number, p: number, provenance?: string | null): FuturesHistoryPoint {
  return {
    timestamp: new Date(at).toISOString(),
    probability: p,
    american_odds: null,
    bookmaker: provenance ? "kalshi" : "consensus",
    ...(provenance ? { provenance } : {}),
  };
}

/** 109085's shape: six days of 2–8 h flat joints, then the bank's minute tier. */
function bankLine(provenance: string | null = "venue_history"): FuturesHistoryPoint[] {
  const joints = [4.1, 7.9, 3.4, 6.8, 2.5, 5.2, 4.0, 3.2]; // hours, as measured
  const out: FuturesHistoryPoint[] = [];
  let at = START;
  let i = 0;
  while (at < NOW - 150 * MIN) {
    out.push(pt(at, i < 10 ? 0.395 : 0.505, provenance));
    at += joints[i % joints.length] * HOUR;
    i += 1;
  }
  for (let m = 149; m >= 0; m -= 1) out.push(pt(NOW - m * MIN, 0.6 + (m % 3) / 100, provenance));
  return out;
}

const line = (history: FuturesHistoryPoint[]): FuturesOutcomeHistory[] => [
  { outcome_id: 1, name: "Adam Hamilton", history },
];

interface DrawnPath {
  d: string;
  dash: string | null;
}

function seriesPaths(html: string): DrawnPath[] {
  const tags = html.match(/<path[^>]*\bd="M [^"]*"[^>]*>/g) ?? [];
  return tags.map((tag) => ({
    d: /\bd="([^"]*)"/.exec(tag)![1],
    dash: /stroke-dasharray="([^"]*)"/.exec(tag)?.[1] ?? null,
  }));
}
const bridges = (html: string) => seriesPaths(html).filter((p) => p.dash === "1 5");
const dots = (html: string) => html.match(/<circle[^>]*\br="3"[^>]*>/g) ?? [];
/** #11929 C: a full chart names each hole instead of bridging it. */
const gapLabels = (html: string) =>
  html.match(/<text[^>]*data-testid="futures-chart-gap-label"[^>]*>/g) ?? [];
const solidRuns = (html: string) => seriesPaths(html).filter((p) => p.dash === null);

function render(history: FuturesHistoryPoint[]) {
  return renderToStaticMarkup(<FuturesChart historyData={line(history)} showAxes fixedYAxis />);
}

describe("#11929 FuturesChart — the venue's bank draws as one line", () => {
  test("the filled 109085 shape: no dotted bridges, no lone dots, one stroke", () => {
    const html = render(bankLine());
    expect(bridges(html)).toHaveLength(0);
    expect(dots(html)).toHaveLength(0);
    expect(seriesPaths(html).filter((p) => p.dash === null)).toHaveLength(1);
  });

  test("control: the same instants as captures keep today's 2 h rule and still break", () => {
    // #11929 C: broken, and labelled rather than bridged.
    const html = render(bankLine(null));
    expect(solidRuns(html).length).toBeGreaterThan(5);
    expect(gapLabels(html).length).toBeGreaterThan(0);
    expect(bridges(html)).toHaveLength(0);
  });

  test("the caption breaks where the line does — no hole claimed across a bank joint", () => {
    expect(render(bankLine())).not.toContain("No numbers for");
    expect(render(bankLine(null))).toContain("No numbers for");
  });

  test("a hole wider than the bank's joint still breaks, and the caption names it", () => {
    const holed = bankLine().filter((p) => {
      const t = Date.parse(p.timestamp);
      return t < START + 40 * HOUR || t > START + 70 * HOUR; // ~30 h with nothing
    });
    const html = render(holed);
    // #11929 C: two strokes and one label over the hole — no connector.
    expect(solidRuns(html)).toHaveLength(2);
    expect(gapLabels(html)).toHaveLength(1);
    expect(bridges(html)).toHaveLength(0);
    expect(html).toContain('data-series-state="gapped"');
  });

  test("the fixed 0–100 axis is unchanged by the bank floor", () => {
    for (const html of [render(bankLine()), render(bankLine(null))]) {
      expect(html).toContain(">100%<");
      expect(html).toContain(">0%<");
    }
  });

  test("control: an already-dense series renders byte-for-byte as it does today", () => {
    const hourly = Array.from({ length: 168 }, (_, i) => pt(START + i * HOUR, 0.4 + (i % 5) / 100));
    const asBank = hourly.map((p) => ({ ...p, provenance: "venue_history" }));
    expect(seriesPaths(render(asBank))).toEqual(seriesPaths(render(hourly)));
    expect(bridges(render(hourly))).toHaveLength(0);
  });
});

describe("#11929 chartSeriesPath — the bank floor, at / above / below", () => {
  /** Minute cadence for an hour, a gap of `gapMs`, minute cadence again. */
  function withGap(gapMs: number): PlottedPoint[] {
    const ts = [
      ...Array.from({ length: 60 }, (_, i) => START + i * MIN),
      ...Array.from({ length: 60 }, (_, i) => START + 59 * MIN + gapMs + i * MIN),
    ];
    return ts.map((t, i) => ({ t, x: (t - START) / MIN, y: i < 60 ? 60 : 40 }));
  }
  const floor = { gapFloorMs: VENUE_BANK_JOINT_MS };

  test("the floor is the bank's 12 h joint, and only for points carrying the bank", () => {
    expect(VENUE_BANK_JOINT_MS).toBe(12 * HOUR);
    expect(venueBankGapFloorMs([{ provenance: "venue_history" }, {}])).toBe(12 * HOUR);
    expect(venueBankGapFloorMs([{}, { provenance: "kalshi_archive" }])).toBeUndefined();
    expect(venueBankGapFloorMs(null)).toBeUndefined();
  });

  test("below: an 11 h joint is not a hole", () => {
    expect(chartSeriesPath(withGap(11 * HOUR), floor).bridges).toEqual([]);
  });

  test("at: exactly 12 h is not a hole (only a gap WIDER than the floor splits)", () => {
    expect(chartSeriesPath(withGap(12 * HOUR), floor).bridges).toEqual([]);
  });

  test("above: 12 h and a minute is a hole", () => {
    expect(chartSeriesPath(withGap(12 * HOUR + MIN), floor).bridges).toHaveLength(1);
  });

  test("control: with no floor given, today's 2 h floor still splits a 3 h gap", () => {
    expect(chartSeriesPath(withGap(3 * HOUR)).bridges).toHaveLength(1);
    expect(chartSeriesPath(withGap(3 * HOUR), floor).bridges).toEqual([]);
  });

  test("a bridge never slopes: a hold at the earlier price, a riser at the later instant", () => {
    const points = withGap(20 * HOUR);
    const { bridges: [bridge] } = chartSeriesPath(points, floor);
    const before = points[59];
    const after = points[60];
    expect(before.y).not.toBe(after.y);
    expect(bridge).toBe(`M ${before.x} ${before.y} H ${after.x} V ${after.y}`);
    expect(bridge).not.toMatch(/ L /);
  });
});
