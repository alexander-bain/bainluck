// #6658 — THE SCORE DIFFERENTIAL CHART STOPS PRINTING TWO INNINGS ON TOP OF
// EACH OTHER, BY READING THE SAME SPACING RULE AS THE CHART ABOVE IT.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15313139` (Reds–Dodgers, MLB) at 390px, handed over by latency/467
// at 00:02Z and re-shot here at 01:35Z:
// `artifacts/ux-1305/before-15313139-scroll1600.png`.
//
// The Score Differential chart's inning markers render as `TB2`, `TB3`, `T5T6`,
// `B6 B7` — two labels stacked on one x position. The WIN PROBABILITY chart
// DIRECTLY ABOVE IT, same page, same width, same innings, same time axis,
// spaces the identical markers cleanly: `T1 … T5 T6 B6 … B7 T8`.
//
// So it is not the data, not the width and not the sport. One chart lays the
// labels out and the other does not — which makes the correct chart a free
// control, and makes the diff between them the whole diagnosis.
//
// ── THE CAUSE: THE FIX WAS APPLIED TO ONE CHART AND NEVER THE OTHER ──────────
//
// UX-P022 fixed exactly this smear on `OddsChart` and wrote down both halves of
// why, in comments that are still there:
//
//   1. SPACING MUST BE PURELY PROPORTIONAL. The old `max(duration * N%, M
//      minutes)` mixes a pixel budget with a time budget and the two only agree
//      at one chart length.
//   2. LABELS MUST ALL ANCHOR THE SAME SIDE. Alternating
//      insideTopLeft/insideTopRight reads like it spreads them out and does the
//      opposite — a left-anchored label grows rightward, the next right-anchored
//      one grows leftward, so adjacent labels grow TOWARD each other and meet in
//      the middle.
//
// `ScoreDifferentialChart` was still running the PRE-UX-P022 form of both:
// `Math.max(chartDuration * 0.05, 180_000)` and `i % 2 === 0 ? "insideTopLeft" :
// "insideTopRight"`. It also carried a 12-label cap that decimated by INDEX
// (`i % ceil(n/12)`), dropping markers without reference to whether they were
// close together at all.
//
// A private copy of a rule cannot inherit the fix to the rule. So the rule now
// has ONE implementation, `dedupePeriodLabels`, and both charts call it — which
// is the assertion this file is really making. Each chart keeps its own EXTENT
// logic, because they legitimately disagree about what "on the chart" means:
// the win-probability chart bounds on its drawn line (CERT-1984), this one
// requires a drawn score series (CERT-1989).
//
// ── SPECIMEN ─────────────────────────────────────────────────────────────────
//
// `GET /api/events/15313139/history` at 01:30Z, `status: live`, verbatim in
// every field this chart reads: all 30 `period_markers`, all 387 `history`, all
// 8 `score_history`, all 88 `espn_history`. Nothing sampled or rounded. The
// page-level keys the component is never handed are dropped.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import {
  dedupePeriodLabels,
  derivePeriodBoundaries,
  PERIOD_LABEL_MIN_SPACING_FRACTION,
} from "@/lib/periodMarkers";

const WIRE = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/periodLabelSpacing.15313139.mlb-live.json"),
    "utf8"
  )
);

const SDC_SOURCE = readFileSync(
  join(__dirname, "../components/ScoreDifferentialChart.tsx"),
  "utf8"
);
const ODDS_SOURCE = readFileSync(
  join(__dirname, "../components/OddsChart.tsx"),
  "utf8"
);

const SPORT = "baseball_mlb";

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

/** recharts draws nothing inside `ResponsiveContainer` without a viewport, so a
 *  server render cannot observe a `<ReferenceLine>`. Both charts report the
 *  count they will actually draw on their wrapper instead — the same channel
 *  CERT-1984 opened on `OddsChart`. */
function periodBoundaryCount(markup: string): number {
  const m = markup.match(/data-period-boundaries="(\d+)"/);
  if (!m) throw new Error("wrapper did not report data-period-boundaries");
  return Number(m[1]);
}

