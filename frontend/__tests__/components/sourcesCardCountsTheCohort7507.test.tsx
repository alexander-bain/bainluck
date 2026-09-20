/**
 * #7507 — EVERY "N SOURCES" ON THE ACCURACY PAGE COUNTS THE COHORT IT NAMES.
 *
 * ── WHAT A READER SAW, MEASURED ON PRODUCTION ───────────────────────────────
 *
 * `https://bainluck.com/calibration` at 390px, 2026-09-20 13:31Z (live at
 * `25468e60d`), in the DEFAULT cohort — the state the page loads in. Hero and
 * stat card fit on one phone screen, ~500px apart:
 *
 *   hero    "… across Kalshi, Polymarket, and sportsbook odds."          3
 *   card    SOURCES 4 · Kalshi · Polymarket · Sportsbooks (…) · DataGolf 4
 *   table   DataGolf — "No outcomes in this cohort"                      0
 *
 * Per provider, from the live Source Comparison table:
 *
 *   kalshi            326,909 full    214,622 default cohort
 *   polymarket        264,956 full     79,278 default cohort
 *   odds_api family   155,127 full    155,127 default cohort
 *   datagolf               36 full          0 default cohort
 *   ── total          747,028 full    449,027 default cohort
 *
 * Both totals reconcile exactly, so DataGolf's contribution to the default
 * cohort is zero, not merely small.
 *
 * ── THE UNCONVERTED REMAINDER OF #7456 ──────────────────────────────────────
 *
 * #7456 converted the sentences that print a LIST, and said in its own comment
 * why: "DataGolf is 0 in the default cohort, so naming it there would be the
 * opposite falsehood." The three sites that print a COUNT — card, "Show the
 * math" population line, footer — kept reading `providerGroups.length`, which
 * is the payload's provider map and cannot see the toggle.
 *
 * It is also #6265 one rung on. That issue made the three count sites AGREE
 * with each other, and they still did: they agreed on a number that was wrong
 * in the cohort all three of them name. Agreement was the contract that shipped;
 * cohort-truth was never asserted, so nothing went red.
 *
 * ── WHAT THIS FILE PINS ─────────────────────────────────────────────────────
 *
 * Read off the rendered DOM, never recomputed here:
 *
 *   1. the card's value, the population line and the footer all equal the
 *      number of providers WITH OUTCOMES IN THE COHORT;
 *   2. the card does not NAME a provider it does not count;
 *   3. #6265's contract survives — the three still answer with one number;
 *   4. the card agrees with the hero's list, which is the pairing #7456 shipped.
 *
 * ── BOTH DIRECTIONS (gotcha #43), AND THE CONTROL THAT MATTERS ──────────────
 *
 * 🔴 "Filter out every provider the table withholds" is the over-broad fix, it
 * passes every default-cohort assertion here, and it is WRONG. There are two
 * different absences and `calibrationSourceRows.ts` exists to keep them apart:
 *
 *   `no-cohort-data`  n === 0 — nothing here. Not a source of this cohort.
 *   `censored`        n > 0, one-sided — withheld from the RANKING only.
 *                     Production's all-markets DataGolf: 36 outcomes, all won.
 *
 * A censored provider IS in the cohort and must stay counted. The third arm
 * below is that control: it renders DataGolf traded and all-winners, and fails
 * on any fix that folds `censoredSourceRows` into the predicate.
 *
 * ── WHY THERE IS NO CLICK ───────────────────────────────────────────────────
 *
 * `testEnvironment: 'node'` + `renderToStaticMarkup`, so the cohort toggle
 * cannot be pressed (the constraint `pinAffordance.test.tsx` records, and the
 * one #7456 works around the same way). The all-markets arithmetic is reached
 * honestly instead — a payload whose DataGolf rows are `price_moved: true`, so
 * the default cohort IS the whole population for that provider.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import { groupSourcesByProvider, providerOf } from "@/lib/calibrationProviders";

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
 * The production source keys and their outcome counts, 2026-09-20 — per SOURCE
 * key, because that is what the payload carries and what `groupSourcesByProvider`
 * folds. Writing the four provider totals instead would hand the code under test
 * its own answer.
 */
const PROD_SOURCES = [
  { source: "kalshi", n: 326_909 },
  { source: "polymarket", n: 264_956 },
  { source: "odds_api_bookmaker", n: 106_030 },
  { source: "odds_api", n: 18_440 },
  { source: "odds_api_totals", n: 15_537 },
  { source: "odds_api_spreads", n: 15_120 },
  { source: "datagolf", n: 36 },
];

/** The share of each source that is `price_moved: false`, as production has it. */
const UNTRADED_SHARE: Record<string, number> = {
  kalshi: 112_287 / 326_909,
  polymarket: 185_678 / 264_956,
  // Sportsbook lines carry no flag at all; traded by construction (D101).
  odds_api_bookmaker: 0,
  odds_api: 0,
  odds_api_totals: 0,
  odds_api_spreads: 0,
  // The whole content of #2176: every DataGolf row is `price_moved: false`.
  datagolf: 1,
};

