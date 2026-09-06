// #3425 — no chart attribute is ever the string "NaN".
//
// Every event page logged 8+ browser console errors on load:
//
//   Error: <stop> attribute offset: Expected number or percentage, "NaN".
//
// with React's SSR twin, `Warning: Received NaN for the 'offset' attribute`.
//
// The chain, all three links needed to fire it:
//
//   1. `primarySeriesKey` is `nonBettingSources[0].dataKey` on any chart with
//      no sportsbook history and no backend blend — i.e. every single-source
//      match, which is what a settled Kalshi-only US Open page is.
//   2. `ensurePoint` seeds only homeDelta/espnDelta/bainLuckDelta, so a
//      gap-filled minute carries no such property and reads `undefined`.
//      Forward-fill cannot cover the minutes BEFORE the first real point —
//      there is no `lastKnown` yet — and the shared domain routinely opens
//      before the data (a ticker-derived `commence_time` put 15h56m of those
//      in front of /events/15300276, which is #3419).
//   3. The readers tested `!== null`. `undefined !== null` is TRUE, and the
//      `(v): v is number` annotation then asserted it was a number, so
//      `Math.max(...)` returned NaN.
//
// The gradient those stops belonged to was DEAD — defined once, referenced by
// nothing (no `url(#probFillGradient-…)`, no <Area>) — so it is deleted rather
// than repaired, and the shared `primaryValueAt` reader makes the remaining
// two consumers honest about the difference between "null" and "absent".
//
// The assertion is the reader's property, not the constant: NO attribute may
// be NaN. Pinning `offset` alone would go green the next time a different
// numeric prop is fed an absent key.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

import OddsChart from "@/components/OddsChart";

// Verbatim shape of /events/15300276: one non-betting source, no sportsbook
// history, no backend blend. Fixed anchor — never Date.now() (gotcha #44).
const FIRST_POINT = Date.UTC(2026, 8, 2, 15, 56, 0);
const KALSHI = Array.from({ length: 12 }, (_, i) => ({
  timestamp: new Date(FIRST_POINT + i * 60_000).toISOString(),
  home_probability: 0.3 + (i % 5) * 0.1,
  away_probability: 0.7 - (i % 5) * 0.1,
}));

/** The domain the event page passes, opening BEFORE the first point (#3419). */
const DOMAIN_OPENS_EARLY = {
  chartStartTime: "2026-09-02T00:00:00.000Z",
  chartEndTime: "2026-09-02T16:08:00.000Z",
  sharedTicks: ["12:00 AM"],
};

function render(props: Record<string, unknown>) {
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Rafael Jodar"
      awayTeam="Yu Bu"
      commenceTime="2026-09-02T00:00:00+00:00"
      isLive={false}
      eventStatus="closed"
      externalTimeRange="live"
      {...props}
    />,
  );
}

/** Every attribute rendered as the literal string NaN. */
const nanAttributes = (html: string): string[] =>
  html.match(/[\w-]+="NaN"/g) ?? [];

const SINGLE_SOURCE = {
  winProbHistory: { kalshi: KALSHI },
  winProbSources: {
    kalshi: { display_name: "Kalshi", color: "#22c55e", type: "prediction_market" },
  },
};

describe("#3425 the chart never renders a NaN attribute", () => {
  test("a single-source chart whose domain opens before its data", () => {
    const html = render({ ...SINGLE_SOURCE, ...DOMAIN_OPENS_EARLY });

    // Not vacuous: the rig has to have actually drawn the chart, or the
    // assertion below passes over an empty string. This is the half that
    // would have hidden the bug.
    expect(html).toContain("recharts-line-curve");

    expect(nanAttributes(html)).toEqual([]);
  });

  test("the dead gradient is gone rather than repaired", () => {
    const html = render({ ...SINGLE_SOURCE, ...DOMAIN_OPENS_EARLY });
    // It was referenced by nothing, so it can only ever have emitted errors.
    // If someone reinstates it, they own giving it a real offset AND a fill
    // that consumes it — this arm makes that a decision, not an accident.
    expect(html).not.toContain("probFillGradient");
    expect(html).not.toContain("<stop");
  });

  test("control: the readers that survive still read the series", () => {
    // `primaryValueAt` replaced the `!== null` guard in the lead-change count
    // and the current-probability callout too. Those must still SEE the data —
    // a reader that returns null for everything also emits no NaN.
    const html = render({ ...SINGLE_SOURCE, ...DOMAIN_OPENS_EARLY });
    const lead = /Lead changes \((\d+)\)/.exec(html);
    expect(lead).not.toBeNull();
    expect(Number(lead![1])).toBeGreaterThan(0);
  });

  test("control: a same-shape chart with NO early domain is unaffected", () => {
    const html = render(SINGLE_SOURCE);
    expect(html).toContain("recharts-line-curve");
    expect(nanAttributes(html)).toEqual([]);
  });
});
