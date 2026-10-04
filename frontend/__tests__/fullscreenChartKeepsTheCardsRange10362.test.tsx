// #10362 — the fullscreen chart opens on the range the card shows, and offers
// the same All / Since Start toggle.
//
// Shopper walk, production `/events/15319770` (Navy @ Air Force) at 390px,
// 2026-10-03 ~17:05Z; ux reproduced on `/events/15319718` at 20:25Z (artifact
// `artifacts/ux-1003-10362/before-all-then-expand.png`). With the card on "All",
// tapping expand drew the chart from kickoff, and there was no control to get
// back. Two causes, one per half of this file:
//
//   1. The page handed the fullscreen `<OddsChart>` none of the card's range
//      inputs (no `chartStartTime`/`chartEndTime`, no `externalTimeRange`), so
//      it fell back to its own default window.
//   2. The toggle WAS rendered, but `fillContainer` gave it a white-on-dark pill
//      (`text-white/15`) left over from the black modal. The dialog is
//      `bg-surface-card` since #10250, so the pills were white on white.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import OddsChart from "@/components/OddsChart";
import { AnalyticsProvider } from "@/components/Analytics";

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
    "utf8",
  ),
);

function render(fillContainer: boolean, externalTimeRange: "all" | "live"): string {
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
        fillContainer,
        externalTimeRange,
        onTimeRangeChange: () => {},
      } as never),
    ),
  );
}

/** label → { pressed, className } for every range pill in the markup. */
function rangePills(html: string): Record<string, { pressed: string; cls: string }> {
  const out: Record<string, { pressed: string; cls: string }> = {};
  const re = /<button[^>]*aria-pressed="(true|false)"[^>]*>(All|Since Start)<\/button>/g;
  for (const m of html.matchAll(re)) {
    const cls = m[0].match(/class="([^"]*)"/);
    out[m[2]] = { pressed: m[1], cls: cls ? cls[1] : "" };
  }
  return out;
}

describe("#10362 the fullscreen range pills are visible on the white dialog", () => {
  const card = rangePills(render(false, "all"));
  const full = rangePills(render(true, "all"));

  it("renders both pills in both layouts (the file is not vacuous)", () => {
    expect(Object.keys(card).sort()).toEqual(["All", "Since Start"]);
    expect(Object.keys(full).sort()).toEqual(["All", "Since Start"]);
  });

  it("styles the fullscreen pills exactly like the card's", () => {
    for (const label of ["All", "Since Start"]) {
      expect(full[label].cls).toBe(card[label].cls);
    }
  });

  it("never paints a pill in white text", () => {
    for (const label of ["All", "Since Start"]) {
      expect(full[label].cls).not.toMatch(/text-white/);
    }
  });

  it("follows the page's range in fullscreen, in both directions", () => {
    expect(full["All"].pressed).toBe("true");
    const live = rangePills(render(true, "live"));
    expect(live["Since Start"].pressed).toBe("true");
    expect(live["All"].pressed).toBe("false");
  });
});

// ── The page half: the fullscreen chart takes the card's range inputs ────────

const PAGE = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");

/** The `<OddsChart … />` element source starting at the first match after `from`. */
function oddsChartAfter(from: number): string {
  const start = PAGE.indexOf("<OddsChart", from);
  if (start < 0) throw new Error("no <OddsChart after offset");
  const end = PAGE.indexOf("/>\n", PAGE.indexOf("awayWithheld", start));
  return PAGE.slice(start, end);
}

function propValue(element: string, prop: string): string | null {
  const m = element.match(new RegExp(`\\b${prop}=\\{([^}]*)\\}`));
  return m ? m[1].trim() : null;
}

const RANGE_PROPS = [
  "chartStartTime",
  "chartEndTime",
  "sharedTicks",
  "chartLabelFormat",
  "externalTimeRange",
  "onTimeRangeChange",
];

describe("#10362 the fullscreen chart is handed the card's range", () => {
  // The card chart is the one that reports its rendered domain back to the page.
  const cardChart = oddsChartAfter(PAGE.indexOf("<OddsChart"));
  const dialogAt = PAGE.indexOf("<ChartFullscreenDialog");
  const fullChart = oddsChartAfter(dialogAt);

  it("finds two distinct charts (control: the card is the onRenderedDomain one)", () => {
    expect(dialogAt).toBeGreaterThan(0);
    expect(cardChart).toMatch(/onRenderedDomain=\{handleRenderedDomain\}/);
    expect(fullChart).toMatch(/\bfillContainer\b/);
    expect(fullChart).not.toBe(cardChart);
  });

  it.each(RANGE_PROPS)("passes %s with the same value as the card", (prop) => {
    const cardValue = propValue(cardChart, prop);
    expect(cardValue).not.toBeNull();
    expect(propValue(fullChart, prop)).toBe(cardValue);
  });
});
