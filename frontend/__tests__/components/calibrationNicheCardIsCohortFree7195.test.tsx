/**
 * #7195 — the "Niche & Long-Shot Markets" card stops claiming a cohort it is
 * not drawing from.
 *
 * Shopped on production, 390px, default (TRADED) view, 2026-09-19:
 *
 *     What About Niche & Long-Shot Markets?   [ TRADED ]
 *     109 categories don't have enough resolved outcomes yet …
 *
 *     CLOSEST TO THE BAR
 *     CFL 847   NCAA Lacrosse 829   Chess 809   SHL 730   …
 *
 * The tag read TRADED; every number under it was the all-markets count.
 * `small_sample_categories[].outcomes` matched the ALL-cohort bucket sum for
 * all 109 categories, exactly, 0 mismatches — and Chess's traded count is 292.
 *
 * ═══ THE TAG WAS THE DEFECT, NOT THE NUMBERS ═══
 *
 * This is where this ship differs from #7190, which fixed the numbers. The
 * publish bar is applied on the ALL-cohort count: in the same payload
 * `geopolitics` is published at 1,749 all-cohort while its traded count is 732,
 * under the 1,000 bar. Closeness to a bar has to be measured in the bar's own
 * units, so cohort-scoping these chips would print categories parked under a
 * 1,000 bar beside a table publishing one at 732 — a new contradiction, in
 * exchange for the old one.
 *
 * The parked/published decision is a property of the BANK. The section is
 * cohort-free; the tag is what had to go, and the fold now names the population
 * the bar counts so a reader who flips the toggle and sees these numbers stand
 * still can tell a fixed bar from a stuck card.
 *
 * ═══ WHY THE FIXTURE IS BUILT THE WAY IT IS ═══
 *
 * The parked categories are given REAL buckets carrying a traded/untraded
 * split, exactly as production has them (all 109 are in `buckets`). Without
 * that, cohort-scoping the chips would be impossible and "it prints the bank
 * number" would be true by construction rather than a choice this suite pins.
 * `chess` here is production's own gap: 809 all, 292 traded.
 *
 * `geopolitics` is in the fixture for the same reason — published, above the
 * bar on all outcomes, below it on traded ones. It is what makes the argument
 * above checkable rather than asserted.
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

const BAR = 1000;

/**
 *   category      traded   untraded   all-cohort   published?
 *   baseball      80,000     60,000      140,000   yes
 *   basketball    58,000     11,000       69,000   yes
 *   geopolitics      732      1,017        1,749   yes — and UNDER the bar traded
 *   chess            292        517          809   no  — parked, production's gap
 *   lacrosse_ncaa    829          0          829   no  — parked, no gap
 */
const SPLIT = [
  { category: "baseball", traded: 80_000, untraded: 60_000 },
  { category: "basketball", traded: 58_000, untraded: 11_000 },
  { category: "geopolitics", traded: 732, untraded: 1_017 },
  { category: "chess", traded: 292, untraded: 517 },
  { category: "lacrosse_ncaa", traded: 829, untraded: 0 },
];

/** What the backend parks: every category under the bar on ALL outcomes. */
const PARKED = ["chess", "lacrosse_ncaa"];

const split = (c: string) => SPLIT.find(s => s.category === c)!;
const tradedTotal = (c: string) => split(c).traded;
const allTotal = (c: string) => split(c).traded + split(c).untraded;

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
    [0, 1, 2, 3, 4].flatMap(i =>
      [
        bucket(s.category, i, true, s.traded / 5),
        ...(s.untraded > 0 ? [bucket(s.category, i, false, s.untraded / 5)] : []),
      ],
    ),
  );
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: SPLIT.reduce((t, s) => t + s.traded + s.untraded, 0),
    total_winners: 100_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-19T10:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-19" },
    min_category_outcomes: BAR,
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: SPLIT.map(s => ({ category: s.category, ece: 0.02, n: allTotal(s.category) })),
    // The backend's parked list: the all-cohort count, which is the unit the
    // bar is applied in.
    small_sample_categories: PARKED.map(c => ({
      category: c,
      outcomes: allTotal(c),
      ece: 6.6,
      disposition: "parked_below_publish_bar",
      publish_bar: BAR,
    })),
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/** The niche section's own markup, from its testid to its closing tag. */
function nicheSection(html: string): string {
  const start = html.indexOf('data-testid="calibration-niche-section"');
  expect(start).toBeGreaterThan(-1);
  const end = html.indexOf("</section>", start);
  expect(end).toBeGreaterThan(start);
  return html.slice(start, end);
}

