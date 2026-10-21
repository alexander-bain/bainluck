/**
 * #11356 — one probability line between the two team poles, an automatic zoom
 * that tells the truth about its edges, and a Sources disclosure that adds the
 * vendor lines without swapping the chart for another one.
 *
 * Alex, on /events/14780562 (Packers–Cowboys, final 23–13): collapsed, two
 * team-coloured complementary lines; opening Sources removed one, changed the
 * main line's colour, brought back the gutter and changed the scale. "The
 * disclosure feels like switching charts."
 *
 * Inputs are the Event page design packet's retained real rows
 * (REAL-CHART-CASES.json, sha256 9b64d888…, copied verbatim into
 * `fixtures/chartSingleTrajectory11356.json` with their original indexes),
 * fed through the CURRENT chart pipeline — bucketing, sorting, admission,
 * gaps. Nothing here sorts, retimes or drops a row to make a case pass:
 *
 *   close-crossing  Jaguars–Eagles 14639175, 14:35–15:05Z. Blend 48.98–71.78%,
 *                   vendors down to 36.76% and up to 72.62%.
 *   one-side        Bears–Eagles 14780549, 02:25–02:55Z. Blend 78.5–99.5%.
 *   reversal-final  the same game's whole retained final, including the record
 *                   stamped 03:30 that arrives BEFORE an appended 03:12 one.
 *
 * Static markup cannot click, so "Sources open" is the chart rendered with
 * `defaultSourcesExpanded`; the toggle itself is exercised in the browser.
 *
 * 🪤 recharts draws nothing inside a `ResponsiveContainer` without a viewport,
 * so it is mocked to 390×300, as in `oddsChartDrawsRecordedCheckpoints4974`.
 */

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

import { Line } from "recharts";

import OddsChart, { calloutLabelCenterY, lineYExtentBetween } from "@/components/OddsChart";
import { AnalyticsProvider } from "@/components/Analytics";
import { teamAxisEdges, teamAxisTick } from "@/lib/eventKeyStats";
import { sourceHex } from "@/lib/sourceColors";
import cases from "../fixtures/chartSingleTrajectory11356.json";

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

type Case = (typeof cases.cases)[number];
const byName = (name: string): Case => {
  const c = cases.cases.find((x) => x.case === name);
  if (!c) throw new Error(`no case ${name}`);
  return c;
};
const CLOSE = byName("close-crossing");
const ONE_SIDE = byName("one-side");
const FINAL = byName("reversal-final-order-refusal");

const BLEND = sourceHex("blend");
type ChartProps = Partial<React.ComponentProps<typeof OddsChart>>;

function chart(c: Case, over: ChartProps = {}): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={[]}
        homeTeam={c.home_team}
        awayTeam={c.away_team}
        sportKey="americanfootball_nfl"
        commenceTime={c.window.start}
        eventStatus={c.captured_status}
        isLive={false}
        winProbHistory={c.win_prob_history as never}
        aggregateLine={c.aggregate_line as never}
        backendBlendServed
        homeTeamColor="#006778"
        awayTeamColor="#004C54"
        chartStartTime={c.window.start}
        chartEndTime={c.window.end}
        externalTimeRange="all"
        {...over}
      />,
    ),
  )
    .replace(/recharts\d+-clip/g, "recharts#-clip")
    .replace(/recharts-(line|scatter)-\d+/g, "recharts-$1-#");
}

interface Curve {
  stroke: string;
  width: number;
  opacity: number;
  d: string;
}
function curves(html: string): Curve[] {
  return [...html.matchAll(/<path[^>]*recharts-line-curve[^>]*>/g)].map(([tag]) => ({
    stroke: /stroke="([^"]+)"/.exec(tag)?.[1] ?? "",
    width: Number(/stroke-width="([^"]+)"/.exec(tag)?.[1] ?? "0"),
    opacity: Number(/stroke-opacity="([^"]+)"/.exec(tag)?.[1] ?? "1"),
    d: /\sd="([^"]+)"/.exec(tag)?.[1] ?? "",
  }));
}
const solid = (cs: Curve[]) => cs.filter((c) => !/stroke-dasharray/.test(c.d));
const blendCurve = (html: string) => {
  const found = curves(html).filter((c) => c.stroke === BLEND && c.width === 3);
  if (found.length !== 1) throw new Error(`expected one blend curve, found ${found.length}`);
  return found[0];
};
const vertices = (d: string) =>
  [...d.matchAll(/[ML](-?[\d.]+),(-?[\d.]+)/g)].map((m) => [Number(m[1]), Number(m[2])]);

