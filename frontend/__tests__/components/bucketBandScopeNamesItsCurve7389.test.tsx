/**
 * #7389 — the "buckets within 5pp" guardrail names the curve it counted.
 *
 * Shopped on production at 390px, 2026-09-20. The methodology bullet read:
 *
 *     "Buckets within 5pp" — the guardrail behind the headline. We split the
 *     curve into probability buckets and check how many land within 5
 *     percentage points of perfect. Across the whole page that is 10 of 10
 *     buckets.
 *
 * The count is `cohortBuckets` — the headline table's ten bins and nothing
 * else. Reproducing this file's own `aggregateBuckets` over the live payload in
 * the DEFAULT traded cohort, the rest of the page reads:
 *
 *     Polymarket panel       9 of 10   40-50% at  -8.3pp  (n=11,705, a solid dot)
 *     shape: moneyline       9 of 10    0-10% at  +6.1pp
 *     shape: Spreads         4 of 10   90-100% at -49.1pp
 *     shape: Totals          3 of 8    70-80% at -72.3pp
 *
 * so "across the whole page" was false by a wide margin, and false in the
 * all-markets state too (that clears the Polymarket bin and leaves the three
 * sportsbook shapes exactly as they are).
 *
 * The scope was backwards rhetorically as well. The bullet's own argument is
 * that a good average can hide thin buckets swinging wildly — and it offered a
 * page-wide count as the reassurance, on a page drawing a thin bucket 72pp out.
 *
 * ═══ WHAT THIS FILE GUARDS, AND WHY IN THIS SHAPE ═══
 *
 * A literal ban on "across the whole page" would be worthless: the claim
 * survives any rephrasing, and an inherited ban that matches spellings instead
 * of the claim is how this class stays alive for months. So there are three
 * arms and the textual one is the weakest of them:
 *
 *   1. BEHAVIOUR — a payload whose headline curve is entirely in band while a
 *      second provider's curve is not. The bullet must print the headline's
 *      count, and the page must be proven to be rendering the out-of-band
 *      bucket at the same time. Without that second half the test passes
 *      against a page that simply stopped drawing the other curves.
 *   2. SHAPE — the bullet may not claim a population wider than the curve it
 *      counted, in any spelling. The predicate is proven against the shipped
 *      pre-fix sentence below, so it cannot quietly stop matching.
 *   3. POSITIVE — it must still say which curve that is. "Delete the scope
 *      phrase" also passes arms 1 and 2 and leaves the reader with a bare
 *      number.
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

/**
 * The chart is stubbed to PUBLISH its series rather than to render nothing.
 *
 * `null` is the usual stub on this page and it would make arm 1 vacuous: with
 * no chart there is no evidence the out-of-band bucket ever reached a reader,
 * and "the bullet counts only the headline" would pass against a page that
 * renders one curve. Recharts internals are not the subject here, so the stub
 * publishes the points the page HANDED the chart — which is the same question a
 * reader answers by looking at the dot.
 */
jest.mock("@/components/CalibrationChart", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ series }: { series: { label?: string; data: { bucket: string; error: number }[] }[] }) =>
      ReactLib.createElement("div", {
        "data-testid": "chart-points",
        "data-points": (series ?? [])
          .flatMap(s => (s.data ?? []).map(d => `${s.label ?? "?"}|${d.bucket}|${d.error}`))
          .join(";"),
      }),
  };
});

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import CalibrationPage from "@/app/calibration/page";

/* ───────────────────────────── the fixture ───────────────────────────── */

