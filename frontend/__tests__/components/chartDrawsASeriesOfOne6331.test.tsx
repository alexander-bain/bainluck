/**
 * #6331 — THE WIRING: a series of one observation reaches the reader.
 *
 * `chartSeriesPath.test.ts` proves which points stand alone. This proves that
 * `FuturesChart` — the kernel behind `/futures/[id]`, `/categories/golf`,
 * `/sport/[sport]/[league]`, `TeamSeasonJourney`, `WinnerEvolutionChart`,
 * `SettledPathChart` and `RaceToTitleChart` — actually draws them, and that the
 * healthy charts those surfaces mostly plot gain nothing at all.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/futures/58675941` ("Vuelta a España 2026: Winner", settled), 390px, read by
 * lane1b/266 on v4572: a Probability Trend panel with a legend naming **Other**
 * — the graded champion — beside a plot with nothing of its colour anywhere in
 * it. #6110 mints the leg the venue settled and we never priced, so that series
 * carries exactly ONE point (100%, frozen at 2026-09-14T04:51:16Z by #6360),
 * and `FuturesChart` opened with `if (points.length < 2) return null`. The
 * result the market actually reached was the one thing the chart of that market
 * would not draw.
 *
 * ═══ WHY A GUARD CHANGE ALONE DID NOT PAY IT ═══
 *
 * `chartSeriesPath` has emitted a zero-length subpath for an isolated point
 * since #3659, painted as a round dot by `stroke-linecap="round"`. Reaching it
 * is a one-word change — and photographed at phone width it came out a **1.5
 * CSS px speck** in the top-right corner of a 600px-wide plot, under a
 * full-size legend swatch. Still "draws nothing" to the person reading it. A
 * line is legible because it is long; a point of the same thickness is not. So
 * the observation is marked in the chart's existing dot vocabulary (the hover
 * dot's `r={4}`, one size down), and this file asserts the mark, not the guard.
 *
 * ═══ THE PAIR ═══
 *
 * Every case here is two-sided, for the reason #2961 and #3659 both wrote into
 * this suite: a chart that always draws a dot has moved the problem, not fixed
 * it. The negative cases are the load-bearing ones.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesOutcomeHistory } from "../../lib/types";

const HOUR = 60 * 60 * 1000;
const NOW = Date.UTC(2026, 8, 15, 7, 36, 0);
// The market opened 2026-08-08T12:02:31Z; the field's last real reading is
// 2026-09-14T04:51:16Z. Fixed anchors — never Date.now() (gotcha #44).
const OPENED = Date.UTC(2026, 7, 8, 12, 2, 31);
const LAST = Date.UTC(2026, 8, 14, 4, 51, 16);

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => {
  jest.useRealTimers();
});

function points(stamps: readonly number[], prob: number) {
  return stamps.map((t) => ({
    timestamp: new Date(t).toISOString(),
    probability: prob,
    american_odds: null,
    bookmaker: "blend",
  }));
}

/** A rider: two readings in August, a 34-day hole, then a run in September. */
function rider(id: number, name: string, prob: number): FuturesOutcomeHistory {
  return {
    outcome_id: id,
    name,
    history: points(
      [
        OPENED,
        OPENED + 0.5 * HOUR,
        ...Array.from({ length: 15 }, (_, k) => LAST - (14 - k) * 4 * HOUR),
      ],
      prob,
    ),
  };
}

/** The graded champion: one observation, at 100%, and nothing before it. */
const CHAMPION: FuturesOutcomeHistory = {
  outcome_id: 99,
  name: "Other",
  history: [
    {
      timestamp: new Date(LAST).toISOString(),
      probability: 1,
      american_odds: null,
      bookmaker: "settlement",
    },
  ],
};

const VUELTA: FuturesOutcomeHistory[] = [
  rider(1, "Tadej Pogacar", 0.865),
  rider(2, "Richard Carapaz", 0.49),
  CHAMPION,
];

/** A field where every series is healthy — the six surfaces' normal case. */
const HEALTHY: FuturesOutcomeHistory[] = [
  rider(1, "Tadej Pogacar", 0.865),
  rider(2, "Richard Carapaz", 0.49),
];