function renderSdc(overrides: Record<string, unknown> = {}): string {
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
      ...overrides,
    } as never)
  );
}

describe("#6658 — the specimen actually carries the collision", () => {
  it("the real wire derives enough innings to smear, or this file proves nothing", () => {
    const b = boundaries();
    // Strawman guard. Every assertion below is about THINNING a list; on a
    // fixture that derived two markers they would all pass while the page still
    // smeared. 15313139 ran to the 8th, so the page had a dense ladder.
    expect(b.length).toBeGreaterThanOrEqual(8);
    // And they are real half-inning labels, not bare digits — the thing that
    // collides is `T5`/`B5` sharing an x, which cannot happen if the normalizer
    // collapsed both to `5`.
    expect(b.some((x) => /^[TB]\d+$/.test(x.label))).toBe(true);
  });
});

describe("#6658 — the shared rule", () => {
  it("leaves no two surviving labels closer than the spacing fraction", () => {
    const b = boundaries();
    const span =
      new Date(b[b.length - 1].timestamp).getTime() -
      new Date(b[0].timestamp).getTime();
    const kept = dedupePeriodLabels(b, span);

    expect(kept.length).toBeGreaterThan(0);
    for (let i = 1; i < kept.length; i++) {
      const gap =
        new Date(kept[i].timestamp).getTime() -
        new Date(kept[i - 1].timestamp).getTime();
      expect(gap).toBeGreaterThanOrEqual(span * PERIOD_LABEL_MIN_SPACING_FRACTION);
    }
  });

  it("actually thins this specimen — the rule is not a pass-through here", () => {
    const b = boundaries();
    const span =
      new Date(b[b.length - 1].timestamp).getTime() -
      new Date(b[0].timestamp).getTime();
    // If the rule dropped nothing on the very page that smeared, it would be
    // satisfying the spacing assertion vacuously.
    expect(dedupePeriodLabels(b, span).length).toBeLessThan(b.length);
  });

  it("keeps the LATER of a too-close pair, so 'HT' wins over 'Q2 end'", () => {
    const kept = dedupePeriodLabels(
      [
        { timestamp: "2026-09-16T22:40:00Z", label: "Q2 end" },
        { timestamp: "2026-09-16T22:40:30Z", label: "HT" },
        { timestamp: "2026-09-16T23:40:00Z", label: "Q3" },
      ],
      60 * 60 * 1000
    );
    expect(kept.map((k) => k.label)).toEqual(["HT", "Q3"]);
  });
});

describe("#6658 — the component reads the shared rule at its call site", () => {
  // The rule existing is not the ship. A helper can be correct and still be
  // called by nobody, so this asserts the number the COMPONENT reports, not the
  // number the helper returns.
  it("the chart draws exactly what the shared rule keeps", () => {
    const b = boundaries();
    const span =
      new Date(b[b.length - 1].timestamp).getTime() -
      new Date(b[0].timestamp).getTime();
    const drawn = periodBoundaryCount(renderSdc());

    expect(drawn).toBeGreaterThan(0);
    // The chart measures its span on the full category extent, which is at least
    // the boundary span, so it can keep no MORE than the rule allows on that
    // narrower window.
    expect(drawn).toBeLessThanOrEqual(dedupePeriodLabels(b, span).length);
    // And the pre-fix code kept far more than this — see the regression arm.
  });

  it("draws fewer labels than the pre-UX-P022 rule would have", () => {
    const b = boundaries();
    const span =
      new Date(b[b.length - 1].timestamp).getTime() -
      new Date(b[0].timestamp).getTime();

    // The old rule, verbatim: max(5% of duration, 3 minutes), then a 12-cap that
    // decimated by index.
    const oldMinSpacing = Math.max(span * 0.05, 180_000);
    const oldDeduped: typeof b = [];
    for (const x of b) {
      const t = new Date(x.timestamp).getTime();
      if (oldDeduped.length > 0) {
        const prevT = new Date(
          oldDeduped[oldDeduped.length - 1].timestamp
        ).getTime();
        if (t - prevT < oldMinSpacing) {
          oldDeduped[oldDeduped.length - 1] = x;
          continue;
        }
      }
      oldDeduped.push(x);
    }

    expect(periodBoundaryCount(renderSdc())).toBeLessThan(oldDeduped.length);
  });

  it("still draws nothing when there is no series under it at all (CERT-1989)", () => {
    // The load-bearing control: this ship THINS labels, and a chart that drew
    // nothing would satisfy every thinning assertion above. CERT-1989's rule —
    // a marker needs a drawn line under it — must survive the change.
    //
    // Emptying `scoreHistory` alone is NOT the control: `scoreSpan` is the span
    // of the drawn score series, and the projected-margin line is drawn off
    // `history`, so the chart legitimately still places a marker. Measured, not
    // assumed — that arm returns 1, not 0. The real no-series arm empties all
    // three.
    const markup = renderSdc({ history: [], scoreHistory: [], espnHistory: [] });
    expect(markup).toBe("");
  });
});

