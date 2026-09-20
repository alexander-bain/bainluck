/**
 * #7374 — the confidence interval reaches a reader only beside its own population.
 *
 * Shopped on production at 390px, 2026-09-20 05:20Z, in both cohort states:
 *
 *     Bain Luck (all sources) [TRADED]      1.0pp per-bucket (95% CI: 0.3-1.2pp) | 449,027 outcomes
 *     Bain Luck (all sources) [ALL MARKETS] 0.9pp per-bucket (95% CI: 0.3-1.2pp) | 747,028 outcomes
 *
 * Two point estimates, two populations, one interval — because `mce_ci_lower` /
 * `mce_ci_upper` are a single payload scalar the producer bootstraps over every
 * bucket with no `price_moved` filter. `_bootstrap_mce_ci` is deterministic
 * (`random.Random(42)`, 1,000 resamples), so reproducing it off the live payload
 * gives the traded cohort's own interval: 0.62-1.29pp. The default view's lower
 * bound was out by about a factor of two.
 *
 * `lib/calibrationIntervalScope.test.ts` holds the predicate and
 * `lib/calibrationIntervalReachesOneFigure7374.test.ts` holds the wiring. This
 * file is the only one that answers the question a reader asks: is the interval
 * on my screen, or isn't it.
 *
 * ═══ WHY THERE ARE TWO PAYLOADS AND NOT A TOGGLE ═══
 *
 * `renderToStaticMarkup` runs no effects, so the cohort button cannot be
 * clicked here. That is not a limitation worked around — it is the better test,
 * because the fix is keyed on the POPULATION (`cohortN === fullN`) and not on
 * the toggle boolean. A payload whose buckets are all traded has one population
 * in both toggle states, and the interval must publish on the view a reader
 * lands on. So:
 *
 *     MIXED payload   (traded + untraded)  -> default cohort is partial -> withheld
 *     WHOLE payload   (nothing untraded)   -> default cohort IS the full -> published
 *
 * The second is the positive control. Without it, "the interval is absent"
 * passes just as well against a page that lost the ability to print one at all,
 * which is a different bug wearing this fix's clothes.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";

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

/* ───────────────────────────── the fixtures ───────────────────────────── */

function bucket(idx: number, priceMoved: boolean, n: number, avgProb: number, actual: number) {
  return {
    bucket_idx: idx,
    source: "kalshi",
    category: "baseball",
    price_moved: priceMoved,
    n,
    winners: Math.round(actual * n),
    avg_prob: avgProb,
    sum_prob: avgProb * n,
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

const TRADED = [
  bucket(0, true, 400_000, 0.05, 0.055),
  bucket(1, true, 40_000, 0.15, 0.18),
];

const UNTRADED = [
  bucket(0, false, 90_000, 0.05, 0.06),
  bucket(1, false, 10_000, 0.15, 0.17),
];

/** The pair the live payload serves, to the digit. */
const CI = { mce_ci_lower: 0.33, mce_ci_upper: 1.19 };

function payload(buckets: ReturnType<typeof bucket>[]): CalibrationData {
  const total = buckets.reduce((s, b) => s + b.n, 0);
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: total,
    total_winners: buckets.reduce((s, b) => s + b.winners, 0),
    ...CI,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-19T10:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-19" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: total }],
    by_category: [{ category: "baseball", ece: 0.02, n: total }],
  } as unknown as CalibrationData;
}

function render(buckets: ReturnType<typeof bucket>[]): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = payload(buckets);
  return renderToStaticMarkup(<CalibrationPage />);
}

const MIXED = () => render([...TRADED, ...UNTRADED]);
const WHOLE = () => render([...TRADED]);

/**
 * Slices, because "95% CI" is a legitimate column header on this page.
 *
 * The Calibration Table publishes a `95% CI` column for every bucket's Wilson
 * interval, and the By Source panels describe their error bars the same way.
 * A page-wide ban on the string would collide with both and would have to be
 * weakened until it caught nothing. Every assertion below is scoped to the one
 * block it is about, and each slice is checked for content first.
 */