function bucket(source: string, idx: number, n: number, avgProb: number, actual: number) {
  return {
    bucket_idx: idx,
    source,
    category: "baseball",
    price_moved: true,
    n,
    winners: Math.round(actual * n),
    avg_prob: avgProb,
    sum_prob: avgProb * n,
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

/**
 * Kalshi carries the mass, so the POOLED headline stays inside the band while
 * Polymarket's own 50-60% bin sits 20pp under it. That is the live defect in
 * miniature: 11,705 Polymarket outcomes at -8.3pp did not move the headline's
 * 50-60% bin off -0.6pp either.
 */
const BUCKETS = [
  bucket("kalshi", 1, 50_000, 0.15, 0.15),
  bucket("kalshi", 5, 100_000, 0.55, 0.55),
  bucket("polymarket", 1, 2_000, 0.15, 0.16),
  bucket("polymarket", 5, 1_000, 0.55, 0.35),
];

function payload(): CalibrationData {
  const total = BUCKETS.reduce((s, b) => s + b.n, 0);
  return {
    buckets: BUCKETS,
    total_markets: 12_000,
    total_outcomes: total,
    total_winners: BUCKETS.reduce((s, b) => s + b.winners, 0),
    mce_ci_lower: 0.33,
    mce_ci_upper: 1.19,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-19T10:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-19" },
    by_source: [
      { source: "kalshi", ece: 0.02, mce: 0.05, n: 150_000 },
      { source: "polymarket", ece: 0.2, mce: 0.2, n: 3_000 },
    ],
    by_category: [{ category: "baseball", ece: 0.02, n: total }],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = payload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/* ─────────────────────────────── readers ─────────────────────────────── */

/** The one bullet this file is about, and nothing either side of it. */
function bandNote(html: string): string {
  const key = 'data-testid="calibration-buckets-in-band-note"';
  const start = html.indexOf(key);
  expect(start).toBeGreaterThan(-1);
  const end = html.indexOf("</li>", start);
  expect(end).toBeGreaterThan(start);
  return html.slice(start, end);
}

/** Every `label|bucket|error` the page handed a chart, across all panels. */
function chartPoints(html: string): { label: string; bucket: string; error: number }[] {
  const out: { label: string; bucket: string; error: number }[] = [];
  const key = 'data-points="';
  let at = html.indexOf(key);
  while (at > -1) {
    const from = at + key.length;
    const to = html.indexOf('"', from);
    for (const point of html.slice(from, to).split(";")) {
      if (!point) continue;
      const [label, bucketLabel, error] = point.split("|");
      out.push({ label, bucket: bucketLabel, error: Number(error) });
    }
    at = html.indexOf(key, to);
  }
  return out;
}

const ENTITIES: Readonly<Record<string, string>> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
  "&nbsp;": " ",
  "&ndash;": "–",
  "&mdash;": "—",
  "&ldquo;": "“",
  "&rdquo;": "”",
};

/**
 * Visible text of a markup fragment: tags dropped, entities decoded, whitespace
 * collapsed. A SCAN, then ONE decode pass over ONE table — the `.replace` chain
 * this replaces earns `js/incomplete-multi-character-sanitization` and
 * `js/double-escaping` from CodeQL, as recorded in
 * `benchmarkRowCarriesItsPerBucketWord7225.test.tsx`.
 *
 * It also drops the JSX comments, which is the point: the comment above the
 * bullet quotes the pre-fix sentence, and a scan over raw markup would read
 * that quote as the page still saying it.
 */
function text(fragment: string): string {
  let out = "";
  let inTag = false;
  for (const ch of fragment) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out
    .replace(/&(?:amp|lt|gt|quot|nbsp|ndash|mdash|ldquo|rdquo|#x27|#39);/g, m => ENTITIES[m])
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Does this sentence claim a population wider than one curve?
 *
 * The SHAPE is "some totalising word attached to the page or the site", not any
 * particular wording — `whole page`, `entire page`, `across the page`,
 * `anywhere on this page`, `every curve on the page`, `page-wide`, `sitewide`.
 * Proven against the shipped pre-fix sentence in the first test below, so it
 * can never silently stop matching the thing it was written for.
 */
const PAGE_WIDE_CLAIM =
  /\b(?:whole|entire|across|throughout|anywhere on|everywhere on|every (?:bucket|curve|panel|chart) on|all (?:buckets|curves|panels) on)\s+(?:the\s+|this\s+)?(?:page|site)\b|\b(?:page|site)[- ]wide\b/i;

/* ════════════════════ the predicate is not a strawman ════════════════════ */

describe("#7389 the scope predicate matches the claim, not a spelling", () => {
  test("it fires on the sentence that shipped", () => {
    expect(PAGE_WIDE_CLAIM.test("Across the whole page that is 10 of 10 buckets.")).toBe(true);
  });

  test.each([
    "Across the entire page that is 10 of 10 buckets.",
    "Everywhere on this page that is 10 of 10 buckets.",
    "Page-wide that is 10 of 10 buckets.",
    "Every bucket on the page is within 5 percentage points.",
    "Throughout the page that is 10 of 10 buckets.",
  ])("and on the rephrasings a literal ban would miss: %s", sentence => {
    expect(PAGE_WIDE_CLAIM.test(sentence)).toBe(true);
  });

  test.each([
    "On the headline curve that is 10 of 10 buckets.",
    "We split the curve into probability buckets.",
    "Each panel states its own sample size.",
  ])("and not on an honestly scoped one: %s", sentence => {
    expect(PAGE_WIDE_CLAIM.test(sentence)).toBe(false);
  });
});

/* ══════════════════════ the fixture is the live shape ═════════════════════ */

describe("#7389 the fixture puts an out-of-band bucket on the page", () => {
  test("the headline pools into the band while Polymarket's own bin does not", () => {
    const points = chartPoints(render());
    // Control — the page drew the curves at all.
    expect(points.length).toBeGreaterThan(0);

    const outOfBand = points.filter(p => Math.abs(p.error) > 5);
    expect(outOfBand).not.toHaveLength(0);
    // …and it is the one the fixture built: Polymarket's 50-60% bin, 20pp under.
    expect(outOfBand.some(p => p.bucket === "50-60%" && Math.abs(p.error - -20) < 0.2)).toBe(true);
  });
});

/* ═══════════════════════════════ the ship ═══════════════════════════════ */

describe("#7389 the guardrail bullet names the curve it counted", () => {
  test("it prints the headline curve's count", () => {
    const note = text(bandNote(render()));
    // Both headline bins are in band, so the honest count is 2 of 2 — and it is
    // the HEADLINE's, taken while a curve on the same page is 20pp out.
    expect(note).toContain("2 of 2");
  });

  test("it claims no population wider than that curve", () => {
    const note = text(bandNote(render()));
    // Control — the bullet is present and is the one about the band.
    expect(note).toContain("5 percentage points");
    expect(note).toContain("2 of 2");
    // …and makes no page-wide claim over it.
    expect(PAGE_WIDE_CLAIM.test(note)).toBe(false);
  });

  test("it still says WHICH curve — a bare number is not the fix", () => {
    const note = text(bandNote(render()));
    expect(note).toMatch(/headline curve/i);
  });
});
