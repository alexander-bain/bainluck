/**
 * #7940 — a home win no longer rules its own line through the `Q4` glyphs.
 *
 * ═══ THE DEFECT, AND THE PREDICATE THAT IS NOT THE OBVIOUS ONE ═══
 *
 * Period labels were pinned to the plot TOP. Both charts plot a HOME-side
 * quantity. So the series and the labels occupy the same band exactly when the
 * home team is winning, and the line is drawn straight through the letters.
 *
 * The issue was filed (ux/1429) naming "a decided game at or near the whistle"
 * as the cause, and named Chiefs 33–30 Colts in Reproduce as a control that
 * would NOT reproduce. ux/1431 then measured 6 games / 12 charts and got perfect
 * separation on a different predicate:
 *
 *   home WON  → 14780545 (2 + 3 collisions) · 14780544 (1) · 15315580 (4 of 4 + 1) · 15316384 (5 of 10 + 3)
 *   home LOST → 15315563 WNBA 69–106 (0 + 0) · 15315936 MLB 1–9 (0 + 0)
 *
 * A 37-point WNBA blowout is spotless and a three-point OT game convicts, so
 * "blowout" was the vivid property of one specimen and not the thing the code
 * keys on. **The negative control here is therefore a home LOSS, never a close
 * game** — and it is built by mirroring the very fixture that convicts, so the
 * two arms differ in the predicate and in nothing else.
 *
 * ═══ WHY THE ASSERTIONS ARE IN DATA SPACE ═══
 *
 * The chip band is a pixel quantity (`PERIOD_CHIP_BAND_PX = 15`) and both charts
 * size through `ResponsiveContainer height="100%"` inside a `flex-1` parent, so
 * neither the component nor this rig knows the plot's pixel height — #7940's own
 * instrument opens by saying a payload-space collision test cannot be built
 * honestly for that reason. So the repair asks a question that HAS an answer
 * without a viewport (which end has more clear air) and this file asserts that
 * question, plus the wiring from its answer to the label props. The pixel-space
 * claim — that the collisions actually go to zero — is a browser measurement and
 * is banked on the issue, not here.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import OddsChart from "@/components/OddsChart";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { AnalyticsProvider } from "@/components/Analytics";
import {
  derivePeriodBoundaries,
  choosePeriodStripBand,
  periodLabelPlacement,
  PERIOD_STRIP_FLIP_MARGIN,
  PERIOD_LABEL_ROW_HEIGHT_PX,
} from "@/lib/periodMarkers";

const WIRE = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/periodLabelStagger.14638444.nfl-final.json"),
    "utf8",
  ),
);

const ODDS_SOURCE = readFileSync(join(__dirname, "../components/OddsChart.tsx"), "utf8");
const SDC_SOURCE = readFileSync(
  join(__dirname, "../components/ScoreDifferentialChart.tsx"),
  "utf8",
);

const SPORT = "americanfootball_nfl";

/**
 * Bills 41–31 Lions, and Buffalo is HOME — a home win, which is the convicting
 * class. Pinned as an assertion below rather than stated here, because the whole
 * file is about which side won and a fixture swap that changed it would turn
 * every arm green for the wrong reason.
 */
const HOME_WON = true;

/**
 * The same game with every home-side quantity reflected: `p → 1 - p` on every
 * series, and the scores swapped. That is a home LOSS carrying the identical
 * markers, the identical timestamps, the identical span and the identical
 * stagger — so any difference in the strip's band is attributable to the
 * predicate and to nothing else about the specimen.
 *
 * Mirroring rather than fetching a second real game is deliberate: a different
 * real game differs in a dozen ways at once, and #7940's filing went wrong
 * precisely by reading a second property of a single specimen as the cause.
 */
function mirror(node: unknown): unknown {
  if (Array.isArray(node)) return node.map(mirror);
  if (node && typeof node === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
      if (k === "home_probability" && typeof v === "number") out[k] = 1 - v;
      else if (k === "away_probability" && typeof v === "number") out[k] = 1 - v;
      else if (k === "home_score" && typeof v === "number") {
        out[k] = (node as Record<string, number>).away_score ?? v;
      } else if (k === "away_score" && typeof v === "number") {
        out[k] = (node as Record<string, number>).home_score ?? v;
      } else if (k === "projected_home_score" && typeof v === "number") {
        out[k] = (node as Record<string, number>).projected_away_score ?? v;
      } else if (k === "projected_away_score" && typeof v === "number") {
        out[k] = (node as Record<string, number>).projected_home_score ?? v;
      } else out[k] = mirror(v);
    }
    return out;
  }
  return node;
}