/** Every provider the PAYLOAD carries — the count the page used to print. */
const PAYLOAD_PROVIDER_N = groupSourcesByProvider(PROD_SOURCES.map(s => s.source)).length;
/** The providers with outcomes in the DEFAULT cohort. DataGolf is not one. */
const COHORT_PROVIDER_N = new Set(
  PROD_SOURCES.filter(s => UNTRADED_SHARE[s.source] < 1).map(s => providerOf(s.source))
).size;

type DataGolfMode = "untraded" | "traded" | "traded-and-censored";

function bucket(
  source: string,
  idx: number,
  priceMoved: boolean | null,
  n: number,
  allWinners = false,
) {
  const p = 0.05 + idx * 0.1;
  return {
    bucket_idx: idx,
    source,
    category: "golf",
    price_moved: priceMoved,
    n,
    winners: allWinners ? n : Math.round(n * p),
    avg_prob: p,
    sum_prob: n * p,
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

/**
 * @param mode how DataGolf's 36 outcomes sit relative to the default cohort:
 *   `untraded`            production today — 0 in the cohort  (`no-cohort-data`)
 *   `traded`              in the cohort, two-sided            (`measured`)
 *   `traded-and-censored` in the cohort, all 36 won           (`censored`)
 */
function makePayload(mode: DataGolfMode = "untraded"): CalibrationData {
  const buckets = PROD_SOURCES.flatMap(s => {
    const isGolf = s.source === "datagolf";
    const untradedShare = isGolf && mode !== "untraded" ? 0 : UNTRADED_SHARE[s.source];
    const untraded = Math.round(s.n * untradedShare);
    const traded = s.n - untraded;
    const flag = s.source.startsWith("odds_api") ? null : true;
    const allWinners = isGolf && mode === "traded-and-censored";
    const rows = [];
    for (let i = 0; i < 5; i++) {
      if (traded > 0) rows.push(bucket(s.source, i, flag, Math.round(traded / 5), allWinners));
      if (untraded > 0) rows.push(bucket(s.source, i, false, Math.round(untraded / 5), allWinners));
    }
    return rows;
  });
  return {
    buckets,
    total_markets: 400_000,
    total_outcomes: buckets.reduce((t, b) => t + b.n, 0),
    total_winners: 300_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-20T09:00:00Z",
    date_range: { start: "2021-09-01", end: "2026-09-20" },
    by_source: PROD_SOURCES.map(s => ({ source: s.source, ece: 0.01, mce: 0.02, n: s.n })),
    by_category: [{ category: "golf", ece: 0.01, n: 400_000 }],
  } as unknown as CalibrationData;
}

function render(mode: DataGolfMode = "untraded"): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload(mode);
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

/** The card's own value element, not a guessed window around the card (#6265). */
function cardValue(html: string): string {
  const m = /data-testid="calibration-stat-sources-value"[^>]*>([^<]*)</.exec(html);
  if (!m) throw new Error("the Sources stat card did not render its value element");
  return m[1].trim();
}

/** The card's detail line — the names printed under the number. */
function cardDetail(html: string): string {
  const m = /data-testid="calibration-stat-sources-detail"[^>]*>([\s\S]*?)<\/div>/.exec(html);
  if (!m) throw new Error("the Sources stat card did not render its detail element");
  return visibleText(m[1]);
}

function footerSourceN(html: string): string {
  const m = /data-testid="calibration-footer-population"[^>]*data-source-n="(\d+)"/.exec(html);
  if (!m) throw new Error("the footer did not publish data-source-n");
  return m[1];
}

/** Every `N sources` a reader can see, in document order. */
function everySourcesPhrase(html: string): string[] {
  return visibleText(html).match(/\d+ sources/g) || [];
}

/* ═══════════ the harness proves itself before it judges an absence ═══════════ */

describe("the harness renders the real calibration page", () => {
  test("positive control: the page is built, not a loading shell", () => {
    // Most assertions below are about a number being SMALLER and a name being
    // ABSENT. A loading state satisfies every one of them.
    const text = visibleText(render());
    expect(text).toContain("Sources");
    expect(text).toContain("categories");
    expect(text).toContain("Kalshi");
  });

  test("the fixture reproduces the production gap this issue is about", () => {
    // If DataGolf ever stopped being cohort-empty in this fixture there would be
    // no gap to detect and the ship assertions would pass vacuously.
    expect(PAYLOAD_PROVIDER_N).toBe(4);
    expect(COHORT_PROVIDER_N).toBe(3);
    expect(COHORT_PROVIDER_N).toBeLessThan(PAYLOAD_PROVIDER_N);
  });

  test("the pre-fix number is the one the payload map yields, so the guard could fail", () => {
    // Names the defect's value explicitly: before this ship all three sites
    // printed PAYLOAD_PROVIDER_N. A fix that changes nothing leaves it here.
    const html = render();
    expect(cardValue(html)).not.toBe(String(PAYLOAD_PROVIDER_N));
  });
});

/* ═══════════════════ SHIP — the default cohort counts three ═══════════════════ */

describe("default cohort: every 'N sources' is the cohort's provider count", () => {
  test("🔴 the Sources card counts the cohort, not the payload's provider map", () => {
    expect(cardValue(render())).toBe(String(COHORT_PROVIDER_N));
  });

  test("🔴 the card does not NAME a provider it does not count", () => {
    const detail = cardDetail(render());
    expect(detail).not.toContain("DataGolf");
    // …and still names the three it does count, so the fix is not "print less".
    expect(detail).toContain("Kalshi");
    expect(detail).toContain("Polymarket");
    expect(detail).toContain("Sportsbooks");
  });

  test("the card's number and its list of names agree", () => {
    // The defect's signature was a count and a list that disagreed. Read both
    // off the DOM and compare them rather than comparing each to a constant.
    const html = render();
    const named = cardDetail(html).split(" · ").filter(Boolean).length;
    expect(named).toBe(Number(cardValue(html)));
  });

  test("the population line and the footer say the same number as the card", () => {
    // #6265's contract, unchanged: the page answers "how many sources" ONCE.
    const html = render();
    const phrases = everySourcesPhrase(html);
    expect(phrases.length).toBeGreaterThanOrEqual(2);
    for (const phrase of phrases) expect(phrase).toBe(`${COHORT_PROVIDER_N} sources`);
    expect(cardValue(html)).toBe(String(COHORT_PROVIDER_N));
  });

  test("the footer's data hook moves with its prose, not with the payload", () => {
    // notice 34: a probe reads the number, not the sentence. If the attribute
    // kept the payload count the contradiction would be invisible to every rail.
    const html = render();
    expect(footerSourceN(html)).toBe(String(COHORT_PROVIDER_N));
    expect(footerSourceN(html)).toBe(cardValue(html));
  });

  test("the card cannot contradict the Source Comparison row for the same provider", () => {
    // The table is what settles who is right, so assert the pairing rather than
    // the card alone: the page still SAYS DataGolf has no outcomes here, and the
    // card above it no longer counts it.
    const html = render();
    expect(visibleText(html)).toContain("No outcomes in this cohort");
    expect(cardDetail(html)).not.toContain("DataGolf");
  });

  test("the hero's list and the card's count are one derivation (#7456's pairing)", () => {
    const html = render();
    const hero = /data-hero-sources="([^"]*)"/.exec(html);
    expect(hero).not.toBeNull();
    const heroNamed = hero![1].split(/,\s*|\s+and\s+/).filter(Boolean).length;
    expect(heroNamed).toBe(Number(cardValue(html)));
  });
});

