/**
 * #7573 — the accuracy page's headline says which KIND of statistic its figure is.
 *
 * Shopped on production at 390px, 2026-09-20 18:4xZ. The hero read:
 *
 *     Across every traded market we track, prices land within about
 *     0.9 percentage points of what actually happened.     <- a BOUND
 *
 *     … ~200px of page …
 *
 *     HOW FAR OFF, ON AVERAGE — 0.9pp                      <- the same number, a MEAN
 *
 * `data-plain-ece="0.9171802586481436"`, read off the live element. That figure
 * is ECE, the n-weighted mean of the ten bucket errors, and the page plots its
 * own counter-examples in the Calibration Table directly below it: four of the
 * ten traded buckets break 0.9pp, and the 70-80% bucket reads 2.69pp over
 * 28,475 outcomes. So the headline stated a bound the page itself disproves,
 * while its own stat card called the same number an average.
 *
 * "about" is not a repair. It hedges the MAGNITUDE of the figure; the defect is
 * the KIND of claim made over it.
 *
 * ═══ WHY "AN AVERAGE OF" AND NOT A NEW WORD (D102 / notice 34) ═══
 *
 * It is the page's own vocabulary, already on screen 200px below in the stat
 * card's label ("How far off, on average"). Same move as #7174 (renamed the MCE
 * column header to "Bucket") and #7225 (put "per-bucket" beside the How We
 * Compare figure) — a mean labelled as something it is not, repaired with a word
 * the page already uses. #7564 is the twin fix on /about, which links here.
 *
 * ═══ WHY THE FIXTURE LOOKS LIKE THIS ═══
 *
 * The guard would be VACUOUS on a flat population. If every bucket carried the
 * same error, ECE would equal that error, "within" would be defensible, and a
 * test asserting the wording would be enforcing a preference rather than a fact.
 * So the fixture separates the mean from the worst bucket the way production
 * does — one large bucket with a small error, one small bucket with a large one:
 *
 *     bucket    n          error    ECE contribution
 *     0-10%     400,000     0.5pp   n-weighted
 *     10-20%     40,000     3.0pp   equal-weighted
 *     ECE = (400000x0.5 + 40000x3.0) / 440000 = 0.727  -> "0.7pp"
 *     worst bucket                             = 3.0pp
 *
 * `theBoundWouldBeALie` below asserts that separation from the fixture itself
 * BEFORE any wording assertion runs, so a later edit that flattens the fixture
 * fails loudly here instead of quietly turning the wording guards into taste.
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

/* ───────────────────────────── the fixture ───────────────────────────── */

/** What the hero's ECE comes out at, given the buckets below. */
const HERO_ECE_TEXT = "0.7 percentage points";

/** One wire bucket. Its error falls out of `winners/n - sum_prob/n`. */
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
  // big bucket, small error: 0.055 - 0.050 = +0.5pp on 400,000 outcomes
  bucket(0, true, 400_000, 0.05, 0.055),
  // small bucket, large error: 0.180 - 0.150 = +3.0pp on 40,000 outcomes
  bucket(1, true, 40_000, 0.15, 0.18),
];

// An untraded population, so the default (traded) cohort is a real filter and
// the headline's scope clause has something to be true about.
const UNTRADED = [
  bucket(0, false, 90_000, 0.05, 0.06),
  bucket(1, false, 10_000, 0.15, 0.17),
];

function makePayload(): CalibrationData {
  const buckets = [...TRADED, ...UNTRADED];
  const total = buckets.reduce((s, b) => s + b.n, 0);
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: total,
    total_winners: buckets.reduce((s, b) => s + b.winners, 0),
    mce_ci_lower: 0.3,
    mce_ci_upper: 1.2,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-20T10:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-20" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: total }],
    by_category: [{ category: "baseball", ece: 0.02, n: total }],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/* ─────────────────────────── reading the page ─────────────────────────── */

/** The entities `renderToStaticMarkup` emits, in ONE table. */
const ENTITIES: Readonly<Record<string, string>> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
  "&nbsp;": " ",
};

