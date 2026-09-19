// #6964 — A PERIOD MARKER'S LABEL IS NEVER PAINTED OUT BY THE DATA.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/14638444` (Bills 41 – Lions 31) at 390px, on the Score Differential
// chart: the `Q3` marker renders as a bare `3`. Filed by the discover lane off a
// D48 shop; evidence `artifacts-discover/shop-1445Z/crop-scorediff-markers.png`.
//
// The label text was never wrong. `Q3` is staggered one row down (#6882) so it
// does not read as one token with `HT`, and on that row the orange `Actual Score
// Diff` step line runs through the same pixels and paints the `Q` out. It fires
// on the shape of the data, which is why the Chiefs–Broncos control game on the
// same night drew all four markers cleanly and why the win-probability chart
// directly above drew `Q3` in full.
//
// ── THE MECHANISM: `isFront` IS A DEAD PROP ──────────────────────────────────
//
// Both charts already passed `isFront` to every period `ReferenceLine`, under a
// comment reading "rendered in front of data area". That comment was false, and
// the prop is the reason it was believable.
//
//   $ grep -rn isFront node_modules/recharts/lib/
//   lib/cartesian/ReferenceLine.js:191:  isFront: false,
//   lib/cartesian/ReferenceArea.js:114:  isFront: false,
//   lib/cartesian/ReferenceDot.js:110:   isFront: false,
//
// Three hits in recharts 2.15.4, all of them `defaultProps`. The library never
// reads it. It is also declared in the `.d.ts`, so it type-checks and no gate
// ever warned — a prop that costs nothing, does nothing, and documents a
// behaviour the chart does not have. It is a recharts v1 survival.
//
// What actually decides the question: SVG has no z-index, so paint order is
// DOCUMENT order, and recharts' `renderByOrder` (util/ReactUtils) pushes children
// in JSX order. Measured on production with `artifacts/ux-1366/paint-order-6964.mjs`
// before the fix — every reference-line group against every series layer, by
// document index, inside the same `<svg.recharts-surface>`:
//
//   chart              marker groups   series layers
//   Win Probability        51 … 63        81 … 105
//   Score Differential     57 … 69        73 … 127
//
// Markers under data on BOTH charts, on every event page. So this was never
// specific to one game; the Bills game is just where a line happened to cross a
// glyph. The fix is that the marker blocks are now the LAST children of each
// chart. There is no prop that does it.
//
// ── WHAT THIS FILE PINS, AND WHY IT RENDERS RATHER THAN READS THE SOURCE ─────
//
// A source scan ("does the marker block appear below the last `<Line>`") would
// pass on any file that merely looks right, and would keep passing if a recharts
// upgrade changed how children are ordered — the exact class of mistake that put
// `isFront` here in the first place. So this renders the real components on the
// real fixture and reads the ORDER OF THE EMITTED SVG, which is the thing the
// browser paints.
//
// 🪤 recharts draws NOTHING inside a `ResponsiveContainer` without a viewport, so
// the obvious version of this test asserts over markup containing no chart at
// all and passes on both arms. `ResponsiveContainer` is mocked to a fixed size
// for that reason (same device as `chartTextStaysInsideThePlot.test.tsx`), and
// the first describe block below refuses to let the file be vacuous: it proves
// the markers and the series are both actually in the markup before anything
// asserts about their order.
//
// ── SPECIMEN ─────────────────────────────────────────────────────────────────
//
// The #6882 fixture, unchanged: `GET /api/events/14638444/history` verbatim. It
// is the same event #6964 was filed on, it carries all four NFL markers, and it
// is the one that puts `Q3` on the staggered row where the step line runs.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import OddsChart from "@/components/OddsChart";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { AnalyticsProvider } from "@/components/Analytics";
import { derivePeriodBoundaries } from "@/lib/periodMarkers";

/** The viewport every claim in this file is made at. */
const PHONE_SVG_PX = 390;
const SVG_HEIGHT_PX = 300;

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

const WIRE = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/periodLabelStagger.14638444.nfl-final.json"),
    "utf8"
  )
);

const SPORT = "americanfootball_nfl";

/** The boundaries the page derives and hands BOTH charts. */
function boundaries() {
  return derivePeriodBoundaries(
    undefined,
    undefined,
    undefined,
    WIRE.commence_time,
    WIRE.period_markers,
    SPORT
  );
}

