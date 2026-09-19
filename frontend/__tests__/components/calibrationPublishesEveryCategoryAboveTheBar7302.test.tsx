/**
 * #7302 — a category that clears the publish bar appears on the page.
 *
 * Shopped on production, phone width, default (TRADED) cohort, 2026-09-19
 * 21:40Z. `page.tsx`'s `categories` memo ended in `.slice(0, 15)`, an unstated
 * second filter on top of the `minCategoryOutcomes` bar. On the live payload 21
 * categories cleared the 1,000-outcome bar and 15 rendered. The six it dropped
 * appeared NOWHERE on the page:
 *
 *     tech             3,444      cricket          3,165
 *     other            2,591      geopolitics      1,749
 *     rugbyleague_nrl  1,219      aussierules_afl  1,211
 *
 * Not in the Categories stat card, which prints `categories.length` and so read
 * "15". Not in the Category Breakdown table, whose own subtitle calls itself
 * "Every published category". And not in the niche card's 109 either, because
 * that list is the backend's BELOW-bar population — so the two lists a reader
 * is told are exhaustive summed to 124 against a payload holding 130.
 *
 * The niche card states the promise this broke in so many words: "The moment
 * one crosses the bar it appears above automatically." Crossing the bar was
 * necessary and not sufficient; a category also had to be in the top fifteen by
 * a total the page never shows.
 *
 * ═══ WHY THE FIXTURE IS BUILT THE WAY IT IS ═══
 *
 * Three things could each hide the defect from a lazier fixture.
 *
 *  1. FEWER THAN SIXTEEN above-bar categories and the slice never fires — every
 *     assertion here passes against the bug. `the fixture can see the slice`
 *     below is the vacuity guard, and it is the first test in the file.
 *  2. NO BELOW-BAR CATEGORIES and "render everything" passes as readily as
 *     "render everything above the bar". Two sit under the bar here, and the
 *     floor is asserted to still bite.
 *  3. NO CATEGORY WHOSE COHORT COUNT STRADDLES THE BAR and a fix that
 *     cohort-scoped the eligibility basis would look correct. Production's
 *     geopolitics is 1,749 all-cohort and 732 traded; the fixture reproduces
 *     exactly that straddle, because #7195 ruled the bar is applied on the
 *     all-cohort count and cohort-scoping it would park a category under a
 *     1,000 bar beside a table publishing one at 732 in the same view.
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

jest.mock("@/components/CalibrationChart", () => ({ __esModule: true, default: () => null }));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import CalibrationPage from "@/app/calibration/page";

const BAR = 1_000;

/**
 * Eighteen categories above the bar and two below, ordered by the all-cohort
 * total the eligibility basis uses.
 *
 * Ranks 16-18 (tech, cricket, geopolitics) are production's stragglers: above
 * the bar, and cut by the slice. Geopolitics carries the straddle — 1,700
 * all-cohort, 700 traded.
 */
const SPLIT = [
  { category: "baseball", traded: 120_000, untraded: 70_000 },
  { category: "soccer", traded: 58_000, untraded: 74_000 },
  { category: "basketball", traded: 118_000, untraded: 11_000 },
  { category: "tennis", traded: 25_000, untraded: 37_000 },
  { category: "weather", traded: 13_000, untraded: 28_000 },
  { category: "football", traded: 22_000, untraded: 12_000 },
  { category: "table_tennis", traded: 10_000, untraded: 17_000 },
  { category: "hockey", traded: 19_000, untraded: 7_000 },
  { category: "esports", traded: 8_000, untraded: 14_000 },
  { category: "golf", traded: 13_000, untraded: 6_000 },
  { category: "politics", traded: 8_000, untraded: 5_000 },
  { category: "economics", traded: 4_000, untraded: 8_000 },
  { category: "entertainment", traded: 2_000, untraded: 3_000 },
  { category: "mma", traded: 2_000, untraded: 2_000 },
  { category: "motorsports", traded: 1_800, untraded: 2_000 },
  // ── the slice used to cut here ──────────────────────────────────────────
  { category: "tech", traded: 1_400, untraded: 2_000 },
  { category: "cricket", traded: 1_400, untraded: 1_700 },
  { category: "geopolitics", traded: 700, untraded: 1_000 },
  // ── below the publish bar; the backend parks these, not the page ────────
  { category: "chess", traded: 400, untraded: 400 },
  { category: "lacrosse_ncaa", traded: 300, untraded: 200 },
];