/* ════════ BOTH DIRECTIONS — a provider that is IN the cohort stays counted ════════ */

describe("all-markets arithmetic: a provider with outcomes is counted and named", () => {
  test("DataGolf traded ⇒ all four counted, everywhere", () => {
    const html = render("traded");
    expect(cardValue(html)).toBe(String(PAYLOAD_PROVIDER_N));
    expect(cardDetail(html)).toContain("DataGolf");
    expect(footerSourceN(html)).toBe(String(PAYLOAD_PROVIDER_N));
    for (const phrase of everySourcesPhrase(html)) {
      expect(phrase).toBe(`${PAYLOAD_PROVIDER_N} sources`);
    }
  });

  test("🔴 a CENSORED provider is still one of the cohort's sources", () => {
    // The control against the over-broad fix. Production's all-markets DataGolf
    // is exactly this row: 36 outcomes, all won, withheld from the RANKING and
    // from nothing else. Folding `censoredSourceRows` into the predicate reads 3
    // here and drops a provider the cohort measurably contains.
    const html = render("traded-and-censored");
    expect(visibleText(html)).toContain("no losses to measure against");
    expect(cardValue(html)).toBe(String(PAYLOAD_PROVIDER_N));
    expect(cardDetail(html)).toContain("DataGolf");
    expect(footerSourceN(html)).toBe(String(PAYLOAD_PROVIDER_N));
  });

  test("the count tracks the cohort rather than a constant, in both directions", () => {
    // One assertion holding the whole contract: the same page, two payloads,
    // two answers. A hard-coded 3 and a hard-coded 4 each fail one arm.
    expect(cardValue(render("untraded"))).toBe(String(COHORT_PROVIDER_N));
    expect(cardValue(render("traded"))).toBe(String(PAYLOAD_PROVIDER_N));
  });
});