const MIRRORED = mirror(WIRE) as typeof WIRE;

function boundaries(wire: typeof WIRE) {
  return derivePeriodBoundaries(undefined, undefined, undefined, wire.period_markers, SPORT);
}

function renderOdds(wire: typeof WIRE): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(OddsChart, {
        history: wire.history,
        homeTeam: wire.home_team,
        awayTeam: wire.away_team,
        commenceTime: wire.commence_time,
        espnHistory: wire.espn_history,
        winProbHistory: wire.win_prob_history,
        winProbSources: wire.win_prob_sources,
        aggregateLine: wire.aggregate_line,
        scoringPlays: wire.scoring_plays,
        eventStatus: wire.status,
        periodBoundaries: boundaries(wire),
      } as never),
    ),
  );
}

function renderSdc(wire: typeof WIRE): string {
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: wire.history,
      homeTeam: wire.home_team,
      awayTeam: wire.away_team,
      commenceTime: wire.commence_time,
      scoreHistory: wire.score_history,
      espnHistory: wire.espn_history,
      eventStatus: wire.status,
      sportKey: SPORT,
      periodBoundaries: boundaries(wire),
    } as never),
  );
}

/** The band each chart reports it will paint its strip in. */
function stripBand(markup: string): string {
  const m = markup.match(/data-period-strip-band="([^"]*)"/);
  if (!m) throw new Error("wrapper did not report data-period-strip-band");
  return m[1];
}

function labelRows(markup: string): number[] {
  const m = markup.match(/data-period-label-rows="([^"]*)"/);
  if (!m) throw new Error("wrapper did not report data-period-label-rows");
  return m[1] === "" ? [] : m[1].split(",").map(Number);
}

/** Build `rows` for the unit arms: `n` samples of one series at a fixed height. */
const flat = (norm: number, n = 40) => Array.from({ length: n }, () => [norm]);

// ───────────────────────────────────────────────────────────────────────────
describe("#7940 — the specimen carries the predicate, and the control inverts it", () => {
  // Strawman guard. Every arm below compares a home win against a home loss; on
  // a fixture where both arms were the same side, they would agree and the file
  // would pass while both charts still struck their labels through.
  it("the fixture is a home WIN and the mirror is a home LOSS", () => {
    const last = WIRE.score_history[WIRE.score_history.length - 1];
    expect(last.home_score > last.away_score).toBe(HOME_WON);

    const mLast = MIRRORED.score_history[MIRRORED.score_history.length - 1];
    expect(mLast.home_score > mLast.away_score).toBe(false);
    // Reflected, not merely different: the same margin the other way.
    expect(mLast.home_score).toBe(last.away_score);
    expect(mLast.away_score).toBe(last.home_score);
  });

  it("the mirror changes the outcome and nothing else about the markers", () => {
    // Same markers, same order, same timestamps — so the strip it has to place
    // is identical and only the series moved.
    expect(boundaries(MIRRORED)).toEqual(boundaries(WIRE));
    expect(labelRows(renderOdds(MIRRORED))).toEqual(labelRows(renderOdds(WIRE)));
    expect(labelRows(renderOdds(WIRE)).length).toBeGreaterThan(0);
  });

  it("the winning series really does finish against the frame", () => {
    // Without this, "the strip moves off the series" could be asserted on a
    // chart that never had a collision to move off.
    const espn = WIRE.win_prob_history.espn;
    expect(espn[espn.length - 1].home_probability).toBeGreaterThan(0.95);
  });
});