const allTotal = (s: (typeof SPLIT)[number]) => s.traded + s.untraded;
const ABOVE_BAR = SPLIT.filter(s => allTotal(s) >= BAR);
const BELOW_BAR = SPLIT.filter(s => allTotal(s) < BAR);
/** Cut by the old `.slice(0, 15)`: above the bar, outside the top fifteen. */
const STRAGGLERS = ABOVE_BAR.slice(15);

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
    min_category_outcomes: BAR,
    total_markets: 12_000,
    total_outcomes: SPLIT.reduce((t, s) => t + allTotal(s), 0),
    total_winners: 200_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-19T21:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-19" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: SPLIT.map(s => ({ category: s.category, ece: 0.02, n: allTotal(s) })),
    // The backend's BELOW-bar population — the niche card's whole input. It is
    // cohort-free and counted on the all-cohort total, per #7195.
    small_sample_categories: BELOW_BAR.map(s => ({
      category: s.category,
      outcomes: allTotal(s),
    })),
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/** Which categories the Category Breakdown table actually rendered a row for. */
function renderedRows(html: string): string[] {
  const out: string[] = [];
  const re = /data-testid="calibration-category-row"[^>]*?data-category="([^"]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) out.push(m[1]);
  return out;
}

/** The number in the CATEGORIES stat card, off its own element. */
function categoriesCardValue(html: string): number {
  const m = /data-testid="calibration-stat-categories-value"[^>]*>([^<]*)</.exec(html);
  expect(m).not.toBeNull();
  return Number(m![1].trim().replace(/,/g, ""));
}

/** How many categories the niche card says are still under the bar. */
function parkedCount(html: string): number {
  const m = /data-testid="calibration-niche-section"[^>]*data-parked-count="(\d+)"/.exec(html);
  expect(m).not.toBeNull();
  return Number(m![1]);
}

/* ═══════ the harness proves itself, and proves the fixture has the gap ═══════ */

describe("the harness renders the real calibration page", () => {
  test("the fixture can see the slice — more than fifteen categories clear the bar", () => {
    // THE VACUITY GUARD. At fifteen or fewer, `.slice(0, 15)` is a no-op and
    // every 🔴 below passes against the unfixed page.
    expect(ABOVE_BAR.length).toBeGreaterThan(15);
    expect(STRAGGLERS.length).toBe(3);
    expect(BELOW_BAR.length).toBeGreaterThan(0);
    // And the straddle, or test 3 below is asserting nothing.
    const geo = SPLIT.find(s => s.category === "geopolitics")!;
    expect(allTotal(geo)).toBeGreaterThanOrEqual(BAR);
    expect(geo.traded).toBeLessThan(BAR);
  });

  test("positive control: the page is built, not a loading shell", () => {
    // Assertions below count rendered rows, and a loading state has none —
    // which would read as a pass on the "floor still bites" test.
    const html = render();
    expect(html).toContain("calibration-stat-categories");
    expect(renderedRows(html).length).toBeGreaterThan(0);
  });
});

/* ═════════ SHIP — the two exhaustive lists account for every category ════════ */

describe("#7302 — clearing the publish bar is enough to be shown", () => {
  test("🔴 every category above the bar gets a row in Category Breakdown", () => {
    // The headline, and what was false on production. The table's own subtitle
    // is "Every published category".
    const rows = renderedRows(render());
    for (const s of ABOVE_BAR) expect(rows).toContain(s.category);
    expect(rows).toHaveLength(ABOVE_BAR.length);
  });

  test("🔴 the three the slice used to cut are the ones to check", () => {
    // Named separately from the loop above so a regression says WHICH went
    // missing rather than just reporting a length.
    const rows = renderedRows(render());
    for (const s of STRAGGLERS) expect(rows).toContain(s.category);
  });

  test("🔴 the CATEGORIES card counts them all, not the first fifteen", () => {
    // The card prints `categories.length`, so the slice was visible as a
    // headline number too. 15 here is exactly what the bug printed.
    expect(categoriesCardValue(render())).toBe(ABOVE_BAR.length);
    expect(categoriesCardValue(render())).not.toBe(15);
  });

  test("🔴 the shown and the parked lists account for every category", () => {
    // The reader-facing arithmetic: the page describes both lists as
    // exhaustive, so nothing may fall between them. On production this read
    // 15 + 109 = 124 against 130.
    const html = render();
    expect(renderedRows(html).length + parkedCount(html)).toBe(SPLIT.length);
  });
});

/* ═══════════════ the two invariants a careless fix would break ═══════════════ */

describe("#7302 — the bar is still the filter, and it is still all-cohort", () => {
  test("the floor still bites: a below-bar category gets no row", () => {
    // Deleting the `minCategoryOutcomes` filter along with the slice would
    // satisfy every 🔴 above. It must not.
    const rows = renderedRows(render());
    for (const s of BELOW_BAR) expect(rows).not.toContain(s.category);
  });

  test("geopolitics is published on its all-cohort total, though its traded count is under the bar", () => {
    // #7195: the bar is applied by the backend on the all-cohort count. A fix
    // that "tidied" the eligibility basis by adding `cohortFilter` here would
    // drop this row — 700 traded against a 1,000 bar — and would be a new
    // defect wearing the shape of the old one.
    expect(renderedRows(render())).toContain("geopolitics");
  });

  test("the curve explorer still defaults to five, not to every category", () => {
    // `catChartData` reads `categories.slice(0, 5)` — a different, STATED cap
    // ("Top 5" is the tab's own label) that this ship does not touch.
    expect(render()).toContain("Top 5");
  });
});