/** The tick values (the home side's 0–100 axis), bottom to top. */
const axis = (html: string) => [...html.matchAll(/data-axis-value="(\d+(?:\.\d+)?)"/g)].map((m) => Number(m[1]));
const domain = (html: string): [number, number] => {
  const ticks = axis(html);
  return [Math.min(...ticks), Math.max(...ticks)];
};
const tickTexts = (html: string) =>
  [...html.matchAll(/data-axis-tick-side="(home|away|even)" data-axis-value="(\d+)"><tspan[^>]*>([^<]*)<\/tspan>/g)].map(
    (m) => ({ side: m[1], value: Number(m[2]), text: m[3] }),
  );
const attr = (html: string, name: string) => new RegExp(`${name}="([^"]*)"`).exec(html)?.[1] ?? null;

const pct = (p: number) => p * 100;
const extent = (pts: Array<{ home_probability: number }>) => {
  const v = pts.map((p) => pct(p.home_probability));
  return [Math.min(...v), Math.max(...v)];
};
const vendorExtent = (c: Case) => extent(Object.values(c.win_prob_history).flat() as Array<{ home_probability: number }>);

describe("the fixture is the packet's retained rows, unchanged", () => {
  it("carries the packet's hash and the real extents the brief quotes", () => {
    expect(cases.source_sha256).toBe("9b64d88858b2c92d22de434f9767ad43c0590975d46d3f8ee03f9cb9a9761c64");
    const [lo, hi] = extent(CLOSE.aggregate_line);
    expect(lo).toBeCloseTo(48.9777, 3);
    expect(hi).toBeCloseTo(71.7791, 3);
    const [vlo, vhi] = vendorExtent(CLOSE);
    expect(vlo).toBeCloseTo(36.76, 2);
    expect(vhi).toBeCloseTo(72.62, 2);
    expect(extent(ONE_SIDE.aggregate_line)).toEqual([78.5, 99.5]);
  });

  it("keeps the final's out-of-order record exactly as retained (no sort, no drop)", () => {
    expect(FINAL.chronology_gate).toBe("FAIL");
    const i = FINAL.aggregate_line.findIndex((p) => p.original_index === 4315);
    expect(FINAL.aggregate_line[i].timestamp).toBe("2026-09-29T03:30:00+00:00");
    expect(FINAL.aggregate_line[i + 1].timestamp).toBe("2026-09-29T03:12:00+00:00");
    expect(FINAL.aggregate_line[i + 1].home_probability).toBe(1.0);
  });
});

describe("collapsed: exactly one line, the blend, between two named poles", () => {
  const html = chart(CLOSE);

  it("draws the blend alone — no faint vendor line under it, no complementary copy", () => {
    const all = solid(curves(html));
    expect(all).toHaveLength(1);
    expect(all[0].stroke).toBe(BLEND);
    expect(all[0].width).toBe(3);
    expect(html).not.toContain("paired-away-line");
    expect(html).toMatch(/\+\s*(<!-- -->)?\s*4\s*(<!-- -->)?\s*sources/);
  });

  it("names both directions in the gutter, home up and away down", () => {
    expect(html.match(/data-pole="(home|away)"/g)).toEqual(['data-pole="home"', 'data-pole="away"']);
    expect(html).toContain("↑ Jaguars");
    expect(html).toContain("↓ Eagles");
  });

  it("CONTROL: the retired #9483 prop changes nothing — no second line can be asked for", () => {
    expect(chart(CLOSE, { pairedAwayLine: true })).toBe(html);
  });
});

