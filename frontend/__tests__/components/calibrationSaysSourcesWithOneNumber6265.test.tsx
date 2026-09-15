/**
 * #6265 — `/calibration` answers "how many sources?" ONCE.
 *
 * Shopped by live/250 on production, 390px, signed out. The page printed two
 * different numbers under the same word, on one screen:
 *
 *     SOURCES  4        (stat card, `providerGroups.length`)
 *     … 441,443 resolved outcomes of 737,437 total · 7 sources · 15 categories
 *                       (population line AND footer, `sources.length`)
 *
 * Both numbers were internally correct. The payload really does carry seven raw
 * keys — `kalshi`, `polymarket`, `odds_api_bookmaker`, `odds_api`,
 * `odds_api_totals`, `odds_api_spreads`, `datagolf` — which group into four
 * providers. They are simply not the same question, and the page called both of
 * them "sources".
 *
 * ═══ THE UNCONVERTED REMAINDER OF A FIX THAT EXISTS TO PREVENT THIS ═══
 *
 * The stat card already carries the rule, in its own comment (page.tsx:1000):
 *
 *     UX-P080 item 2: counts PROVIDERS, from the same `providerGroups` the two
 *     tables below are built from — SO THE CARD CANNOT SAY 5 WHILE THEY SAY 3.
 *
 * That conversion (recorded on #1865) fixed the card and the two tables and
 * stopped there. Two reader-visible sites never adopted it, so the contradiction
 * the item was written to kill is still on the page — it moved from
 * card-vs-table to card-vs-footer. This is the same shape as #6301 the same
 * night: the rule is not missing, the call sites never asked for it.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) — AND THE CONTROL IS THE POINT ═══
 *
 * 🔴 "Replace `sources.length` with `providerGroups.length` everywhere" passes
 * every positive assertion in this file and is WRONG. One site is honest and
 * must keep the raw count, because it says a different word:
 *
 *     … open "Break out the shapes" inside the Sportsbooks panel to
 *     see all 7 KEYS separately.
 *
 * Seven is the right answer there — that panel really does break out seven keys.
 * The defect was never "7 is wrong", it was "7 is not what 'sources' means on
 * this page". So the last test below pins the keys line to the RAW count, and it
 * is the one that fails on the over-broad fix.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import { groupSourcesByProvider } from "@/lib/calibrationProviders";

// ---------------------------------------------------------------------------
// The page is a `"use client"` component behind SWR. Mocking the hook — not the
// fetcher — is what lets one synchronous render see the payload:
// `renderToStaticMarkup` never runs an effect, so a real SWR hands the page
// `undefined` and the suite photographs the loading state instead.
// ---------------------------------------------------------------------------
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

// The curve draws no text this file reads, and recharts in a static render is
// slow and noisy.
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
 * The SEVEN keys production actually served when live/250 shopped the page, in
 * the order the payload lists them. Not a synthetic set: the whole defect is the
 * gap between this count and the number of providers it groups into, so a
 * fixture that flattened the `odds_api` family would have no gap to detect.
 */
const REAL_SOURCE_KEYS = [
  "kalshi",
  "polymarket",
  "odds_api_bookmaker",
  "odds_api",
  "odds_api_totals",
  "odds_api_spreads",
  "datagolf",
];

/**
 * DERIVED, never hard-coded.
 *
 * Writing `expect(...).toContain("4 sources")` would pin the assertion to
 * today's provider map: the day a source moves families, the guard fails while
 * the page is correct, and the cheap way to "fix" it is to edit the expectation.
 * Asking the real helper means this file tests the AGREEMENT, which is the
 * actual contract, and stays true under any regrouping.
 */
const PROVIDER_N = groupSourcesByProvider(REAL_SOURCE_KEYS).length;
const RAW_KEY_N = REAL_SOURCE_KEYS.length;

