/**
 * #7486 — the "What's a Brier score?" bullet cites the population the page is
 * showing, and prints the string the Brier Score card prints.
 *
 * Shopped on production at 390px, 2026-09-20 12:20Z, DEFAULT (traded) cohort.
 * One page, one metric, two answers, four screens apart:
 *
 *   Brier Score stat card (y≈830)      0.1763
 *   "show the math" line (y≈2,100)     Brier 0.1763
 *   cohort comparison table (y≈3,600)  0.1763
 *   methodology bullet (y≈9,570)       "…0.25 is random guessing. Ours is 0.17."
 *
 * `0.1763` does not round to `0.17` — it rounds to `0.18` — so the bullet was
 * never a shortening of the number above it. It was `overallBrier.toFixed(2)`,
 * an UNFILTERED `brierScore(normalized)` over all 747,028 outcomes, printed
 * under a hero that tells the reader in so many words that the page excludes
 * the 298,001 untraded ones. Recomputed from the served `buckets[]`:
 *
 *   cohort (price_moved !== false)   449,027   0.176336
 *   all markets                      747,028   0.170763
 *
 * The tell is #7422's, one metric over: the bullet was the only Brier on the
 * page that did NOT move when the reader toggled the cohort, because it was
 * already the all-markets figure — correct only in the cohort the reader is not
 * in by default.
 *
 * ═══ WHAT THIS FILE GUARDS, AND WHY IN THIS SHAPE ═══
 *
 *   1. PAIRING — the bullet's figure IS the stat card's figure, read as strings
 *      off the rendered page. Both now come from one `cohortBrierText`, so the
 *      assertion is on the rendered output rather than on the wiring: a later
 *      hand-formatted `.toFixed(2)` at either call site reopens the gap and is
 *      caught here, not in review.
 *   2. NOT VACUOUS — the fixture is adversarial by assertion. Its cohort figure
 *      and its all-markets figure are checked to differ by more than the
 *      display precision, at BOTH 4dp and 2dp, before the pairing is read. A
 *      fixture whose two populations happen to agree satisfies arm 1 against
 *      the broken code, which is the only way this guard could be a decoration.
 *   3. THE DEFECT, NAMED — the bullet must not print the all-markets figure in
 *      any rendering of it. Arm 1 alone would pass if both surfaces regressed
 *      together.
 *   4. NO-CHANGE — the three surfaces that were already right (card, "show the
 *      math", cohort table) still print the cohort figure and still agree. This
 *      fix routed them through a shared string; a fix that MOVED them would be
 *      the regression, not the repair.
 *   5. NO REINTRODUCTION — the page declares no unfiltered aggregate. The
 *      defect was not the bullet's wording, it was a `brierScore(normalized)`
 *      sitting in scope with nothing to stop the next bullet reaching for it.
 *
 * The other cohort cannot be reached here: the toggle is `useState` and this
 * page renders statically. Arm 5 is what covers it — with no unfiltered figure
 * in scope, there is nothing for either cohort to disagree about.
 */

import React from "react";
import fs from "fs";
import path from "path";
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

