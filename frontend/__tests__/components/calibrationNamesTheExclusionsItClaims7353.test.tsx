/**
 * #7353 — the accuracy page stops promising it covers "every exclusion", and
 * names eight rules that reached no reader.
 *
 * THE DEFECT, ON PRODUCTION (LOOK at 390px, `SHOT_SCROLL=9300`,
 * `docHeight=12113`, 2026-09-20 ~03:05Z). Under the hero, inside "show the
 * math":
 *
 *     …How we measure this covers which price we use, who we count as the
 *     winner, and every exclusion.
 *
 * The methodology it links to listed six exclusion rules. The payload carried
 * nine more `*_filter` blocks — eight non-zero, 147,721 outcomes — and NONE of
 * those nine field names appeared anywhere under `frontend/`. Three of them are
 * bigger than the void filter the page spells out in full, and the biggest
 * (`heuristic_filter`, 66,921) is bigger than the liquidity filter it also
 * spells out. So the page named the small rules and withheld the large ones,
 * under a sentence that said it had named them all.
 *
 * ═══ WHY THE FIX IS BOTH HALVES, AND WHY THE SENTENCE STILL CHANGES ═══
 *
 * Adding the eight does not make "every" true. `truth_evidence`'s price-derived
 * rung (454,743) and `mex_normalization`'s field-incomplete rung (18,258) are
 * exclusions measured over a DIFFERENT population, and the accounting that
 * would reconcile all of them — `calibration_coverage_census` — reads
 * `status: "unavailable"` in production. A page cannot keep a completeness
 * promise out of a list, so the disclosure goes up and the quantifier goes.
 *
 * ═══ THE TRAP THIS SUITE IS WRITTEN AROUND ═══
 *
 * An absence assertion is worth exactly what its control is worth (the lesson
 * `calibrationNoDiagnosticProse4340` was built on). Every `not.toContain` below
 * is paired with the same predicate run over the frozen pre-fix sentence, so a
 * typo'd needle — which would pass forever — fails here instead.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import { NAMED_EXCLUSION_LABELS } from "@/lib/calibrationNamedExclusions";

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

/** The sentence as it shipped, from `git show HEAD~:page.tsx`. Frozen. */
const PRE_FIX_SENTENCE =
  "covers which price we use, who we count as the winner, and every exclusion.";

/** The eight non-zero rules and one measured zero, live counts, live shapes. */
const THE_NINE = {
  heuristic_filter: { excluded_by_source: { kalshi: 22_480, polymarket: 44_441 } },
  kalshi_prop_threshold_filter: { excluded: 45_102 },
  poly_placeholder_filter: { excluded: 19_697 },
  no_winner_filter: { excluded: 12_237 },
  draw_authority_filter: { excluded: 1_805 },
  golf_placeholder_filter: { excluded: 1_707 },
  malformed_binary_filter: { excluded: 158 },
  weather_wide_spread_filter: { excluded: 94 },
  orphan_partition_filter: { excluded: 0 },
};

function bucket(idx: number, n: number) {
  return {
    bucket_idx: idx,
    source: "kalshi",
    category: "baseball",
    price_moved: true,
    n,
    winners: Math.round(n * (0.05 + idx * 0.1)),
    avg_prob: 0.05 + idx * 0.1,
    sum_prob: n * (0.05 + idx * 0.1),
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

function makePayload(overrides: Record<string, unknown> = {}): CalibrationData {
  return {
    buckets: [0, 1, 2, 3, 4].map(i => bucket(i, 20_000)),
    total_markets: 12_000,
    total_outcomes: 100_000,
    total_winners: 40_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-20T03:00:00Z",
    date_range: { start: "2021-09-01", end: "2026-09-19" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 100_000 }],
    by_category: [{ category: "baseball", ece: 0.02, n: 100_000 }],
    // The six with their own bullet, so nothing below passes for want of a rival.
    liquidity_filter: { applies_to: "kalshi", rule: "…", kalshi_included: 632_525, kalshi_excluded: 43_235 },
    writer_bar_filter: { applies_to: "kalshi", rule: "…", included: 473_290, excluded: 202_470 },
    esports_multi_bundle_filter: { applies_to: "all", rule: "…", excluded: 187_263 },
    soccer_2way_filter: { applies_to: "soccer", rule: "…", excluded: 67_915 },
    void_filter: { applies_to: "golf", rule: "…", excluded: 16_269 },
    nonexclusive_bundle_filter: { applies_to: "all", rule: "…", excluded: 203_906 },
    ...THE_NINE,
    ...overrides,
  } as unknown as CalibrationData;
}

function render(overrides: Record<string, unknown> = {}): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload(overrides);
  return renderToStaticMarkup(<CalibrationPage />);
}