function renderOdds(): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(OddsChart, {
        history: WIRE.history,
        homeTeam: WIRE.home_team,
        awayTeam: WIRE.away_team,
        commenceTime: WIRE.commence_time,
        espnHistory: WIRE.espn_history,
        winProbHistory: WIRE.win_prob_history,
        winProbSources: WIRE.win_prob_sources,
        aggregateLine: WIRE.aggregate_line,
        scoringPlays: WIRE.scoring_plays,
        eventStatus: WIRE.status,
        periodBoundaries: boundaries(),
      } as never)
    )
  );
}

function renderSdc(): string {
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: WIRE.history,
      homeTeam: WIRE.home_team,
      awayTeam: WIRE.away_team,
      commenceTime: WIRE.commence_time,
      scoreHistory: WIRE.score_history,
      espnHistory: WIRE.espn_history,
      eventStatus: WIRE.status,
      sportKey: SPORT,
      periodBoundaries: boundaries(),
    } as never)
  );
}

const CHARTS = [
  ["OddsChart", renderOdds],
  ["ScoreDifferentialChart", renderSdc],
] as const;

/**
 * Document-order positions of every period-marker group in the emitted markup.
 *
 * A marker is a `<g class="... recharts-reference-line">` whose subtree contains
 * a `recharts-label` — which is what distinguishes the four LABELLED period
 * boundaries from the unlabelled rules that share the class (the `y=0`/`y=50`
 * guides and the Final marker, which carries no caption by #3541). Matching on
 * the group rather than on the glyph means the assertion cannot be satisfied by
 * a label that renders somewhere else in the tree.
 *
 * String position IS document position: `renderToStaticMarkup` serialises the
 * tree in order, and SVG paints in that same order.
 */
function labelledReferenceLines(markup: string): Array<{ label: string; at: number }> {
  const out: Array<{ label: string; at: number }> = [];
  const groupRe = /<g class="[^"]*recharts-reference-line[^"]*">/g;
  let m: RegExpExecArray | null;
  while ((m = groupRe.exec(markup)) !== null) {
    const start = m.index;
    // The group's own extent: up to the next reference-line group, or the end.
    groupRe.lastIndex = m.index + m[0].length;
    const nextIdx = markup.slice(groupRe.lastIndex).search(/<g class="[^"]*recharts-reference-line/);
    const end = nextIdx === -1 ? markup.length : groupRe.lastIndex + nextIdx;
    const body = markup.slice(start, end);
    // recharts' `Text` wraps the caption in a `<tspan>`, so the glyphs are one
    // element deeper than the labelled `<text>`. Take the element's whole text
    // content rather than its first text node, or every label reads as "".
    const text = body.match(/<text[^>]*class="[^"]*recharts-label[^"]*"[^>]*>([\s\S]*?)<\/text>/);
    const label = text ? text[1].replace(/<[^>]*>/g, "").trim() : "";
    if (label) out.push({ label, at: start });
  }
  return out;
}

/**
 * The labelled reference lines that are PERIOD MARKERS, by the labels the page
 * actually handed the chart — not by shape, and not by "everything with a
 * caption". Both charts also draw a labelled horizontal guide rule (`0` on the
 * score chart), which is a different thing that deliberately stays behind the
 * data; keying on the derived boundary set is what keeps the two apart without
 * hard-coding a denylist that a new sport's label could fall through.
 */
function periodMarkerPositions(markup: string): Array<{ label: string; at: number }> {
  const want = new Set(boundaries().map((b) => b.label));
  return labelledReferenceLines(markup).filter((g) => want.has(g.label));
}

/** Document-order positions of every drawn data series. */
function seriesPositions(markup: string): number[] {
  const out: number[] = [];
  const re = /<g class="[^"]*recharts-line[^"]*">/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) out.push(m.index);
  return out;
}

const RENDERED = new Map(CHARTS.map(([name, render]) => [name, render()]));