/** Every `<circle>` in the rendered SVG, as raw tags. */
function circles(html: string): string[] {
  return html.match(/<circle[^>]*>/g) ?? [];
}

/** The `cx`/`cy`/`r`/`fill` of each circle, parsed. */
function marks(html: string) {
  return circles(html).map((c) => ({
    cx: Number(/cx="([-\d.]+)"/.exec(c)?.[1]),
    cy: Number(/cy="([-\d.]+)"/.exec(c)?.[1]),
    r: Number(/r="([-\d.]+)"/.exec(c)?.[1]),
    fill: /fill="([^"]+)"/.exec(c)?.[1],
  }));
}

describe("#6331 the settled champion's only observation is drawn", () => {
  test("RED-FIRST: the champion's series produces a mark at all", () => {
    // On master this array is empty — `points.length < 2` returned null before
    // anything could be drawn, so the panel had a legend entry and no plot.
    const html = renderToStaticMarkup(
      <FuturesChart historyData={VUELTA} settled height={200} />,
    );

    expect(marks(html)).toHaveLength(1);
  });

  test("the mark sits at 100%, at the instant the market settled", () => {
    // Not at the clock and not at the plot's edge: a chart whose whole job is
    // WHEN things moved may not place a result at a time we did not observe.
    // #6360 froze this point at the field's own last reading; the mark has to
    // land on the same x as the riders' final points, and on the 100% line.
    const html = renderToStaticMarkup(
      <FuturesChart historyData={VUELTA} settled height={200} />,
    );
    const [mark] = marks(html);

    // y: 100% on a 0–1 axis is the top of the plot area (padding.top = 20).
    expect(mark.cy).toBe(20);
    // x: the champion's stamp IS the field's newest stamp, so it is maxTime —
    // the right edge of the plot area (chartWidth 800 − padding.right 20).
    expect(mark.cx).toBe(780);
  });

  test("the mark is the series' own colour, so it matches its legend swatch", () => {
    // The defect was a legend entry with no counterpart in the plot. A mark in
    // a different colour would leave that exactly as it was.
    const html = renderToStaticMarkup(
      <FuturesChart historyData={VUELTA} settled height={200} />,
    );
    const [mark] = marks(html);

    // Third series → third palette entry. Read off the rendered line colours
    // rather than restated, so a palette change cannot make this pass falsely.
    const strokes = [...html.matchAll(/<path[^>]*stroke="(#[0-9a-fA-F]{6})"/g)].map(
      (m) => m[1],
    );
    expect(strokes).toContain(mark.fill);
    // …and specifically NOT a colour already carrying a rider's line.
    const riderStrokes = strokes.filter((s) => s !== mark.fill);
    expect(riderStrokes).not.toContain(mark.fill);
  });

  test("the mark is bigger than the line weight — the speck was the defect", () => {
    // A zero-length subpath is painted at the LINE's width (2), which measured
    // 1.5 CSS px on the real page. This is the assertion that keeps the fix a
    // fix: whatever the radius becomes, it may not shrink back to the stroke.
    const html = renderToStaticMarkup(
      <FuturesChart historyData={VUELTA} settled height={200} />,
    );
    const [mark] = marks(html);

    expect(mark.r * 2).toBeGreaterThan(2);
  });
});

describe("#6331 a healthy chart gains nothing", () => {
  test("no series of one, no marks", () => {
    // The load-bearing negative: six of the seven surfaces plot unbroken lines
    // nearly all of the time, and none of them may sprout dots.
    const html = renderToStaticMarkup(
      <FuturesChart historyData={HEALTHY} settled height={200} />,
    );

    expect(marks(html)).toEqual([]);
  });

  test("a hole between two healthy runs draws a bridge and no mark", () => {
    // Both riders carry the 34-day hole this market really has. A break in a
    // line is not an isolated observation, and must not be marked as one.
    const html = renderToStaticMarkup(
      <FuturesChart historyData={HEALTHY} settled height={200} />,
    );

    expect(html).toContain('stroke-dasharray="1 5"'); // the #3659 bridge
    expect(marks(html)).toEqual([]);
  });

  test("the champion is the ONLY thing marked on the settled field", () => {
    // Two riders with holes plus one lone champion: exactly one mark.
    const html = renderToStaticMarkup(
      <FuturesChart historyData={VUELTA} settled height={200} />,
    );

    expect(marks(html)).toHaveLength(1);
  });
});