/** The wire's bucket shape — `bucket_idx`/`avg_prob`/`winners`, not a guess. */
function bucket(source: string, idx: number) {
  return {
    bucket_idx: idx,
    source,
    category: "baseball",
    price_moved: true,
    n: 400,
    winners: 200,
    avg_prob: 0.05 + idx * 0.1,
    sum_prob: 400 * (0.05 + idx * 0.1),
    sum_sq_err: 40,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

function makePayload(): CalibrationData {
  const buckets = REAL_SOURCE_KEYS.flatMap((s) => [0, 1, 2, 3, 4].map((i) => bucket(s, i)));
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: 737_437,
    total_winners: 441_443,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-14T23:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-14" },
    by_source: REAL_SOURCE_KEYS.map((source) => ({ source, ece: 0.02, mce: 0.05, n: 2_000 })),
    by_category: [
      { category: "baseball", ece: 0.02, n: 4_000 },
      { category: "football", ece: 0.03, n: 3_000 },
    ],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/** Visible text only — attributes are not copy, and the source KEYS live in them. */
function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/* ═══════════ the harness proves itself before it judges an absence ═══════════ */

describe("the harness renders the real calibration page", () => {
  test("positive control: the page is built, not a loading shell", () => {
    // Several assertions below are absences. A loading state satisfies them all.
    const text = visibleText(render());
    expect(text).toContain("Sources");
    expect(text).toContain("categories");
  });

  test("the fixture actually contains the gap this issue is about", () => {
    // If the fixture's keys ever collapsed to one-per-provider there would be
    // nothing to detect and every test below would pass vacuously. Assert the
    // gap exists before relying on it.
    expect(RAW_KEY_N).toBe(7);
    expect(PROVIDER_N).toBe(4);
    expect(PROVIDER_N).toBeLessThan(RAW_KEY_N);
  });
});

/* ══════════════ SHIP — one word, one number, everywhere it appears ══════════════ */

describe("every reader-visible 'N sources' is the PROVIDER count", () => {
  test("🔴 the page never prints the raw key count beside the word 'sources'", () => {
    // The headline assertion, and the one that was false on production: the
    // footer and the population line both said "7 sources".
    const text = visibleText(render());
    expect(text).not.toContain(`${RAW_KEY_N} sources`);
    expect(text).toContain(`${PROVIDER_N} sources`);
  });

  test("the population line and the footer agree with the stat card", () => {
    const html = render();
    const text = visibleText(html);
    // The card's number, read off the card itself rather than assumed. Sliced to
    // the NEXT stat card rather than to the first `</div>` — the value sits in a
    // nested element, so a lazy close-tag match ends before reaching it and the
    // assertion then reads only the label "Sources".
    // `StatCard` gives the VALUE its own testid, so ask that element rather than
    // slicing a window around the card — a window has to guess where the card
    // ends, and the nearest landmark (`data-testid="calibration-stat-`) is a
    // PREFIX of this very element's id, so the slice collapsed onto the label.
    const cardValue = /data-testid="calibration-stat-sources-value"[^>]*>([^<]*)</.exec(html);
    expect(cardValue).not.toBeNull();
    expect(cardValue![1].trim()).toBe(String(PROVIDER_N));
    // Both prose sites now say the same thing …
    const saidSources = text.match(/(\d+) sources/g) || [];
    expect(saidSources.length).toBeGreaterThanOrEqual(2);
    // … and every one of them is the provider count, not just the first.
    for (const phrase of saidSources) expect(phrase).toBe(`${PROVIDER_N} sources`);
  });

  test("the footer publishes the count as data, not only as prose", () => {
    // notice 34: a probe should read a number, not parse a sentence.
    const html = render();
    const m = /data-testid="calibration-footer-population"[^>]*data-source-n="(\d+)"/.exec(html);
    expect(m).not.toBeNull();
    expect(Number(m![1])).toBe(PROVIDER_N);
  });
});

/* ════════ THE OTHER DIRECTION — the honest raw count is NOT suppressed ════════ */

describe("the one site that legitimately counts KEYS still counts keys", () => {
  test("🔴 'see all N keys separately' keeps the RAW count", () => {
    // THE CONTROL. A blanket `sources.length` → `providerGroups.length` sweep
    // passes every test above and breaks this one: the Sportsbooks panel really
    // does break out seven keys, so seven is the correct answer there. The
    // defect was never that 7 is wrong — it was that 7 is not what "sources"
    // means on this page.
    const text = visibleText(render());
    expect(text).toContain(`${RAW_KEY_N} keys`);
    expect(text).not.toContain(`${PROVIDER_N} keys`);
  });
});
