/**
 * #8182 — A SOURCE THAT DRAWS NO LINE STOPS SAYING "SHOWN AS THIS LINE ON THE CHART".
 *
 * ═══ WHAT A READER GOT ═══
 *
 * `/events/15011303/models` (Real Sociedad 4-1 Real Betis, FINAL), 390px, read
 * off production 2026-09-23 10:33Z. Two cards. The Kalshi one carried:
 *
 *     Kalshi   market                      (no probability at all)
 *     …
 *     1 data points captured for this event
 *     - - -  Shown as this line on the chart
 *
 * The chart draws no Kalshi mark. Kalshi's whole series in the range the chart
 * shows is ONE point, and every series is stroked `dot={false}`, so nothing is
 * rendered. The page named a line, gave its dash pattern in the reader's own
 * colours, and sent them to a plot that has no such line on it. The count
 * above it disagreed with itself in the same breath.
 *
 * ═══ WHY THE PAGE WAS NOT WRONG ABOUT ITS OWN DATA ═══
 *
 * This is the part worth keeping. The page asked for the whole journey and
 * Kalshi genuinely has TWO points there — so any check written against the
 * payload the page already held would have answered "drawable" and shipped
 * green. The chart's first paint asks a DIFFERENT question
 * (`hours=48&range=since_start`), and in that answer Kalshi is one point.
 * Measured on production, same minute, same event:
 *
 *     win_prob_history.kalshi   no range -> 2 points
 *     win_prob_history.kalshi   since_start -> 1 point
 *
 * So the fixtures below are a PAIR, and they differ in exactly that way. A
 * single fixture serving both reads cannot express the defect at all, which is
 * why `it("is the two-range gap doing the work, not a blanket hide")` exists
 * below: it feeds the page's own untrimmed payload in as the chart payload and
 * requires Kalshi to be judged DRAWABLE. If that arm ever goes green alongside
 * the others, this file has stopped testing the thing it was written for.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * An over-claim is fixed by drawing less, so the failure mode of the fix is an
 * UNDER-claim — and the card that would take it is Betting, which draws on
 * essentially every one of these pages. The census runs first and the Betting
 * strip is required by name, so "Kalshi stopped claiming a line" can never pass
 * by the page having stopped claiming anything.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  drawableChartSources,
  MIN_POINTS_TO_STROKE,
} from "@/lib/event/chartDrawableSources";
import type { EventHistoryResponse } from "@/lib/types";

/**
 * The two fixtures below are the fields of the real payload this page and this
 * chart actually read, not whole `EventHistoryResponse`s — everything else on
 * the wire is irrelevant to the claim under test and inventing it would only
 * make the specimen harder to compare against the production capture it came
 * from. Narrowed once, here, rather than with a cast at each use.
 */
const asPayload = (p: unknown) => p as EventHistoryResponse;

const pts = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    timestamp: new Date(Date.parse("2026-09-20T18:00:00.000Z") + i * 60000).toISOString(),
    home_probability: 0.5,
  }));

const EVENT = {
  id: 15011303,
  home_team: "Real Sociedad",
  away_team: "Real Betis",
  status: "completed",
  current_odds: { home_probability: 0.942 },
  // The specimen carries NO kalshi key here — which is why that card prints no
  // percentage. Kept, because it is the state the defect was photographed in.
  win_probability_sources: {},
};

/**
 * What the PAGE asks for: the whole journey.
 *
 * `polymarket` is the POSITIVE CONTROL and it is not decoration. Betting alone
 * cannot stand in for one, because betting is admitted off `history` — a
 * different branch of the rule entirely. Without a model source that survives,
 * "kalshi stopped claiming a line" would also pass on a fix that hid every
 * `win_prob_history` card on the page.
 */
const PAGE_HISTORY = {
  points: 604,
  history: pts(604),
  win_prob_history: { kalshi: pts(2), polymarket: pts(40) },
  win_prob_sources: {
    kalshi: {
      display_name: "Kalshi",
      type: "market",
      color: "#22c55e",
      dash_pattern: "8 4",
      snapshot_count: 1,
    },
    polymarket: {
      display_name: "Polymarket",
      type: "market",
      color: "#3b82f6",
      dash_pattern: "2 2",
      snapshot_count: 40,
    },
  },
};

/**
 * What the CHART asks for: `since_start`. Kalshi is one point — it strokes
 * nothing — while Polymarket kept quoting after kick-off and still draws.
 */
const CHART_HISTORY = {
  points: 45,
  history: pts(45),
  win_prob_history: { kalshi: pts(1), polymarket: pts(40) },
  win_prob_sources: PAGE_HISTORY.win_prob_sources,
};

/**
 * 🪤 THE FETCHER IS RUN, NOT BYPASSED, AND THAT IS LOAD-BEARING.
 *
 * The first version of this mock chose its fixture by matching `range=` in the
 * SWR KEY. It passed everything — including a mutation that left the key alone
 * and changed the actual `fetchEventHistory(...)` call to drop the range, i.e.
 * a page that asks its own question twice and learns nothing about the chart.
 * The key is a label the page writes; the arguments are what goes on the wire.
 * So the fixture is selected by the ARGUMENTS, and the wiring is asserted.
 */