function showTheMath(html: string): string {
  const start = html.indexOf('data-testid="calibration-show-the-math"');
  expect(start).toBeGreaterThan(-1);
  const end = html.indexOf("How we measure this", start);
  expect(end).toBeGreaterThan(start);
  return html.slice(start, end);
}

function ourBenchmarkRow(html: string): string {
  const start = html.indexOf('data-benchmark-highlight="1"');
  expect(start).toBeGreaterThan(-1);
  const next = html.indexOf('data-testid="calibration-benchmark-row"', start);
  expect(next).toBeGreaterThan(start); // there is always a row after ours
  return html.slice(start, next);
}

/** Visible text: tags dropped, the entities this page emits decoded. */
function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&ndash;/g, "–")
    .replace(/&nbsp;/g, " ")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

/* ═════════════════════════ the fixtures are real ═════════════════════════ */

describe("#7374 the two fixtures differ in the one way that matters", () => {
  test("MIXED renders a partial default cohort; WHOLE renders the full one", () => {
    // Read off the page's own published counts rather than asserted from the
    // fixture, so this cannot agree with a page that ignores `price_moved`.
    const mixed = MIXED();
    expect(mixed).toContain('data-unchanged-n="100000"');
    expect(mixed).toContain('data-moved-n="440000"');

    const whole = WHOLE();
    expect(whole).toContain('data-unchanged-n="0"');
    expect(whole).toContain('data-moved-n="440000"');
  });

  test("both payloads carry the same interval on the wire", () => {
    // The interval is not what varies. The population under it is.
    expect(payload([...TRADED, ...UNTRADED]).mce_ci_lower).toBe(0.33);
    expect(payload([...TRADED]).mce_ci_lower).toBe(0.33);
  });
});

/* ═══════════════════════════════ the ship ═══════════════════════════════ */

describe("#7374 the interval is printed only over the population it describes", () => {
  test("POSITIVE CONTROL — the whole population prints it, with its figure", () => {
    const fold = text(showTheMath(WHOLE()));
    expect(fold).toContain("95% confidence interval on that figure: 0.3-1.2pp");
    // And it is the n-weighted sentence it belongs to, not a floating clause.
    expect(fold).toContain("ECE");
    expect(fold).toContain("n-weighted");
  });

  test("a partial cohort prints none", () => {
    const fold = text(showTheMath(MIXED()));
    // Control — the fold itself is still there and still says what it is.
    expect(fold).toContain("n-weighted");
    expect(fold).toContain("Per-bucket error");
    // …and carries no interval.
    expect(fold).not.toContain("confidence interval");
    expect(fold).not.toContain("0.3-1.2pp");
  });

  test("and says nothing about the absence (notice 34)", () => {
    // The failure mode this rules out is a sentence explaining the gap. If the
    // interval cannot be shown honestly the space is simply empty.
    const fold = text(showTheMath(MIXED()));
    for (const excuse of ["confidence", "interval", "bootstrap", "95%", "cohort"]) {
      expect(fold).not.toContain(excuse);
    }
  });

  test("it never claims to be an interval on the per-bucket figure", () => {
    // It is bootstrapped n-weighted; the per-bucket number is equal-weighted.
    // Checked on the arm that actually prints it, so this is not vacuous.
    const fold = text(showTheMath(WHOLE()));
    expect(fold).toContain("confidence interval"); // the arm is live
    expect(fold).not.toContain("interval on the per-bucket figure");
  });
});

describe("#7374 the How We Compare row carries no interval in either cohort", () => {
  test.each([["partial", MIXED], ["whole", WHOLE]])(
    "%s cohort",
    (_label, build) => {
      const row = text(ourBenchmarkRow(build()));
      // Control — it is the row that prints the equal-weighted figure.
      expect(row).toContain("per-bucket");
      expect(row).toContain("440,000 outcomes");
      // …and it prints no interval beside it.
      expect(row).not.toContain("95% CI");
      expect(row).not.toContain("0.3-1.2pp");
    }
  );
});
