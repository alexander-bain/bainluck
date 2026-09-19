/**
 * #7190 — the CATEGORIES card reports the cohort the reader is looking at.
 *
 * Shopped on production, 390px, default (TRADED) cohort, 2026-09-19 10:44Z. The
 * summary card at the top of the page and the Category Breakdown table further
 * down printed different sizes for the same categories on the same screen:
 *
 *     CATEGORIES  15
 *     Baseball (190,958), Soccer (132,357), Basketball (129,438)   <- the card
 *
 *     CATEGORY     OUTCOMES
 *     Baseball      129,771                                        <- its table
 *     Basketball    118,714
 *     Soccer         58,440
 *
 * `page.tsx`'s `topCats` summed raw `normalized` with no `cohortFilter`, so it
 * reported the whole 747,028-outcome superset while every other figure on the
 * page respected the traded/untraded toggle. Not a stale number and not a
 * rounding artifact: 190,958 is EXACTLY the all-cohort rollup of the four
 * baseball keys (140,893 + 33,011 + 12,919 + 4,135). It was the wrong
 * population.
 *
 * ═══ THE RULE ALREADY EXISTED TWO CARDS AWAY ═══
 *
 * The `Sources` card carries it in its own comment (UX-P080 item 2): "counts
 * PROVIDERS, from the same `providerGroups` the two tables below are built from
 * — so the card cannot say 5 while they say 3." The categories card's detail
 * string is the call site that never asked for it. Same shape as #6265 and
 * #7183: the rule is not missing, one site skipped it.
 *
 * ═══ WHY THE FIXTURE IS BUILT THE WAY IT IS ═══
 *
 * Two independent things were wrong, and a fixture can easily see only one.
 *
 *  1. THE COUNTS. Needs a cohort gap — every category must hold both traded and
 *     untraded rows, or filtered and unfiltered totals coincide and the guard
 *     passes against the bug.
 *  2. THE ORDER. `categories` is sorted by the UNFILTERED total, so correcting
 *     the counts alone would print a mis-sorted list — a NEW defect. This
 *     fixture reproduces production's actual inversion: all-cohort soccer
 *     outranks basketball, traded basketball outranks soccer. A fix that
 *     filters without re-sorting fails `the card is ordered by the cohort's own
 *     sizes` below.
 *
 * The numbers are chosen so no traded total can be mistaken for an all-cohort
 * one, and every category clears the 1,000-outcome floor in BOTH cohorts — so
 * nothing in here is testing the floor by accident.
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

/**
 * Per-category traded/untraded split, reproducing production's inversion.
 *
 *   category      traded    untraded    all-cohort
 *   baseball     120,000      70,000      190,000
 *   basketball   118,000      11,000      129,000
 *   soccer        58,000      74,000      132,000
 *   tennis        20,000       5,000       25,000
 *
 * ALL-COHORT order: baseball > soccer > basketball > tennis
 * TRADED     order: baseball > basketball > soccer > tennis   <- soccer/basketball swap
 */
const SPLIT = [
  { category: "baseball", traded: 120_000, untraded: 70_000 },
  { category: "basketball", traded: 118_000, untraded: 11_000 },
  { category: "soccer", traded: 58_000, untraded: 74_000 },
  { category: "tennis", traded: 20_000, untraded: 5_000 },
];

const tradedTotal = (c: string) => SPLIT.find(s => s.category === c)!.traded;
const allTotal = (c: string) => {
  const s = SPLIT.find(x => x.category === c)!;
  return s.traded + s.untraded;
};

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
  // Five buckets per cohort per category, so each category carries BOTH a
  // price_moved:true and a price_moved:false population.
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
    by_category: SPLIT.map(s => ({ category: s.category, ece: 0.02, n: s.traded + s.untraded })),
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/** The card's detail line, read off its own element rather than a sliced window. */
function categoriesCardDetail(html: string): string {
  const m = /data-testid="calibration-stat-categories-detail"[^>]*>([^<]*)</.exec(html);
  expect(m).not.toBeNull();
  return m![1].trim();
}

