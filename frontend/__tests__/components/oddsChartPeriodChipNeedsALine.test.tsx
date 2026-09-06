/**
 * #3348 / CERT-1984 — A PERIOD CHIP DOES NOT DRAW WHERE THIS CHART HAS NO LINE.
 *
 * The server drops period markers no chart can place. It cannot do the whole
 * job: `period_markers` is ONE array and the event page hands it to two
 * renderers — `OddsChart` (probability lines) and `ScoreDifferentialChart`
 * (score lines). An event whose score chart draws a full match while its
 * probability chart draws nothing is a real shape, and on it the server is
 * right to keep the marker. Only this component knows its own plot is blank.
 *
 * So `filteredPeriodBoundaries` bounds against the DRAWN LINE. That is not the
 * same as bounding against `chartData`, which is what it used to do and what
 * shipped the bug: `chartData` holds a row per odds bucket even when the
 * probability is null, plus gap-filled minutes, plus — circularly — the very
 * boundary timestamps this component inserts so recharts can match a categorical
 * ReferenceLine. Measuring the extent of that always finds the chip inside it.
 *
 * Read through `data-period-boundaries` on the wrapper, following the note on
 * ScoreDifferentialChart's `data-*-series`: recharts renders nothing inside
 * `ResponsiveContainer` without a viewport, so a guard looking for the "1H"
 * label in the markup would pass on both arms and be worth nothing.
 *
 * Every test below is paired with a control on the same fixture, because a
 * guard that hides the chip by hiding every chip is not a fix.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OddsChart from "@/components/OddsChart";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

const KICKOFF = Date.UTC(2026, 7, 30, 19, 0, 0); // fixed anchor — never Date.now()
const MIN = 60 * 1000;

const iso = (offsetMin: number) => new Date(KICKOFF + offsetMin * MIN).toISOString();

/** The two soccer chips the server serves for a completed match. */
const BOUNDARIES = [
  { timestamp: iso(0), label: "1H" },
  { timestamp: iso(47), label: "2H" },
];

/** `history` rows carrying a timestamp and NO probability — a book quoting only
 *  a total. The route emits these, and this chart draws nothing for them.
 *
 *  All three sit at or after kickoff on purpose: the chart's default time range
 *  is "since commence_time", so a pre-kickoff point would be filtered out before
 *  any of this runs and the control arm would be measuring that instead. */
const NULL_ONLY_HISTORY = [
  { timestamp: iso(0), home_probability: null, away_probability: null },
  { timestamp: iso(30), home_probability: null, away_probability: null },
  { timestamp: iso(120), home_probability: null, away_probability: null },
];

/** The same rows, quoted. The only difference between the arms. */
const QUOTED_HISTORY = NULL_ONLY_HISTORY.map((p) => ({
  ...p,
  home_probability: 0.58,
  away_probability: 0.42,
}));

function boundaryCount(html: string): number {
  const match = html.match(/data-period-boundaries="(\d+)"/);
  if (!match) throw new Error("wrapper lost its data-period-boundaries attribute");
  return Number(match[1]);
}

/**
 * `OddsChart` calls `useAnalyticsContext`, which throws outside the provider.
 * Wrap in the REAL `AnalyticsProvider` — the one `app/layout.tsx` uses — so what
 * renders is what ships.
 */
function draw(children: React.ReactElement): string {
  return renderToStaticMarkup(
    React.createElement(AnalyticsProvider, null, children),
  );
}

function render(history: unknown[]) {
  return draw(
    <OddsChart
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      history={history as any}
      homeTeam="Ajax"
      awayTeam="Union SG"
      commenceTime={new Date(KICKOFF).toISOString()}
      isLive={false}
      eventStatus="completed"
      periodBoundaries={BOUNDARIES}
    />,
  );
}