jest.mock("@/components/CalibrationChart", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: () => ReactLib.createElement("div", { "data-testid": "chart" }),
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

/**
 * `sumSqErr` is set directly rather than derived: the Brier score is the only
 * thing under test, and pinning it is what lets the two populations be pulled
 * apart far enough to be unmistakable at 2dp as well as 4dp.
 */
function bucket(
  source: string,
  idx: number,
  n: number,
  avgProb: number,
  winners: number,
  priceMoved: boolean | null,
  brier: number,
) {
  return {
    bucket_idx: idx,
    source,
    category: "baseball",
    price_moved: priceMoved,
    n,
    winners,
    avg_prob: avgProb,
    sum_prob: avgProb * n,
    sum_sq_err: n * brier,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

/**
 * Production's shape, exaggerated: a traded slice that scores materially WORSE
 * than the untraded bulk it is pooled with, so pooling drags the figure down
 * and the bullet's number is the flattering one. That is the direction
 * production showed (0.1763 traded against 0.1708 pooled), which is the
 * direction that matters — the wrong number was the better-looking one.
 *
 *   kalshi traded      100,000 @ 0.19
 *   sportsbook (null)   50,000 @ 0.19   ← kept by the cohort: `price_moved !== false`
 *   polymarket untraded 200,000 @ 0.05  ← excluded by default
 *
 *   cohort      150,000 → 0.1900
 *   all markets 350,000 → 0.1100
 */
const KALSHI_TRADED = bucket("kalshi", 5, 100_000, 0.55, 52_000, true, 0.19);
const SPORTSBOOK_NA = bucket("odds_api", 5, 50_000, 0.52, 25_500, null, 0.19);
const POLY_UNTRADED = bucket("polymarket", 5, 200_000, 0.55, 110_000, false, 0.05);

const BUCKETS = [KALSHI_TRADED, SPORTSBOOK_NA, POLY_UNTRADED];

/** The two figures, computed the way the page computes them. */
function brierOver(pred?: (b: typeof BUCKETS[number]) => boolean): number {
  let n = 0;
  let sq = 0;
  for (const b of BUCKETS) {
    if (pred && !pred(b)) continue;
    n += b.n;
    sq += b.sum_sq_err;
  }
  return n > 0 ? sq / n : 0;
}

const COHORT_BRIER = brierOver(b => b.price_moved !== false);
const ALL_MARKETS_BRIER = brierOver();

function payload(): CalibrationData {
  const total = BUCKETS.reduce((s, b) => s + b.n, 0);
  return {
    buckets: BUCKETS,
    total_markets: 300_000,
    total_outcomes: total,
    total_winners: BUCKETS.reduce((s, b) => s + b.winners, 0),
    mce_ci_lower: 0.33,
    mce_ci_upper: 1.19,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-20T07:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-20" },
    by_source: [
      { source: "kalshi", ece: 1.0, mce: 1.3, n: 100_000 },
      { source: "polymarket", ece: 0.9, mce: 1.1, n: 200_000 },
      { source: "odds_api", ece: 1.5, mce: 1.6, n: 50_000 },
    ],
    by_category: [{ category: "baseball", ece: 0.9, n: total }],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = payload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/* ─────────────────────────────── readers ─────────────────────────────── */

/** The entities `renderToStaticMarkup` emits on this page, in ONE table. */
const ENTITIES: Readonly<Record<string, string>> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
  "&nbsp;": " ",
  "&rsquo;": "’",
  "&sup2;": "²",
};

/**
 * Visible text of a markup fragment: tags dropped by a SCAN, entities decoded in
 * ONE pass over ONE table, whitespace collapsed.
 *
 * Copied from `benchmarkRowCarriesItsPerBucketWord7225.test.tsx`, which carries
 * the reasoning, because the obvious first draft — `.replace(/<[^>]*>/g, "")`
 * followed by a chain of entity replaces — is a HIGH CodeQL finding
 * (`js/incomplete-multi-character-sanitization`, `js/double-escaping`) and a
 * test file is not an exemption. This file's first draft was that draft, and
 * CodeQL failed the sha for it; the scan cannot mis-handle a nested bracket and
 * no replacement's output is ever re-read.
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
    .replace(/&(?:amp|lt|gt|quot|nbsp|rsquo|sup2|#x27|#39);/g, m => ENTITIES[m])
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The text of the element carrying `testid`, walked to its OWN closing tag —
 * the bullet's sentence is broken by a `<strong>`, so the phrase a reader sees
 * is not a substring of the markup.
 */
function textOf(html: string, testid: string): string {
  const at = html.indexOf(`data-testid="${testid}"`);
  if (at === -1) return "";
  const open = html.indexOf(">", at);
  let depth = 1;
  const tag = /<(\/?)(?:div|p|span|strong|em|a|li)\b[^>]*?(\/?)>/g;
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
  if (end <= open) return "";
  return text(html.slice(open + 1, end));
}

function attrOf(html: string, testid: string, name: string): string | null {
  const m = html.match(new RegExp(`<[a-z]+[^>]*data-testid="${testid}"[^>]*>`));
  if (!m) return null;
  const a = m[0].match(new RegExp(`${name}="([^"]*)"`));
  return a ? a[1] : null;
}

/**
 * Every 4dp figure the page prints, so "did anything else move" is answerable.
 * Read off `text()`, not the raw markup: a class name or a data attribute
 * carrying digits is not something a reader sees.
 */
function fourDpFigures(html: string): string[] {
  // No `\b` on either side: the page's text runs figures straight into the next
  // label ("…0.1900Kalshi…"), and a trailing word boundary silently drops every
  // one of those — it found 2 of the 7 on this fixture, which is how a
  // "nothing else moved" arm quietly stops looking at most of the page.
  return (text(html).match(/0\.\d{4}/g) ?? []).sort();
}

/* ──────────────────────────────── the arms ───────────────────────────── */

describe("#7486 — the fixture is adversarial (arm 2, read first)", () => {
  it("the cohort figure and the all-markets figure really do differ, at both precisions", () => {
    // Without this, arm 1 passes against the broken code whenever the two
    // populations happen to agree — which is exactly what rounding to 2dp did
    // for every Brier on this page until the traded and untraded slices drifted
    // apart. The guard rests entirely on this being true.
    expect(COHORT_BRIER).toBeCloseTo(0.19, 6);
    expect(ALL_MARKETS_BRIER).toBeCloseTo(0.11, 6);
    expect(Math.abs(COHORT_BRIER - ALL_MARKETS_BRIER)).toBeGreaterThan(0.005);
    expect(COHORT_BRIER.toFixed(4)).not.toBe(ALL_MARKETS_BRIER.toFixed(4));
    expect(COHORT_BRIER.toFixed(2)).not.toBe(ALL_MARKETS_BRIER.toFixed(2));
  });

  it("the page renders both surfaces the pairing is read across", () => {
    // A pairing over a missing element is the other way to be vacuous.
    const html = render();
    expect(textOf(html, "calibration-stat-brier-value")).not.toBe("");
    expect(textOf(html, "calibration-brier-bullet")).toContain("Brier score");
  });
});

describe("#7486 — the bullet is the card (arm 1)", () => {
  it("prints the identical string the Brier Score card prints", () => {
    const html = render();
    const card = textOf(html, "calibration-stat-brier-value");
    expect(attrOf(html, "calibration-brier-bullet", "data-brier")).toBe(card);
    expect(textOf(html, "calibration-brier-bullet")).toContain(`Ours is ${card}.`);
  });

  it("that string is the COHORT figure", () => {
    const html = render();
    expect(textOf(html, "calibration-stat-brier-value")).toBe(COHORT_BRIER.toFixed(4));
  });
});

describe("#7486 — the all-markets figure does not reach the bullet (arm 3)", () => {
  it("neither at 4dp nor at the 2dp it used to ship at", () => {
    // Pre-#7486 this bullet read "Ours is 0.11." against a card reading
    // "0.1900" — arm 1 would still fail then, but only because the two happen
    // to differ as strings. This says the wrong POPULATION is absent, which is
    // the thing the reader was misled about.
    const bulletText = textOf(render(), "calibration-brier-bullet");
    expect(bulletText).not.toContain(ALL_MARKETS_BRIER.toFixed(4));
    expect(bulletText).not.toContain(`Ours is ${ALL_MARKETS_BRIER.toFixed(2)}`);
  });
});

describe("#7486 — nothing that was already right moved (arm 4)", () => {
  it("every 4dp figure on the page is still the cohort figure", () => {
    // The card, the "show the math" line and the cohort comparison table all
    // printed `cohortBrier.toFixed(4)` before this fix and print a shared
    // string now. Identical output is the requirement; a fix that moved one of
    // them would be a visible regression, not a repair.
    const figures = fourDpFigures(render());
    expect(figures.length).toBeGreaterThanOrEqual(5);
    expect(new Set(figures)).toEqual(new Set([COHORT_BRIER.toFixed(4)]));
  });
});

describe("#7486 — no unfiltered aggregate is left in scope (arm 5)", () => {
  it("the page computes no page-wide Brier that ignores the cohort", () => {
    // The wording was the symptom. The cause was an unfiltered
    // `brierScore(normalized)` declared at the top of the component with one
    // consumer and no reason a second could not reach for it. Comments are
    // stripped first so that this file's own explanation of the defect, and the
    // page's, do not satisfy or trip the check.
    const src = fs
      .readFileSync(path.join(process.cwd(), "app/calibration/page.tsx"), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    expect(src).not.toMatch(/brierScore\(\s*normalized\s*\)/);
  });
});