describe("#6331 the mark carries the chart's existing weighting", () => {
  test("dimmed when another series is highlighted", () => {
    // The champion's mark must fade with its line, not sit at full strength
    // over a dimmed field — it is the same series, said once.
    const html = renderToStaticMarkup(
      <FuturesChart
        historyData={VUELTA}
        settled
        height={200}
        highlightedOutcomeId={1}
      />,
    );
    const [mark] = circles(html);

    expect(mark).toContain('fill-opacity="0.2"');
  });

  test("at full strength when nothing is highlighted", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={VUELTA} settled height={200} />,
    );
    const [mark] = circles(html);

    expect(mark).toContain('fill-opacity="1"');
  });

  test("a mini sparkline marks it smaller, and still marks it", () => {
    // `mini` has a 4px padding and a 1.5 line: a 3-radius dot would be a blob.
    const html = renderToStaticMarkup(
      <FuturesChart historyData={VUELTA} mini settled />,
    );
    const [mark] = marks(html);

    expect(mark).toBeDefined();
    expect(mark.r).toBeLessThan(3);
  });
});

describe("#6331 what this fix deliberately does not touch", () => {
  test("the gap caption still describes the hole it always described", () => {
    // Arm 1 of the issue was measured and REFUTED by ux/1271: the 34-day
    // sentence is the union's real largest gap, to the minute. Suppressing it
    // would delete a true warning about a line bridging a month of silence.
    // Pinned here so a later pass at this panel does not "tidy" it away.
    //
    // Read ten minutes after the field's last observation, because
    // `seriesFreshness` ranks "behind NOW" ABOVE "holed" and every rider shares
    // the same stamps, so the union's median gap is 0 and `staleAfter` collapses
    // to the 15-minute floor. Which of the two sentences the panel prints is
    // therefore a fact about the clock, not about this fix.
    //
    // Worth recording, because it re-reads the original capture: lane1b saw the
    // gap sentence at 07:36Z on a 26-hour-old field only BECAUSE #6360 was
    // stamping the champion's point at `now()` — age ≈ 0 let the gapped branch
    // win. With that point frozen, this page now prints "Last number 26 hours
    // ago", which is true. So the pin here is the caption's survival in
    // general, on a series that really is holed-but-fresh.
    jest.setSystemTime(LAST + 10 * 60 * 1000);
    try {
      const html = renderToStaticMarkup(
        <FuturesChart historyData={VUELTA} settled height={200} />,
      );

      expect(html).toMatch(/No numbers for \d+ days in this stretch/);
      // …and the champion is still marked while that sentence is on screen:
      // the caption and the mark describe different things and neither
      // suppresses the other.
      expect(marks(html)).toHaveLength(1);
    } finally {
      jest.setSystemTime(NOW);
    }
  });

  test("a series with no points at all is still not drawn", () => {
    // The guard moved from `< 2` to `=== 0`, and the floor has to hold: an
    // outcome we have never priced gets no mark, because there is nothing to
    // mark. Its legend entry is a separate question and not this fix's.
    const empty: FuturesOutcomeHistory[] = [
      ...HEALTHY,
      { outcome_id: 42, name: "Never priced", history: [] },
    ];
    const html = renderToStaticMarkup(
      <FuturesChart historyData={empty} settled height={200} />,
    );

    expect(marks(html)).toEqual([]);
  });

  test("a null-probability-only series is not drawn either", () => {
    // `probability: null` rows are filtered before the guard, so a series of
    // nothing-but-nulls reaches it as length 0 and must behave like the above.
    const nulls: FuturesOutcomeHistory[] = [
      ...HEALTHY,
      {
        outcome_id: 43,
        name: "All nulls",
        history: [
          {
            timestamp: new Date(LAST).toISOString(),
            probability: null,
            american_odds: null,
            bookmaker: "blend",
          },
        ],
      },
    ];
    const html = renderToStaticMarkup(
      <FuturesChart historyData={nulls} settled height={200} />,
    );

    expect(marks(html)).toEqual([]);
  });
});