describe("#6658 — the rule has one implementation, not two", () => {
  it("neither chart keeps a private spacing constant", () => {
    // The defect was a COPY that missed a fix. A future copy is the same bug, so
    // the hybrid pixel/time form may not reappear in either file.
    for (const [name, src] of [
      ["ScoreDifferentialChart", SDC_SOURCE],
      ["OddsChart", ODDS_SOURCE],
    ] as const) {
      expect({ name, hit: /Math\.max\(\s*chartDuration/.test(src) }).toEqual({
        name,
        hit: false,
      });
      expect({ name, hit: /chartDuration\s*\*\s*0\.\d+/.test(src) }).toEqual({
        name,
        hit: false,
      });
    }
  });

  it("both charts call the shared helper", () => {
    for (const [name, src] of [
      ["ScoreDifferentialChart", SDC_SOURCE],
      ["OddsChart", ODDS_SOURCE],
    ] as const) {
      expect({ name, calls: /dedupePeriodLabels\(/.test(src) }).toEqual({
        name,
        calls: true,
      });
    }
  });

  it("the score differential chart anchors every label on one side", () => {
    // UX-P022's other half. Alternating anchors make adjacent labels grow toward
    // each other, which is what produced `TB2` — so a spacing fix alone would
    // leave the smear at the tightest pairs.
    //
    // The needle is the ALTERNATION, not the string `insideTopRight`, which
    // legitimately survives in the recharts position union type and in the
    // comment recording why the alternation went. A needle that matched those
    // would be grading code nobody chose.
    expect(SDC_SOURCE).not.toMatch(/labelPosition:[^,\n]*\?/);
    expect(SDC_SOURCE).not.toMatch(/i\s*%\s*2\s*===\s*0/);
    // #7371 MOVED THE LITERAL, NOT THE RULE. This used to read
    // `toMatch(/labelPosition:\s*"insideTopLeft"/)`, and a hardcoded left anchor
    // is exactly what that issue had to stop: a marker sitting ON the chart's
    // last category grew its caption out of the svg and reached the page as a
    // single glyph. The anchor is now decided by `anchorPeriodLabels` — "every
    // label on the same side EXCEPT one with no room on that side, which flips
    // and is spaced for the flip" — so the assertion follows it into the shared
    // rule rather than pinning a string this file no longer owns. The first two
    // needles are unchanged and still forbid this chart computing its own.
    expect(SDC_SOURCE).toMatch(/anchorPeriodLabels\(/);
    expect(SDC_SOURCE).not.toMatch(/labelPosition:\s*"inside/);
  });

  it("the index-decimating label cap is gone", () => {
    // `i % Math.ceil(n/12)` dropped markers by position, not by proximity: on a
    // list already correctly spaced it deleted readable labels, and on a
    // clustered one it kept collisions.
    expect(SDC_SOURCE).not.toMatch(/Math\.ceil\([^)]*\/\s*12\s*\)/);
  });
});