// ───────────────────────────────────────────────────────────────────────────
describe("#7940 — both charts move the strip off a home win, and leave a home loss alone", () => {
  it.each([
    ["OddsChart", renderOdds],
    ["ScoreDifferentialChart", renderSdc],
  ] as const)("%s puts the strip at the BOTTOM on a home win", (_name, render) => {
    expect(stripBand(render(WIRE))).toBe("bottom");
  });

  it.each([
    ["OddsChart", renderOdds],
    ["ScoreDifferentialChart", renderSdc],
  ] as const)("%s leaves the strip at the TOP on a home loss", (_name, render) => {
    // The negative control the issue's correction insisted on. A repair that
    // simply moved every strip to the bottom would pass the arm above and fail
    // here — and would have re-created the identical defect upside down on the
    // other half of all completed games.
    expect(stripBand(render(MIRRORED))).toBe("top");
  });
});

// ───────────────────────────────────────────────────────────────────────────
describe("#7940 — choosePeriodStripBand compares clear air, in domain space", () => {
  it("moves the strip away from a series pinned against the top", () => {
    expect(choosePeriodStripBand(flat(0.98), [0, 1])).toBe("bottom");
  });

  it("leaves the strip alone when the series is pinned against the bottom", () => {
    expect(choosePeriodStripBand(flat(0.02), [0, 1])).toBe("top");
  });

  it("leaves a series down the middle exactly where it has always been", () => {
    // The deadband's whole purpose: the default answer is the pre-#7940
    // rendering, so a chart with air at both ends never moves.
    expect(choosePeriodStripBand(flat(0.5), [0, 1])).toBe("top");
  });

  it("reads the AXIS, not the values — a zoomed domain moves the frame", () => {
    // `computeWinProbYAxis` zooms (#3973). The SAME 0.55 sits comfortably
    // mid-plot on a 0–1 axis and hard against the frame on a 0.50–0.56 one, and
    // the frame is what a label collides with. A rule that normalised against
    // the data's own range instead of the axis would answer the same to both —
    // and the zoomed case is the whole tennis/soccer population, where a series
    // that never leaves a four-point window still runs along the top of its plot.
    expect(choosePeriodStripBand(flat(0.55), [0, 1])).toBe("top");
    expect(choosePeriodStripBand(flat(0.55), [0.5, 0.56])).toBe("bottom");
  });

  it("asks per sample which line is NEAREST each frame, not where the average is", () => {
    // A two-source chart with one line on the ceiling and one on the floor has
    // NO free band, and the strip must not move: wherever it goes it is struck
    // through. A mean-of-all-values rule reads this as 0.5 and answers "top" for
    // the right number by the wrong route — so this arm is here to kill that
    // implementation, which is the obvious one.
    const straddle = Array.from({ length: 40 }, () => [0.99, 0.01]);
    expect(choosePeriodStripBand(straddle, [0, 1])).toBe("top");

    // And the same two samples averaged would also be 0.5, but with both lines
    // high the top really is taken and the bottom really is free.
    const bothHigh = Array.from({ length: 40 }, () => [0.99, 0.9]);
    expect(choosePeriodStripBand(bothHigh, [0, 1])).toBe("bottom");
  });

  it("the deadband is real, and it is PERIOD_STRIP_FLIP_MARGIN wide", () => {
    // Pins the constant to behaviour from both sides. `flat(n)` gives top air
    // `1 - n` and bottom air `n`, so the margin is crossed at `n = (1 + M) / 2`.
    // A mutation that drops the margin, flips the comparison, or turns `>=` into
    // `>` at the exact boundary changes one of these three.
    const boundary = (1 + PERIOD_STRIP_FLIP_MARGIN) / 2;
    expect(choosePeriodStripBand(flat(boundary - 0.01), [0, 1])).toBe("top");
    expect(choosePeriodStripBand(flat(boundary + 0.01), [0, 1])).toBe("bottom");
    expect(choosePeriodStripBand(flat(boundary), [0, 1])).toBe("bottom");
  });

  it("clamps ink outside the frame instead of paying it air it has not earned", () => {
    // A series far above a zoomed axis is not drawn above the frame — it is
    // clipped at it. Letting the normalised value run past 1 would make the
    // bottom look emptier than it is and could flip a chart on ink nobody sees.
    expect(choosePeriodStripBand(flat(5), [0, 1])).toBe(
      choosePeriodStripBand(flat(1), [0, 1]),
    );
    expect(choosePeriodStripBand(flat(-5), [0, 1])).toBe(
      choosePeriodStripBand(flat(0), [0, 1]),
    );
  });

  it("answers top for every input it cannot read", () => {
    // Each of these is a caller bug or an empty chart, and the honest answer to
    // one is the rendering the chart already had — never a band chosen off a NaN.
    expect(choosePeriodStripBand(flat(0.98), [1, 1])).toBe("top"); // zero-height
    expect(choosePeriodStripBand(flat(0.98), [1, 0])).toBe("top"); // inverted
    expect(choosePeriodStripBand(flat(0.98), [NaN, 1])).toBe("top");
    expect(choosePeriodStripBand([], [0, 1])).toBe("top");
    expect(choosePeriodStripBand([[null, undefined], [NaN]], [0, 1])).toBe("top");
  });

  it("reads only from the first label onward, not across the pre-game stretch", () => {
    // 🔴 MEASURED, and it is the arm that changes a real answer. Built without
    // this window first: `15315580` (White Sox 8–1, a home win) draws `T1 B3 T5
    // T9` at x = 248…329 of a plot spanning 100…352 — every label in the right
    // 40% — and all 4 of its collisions SURVIVED the fix, because two thirds of
    // the samples are a flat pre-game line sitting mid-plot and they dragged the
    // mean back inside the deadband. Three of the four convicting games flipped
    // anyway, so without this arm the fix looks finished and is not.
    // The shape that reproduced it: a long pre-game stretch with the home side
    // a modest underdog, then a short in-play stretch where it blows the game
    // open. That is White Sox 8–1 — and it is why "the home team won" is not the
    // same statement as "the line was at the top for most of the chart".
    const preGame = Array.from({ length: 60 }, () => [0.3]);
    const inPlay = Array.from({ length: 40 }, () => [0.97]);
    const rows = [...preGame, ...inPlay];

    const stamps = rows.map((_, i) => new Date(i * 60_000).toISOString());
    // The only labels are in the in-play stretch, which is the whole point.
    const boundaries = [{ timestamp: new Date(62 * 60_000).toISOString() }];

    // Whole series: the pre-game half balances the air and nothing moves.
    expect(choosePeriodStripBand(rows, [0, 1])).toBe("top");
    // Windowed to where the labels actually are: the top is plainly taken.
    expect(
      choosePeriodStripBand(rows, [0, 1], { categoryTimestamps: stamps, boundaries }),
    ).toBe("bottom");
  });

  it("falls back to the whole series when the window cannot be trusted", () => {
    const rows = flat(0.97, 40);
    const stamps = rows.map((_, i) => new Date(i * 60_000).toISOString());
    // No boundaries: there are no labels to place, so there is no window.
    expect(choosePeriodStripBand(rows, [0, 1], { categoryTimestamps: stamps, boundaries: [] })).toBe(
      "bottom",
    );
    // Mismatched lengths — the timestamps are not this chart's categories, so
    // an index computed from them would point at the wrong sample.
    expect(
      choosePeriodStripBand(rows, [0, 1], {
        categoryTimestamps: stamps.slice(0, 5),
        boundaries: [{ timestamp: stamps[20] }],
      }),
    ).toBe("bottom");
    // A boundary before every category: not an empty window, just no window.
    expect(
      choosePeriodStripBand(rows, [0, 1], {
        categoryTimestamps: stamps,
        boundaries: [{ timestamp: new Date(-1e6).toISOString() }],
      }),
    ).toBe("bottom");
  });

  it("skips gaps without letting them vote", () => {
    // A forward-filled chart has null-only samples before its first reading. If
    // those counted as air at both ends they would dilute a real pin toward the
    // deadband and the fix would stop firing on exactly the long pre-game
    // windows the "All" range draws.
    const withGaps = [
      ...Array.from({ length: 60 }, () => [null, undefined]),
      ...flat(0.98, 40),
    ] as Array<Array<number | null | undefined>>;
    expect(choosePeriodStripBand(withGaps, [0, 1])).toBe("bottom");
  });
});