/**
 * Visible text of a markup fragment: tags dropped, entities decoded, whitespace
 * collapsed.
 *
 * A SCAN and a single-pass decode, not a chain of `.replace` calls — CodeQL
 * fails the latter with `js/incomplete-multi-character-sanitization` and
 * `js/double-escaping`, and both are real: a one-pass `<...>` delete is wrong on
 * nested angle brackets, and decoding in separate passes lets one pass re-read
 * another's output. (Learned on #7225's PR.)
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
    .replace(/&(?:amp|lt|gt|quot|nbsp|#x27|#39);/g, m => ENTITIES[m])
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The text of the element carrying `data-testid`, read off the element itself.
 * A window sliced around a phrase is not usable here: the hero's sentence is
 * broken by a `<strong>`, so the phrase a reader sees does not exist as a
 * substring of the markup.
 */
function elementText(html: string, testId: string): string {
  const at = html.indexOf(`data-testid="${testId}"`);
  expect(at).toBeGreaterThan(-1);
  const open = html.indexOf(">", at);
  let depth = 1;
  const tag = /<(\/?)(?:div|p|span|strong|em|a)\b[^>]*?(\/?)>/g;
  tag.lastIndex = open + 1;
  let t: RegExpExecArray | null;
  let end = -1;
  while ((t = tag.exec(html)) !== null) {
    if (t[2] === "/") continue; // self-closing
    depth += t[1] === "/" ? -1 : 1;
    if (depth === 0) {
      end = t.index;
      break;
    }
  }
  expect(end).toBeGreaterThan(open);
  return text(html.slice(open + 1, end));
}

/* ──────────────────────────────── the guard ──────────────────────────────── */

describe("#7573 the hero headline states an average, not a bound", () => {
  const html = render();
  const headline = elementText(html, "calibration-plain-headline");

  test("the fixture separates the mean from its worst bucket, so a bound WOULD be a lie", () => {
    // Read the separation off the fixture, not off the page: this is the fact
    // the wording assertions below depend on, and it must hold independently of
    // anything the page does with it.
    const errs = TRADED.map(b => Math.abs(b.winners / b.n - b.sum_prob / b.n) * 100);
    const n = TRADED.reduce((s, b) => s + b.n, 0);
    const ece = TRADED.reduce((s, b, i) => s + errs[i] * b.n, 0) / n;
    const worst = Math.max(...errs);

    expect(ece).toBeCloseTo(0.727, 2);
    expect(worst).toBeCloseTo(3.0, 2);
    // The whole point: the worst bucket is multiples of the mean, so "prices
    // land within <mean>" is false of a real, plotted slice of the population.
    expect(worst).toBeGreaterThan(ece * 2);
  });

  test("the headline publishes that figure", () => {
    expect(headline).toContain(HERO_ECE_TEXT);
  });

  test("the headline does not state a bound over it", () => {
    // The regression this file exists to catch, in any of its shapes.
    expect(headline).not.toMatch(/\bwithin\b/i);
    expect(headline).not.toMatch(/\bno more than\b/i);
    expect(headline).not.toMatch(/\bat most\b/i);
    expect(headline).not.toMatch(/\bnever more than\b/i);
  });

  test("the headline names the kind of statistic, in the stat card's own word", () => {
    expect(headline).toMatch(/\ban average of\b/i);
    // …and the card it is borrowing that word from is still on the page saying
    // it, so the two cannot drift apart into two vocabularies for one number.
    expect(text(html)).toContain("How far off, on average");
  });

  test("the figure and the scope clause are untouched by this fix", () => {
    // #7202 owns the scope: it comes from the partition, never from a literal
    // in the page. Rewording the verb must not have taken the scope with it.
    expect(headline).toContain("traded");
    expect(headline.startsWith("Across every traded market we track,")).toBe(true);
    // The number itself never moved — only the claim made over it.
    const ece = html.match(/data-plain-ece="([\d.]+)"/);
    expect(ece).not.toBeNull();
    expect(Number(ece![1])).toBeCloseTo(0.727, 2);
  });
});
