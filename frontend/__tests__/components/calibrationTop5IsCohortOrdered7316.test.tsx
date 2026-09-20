/**
 * #7316 — the By Category "Top 5" tab is the top 5 of the cohort on screen.
 *
 * Reproduced against the live payload (`/api/calibration`, 2026-09-19 23:0xZ) in
 * the DEFAULT (traded) view — the one every reader lands on. The tab labelled
 * "Top 5" rendered, in this order:
 *
 *     Baseball (129,771)
 *     Soccer (58,440)          <- printed ABOVE a category twice its size
 *     Basketball (118,714)
 *     Tennis (25,207)
 *     Weather (12,967)         <- displaced Football (22,684), 41% smaller
 *
 * Two defects in one legend: the numbers do not descend, and the fifth slot is
 * the wrong category. `catChartData` selected with `categories.slice(0, 5)` —
 * `categories` is sorted by the UNFILTERED total — while each label's number was
 * computed WITH `cohortFilter`. Selection and display were reading two different
 * populations.
 *
 * It corrected itself when the reader flipped the toggle to the all-cohort side,
 * because that is the order the list was sorted in. The default view was the
 * broken one.
 *
 * ═══ #7190 PREDICTED THIS EXACT PAIR, ONE SECTION UP ═══
 *
 * The Categories card had the same bug and its fix comment names these two rows
 * by name: "traded basketball (118,714) outranks traded soccer (58,440) while
 * all-cohort soccer outranks basketball". Those are the production numbers
 * above. #7190 re-sorted `categoryMetrics` for the card and left the chart and
 * the tab strip on `categories`. Same shape as #6265, #7183 and #7190 itself:
 * the rule is not missing, one more call site skipped it.
 *
 * ═══ WHY THE FIXTURE HAS SIX CATEGORIES, NOT FOUR ═══
 *
 * #7190's fixture proves an ORDER inversion, and with four categories a top-5
 * slice cuts nothing — every ordering has the same membership, so a fixture that
 * small cannot see the worse half of this defect. Six categories make the cut
 * real, and the split is chosen so the two orderings differ BOTH ways:
 *
 *   category      traded    untraded    all-cohort
 *   baseball     120,000      70,000      190,000
 *   basketball   118,000      11,000      129,000
 *   soccer        58,000      74,000      132,000
 *   tennis        20,000      42,000       62,000
 *   football      22,000       8,000       30,000
 *   weather       12,000      29,000       41,000
 *
 *   ALL-COHORT top 5: baseball, soccer, basketball, tennis, weather
 *   TRADED     top 5: baseball, basketball, soccer, football, tennis
 *                     └ swap ┘              └ football IN, weather OUT ┘
 *
 * So a fix that re-sorts but keeps selecting from the unfiltered list still
 * shows Weather and still hides Football, and a fix that selects correctly but
 * does not re-sort still prints Soccer above Basketball. Neither passes.
 *
 * Every category clears the 1,000-outcome publish bar in BOTH cohorts, so
 * nothing here is testing the floor by accident, and no traded total can be
 * mistaken for an all-cohort one.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";

// The page is a `"use client"` component behind SWR. Mock the hook, not the
// fetcher: `renderToStaticMarkup` never runs an effect, so a real SWR hands the
// page `undefined` and the suite photographs the loading state instead. (#6265)
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as unknown as { __calPayload: CalibrationData }).__calPayload,
  }),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

// #7190's suite mocks the chart to `null`; this one is ABOUT the chart's series,
// so the mock has to publish them. The labels are the component's own — built in
// `catChartData` — not re-derived here, or the assertion would be checking this
// file's arithmetic instead of the page's.
jest.mock("@/components/CalibrationChart", () => ({
  __esModule: true,
  default: ({ series }: { series?: { label: string }[] }) => {
    const ReactLib = require("react");
    return ReactLib.createElement("div", {
      "data-testid": "chart-series",
      "data-labels": (series ?? []).map(s => s.label).join("|"),
    });
  },
}));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import CalibrationPage from "@/app/calibration/page";

const SPLIT = [
  { category: "baseball", traded: 120_000, untraded: 70_000 },
  { category: "basketball", traded: 118_000, untraded: 11_000 },
  { category: "soccer", traded: 58_000, untraded: 74_000 },
  { category: "tennis", traded: 20_000, untraded: 42_000 },
  { category: "football", traded: 22_000, untraded: 8_000 },
  { category: "weather", traded: 12_000, untraded: 29_000 },
];

const traded = (c: string) => SPLIT.find(s => s.category === c)!.traded;
const all = (c: string) => {
  const s = SPLIT.find(x => x.category === c)!;
  return s.traded + s.untraded;
};
const topBy = (f: (c: string) => number, k: number) =>
  [...SPLIT].sort((a, b) => f(b.category) - f(a.category)).slice(0, k).map(s => s.category);

/** The wire's bucket shape — `bucket_idx`/`avg_prob`/`winners`, not a guess. */
function bucket(category: string, idx: number, priceMoved: boolean, n: number) {
  return {
    bucket_idx: idx,
    source: "kalshi",
    category,
    price_moved: priceMoved,
    n,
    winners: Math.round(n * (0.05 + idx * 0.1)),
    avg_prob: 0.05 + idx * 0.1,
    sum_prob: n * (0.05 + idx * 0.1),
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

function makePayload(): CalibrationData {
  const buckets = SPLIT.flatMap(s =>
    [0, 1, 2, 3, 4].flatMap(i => [
      bucket(s.category, i, true, s.traded / 5),
      bucket(s.category, i, false, s.untraded / 5),
    ]),
  );
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: SPLIT.reduce((t, s) => t + s.traded + s.untraded, 0),
    total_winners: 200_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-19T10:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-19" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: SPLIT.map(s => ({ category: s.category, ece: 0.02, n: all(s.category) })),
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/** Just the By Category section, so no other chart or tab strip can answer. */
function byCategorySection(html: string): string {
  const start = html.indexOf('data-testid="calibration-by-category"');
  expect(start).toBeGreaterThan(-1);
  return html.slice(start);
}

/** The series the By Category chart was actually handed, in order. */
function chartLabels(html: string): string[] {
  const m = /data-testid="chart-series" data-labels="([^"]*)"/.exec(byCategorySection(html));
  expect(m).not.toBeNull();
  return m![1] ? m![1].split("|") : [];
}

/** `Baseball (120,000)` -> `baseball`; the label is the page's, parsed not rebuilt. */
const labelCategory = (l: string) => l.replace(/\s*\([\d,]+\)\s*$/, "").trim().toLowerCase();
const labelN = (l: string) => Number(/\(([\d,]+)\)/.exec(l)![1].replace(/,/g, ""));

/** The category chips, in render order, excluding the leading "Top 5" button. */
function tabLabels(html: string): string[] {
  const strip = byCategorySection(html);
  const start = strip.indexOf('data-testid="calibration-category-tabs"');
  expect(start).toBeGreaterThan(-1);
  const end = strip.indexOf("</div>", start);
  const out = [...strip.slice(start, end).matchAll(/<button[^>]*>([^<]+)<\/button>/g)].map(m => m[1]);
  expect(out[0]).toBe("Top 5");
  return out.slice(1).map(s => s.trim().toLowerCase());
}

/* ═══════ the harness proves itself, and proves the fixture can separate ═══════ */

describe("the harness renders the real calibration page", () => {
  test("positive control: the page is built, not a loading shell", () => {
    // Several assertions below are absences, and a loading state satisfies them.
    const html = render();
    expect(html).toContain("calibration-by-category");
    expect(chartLabels(html).length).toBe(5);
    expect(tabLabels(html).length).toBe(SPLIT.length);
  });

  test("🔴 the fixture separates the two orderings in BOTH membership and order", () => {
    // Without this the tests below can pass against the bug. Asserted on the
    // fixture itself, before anything is asserted on the page.
    const allTop5 = topBy(all, 5);
    const tradedTop5 = topBy(traded, 5);
    // membership differs: football is in one, weather in the other
    expect(allTop5).toContain("weather");
    expect(allTop5).not.toContain("football");
    expect(tradedTop5).toContain("football");
    expect(tradedTop5).not.toContain("weather");
    // and the order differs too — production's soccer/basketball inversion
    expect(all("soccer")).toBeGreaterThan(all("basketball"));
    expect(traded("basketball")).toBeGreaterThan(traded("soccer"));
    // every category clears the publish bar in both cohorts
    for (const s of SPLIT) expect(Math.min(s.traded, all(s.category))).toBeGreaterThan(1_000);
  });
});

/* ════════════ SHIP — "Top 5" means the five the page is showing ════════════ */

describe('#7316 — the "Top 5" tab is the cohort\'s top 5', () => {
  test("🔴 the five are selected by the cohort, so Football is in and Weather is out", () => {
    // The half a re-sort alone does not fix. This was false on production.
    const shown = chartLabels(render()).map(labelCategory);
    expect(shown.sort()).toEqual([...topBy(traded, 5)].sort());
  });

  test("🔴 the legend's own numbers descend", () => {
    // The half a membership-only fix does not fix: production printed Soccer
    // (58,440) above Basketball (118,714).
    const ns = chartLabels(render()).map(labelN);
    expect(ns).toEqual([...ns].sort((a, b) => b - a));
  });

  test("🔴 the numbers are the COHORT's, never the all-cohort superset", () => {
    // Guards the other direction: selecting correctly but labelling with the
    // unfiltered totals would satisfy both tests above.
    for (const l of chartLabels(render())) {
      expect(labelN(l)).toBe(traded(labelCategory(l)));
      expect(labelN(l)).not.toBe(all(labelCategory(l)));
    }
  });

  test("the first five chips ARE the Top 5, in the same order", () => {
    // The consistency the fix must not break while fixing the chart: ordering
    // the strip by the unfiltered total while the chart picks the cohort's five
    // trades one visible contradiction for another.
    const html = render();
    expect(tabLabels(html).slice(0, 5)).toEqual(chartLabels(html).map(labelCategory));
  });

  test("the tab strip still offers EVERY published category (#7302 holds)", () => {
    // Order is all this ship changes. A fix that sliced the strip to the five
    // would pass everything above and re-open the defect #7302 closed.
    expect(tabLabels(render()).sort()).toEqual(SPLIT.map(s => s.category).sort());
  });
});