// ───────────────────────────────────────────────────────────────────────────
describe("#7940 — the stagger reflects with the band", () => {
  it("stacks rows DOWN from the top frame and UP from the bottom one", () => {
    // `dy` shifts the text block down from whatever `position` computed. In the
    // bottom band the frame is underneath, so a positive `dy` would push row 1
    // through the x axis and out of the plot — which reads on a screenshot as
    // "the stagger stopped working" rather than as a sign error.
    expect(periodLabelPlacement({ labelRow: 1 }, "top").dy).toBe(PERIOD_LABEL_ROW_HEIGHT_PX);
    expect(periodLabelPlacement({ labelRow: 1 }, "bottom").dy).toBe(-PERIOD_LABEL_ROW_HEIGHT_PX);
    expect(periodLabelPlacement({ labelRow: 0 }, "bottom").dy).toBe(0);
  });

  it("keeps #7371's left/right flip through the reflection", () => {
    // The flip is about running off the RIGHT rule and is orthogonal to the
    // band. Losing it in the bottom band would bring back the bare `T` (#7371)
    // on exactly the live charts this fix is most visible on.
    expect(periodLabelPlacement({ labelPosition: "insideTopRight" }, "top").position).toBe(
      "insideTopRight",
    );
    expect(periodLabelPlacement({ labelPosition: "insideTopRight" }, "bottom").position).toBe(
      "insideBottomRight",
    );
    expect(periodLabelPlacement({ labelPosition: "insideTopLeft" }, "bottom").position).toBe(
      "insideBottomLeft",
    );
    expect(periodLabelPlacement({}, "bottom").position).toBe("insideBottomLeft");
  });

  it("renders the top band byte-identically to its pre-#7940 props", () => {
    // The default path must not move. Row 0 unflipped is what the overwhelming
    // majority of labels are, and it has to come out exactly as it always did.
    expect(periodLabelPlacement({ labelRow: 0, labelPosition: "insideTopLeft" }, "top")).toEqual({
      position: "insideTopLeft",
      dy: 0,
    });
  });
});

