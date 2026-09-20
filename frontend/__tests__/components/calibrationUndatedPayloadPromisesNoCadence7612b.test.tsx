/**
 * #7612, the residual — an undated payload stops filling the date slot with a
 * cadence.
 *
 * The hero footer read:
 *
 *     Data Sep 2021–Sep 2026 · Updated hourly
 *
 * whenever `generated_at` was absent. "Updated <when>" promises a DATE; the
 * fallback answered with a SCHEDULE, in the one state where the date could not
 * be read. Same claim `methodologyRefreshClause` withholds one card down, same
 * rule #2649 settled for the banner: THE PAGE MAY DESCRIBE, IT MAY NOT PREDICT.
 *
 * ═══ WHY THIS INSTANCE IS THE WORSE OF THE TWO ═══
 *
 * The banner is driven by `availability`/`cache`, never by this field, so
 * `decideCalibrationStaleness` returns null on a payload that is `fresh` but
 * undated (`calibrationStaleness.ts:231`). Nothing renders above to correct the
 * word and the reassurance lands alone — the degraded branch asserting MORE
 * than the branch that has the facts, which is gotcha #53's shape. Both renders
 * below therefore use the FRESH envelope: the state with no banner is the state
 * this fix is for.
 *
 * ═══ WHY #7612's OWN GUARD DID NOT CATCH IT ═══
 *
 * It very nearly did. `calibrationMethodologyRefreshPromiseIsGated7612`'s
 * relation test bans exactly this shape — its regex carries
 * `updated?\s+(?:hourly|every hour)` — but scopes the read to the methodology
 * `<li>`, so the identical words 1,650 lines up were outside the element it
 * looked at. The claim was right and the aim was short by one element. This
 * file points the same shape at the footer.
 *
 * ═══ REACHABILITY, STATED PLAINLY ═══
 *
 * LATENT, not shopped. `precompute_calibration` stamps `generated_at` on every
 * artifact and every serve tier derives from one, so production could not be
 * made to render this on 2026-09-20 (the live payload carried
 * `2026-09-15T11:16:10Z`). It is fixed because it is #7612's own sentence one
 * grep away, and because the field is typed nullable (`lib/types.ts:2741`) with
 * the route already defending against a non-str at `routes/calibration.py:1391`
 * — the shape that reaches it is an interrupted publication or a cold start,
 * which is #5000's whole subject ("honest dates").
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

/** The curve is current and the server says so. No banner renders. */
const FRESH_ENVELOPE = {
  availability: "fresh",
  staged: { measured: true, frozen_over_drift: false, units_drifted: 0, units_banked: 128 },
  producer: { task: "precompute_calibration_main", interval_s: 3600, beats_missed: 0, stalled: false },
  cache: null,
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

const CATEGORIES = [
  { category: "baseball", traded: 80_000, untraded: 60_000 },
  { category: "basketball", traded: 58_000, untraded: 11_000 },
];

/**
 * `generatedAt` is the ONLY axis. Everything else — envelope included — is held
 * byte-identical between the two renders, so a sentence that moves can only
 * have moved because of the date. (The positive control below asserts that.)
 */
function makePayload(generatedAt: string | null): CalibrationData {
  const buckets = CATEGORIES.flatMap(c =>
    [0, 1, 2, 3, 4].flatMap(i => [
      bucket(c.category, i, true, c.traded / 5),
      bucket(c.category, i, false, c.untraded / 5),
    ]),
  );
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: CATEGORIES.reduce((t, c) => t + c.traded + c.untraded, 0),
    total_winners: 100_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: generatedAt,
    date_range: { start: "2021-09-01", end: "2026-09-15" },
    min_category_outcomes: 1000,
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: CATEGORIES.map(c => ({
      category: c.category,
      ece: 0.02,
      n: c.traded + c.untraded,
    })),
    small_sample_categories: [],
    ...FRESH_ENVELOPE,
  } as unknown as CalibrationData;
}

const DATED = "2026-09-15T11:16:10.215051+00:00";

function render(generatedAt: string | null): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload(generatedAt);
  return renderToStaticMarkup(<CalibrationPage />);
}

/** The hero footer, from its own testid to its closing tag. */
function footer(html: string): string {
  const at = html.indexOf('data-testid="calibration-generated-at"');
  expect(at).toBeGreaterThan(-1);
  const open = html.lastIndexOf("<p", at);
  const end = html.indexOf("</p>", at);
  expect(open).toBeGreaterThan(-1);
  expect(end).toBeGreaterThan(open);
  return html.slice(open, end);
}

/** Does the page render a staleness banner at all? */
function hasBanner(html: string): boolean {
  return html.includes("data-staleness-kind=");
}

/* ═══════ the harness proves itself before it proves an absence ═══════ */

describe("the harness renders the real calibration page", () => {
  test("positive control: both renders build the hero footer", () => {
    // The load-bearing assertion below is an ABSENCE, and a loading shell or a
    // crashed render satisfies every absence ever written.
    for (const generatedAt of [DATED, null]) {
      expect(footer(render(generatedAt))).toContain("Data Sep 2021");
    }
  });

  test("positive control: no banner renders in either state", () => {
    // The premise of the fix. If a banner DID render here the undated page
    // would at least be corrected from above, and the defect would be milder
    // than this file claims.
    for (const generatedAt of [DATED, null]) {
      expect(hasBanner(render(generatedAt))).toBe(false);
    }
  });

  test("positive control: the date is the only thing that moves", () => {
    const dated = makePayload(DATED) as unknown as Record<string, unknown>;
    const undated = makePayload(null) as unknown as Record<string, unknown>;
    const differing = Object.keys(dated).filter(
      k => JSON.stringify(dated[k]) !== JSON.stringify(undated[k]),
    );
    expect(differing).toEqual(["generated_at"]);
  });
});

describe("#7612 residual — an undated payload names no cadence", () => {
  test("dated: the slot reads the date it promises", () => {
    const text = footer(render(DATED));
    expect(text).toContain("· Updated Sep 15");
  });

  test("undated: the segment is withheld, not filled", () => {
    const text = footer(render(null));
    // The whole `· Updated …` segment goes, rather than being replaced by a
    // hedge — #4113 / notice 34. No paragraph explains the absence either.
    expect(text).not.toContain("Updated");
  });

  test("undated: withheld, NOT deleted — the half we can still prove survives", () => {
    // Guards the over-correction: dropping the entire footer would also pass
    // the assertion above while costing the reader a true sentence.
    const text = footer(render(null));
    expect(text).toContain("Data Sep 2021–Sep 2026");
  });

  test("the relation, not the string: the footer names a cadence only when it is naming a date", () => {
    // The same shape #7612's relation test bans in the methodology bullet,
    // aimed at the element that carried it. A future fallback that says
    // "refreshes every hour" instead fails this identically.
    const NAMES_A_CADENCE = /updated?\s+(?:hourly|every hour)|refreshe?s?\s+(?:hourly|every hour)|rebuild(?:s|ed)?\s+hourly/i;

    expect(NAMES_A_CADENCE.test(footer(render(null)))).toBe(false);
    expect(NAMES_A_CADENCE.test(footer(render(DATED)))).toBe(false);
  });
});