describe("OddsChart period chips need a probability line under them", () => {
  test("null-only history draws NO period chip", () => {
    // The defect. Three timestamped rows, zero ink: bounding against the data
    // extent puts both chips comfortably "inside" a plot with nothing on it.
    expect(boundaryCount(render(NULL_ONLY_HISTORY))).toBe(0);
  });

  test("the control — the same rows WITH probabilities draw both chips", () => {
    // What makes the test above mean something. Identical fixture, identical
    // boundaries; the only change is that the books quoted a moneyline.
    expect(boundaryCount(render(QUOTED_HISTORY))).toBe(2);
  });

  test("a chip to the LEFT of where the line starts does not draw", () => {
    // Event 15297176's shape: the line begins mid-match, so the kickoff chip has
    // no ink under it even though the chart is far from empty. `before_start` is
    // the more common half — 10 of native/029's 70-event cohort, against 3 for
    // `past_end`.
    const lateLine = [
      { timestamp: iso(60), home_probability: 0.6, away_probability: 0.4 },
      { timestamp: iso(120), home_probability: 0.7, away_probability: 0.3 },
    ];
    const html = draw(
      <OddsChart
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        history={lateLine as any}
        homeTeam="Ajax"
        awayTeam="Union SG"
        commenceTime={new Date(KICKOFF).toISOString()}
        isLive={false}
        eventStatus="completed"
        periodBoundaries={BOUNDARIES}
      />,
    );
    // "1H" at kickoff is left of the first point; "2H" at +47 is too. Both go.
    expect(boundaryCount(html)).toBe(0);
  });

  test("a chip ON the drawn stretch still draws when an earlier one cannot", () => {
    // The tightest control: same late-starting line, one chip inside it. This
    // separates "bounds correctly" from "drops whenever anything is missing".
    const lateLine = [
      { timestamp: iso(60), home_probability: 0.6, away_probability: 0.4 },
      { timestamp: iso(120), home_probability: 0.7, away_probability: 0.3 },
    ];
    const html = draw(
      <OddsChart
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        history={lateLine as any}
        homeTeam="Ajax"
        awayTeam="Union SG"
        commenceTime={new Date(KICKOFF).toISOString()}
        isLive={false}
        eventStatus="completed"
        periodBoundaries={[
          { timestamp: iso(0), label: "1H" },   // before the line
          { timestamp: iso(90), label: "2H" },  // on it
        ]}
      />,
    );
    expect(boundaryCount(html)).toBe(1);
  });
});

/**
 * THE OTHER CHART, WHICH MAKES THE SAME MISTAKE IN THE OPPOSITE DIRECTION.
 *
 * CERT-1989: the server keeps a marker supported by EITHER the probability line
 * or the score line, because one `period_markers` array feeds two charts and it
 * cannot know which of them is blank. So a probability-only kickoff marker
 * legitimately reaches `ScoreDifferentialChart`, and that chart used to bound it
 * against its own `chartData` extent — which contains gap-filled minutes, a
 * `pm_*_spread` constant painted onto every point, and the marker timestamps the
 * component itself inserted. Every marker is inside that by construction.
 *
 * It now bounds against the span of its DRAWN SCORE SERIES, measured before any
 * of that synthesis.
 */
describe("ScoreDifferentialChart period chips need a score line under them", () => {
  const scoreDiffCount = (html: string): number => {
    const m = html.match(/data-period-boundaries="(\d+)"/);
    if (!m) throw new Error("wrapper lost its data-period-boundaries attribute");
    return Number(m[1]);
  };

  const drawScoreDiff = (props: Record<string, unknown>) =>
    draw(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      React.createElement(ScoreDifferentialChart as any, {
        homeTeam: "Ajax",
        awayTeam: "Union SG",
        commenceTime: new Date(KICKOFF).toISOString(),
        eventStatus: "completed",
        sportKey: "soccer_uefa_champs_league",
        ...props,
      }),
    );

  test("a kickoff chip before the first score point does NOT draw", () => {
    // The blocking case: the probability chart has a line at kickoff, so the
    // server keeps the marker — but this chart's scores only start at +60.
    const html = drawScoreDiff({
      history: [],
      scoreHistory: [
        { timestamp: iso(60), home_score: 1, away_score: 0 },
        { timestamp: iso(120), home_score: 2, away_score: 1 },
      ],
      periodBoundaries: [{ timestamp: iso(0), label: "1H" }],
    });

    expect(scoreDiffCount(html)).toBe(0);
  });

  test("the control — a chip inside the score span still draws", () => {
    // Same fixture, marker moved onto the drawn stretch. Without this arm the
    // test above would pass on a chart that had stopped drawing chips at all.
    const html = drawScoreDiff({
      history: [],
      scoreHistory: [
        { timestamp: iso(60), home_score: 1, away_score: 0 },
        { timestamp: iso(120), home_score: 2, away_score: 1 },
      ],
      periodBoundaries: [{ timestamp: iso(90), label: "2H" }],
    });

    expect(scoreDiffCount(html)).toBe(1);
  });

  test("a chart with no series at all renders nothing, chips included", () => {
    // Not `data-period-boundaries="0"` — the component returns null before it
    // has a wrapper to hang the attribute on, which is the older and stronger
    // form of the same answer. Asserted as absence of the whole chart so this
    // does not read as the attribute having gone missing.
    const html = drawScoreDiff({
      history: [],
      scoreHistory: [],
      periodBoundaries: [
        { timestamp: iso(0), label: "1H" },
        { timestamp: iso(47), label: "2H" },
      ],
    });

    expect(html).toBe("");
  });
});