// ───────────────────────────────────────────────────────────────────────────
describe("#7940 — the callout does not clear a strip that has moved away", () => {
  it("OddsChart passes zero chip rows when the strip is at the bottom", () => {
    // `calloutLabelCenterY` drops the terminal-value label to clear the TOP
    // strip (#5581 → #7134). When the strip is at the bottom there is nothing up
    // there to clear, and paying the drop anyway would push the callout 15–28px
    // below its own datum — #5581's defect reintroduced upside down.
    //
    // Asserted on the source because the drop happens inside a recharts `dot`
    // shape, which a server render does not call at all (no viewport) — the same
    // reason the row wiring is source-asserted in the #6882 file.
    expect(ODDS_SOURCE).toMatch(
      /periodChipRows:\s*periodStripBand === "bottom" \? 0 : periodChipRowCount/,
    );
  });
});

// ───────────────────────────────────────────────────────────────────────────
describe("#7940 — neither chart decides the band privately", () => {
  it("both call the shared helper and neither re-derives the margin", () => {
    // latency/467: the score chart once carried a private copy of the spacing
    // rule and smeared its inning labels for it. Two copies of "which end" would
    // fail the same way, and only on the chart nobody screenshotted.
    for (const [name, src] of [
      ["OddsChart", ODDS_SOURCE],
      ["ScoreDifferentialChart", SDC_SOURCE],
    ] as const) {
      expect({ name, calls: /choosePeriodStripBand\(/.test(src) }).toEqual({ name, calls: true });
      expect({ name, places: /periodLabelPlacement\(/.test(src) }).toEqual({ name, places: true });
      expect({ name, owns: /PERIOD_STRIP_FLIP_MARGIN\s*=\s*[\d.]/.test(src) }).toEqual({
        name,
        owns: false,
      });
      // The PERIOD label's props come from the helper by spread, so there is no
      // literal anchor left for the band to be unable to move. Asserted as the
      // spread rather than as "no `position:` literal anywhere", which would be
      // a false positive on OddsChart's `Start` marker — a different, single,
      // deliberately top-anchored rule that is drawn only when there are no
      // period boundaries at all, and so can never be the one struck through.
      expect({
        name,
        spread: /\.\.\.periodLabelPlacement\(\s*b as \{ labelPosition\?: string; labelRow\?: number \},\s*periodStripBand,?\s*\)/.test(
          src,
        ),
      }).toEqual({ name, spread: true });
    }
  });
});