jest.mock("@/lib/api", () => ({
  fetchEvent: jest.fn(() => EVENT),
  fetchEventHistory: jest.fn(
    (_id: number, _hours?: number, range?: string) =>
      range === "since_start" ? CHART_HISTORY : PAGE_HISTORY,
  ),
}));

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: string | null, fetcher: () => unknown) => {
    if (key === null) return { data: undefined, error: undefined };
    return { data: fetcher(), error: undefined };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

import ModelsPage from "@/app/events/[id]/models/page";

function markup(): string {
  return renderToStaticMarkup(
    React.createElement(ModelsPage, { params: { id: "15011303" } }),
  );
}

/** The `data-source` of every card, in render order. */
function cardSources(html: string): string[] {
  return [...html.matchAll(/data-testid="model-source-card" data-source="([^"]+)"/g)].map(
    (m) => m[1],
  );
}

/** The `data-source` of every card that claims a line on the chart. */
function claimsALine(html: string): string[] {
  return [
    ...html.matchAll(/data-testid="model-source-chart-key" data-source="([^"]+)"/g),
  ].map((m) => m[1]);
}

describe("#8182 census — nothing below may pass by the page rendering less", () => {
  it("still draws every card, by name", () => {
    expect(cardSources(markup()).sort()).toEqual(["betting", "kalshi", "polymarket"]);
  });

  it("still prints the number it printed before", () => {
    const html = markup();
    expect(html).toContain("94.2%");
    expect(html).toContain("Real Sociedad");
  });
});

describe("#8182 — the claim is made only where the chart draws a line", () => {
  it("BETTING still says it: 45 points in the chart's range is a real line", () => {
    expect(claimsALine(markup())).toContain("betting");
  });

  it("KALSHI no longer says it — one point in the chart's range strokes nothing", () => {
    expect(claimsALine(markup())).not.toContain("kalshi");
  });

  it("a MODEL source that does draw still says so — this is not a blanket hide", () => {
    // Polymarket goes through the same `win_prob_history` branch kalshi does.
    expect(claimsALine(markup())).toContain("polymarket");
  });

  it("the sentence and the swatch go together — neither is left behind", () => {
    const html = markup();
    expect(claimsALine(html).sort()).toEqual(["betting", "polymarket"]);
    expect(html.match(/Shown as this line on the chart/g)).toHaveLength(2);
    // The dash pattern is the visual half of the claim; Kalshi's must not
    // survive on its own as an unexplained green dashed rule.
    expect(html).not.toContain('stroke-dasharray="8 4"');
    // …while the one belonging to a source that DOES draw is still painted.
    expect(html).toContain('stroke-dasharray="2 2"');
  });
});

describe("#8182 — the count agrees with itself", () => {
  it('prints "1 data point", not "1 data points"', () => {
    const html = markup();
    expect(html).toContain("1 data point ");
    expect(html).not.toContain("1 data points");
  });

  it("still pluralises the counts that are not one", () => {
    // Polymarket's 40 reads the OTHER branch of the same ternary off real
    // rendered text, rather than restating the expression — which would
    // assert nothing at all.
    expect(markup()).toContain("40 data points captured for this event");
  });
});

describe("#8182 — the page asks the CHART's question, not its own twice", () => {
  it("issues the second read with the chart's shared hours and range", () => {
    markup();
    const { fetchEventHistory } = jest.requireMock("@/lib/api");
    expect(fetchEventHistory.mock.calls).toContainEqual([15011303, 48, "since_start"]);
  });

  it("still issues the page's own untrimmed read, which every count depends on", () => {
    markup();
    const { fetchEventHistory } = jest.requireMock("@/lib/api");
    expect(fetchEventHistory.mock.calls).toContainEqual([15011303]);
  });
});

describe("#8182 non-vacuity — the two-range gap is what does the work", () => {
  it("is not a blanket hide: the page's OWN payload judges kalshi drawable", () => {
    // If the fix were "hide kalshi" rather than "ask the chart's range", this
    // arm would go green too and the file would be proving nothing.
    expect(drawableChartSources(asPayload(PAGE_HISTORY)).has("kalshi")).toBe(true);
    expect(drawableChartSources(asPayload(CHART_HISTORY)).has("kalshi")).toBe(false);
  });
});

describe("#8182 — drawableChartSources, the rule on its own", () => {
  it("needs two points: one strokes nothing because every line is dot={false}", () => {
    expect(MIN_POINTS_TO_STROKE).toBe(2);
    expect(drawableChartSources({ win_prob_history: { k: pts(2) } } as never).has("k")).toBe(true);
    expect(drawableChartSources({ win_prob_history: { k: pts(1) } } as never).has("k")).toBe(false);
  });

  it("treats #2000's EMPTIED series as undrawable, so the two fixes agree", () => {
    expect(drawableChartSources({ win_prob_history: { k: [] } } as never).has("k")).toBe(false);
  });

  it("reads BETTING off `history`, which is the series the chart strokes for it", () => {
    expect(drawableChartSources({ history: pts(2) } as never).has("betting")).toBe(true);
    expect(drawableChartSources({ history: pts(1) } as never).has("betting")).toBe(false);
  });

  it("reaches espn_history only as a fallback, mirroring the chart's `else`", () => {
    // No modern series -> the legacy ESPN card is the one on the plot.
    expect(drawableChartSources({ espn_history: pts(9) } as never).has("espn")).toBe(true);
    // Modern series present -> espn_history is NOT what the chart is drawing,
    // so a long legacy array must not credit ESPN with a line.
    expect(
      drawableChartSources({
        win_prob_history: { kalshi: pts(5) },
        espn_history: pts(9),
      } as never).has("espn"),
    ).toBe(false);
  });

  it("answers UNKNOWN as not-drawable, so a failed read cannot print the claim", () => {
    expect(drawableChartSources(undefined).size).toBe(0);
    expect(drawableChartSources(null).size).toBe(0);
    expect(drawableChartSources({} as never).size).toBe(0);
  });
});