/** Just the new bullet, so no other element on a 2,900-line page can answer. */
function theFold(html: string): string {
  const start = html.indexOf('data-testid="calibration-other-exclusions"');
  expect(start).toBeGreaterThan(-1);
  const end = html.indexOf("</details>", start);
  expect(end).toBeGreaterThan(start);
  return html.slice(start, end);
}

const attr = (html: string, name: string) =>
  new RegExp(`${name}="([^"]*)"`).exec(theFold(html))?.[1];

describe("the harness renders the real page with the real payload shape", () => {
  test("it is the calibration page and the methodology is on it", () => {
    const html = render();
    expect(html).toContain('id="methodology"');
    expect(html).toContain("Liquidity filter (Kalshi)");
    expect(html.length).toBeGreaterThan(20_000);
  });
});

describe("the page no longer promises it covers every exclusion", () => {
  test("the pre-fix sentence is gone", () => {
    expect(render()).not.toContain(PRE_FIX_SENTENCE);
  });

  test("and the needle is a real one — the same check fires on the frozen text", () => {
    expect(PRE_FIX_SENTENCE).toContain(PRE_FIX_SENTENCE);
    expect(PRE_FIX_SENTENCE).toContain("every exclusion");
  });

  test("what replaced it says what the section delivers, without quantifying", () => {
    const html = render();
    expect(html).toContain("why the published");
    expect(html).toContain("total is lower than the raw count");
    // The link a reader clicks is untouched — this is a copy fix, not a re-plumb.
    expect(html).toContain("How we measure this");
  });
});

describe("the eight rules reach the reader", () => {
  test.each(
    Object.entries(THE_NINE).filter(([, v]) => (v as { excluded?: number }).excluded !== 0)
  )("%s is named and counted", key => {
    const fold = theFold(render());
    expect(fold).toContain(`data-rule="${key}"`);
    expect(fold).toContain(NAMED_EXCLUSION_LABELS[key]);
  });

  test("the counts printed are the payload's, formatted", () => {
    const fold = theFold(render());
    for (const n of [66_921, 45_102, 19_697, 12_237, 1_805, 1_707, 158, 94]) {
      expect(fold).toContain(n.toLocaleString());
    }
  });

  test("the summary says how many there are, and the attributes let a probe count", () => {
    const html = render();
    expect(theFold(html)).toContain("(8 more)");
    expect(attr(html, "data-rules")).toBe("8");
    expect(attr(html, "data-empty-rules")).toBe("1");
    expect(attr(html, "data-unlisted-rules")).toBe("0");
  });

  test("the measured zero is stated, not dropped", () => {
    expect(theFold(render())).toContain("1 further rule set aside nothing at all");
  });
});

describe("it is folded, and the counts are not an addable column", () => {
  test("the bullet is a closed <details> — notice 34 / D102", () => {
    const fold = theFold(render());
    expect(fold).toContain("<details");
    expect(fold).toContain("<summary");
    // Closed: a `<details open>` is a wall of grey text, which is the thing the
    // notice bans. `renderToStaticMarkup` would print the attribute if set.
    expect(/<details[^>]*\sopen/.test(fold)).toBe(false);
  });

  test("and it warns the reader off summing overlapping cohorts", () => {
    expect(theFold(render())).toContain("not a column to add up");
  });

  test("no rule with its own bullet is repeated inside the fold", () => {
    const fold = theFold(render());
    for (const already of ["Liquidity filter", "Esports match-bundle", "Void filter", "Soccer 2-way"]) {
      expect(fold).not.toContain(already);
    }
    // Control: those sentences ARE on the page, so the absence above is a
    // statement about the fold and not about the render failing.
    const html = render();
    for (const already of ["Liquidity filter", "Esports match-bundle", "Void filter", "Soccer 2-way"]) {
      expect(html).toContain(already);
    }
  });
});

describe("a payload with nothing to list renders no fold at all", () => {
  test("an older payload carrying none of the nine", () => {
    const stripped: Record<string, unknown> = {};
    for (const key of Object.keys(THE_NINE)) stripped[key] = undefined;
    const html = render(stripped);
    expect(html).not.toContain('data-testid="calibration-other-exclusions"');
    // Control: the same render WITH them has the fold, so this is the payload
    // talking and not a selector that stopped matching.
    expect(render()).toContain('data-testid="calibration-other-exclusions"');
  });

  test("and the rest of the methodology is untouched by its absence", () => {
    const stripped: Record<string, unknown> = {};
    for (const key of Object.keys(THE_NINE)) stripped[key] = undefined;
    const html = render(stripped);
    expect(html).toContain("Prices nobody could have traded at (Kalshi)");
    expect(html).toContain("s included?"); // "What’s included?" — a curly apostrophe
  });
});