describe("truthful automatic zoom (close game)", () => {
  const closed = chart(CLOSE);
  const opened = chart(CLOSE, { defaultSourcesExpanded: true });
  const [blendLo, blendHi] = extent(CLOSE.aggregate_line);
  const [vendorLo, vendorHi] = vendorExtent(CLOSE);

  it("collapsed: the window holds the blend and is NOT widened by the hidden vendor lines", () => {
    const [lo, hi] = domain(closed);
    expect(lo).toBeLessThanOrEqual(blendLo);
    expect(hi).toBeGreaterThanOrEqual(blendHi);
    // A hidden 36.76% vendor reading would have pulled the floor below it.
    expect(lo).toBeGreaterThan(vendorLo);
    // The blend crosses 50/50, so 50 stays on the axis.
    expect(axis(closed)).toContain(50);
  });

  it("Sources open: the window grows to every revealed vendor high and low", () => {
    const [lo, hi] = domain(opened);
    expect(lo).toBeLessThanOrEqual(vendorLo);
    expect(hi).toBeGreaterThanOrEqual(vendorHi);
    expect(lo).toBeLessThan(domain(closed)[0]);
    expect(axis(opened)).toContain(50);
  });

  it("Sources closed again is the blend's own window, byte for byte", () => {
    expect(chart(CLOSE, { defaultSourcesExpanded: false })).toBe(closed);
  });

  it("a cropped edge prints its own number and never claims a team at 100%", () => {
    const [lo, hi] = domain(closed);
    expect(hi).toBeLessThan(100);
    expect(lo).toBeGreaterThan(0);
    const ticks = tickTexts(closed);
    expect(ticks.map((t) => t.text)).not.toContain("100%");
    expect(attr(closed, "data-axis-top")).toBe(`home:${hi}`);
    expect(attr(closed, "data-axis-bottom")).toBe(`away:${100 - lo}`);
    expect(closed).toContain(`the top of this view is Jaguars at ${hi}%.`);
    expect(closed).toContain(`the bottom of this view is Eagles at ${100 - lo}%.`);
    expect(closed).not.toMatch(/(axis|view) is (Jaguars|Eagles) at 100%/);
  });

  it("each tick prints the chance of the side it sits on, in that side's colour", () => {
    for (const t of tickTexts(opened)) {
      expect(t).toEqual({ ...t, ...teamAxisTick(t.value, true) });
    }
    const sides = new Set(tickTexts(opened).map((t) => t.side));
    expect(sides).toEqual(new Set(["home", "even", "away"]));
  });
});

describe("a revealed source's own swing is never clipped by the zoom (causal control)", () => {
  // Synthetic on purpose — the real close game's vendor extremes already sit
  // inside the true-extremes rule (#7837 rule 1b), so they cannot show this
  // rule biting. Here one source's brief early swing to 92% is under 2% of
  // all the samples the axis sees, which the percentile zoom would trim and
  // clip at the frame. Collapsed it is hidden and must not set the scale;
  // revealed, it must be inside the window.
  const T0 = Date.parse("2026-10-11T14:00:00Z");
  const at = (m: number) => new Date(T0 + m * 60_000).toISOString();
  const wave = (m: number) => 0.5 + 0.08 * Math.sin(m / 9);
  const rows = (f: (m: number) => number) =>
    Array.from({ length: 120 }, (_, m) => ({ timestamp: at(m), home_probability: f(m), away_probability: 1 - f(m) }));
  const swing: Case = {
    ...CLOSE,
    window: { start: at(0), end: at(119) },
    aggregate_line: rows(wave) as never,
    win_prob_history: {
      kalshi: rows((m) => wave(m) + 0.01),
      espn: rows((m) => (m >= 10 && m < 13 ? 0.92 : wave(m) - 0.01)),
    } as never,
  };

  it("collapsed ignores the hidden swing; Sources open puts all of it on the plot", () => {
    const closed = domain(chart(swing));
    expect(closed[1]).toBeLessThan(92);
    const opened = domain(chart(swing, { defaultSourcesExpanded: true }));
    expect(opened[1]).toBeGreaterThanOrEqual(92);
  });
});

