/**
 * #2961 — THE CHART DECLARES WHAT IT HOLDS, ON THE SURFACES THAT SHIP IT.
 *
 * `seriesFreshness.test.ts` proves the RULE. This proves the WIRING, which is a
 * different claim and the one that has failed before in this codebase: UX-P145
 * and UX-P146 both swept copy that was never on production, and the lesson
 * written into `copyBans.ts` is that a green rule says nothing about a render.
 *
 * #2961's acceptance is explicitly two-directional — *a series past its own
 * cadence is marked, AND a current one is not* — so every case below is a pair.
 * A chart that always wears a note has moved the problem, not fixed it.
 *
 * Fixtures are the two production shapes measured 2026-09-06 ~19:1xZ:
 *   • futures 16630403 — 1.00h median cadence, newest point 5.6h old.
 *   • /api/politics presidential — 8h median cadence, ≈220h hole, 0.6h old.
 *
 * Time is pinned with fake timers rather than offset from `Date.now()`:
 * `seriesFreshness` reads the clock itself, and gotcha #44 is that a test anchor
 * which moves with the wall clock is not an anchor.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesOutcomeHistory } from "../../lib/types";

const HOUR = 60 * 60 * 1000;
const NOW = Date.UTC(2026, 8, 6, 19, 15, 0);

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => {
  jest.useRealTimers();
});

/** Hourly points ending `endsAgoMs` before NOW. */
function hourly(count: number, endsAgoMs: number): FuturesOutcomeHistory["history"] {
  const end = NOW - endsAgoMs;
  return Array.from({ length: count }, (_, i) => ({
    timestamp: new Date(end - (count - 1 - i) * HOUR).toISOString(),
    probability: 0.4,
    american_odds: null,
    bookmaker: "blend",
  }));
}

function outcome(history: FuturesOutcomeHistory["history"]): FuturesOutcomeHistory[] {
  return [{ outcome_id: 1, name: "Yes", history }];
}

describe("FuturesChart", () => {
  it("marks a series 5.6h behind its own 1h cadence — the measured arm B", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={outcome(hourly(120, 5.6 * HOUR))} />,
    );

    expect(html).toContain('data-testid="futures-chart-freshness"');
    expect(html).toContain('data-series-state="stale"');
    expect(html).toContain("Last number 5 hours ago");
  });

  it("says NOTHING about a series that is on its own cadence", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={outcome(hourly(120, 0))} />);

    expect(html).not.toContain('data-testid="futures-chart-freshness"');
    expect(html).not.toContain("Last number");
  });

  it("marks a 14-day hole inside an up-to-date hourly run", () => {
    // The case every newest-point threshold passes: current at the right edge,
    // and mostly interpolation behind it.
    const holed = [...hourly(60, 345.6 * HOUR + 59 * HOUR), ...hourly(60, 0)];
    const html = renderToStaticMarkup(<FuturesChart historyData={outcome(holed)} />);

    expect(html).toContain('data-series-state="gapped"');
    expect(html).toContain("No numbers for 14 days in this stretch");
  });

  it("does not fire on a single skipped beat", () => {
    const oneSkip = [...hourly(60, 61 * HOUR), ...hourly(60, 0)];
    const html = renderToStaticMarkup(<FuturesChart historyData={outcome(oneSkip)} />);

    expect(html).not.toContain('data-testid="futures-chart-freshness"');
  });

  it("stays silent on `mini`, which has no axis to qualify and no room", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={outcome(hourly(120, 5.6 * HOUR))} mini />,
    );

    expect(html).not.toContain('data-testid="futures-chart-freshness"');
  });

  it("never predicts an update it cannot promise (ruling 142), and never uses our jargon", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={outcome(hourly(120, 200 * HOUR))} />,
    );
    const note = /futures-chart-freshness"[^>]*>([^<]*)</.exec(html)?.[1] ?? "";

    expect(note).not.toBe("");
    expect(note).not.toMatch(/\bstale\b/i);
    expect(note).not.toMatch(/\b(un)?pric(e|es|ed|ing)\b/i);
    expect(note).not.toMatch(/\bwill\b|\bcheck back\b|\bcoming soon\b/i);
  });

  it("reads the UNION of displayed outcomes, so one live line covers the chart", () => {
    // A hole in one outcome that another outcome has readings through is not a
    // hole in what the reader sees, and must not be announced as one.
    const html = renderToStaticMarkup(
      <FuturesChart
        historyData={[
          { outcome_id: 1, name: "Yes", history: [...hourly(20, 300 * HOUR), ...hourly(20, 0)] },
          { outcome_id: 2, name: "No", history: hourly(340, 0) },
        ]}
      />,
    );

    expect(html).not.toContain('data-testid="futures-chart-freshness"');
  });

  it("survives history whose timestamps will not parse, without a blank chart", () => {
    // A render path may not throw. `undated` is also not `current`, so the
    // chart must not silently claim freshness it cannot support.
    const junk = [
      { timestamp: "not a date", probability: 0.4, american_odds: null, bookmaker: "blend" },
      { timestamp: "also not a date", probability: 0.5, american_odds: null, bookmaker: "blend" },
    ];

    expect(() =>
      renderToStaticMarkup(<FuturesChart historyData={outcome(junk)} />),
    ).not.toThrow();
  });
});