/** Each parked chip, as the reader sees it: category key → printed number. */
function chipCounts(html: string): Record<string, number> {
  const out: Record<string, number> = {};
  const re = /data-category="([^"]+)"[^>]*?data-outcomes="(\d+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(nicheSection(html))) !== null) out[m[1]] = Number(m[2]);
  return out;
}

/** What the Category Breakdown table says each published category's size is. */
function tableCounts(html: string): Record<string, number> {
  const out: Record<string, number> = {};
  const re = /data-testid="calibration-category-row"[^>]*?data-category="([^"]+)"[^>]*?data-n="(\d+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) out[m[1]] = Number(m[2]);
  return out;
}

/* ═══════ the harness proves itself, and proves the fixture has the gap ═══════ */

describe("the harness renders the real calibration page", () => {
  test("positive control: the page is built, and the niche card is in it", () => {
    // Two of the assertions below are ABSENCES, and a loading shell satisfies
    // every absence ever written.
    const html = render();
    expect(html).toContain("calibration-niche-section");
    expect(Object.keys(chipCounts(html)).length).toBe(PARKED.length);
  });

  test("the fixture gives a parked category a real cohort gap", () => {
    // Without this, "the chips print the bank number" is true by construction:
    // the filtered and unfiltered sums would be the same number.
    expect(tradedTotal("chess")).not.toBe(allTotal("chess"));
    expect(allTotal("chess")).toBeLessThan(BAR); // genuinely parked
  });

  test("the fixture reproduces the geopolitics case the exemption rests on", () => {
    // Published on all outcomes, under the bar on traded ones. This is the
    // contradiction that cohort-scoping the chips would create.
    expect(allTotal("geopolitics")).toBeGreaterThanOrEqual(BAR);
    expect(tradedTotal("geopolitics")).toBeLessThan(BAR);
    expect(PARKED).not.toContain("geopolitics");
  });
});

/* ═════════════ SHIP — the section claims the population it reports ═════════════ */

describe("#7195 — the niche card claims no cohort", () => {
  test("🔴 the heading carries no cohort tag", () => {
    // The defect, verbatim: this section printed "TRADED" over all-markets
    // numbers. A tag here is a claim the data cannot support.
    expect(nicheSection(render())).not.toContain('data-testid="calibration-cohort-tag"');
  });

  test("the rest of the page still tags the sections that DO draw from a cohort", () => {
    // The kill for the lazy fix: deleting <CohortTag> from the page satisfies
    // the assertion above and destroys the labelling contract (UX-P080 item 4).
    const html = render();
    const tags = html.match(/data-testid="calibration-cohort-tag"/g) ?? [];
    expect(tags.length).toBeGreaterThanOrEqual(6);
  });

  test("🔴 the chips report the bar's own units — every resolved outcome", () => {
    // The other half. A fix that removed the tag AND filtered the numbers
    // would pass the two tests above; it would also print Chess 292 under a
    // 1,000 bar while the table published geopolitics at 732.
    const counts = chipCounts(render());
    for (const c of PARKED) expect(counts[c]).toBe(allTotal(c));
    expect(counts.chess).not.toBe(tradedTotal("chess"));
  });

  test("the table beside it stays cohort-scoped, as it always was", () => {
    // The two sections report different populations on one page. That is
    // legitimate — and it is exactly why only one of them may wear the tag.
    const counts = tableCounts(render());
    expect(counts.geopolitics).toBe(tradedTotal("geopolitics"));
    expect(counts.baseball).toBe(tradedTotal("baseball"));
  });

  test("the fold names the population the bar counts", () => {
    // Without this sentence a reader who flips the toggle and sees these
    // numbers stand still cannot tell a fixed bar from a stuck card. It lives
    // in the collapsed method note, not the card body (notice 34 / D102).
    const section = nicheSection(render());
    expect(section).toMatch(/every resolved outcome, traded or not/);
  });
});