describe("Sources keeps the chart's identity and time geometry", () => {
  const closed = chart(CLOSE);
  const opened = chart(CLOSE, { defaultSourcesExpanded: true });

  it("adds each vendor line, legibly, and keeps the blend's colour and weight", () => {
    expect(solid(curves(opened)).length).toBeGreaterThanOrEqual(5);
    expect(blendCurve(opened).stroke).toBe(blendCurve(closed).stroke);
    expect(blendCurve(opened).width).toBe(3);
    for (const c of solid(curves(opened)).filter((x) => x.stroke !== BLEND)) {
      expect(c.width).toBe(1.75);
      expect(c.opacity).toBe(0.85);
    }
  });

  it("the blend's vertices keep their x (time) and their order; only the vertical scale moves", () => {
    const a = vertices(blendCurve(closed).d);
    const b = vertices(blendCurve(opened).d);
    expect(b.length).toBe(a.length);
    for (let i = 0; i < a.length; i++) expect(b[i][0]).toBeCloseTo(a[i][0], 6);
    // The rescale is real (the window grew), and it is monotone: a higher
    // reading is higher on both plots.
    expect(b.some((p, i) => Math.abs(p[1] - a[i][1]) > 1)).toBe(true);
    for (let i = 1; i < a.length; i++) {
      expect(Math.sign(b[i][1] - b[i - 1][1])).toBe(Math.sign(a[i][1] - a[i - 1][1]));
    }
  });

  it("the plot box, gutter and orientation do not move", () => {
    const box = (h: string) => /<clipPath id="recharts#-clip"><rect x="([\d.]+)" y="([\d.]+)" height="([\d.]+)" width="([\d.]+)"/.exec(h)?.slice(1);
    expect(box(opened)).toEqual(box(closed));
    expect(box(closed)).toBeDefined();
    const gutter = (h: string) => /<div class="flex flex-col items-center justify-between py-3 shrink-0" style="width:28px"/.test(h);
    expect(gutter(closed) && gutter(opened)).toBe(true);
    expect(opened.match(/data-pole="(home|away)"/g)).toEqual(closed.match(/data-pole="(home|away)"/g));
  });

  it("the end of the line reads the same reading in both states", () => {
    expect(attr(opened, "data-callout-label")).toBe(attr(closed, "data-callout-label"));
    expect(attr(opened, "data-callout-at")).toBe(attr(closed, "data-callout-at"));
    expect(attr(opened, "data-callout-text")).toBe(attr(closed, "data-callout-text"));
  });
});

describe("an entirely one-sided window", () => {
  const html = chart(ONE_SIDE);

  it("zooms into that side's range and does not force 50/50 in", () => {
    const [lo, hi] = domain(html);
    expect(lo).toBeGreaterThan(50);
    expect(lo).toBeLessThanOrEqual(78.5);
    expect(hi).toBeGreaterThanOrEqual(99.5);
    expect(axis(html)).not.toContain(50);
  });

  it("both directions stay named, and the crop at the bottom is the home side's own number", () => {
    const [lo] = domain(html);
    expect(html).toContain("↑ Bears");
    expect(html).toContain("↓ Eagles");
    expect(attr(html, "data-axis-bottom")).toBe(`home:${lo}`);
    expect(html).toContain(`the bottom of this view is Bears at ${lo}%.`);
    expect(html).not.toMatch(/bottom of this (axis|view) is Eagles/);
    for (const t of tickTexts(html)) expect(t.side).toBe("home");
  });
});