// ─────────────────────────────────────────────────────────────────────────────
// Strawman guard. Everything below is "marker AFTER series". On a render that
// drew no markers, or no series, every one of those assertions passes while the
// page still paints the `Q` out. These four run first so the file cannot go
// quietly vacuous — the failure mode the sibling chart guards all call out.
// ─────────────────────────────────────────────────────────────────────────────
describe("#6964 — the render is actually a chart with both things in it", () => {
  it.each(CHARTS.map(([n]) => n))("%s draws an svg at phone width", (name) => {
    const markup = RENDERED.get(name)!;
    expect(markup).toContain("recharts-surface");
    expect(markup).toContain(`width="${PHONE_SVG_PX}"`);
    expect(markup).toContain(`height="${SVG_HEIGHT_PX}"`);
  });

  it.each(CHARTS.map(([n]) => n))("%s draws all four NFL period labels", (name) => {
    const labels = periodMarkerPositions(RENDERED.get(name)!).map((g) => g.label);
    expect(labels).toEqual(["Q2", "HT", "Q3", "Q4"]);
  });

  it("ScoreDifferentialChart also draws the labelled `0` guide rule", () => {
    // The chart carries a second labelled reference line, and the order rule
    // below deliberately exempts it. Pinned so that exemption is a stated fact
    // about a rule that exists, rather than a filter quietly matching nothing.
    const all = labelledReferenceLines(RENDERED.get("ScoreDifferentialChart")!);
    expect(all.map((g) => g.label)).toContain("0");
  });

  it.each(CHARTS.map(([n]) => n))("%s draws data series to be painted over by", (name) => {
    expect(seriesPositions(RENDERED.get(name)!).length).toBeGreaterThan(0);
  });

  it("the specimen is the one that carries the defect: Q3 is on the staggered row", () => {
    // If `Q3` ever stops being staggered, the glyph the issue lost is back on
    // the top row and this file would be guarding a case the page no longer has.
    for (const [name] of CHARTS) {
      const rows = RENDERED.get(name)!.match(/data-period-label-rows="([^"]*)"/);
      expect(rows).not.toBeNull();
      expect(rows![1]).toBe("0,0,1,0");
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
describe("#6964 — period markers paint above every data series", () => {
  it.each(CHARTS.map(([n]) => n))(
    "%s: every labelled marker is emitted after every series",
    (name) => {
      const markup = RENDERED.get(name)!;
      const markers = periodMarkerPositions(markup);
      const lastSeries = Math.max(...seriesPositions(markup));

      // Named individually so a failure says WHICH marker went under, rather
      // than only that one did.
      const under = markers.filter((g) => g.at < lastSeries).map((g) => g.label);
      expect(under).toEqual([]);
    }
  );

  it("ScoreDifferentialChart: Q3 is emitted after the orange step line that erased it", () => {
    // The specific pixels in the issue. `#f97316` is `Actual Score Diff`; its
    // riser is what painted over the `Q`. Pinning this series by colour ties the
    // guard to the reported defect rather than to "some series".
    const markup = RENDERED.get("ScoreDifferentialChart")!;
    const orange = markup.indexOf('stroke="#f97316"');
    expect(orange).toBeGreaterThan(-1);

    const q3 = periodMarkerPositions(markup).find((g) => g.label === "Q3");
    expect(q3).toBeDefined();
    expect(q3!.at).toBeGreaterThan(orange);
  });

  it("the horizontal guide rules deliberately stay BELOW the series", () => {
    // Not an oversight and not collateral: `y=0` here (and `y=50` on the win
    // probability chart) is a background rule a reader reads the data against.
    // Raising it with the markers would put a rule over every line on the chart.
    // Pinned so a later sweep does not "finish the job" and change the chart.
    const markup = RENDERED.get("ScoreDifferentialChart")!;
    const firstSeries = Math.min(...seriesPositions(markup));
    const zeroRule = markup.search(/<g class="[^"]*recharts-reference-line/);
    expect(zeroRule).toBeGreaterThan(-1);
    expect(zeroRule).toBeLessThan(firstSeries);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
describe("#6964 — the dead prop does not come back", () => {
  // `isFront` reads as the fix and is not one. Anyone re-adding it is about to
  // move the markers back up and trust it, so the name is banned in the two
  // chart files outside of the comment that explains why.
  it.each([
    ["OddsChart", "../components/OddsChart.tsx"],
    ["ScoreDifferentialChart", "../components/ScoreDifferentialChart.tsx"],
  ])("%s passes no isFront prop", (_name, rel) => {
    const source = readFileSync(join(__dirname, rel), "utf8");
    const propUses = source
      .split("\n")
      .filter((l) => /^\s*isFront\b/.test(l) || /\bisFront=\{/.test(l));
    expect(propUses).toEqual([]);
  });

  it("recharts still does not read isFront, so the comment stays true", () => {
    // If a recharts upgrade ever implements it, this fails and the explanation
    // in both components needs rewriting — better than the comment silently
    // becoming false a second time.
    const lib = join(__dirname, "../node_modules/recharts/lib/cartesian/ReferenceLine.js");
    const source = readFileSync(lib, "utf8");
    const hits = source.split("\n").filter((l) => l.includes("isFront"));
    expect(hits.map((l) => l.trim())).toEqual(["isFront: false,"]);
  });
});