/** What the Category Breakdown table says each category's size is. */
function tableCounts(html: string): Record<string, number> {
  const out: Record<string, number> = {};
  const re = /data-testid="calibration-category-row"[^>]*?data-category="([^"]+)"[^>]*?data-n="(\d+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) out[m[1]] = Number(m[2]);
  return out;
}

/* ═══════ the harness proves itself, and proves the fixture has the gap ═══════ */

describe("the harness renders the real calibration page", () => {
  test("positive control: the page is built, not a loading shell", () => {
    // Two assertions below are absences, and a loading state satisfies both.
    const html = render();
    expect(html).toContain("calibration-stat-categories");
    expect(Object.keys(tableCounts(html)).length).toBe(SPLIT.length);
  });

  test("the fixture contains the cohort gap AND the order inversion", () => {
    // Without BOTH, tests below pass vacuously against the bug.
    for (const s of SPLIT) expect(s.untraded).toBeGreaterThan(0);
    expect(tradedTotal("baseball")).not.toBe(allTotal("baseball"));
    // all-cohort: soccer outranks basketball …
    expect(allTotal("soccer")).toBeGreaterThan(allTotal("basketball"));
    // … traded: the other way round. This is the inversion production had.
    expect(tradedTotal("basketball")).toBeGreaterThan(tradedTotal("soccer"));
  });

  test("the table is the cohort-scoped side, as it always was", () => {
    // The card is being brought to the table, so pin what the table says first.
    const counts = tableCounts(render());
    for (const s of SPLIT) expect(counts[s.category]).toBe(s.traded);
  });
});

/* ══════════════════ SHIP — one number per category, per page ══════════════════ */

describe("#7190 — the CATEGORIES card reports the cohort on screen", () => {
  test("🔴 the card prints the TRADED count, never the all-cohort superset", () => {
    // The headline assertion, and the one that was false on production.
    const detail = categoriesCardDetail(render());
    expect(detail).toContain(`Baseball (${tradedTotal("baseball").toLocaleString()})`);
    // The kill: 190,000 here is what the old expression printed.
    expect(detail).not.toContain(allTotal("baseball").toLocaleString());
    expect(detail).not.toContain(allTotal("soccer").toLocaleString());
    expect(detail).not.toContain(allTotal("basketball").toLocaleString());
  });

  test("🔴 the card is ordered by the COHORT's sizes, not the unfiltered ones", () => {
    // The half a counts-only fix misses. `categories` is sorted by the
    // unfiltered total, so filtering without re-sorting prints Baseball,
    // Soccer, Basketball with traded numbers — descending labels over
    // non-descending values.
    const detail = categoriesCardDetail(render());
    expect(detail.indexOf("Basketball")).toBeGreaterThan(-1);
    expect(detail.indexOf("Basketball")).toBeLessThan(detail.indexOf("Soccer"));
  });

  test("the card and its own table cannot disagree about a category's size", () => {
    // The structural claim, and the reason the fix reads `categoryMetrics`
    // rather than re-deriving a filtered sum: agreement by construction, not by
    // coincidence. Asserted over every category the card names, so a later
    // change that fixes the first and leaves the rest cannot pass.
    const html = render();
    const counts = tableCounts(html);
    const named = [...categoriesCardDetail(html).matchAll(/([A-Za-z ]+) \(([\d,]+)\)/g)];
    expect(named.length).toBe(3); // the card names exactly its top three
    for (const [, label, shown] of named) {
      const key = label.trim().toLowerCase();
      expect(counts[key]).toBeDefined();
      expect(Number(shown.replace(/,/g, ""))).toBe(counts[key]);
    }
  });

  test("the three it names are the three biggest in the cohort", () => {
    // Not just "three agreeing numbers" — the RIGHT three. Tennis is smallest
    // in both cohorts and must stay off the card; a fix that sorted ascending
    // would satisfy every assertion above and fail this one.
    const detail = categoriesCardDetail(render());
    const biggest = [...SPLIT].sort((a, b) => b.traded - a.traded).slice(0, 3).map(s => s.category);
    for (const c of biggest) {
      expect(detail.toLowerCase()).toContain(c);
    }
    expect(detail.toLowerCase()).not.toContain("tennis");
  });
});