describe("the final, through the current pipeline", () => {
  const html = chart(FINAL);

  it("keeps the existing terminal authority: the same end, at the same instant, as before this change", () => {
    // Characterisation, read on unchanged master 7e60a65a14 with this exact
    // fixture: completed → the line ends at 03:42 printing 100%; the same rows
    // marked live end at 03:42 printing >99%. That terminal rule is the
    // existing pipeline's (the retained final records), not this change's, and
    // the redesign must not move it — in either Sources state.
    expect(attr(html, "data-callout-at")).toBe("2026-09-29T03:42:00.000Z");
    expect(attr(html, "data-callout-label")).toBe("100%");
    const live = chart(FINAL, { eventStatus: "live" });
    expect(attr(live, "data-callout-label")).toBe("&gt;99%");
    const opened = chart(FINAL, { defaultSourcesExpanded: true });
    expect(attr(opened, "data-callout-at")).toBe(attr(html, "data-callout-at"));
    expect(attr(opened, "data-callout-label")).toBe(attr(html, "data-callout-label"));
  });

  it("draws one line, the blend, over the whole game", () => {
    expect(solid(curves(html))).toHaveLength(1);
    expect(blendCurve(html).d.length).toBeGreaterThan(0);
  });

  it("the blend crosses 50/50 in this game, so 50 is on its axis", () => {
    expect(axis(html)).toContain(50);
  });
});

describe("the end label reads like its tick: the side the dot sits on", () => {
  // The same final's retained rows up to 00:31Z, when the Eagles led — a
  // reading window like the packet's own two, selected, never re-ordered. The
  // blend's last row there is 00:30, at 46.24%.
  const END = "2026-09-29T00:31:00+00:00";
  const upTo = <T extends { timestamp: string }>(rows: T[]) => rows.filter((r) => Date.parse(r.timestamp) <= Date.parse(END));
  const early = {
    ...FINAL,
    window: { start: FINAL.window.start, end: END },
    aggregate_line: upTo(FINAL.aggregate_line),
    win_prob_history: Object.fromEntries(Object.entries(FINAL.win_prob_history).map(([k, v]) => [k, upTo(v)])),
  } as unknown as Case;
  const html = chart(early, { eventStatus: "live" });

  it("prints the away side's chance below 50/50, from the same resolved pair as the home label", () => {
    const home = Number(attr(html, "data-callout-label")!.replace("%", ""));
    const printed = Number(attr(html, "data-callout-text")!.replace("%", ""));
    expect(home).toBeLessThan(50);
    expect(printed).toBe(100 - home);
  });
});

describe("draw-priced winner: no away side is ever claimed", () => {
  const html = chart(CLOSE, { awayWithheld: true, sportKey: "soccer_epl" });

  it("keeps the home pole alone and every tick on the home side's chance", () => {
    expect(html.match(/data-pole="(home|away)"/g)).toEqual(['data-pole="home"']);
    expect(html).not.toContain('data-axis-tick-side="away"');
    expect(html).not.toContain('data-axis-tick-side="even"');
    const [lo] = domain(html);
    expect(tickTexts(html).find((t) => t.value === lo)?.text).toBe(`${lo}%`);
  });

  it("the end label is the home side's number", () => {
    expect(attr(html, "data-callout-text")).toBe(attr(html, "data-callout-label"));
  });
});

describe("the full-size view keeps its plot height when Sources opens", () => {
  it("its legend is one row that scrolls sideways; the card's legend still wraps", () => {
    const full = chart(CLOSE, { fillContainer: true, defaultSourcesExpanded: true });
    expect(full).toMatch(/class="flex flex-nowrap[^"]*overflow-x-auto[^"]*"[^>]*data-testid="chart-source-legend"/);
    const card = chart(CLOSE, { defaultSourcesExpanded: true });
    expect(card).toMatch(/class="flex flex-wrap[^"]*"[^>]*data-testid="chart-source-legend"/);
  });
});

describe("teamAxisTick / teamAxisEdges", () => {
  it("full scale: home 100% at the top, 50/50, away 100% at the bottom", () => {
    expect([100, 75, 50, 25, 0].map((v) => teamAxisTick(v, true).text)).toEqual(["100%", "75%", "50%", "75%", "100%"]);
    expect(teamAxisEdges([0, 100], true)).toEqual({
      top: { side: "home", percent: 100, isPole: true },
      bottom: { side: "away", percent: 100, isPole: true },
    });
  });

  it("a crop is never a pole", () => {
    expect(teamAxisEdges([30, 80], true)).toEqual({
      top: { side: "home", percent: 80, isPole: false },
      bottom: { side: "away", percent: 70, isPole: false },
    });
  });

  it("a draw-priced axis prints the home side's chance everywhere, and its 0 is not the away pole", () => {
    expect([100, 50, 0].map((v) => teamAxisTick(v, false))).toEqual([
      { text: "100%", side: "home" },
      { text: "50%", side: "home" },
      { text: "0%", side: "home" },
    ]);
    expect(teamAxisEdges([0, 100], false).bottom).toEqual({ side: "home", percent: 0, isPole: false });
  });
});

describe("the tooltip's hole notes describe drawn lines only", () => {
  // A tooltip only renders under a pointer, which static markup has not got;
  // the browser walk reads it (Bears–Eagles: "Polymarket no readings" under a
  // collapsed blend before, absent after). This pins the gate in source.
  const src = readFileSync(join(__dirname, "..", "..", "components", "OddsChart.tsx"), "utf8");
  const body = src.slice(src.indexOf("const gapNotesAt = "), src.indexOf("const CustomTooltip = "));

  it("returns no note while Sources is closed over the blend", () => {
    // Gated on "hidden behind the blend", never on "source lines drawn": with
    // no blend the one Sportsbooks line is drawn and keeps its hole notes
    // (#7878; behaviour in chartSourcesClosedGatesSourceProse11356).
    expect(body).toMatch(/if \(sourcesHiddenBehindBlend\) return notes;\s*for \(const source of resolvedSources\)/);
    expect(src).toMatch(/const sourcesHiddenBehindBlend = showBlendLine && !legendExpanded;/);
  });
});

describe("the end label does not paint out the line's last stretch at the frame", () => {
  // Read on the candidate's own browser frames of /events/14780562 at 390px:
  // the final climbs to 100% and runs along the top edge, the period strip sits
  // at the bottom, so #5581 moved the label only clear of the edge — onto that
  // stretch. Its white plate (#4338) erased the climb and the line read as
  // ending short of the result. These finals end on the frame the same way.
  const plate = (html: string) => {
    const m = /<rect x="([\d.]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)" rx="3" fill="#FFFFFF"><\/rect><text/.exec(html);
    if (!m) throw new Error("no callout plate");
    const [x, y, w, h] = m.slice(1).map(Number);
    return { x0: x, x1: x + w, top: y, bottom: y + h };
  };
  /** The blend's ink across [x0, x1], interpolated at both edges. */
  const inkBetween = (d: string, x0: number, x1: number) => {
    const v = vertices(d);
    const ys: number[] = [];
    v.forEach(([x, y], i) => {
      if (x >= x0 && x <= x1) ys.push(y);
      const p = v[i - 1];
      if (!p || p[0] === x) return;
      for (const e of [x0, x1]) {
        if (e > Math.min(p[0], x) && e < Math.max(p[0], x)) ys.push(p[1] + ((y - p[1]) * (e - p[0])) / (x - p[0]));
      }
    });
    return { top: Math.min(...ys), bottom: Math.max(...ys) };
  };
  const clear = (html: string) => {
    const box = plate(html);
    const ink = inkBetween(blendCurve(html).d, box.x0, box.x1);
    // 1.5 = half the blend's 3px stroke.
    return ink.bottom + 1.5 <= box.top + 1e-6 || ink.top - 1.5 >= box.bottom - 1e-6;
  };

  it.each([
    ["the final, Sources closed", () => chart(FINAL)],
    ["the final, Sources open", () => chart(FINAL, { defaultSourcesExpanded: true })],
    ["the one-sided window", () => chart(ONE_SIDE)],
  ])("%s: the plate sits clear of the blend's ink", (_name, html) => {
    expect(clear(html())).toBe(true);
  });

  it("CONTROL: off the frame the label still sits on the dot's row (#3561), so the rule did not move it", () => {
    const html = chart(CLOSE);
    const box = plate(html);
    const dot = /<circle cx="[\d.]+" cy="([\d.]+)" r="5"/.exec(html);
    expect(dot).not.toBeNull();
    expect((box.top + box.bottom) / 2).toBeCloseTo(Number(dot![1]), 6);
  });
});

describe("calloutLabelCenterY: stepping off the line is bounded", () => {
  const frame = { plotTop: 15, plotHeight: 250, periodChipRows: 1 };
  const half = (11 * 1.2) / 2 + 2; // the plate's half height
  const atTop = calloutLabelCenterY({ ...frame, cy: 15, periodStripBand: "bottom" });

  it("moved off the top frame onto the line: steps just below the line's ink", () => {
    expect(atTop).toBeCloseTo(15 + half, 6);
    expect(calloutLabelCenterY({ ...frame, cy: 15, periodStripBand: "bottom", avoid: { top: 13.5, bottom: 26 } })).toBeCloseTo(26 + half, 6);
  });

  it("not covering the line: the frame's own answer stands", () => {
    expect(calloutLabelCenterY({ ...frame, cy: 15, periodStripBand: "bottom", avoid: { top: 60, bottom: 90 } })).toBe(atTop);
  });

  it("a step further than two plate heights keeps the frame's answer (the plate overprints, #4338)", () => {
    expect(calloutLabelCenterY({ ...frame, cy: 15, periodStripBand: "bottom", avoid: { top: 13.5, bottom: 120 } })).toBe(atTop);
  });

  it("a taller plot (the full-size view) allows a tenth of its height, so the same climb is cleared there", () => {
    const tall = { plotTop: 15, plotHeight: 626, periodChipRows: 1 };
    const avoid = { top: 13.5, bottom: 61.5 };
    // 46px past the frame's row: over two plate heights, under a tenth of 626.
    expect(calloutLabelCenterY({ ...tall, cy: 15, periodStripBand: "bottom", avoid })).toBeCloseTo(61.5 + half, 6);
    expect(calloutLabelCenterY({ ...frame, cy: 15, periodStripBand: "bottom", avoid })).toBe(atTop);
  });

  it("never steps into the bottom strip", () => {
    const short = { plotTop: 15, plotHeight: 60, periodChipRows: 1 };
    const placed = calloutLabelCenterY({ ...short, cy: 15, periodStripBand: "bottom" });
    expect(calloutLabelCenterY({ ...short, cy: 15, periodStripBand: "bottom", avoid: { top: 13.5, bottom: 50 } })).toBe(placed);
  });

  it("a 0% finish moved up off the bottom frame steps ABOVE the line", () => {
    const bottom = 15 + 250;
    expect(
      calloutLabelCenterY({ plotTop: 15, plotHeight: 250, periodChipRows: 0, cy: bottom, avoid: { top: 240, bottom: bottom + 1.5 } }),
    ).toBeCloseTo(240 - half, 6);
  });

  it("a label already on the dot's row ignores the line entirely (#3561's halo rule)", () => {
    expect(calloutLabelCenterY({ ...frame, cy: 120, periodStripBand: "bottom", avoid: { top: 100, bottom: 140 } })).toBe(120);
  });
});

describe("lineYExtentBetween", () => {
  const state = (dataKey: unknown, points: Array<{ x: number; y: number | null }>) => ({
    formattedGraphicalItems: [{ item: { type: Line, props: { dataKey } }, props: { points } }],
  });

  it("reads the ink inside the span and interpolates the segments crossing its edges", () => {
    const s = state("k", [
      { x: 0, y: 100 },
      { x: 10, y: 50 },
      { x: 20, y: 20 },
    ]);
    // x=5 → 75; x=10 → 50; x=15 → 35.
    expect(lineYExtentBetween(s, ["k"], 5, 15)).toEqual({ top: 35, bottom: 75 });
  });

  it("joins across a null vertex (connectNulls) and matches a function key by identity", () => {
    const read = () => null;
    const s = state(read, [
      { x: 0, y: 40 },
      { x: 10, y: null },
      { x: 20, y: 20 },
    ]);
    expect(lineYExtentBetween(s, [read], 9, 11)).toEqual({ top: 29, bottom: 31 });
    expect(lineYExtentBetween(s, [() => null], 9, 11)).toBeNull();
  });
});
