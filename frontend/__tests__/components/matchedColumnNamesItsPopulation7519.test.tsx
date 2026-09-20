/**
 * #7519 — the matched-bucket column headed "Traded" says which rows it holds,
 * and the section reconciles them to the traded total the page publishes.
 *
 * Shopped on production at 390px, 2026-09-20 ~14:50Z, DEFAULT (traded) cohort.
 * Under "Does a price that moves predict better?", summing the two columns over
 * the ten buckets as they render:
 *
 *   Traded column      293,900
 *   Untraded column    298,001
 *
 * ~1,300px below, in the same section, the page's own reconciliation note
 * (`calibration-activity-partition`) reads, verbatim:
 *
 *   "Sportsbook lines (155,127 outcomes) carry no price-moved flag and need
 *    none — a sportsbook moves its line with money — so they count as traded:
 *    293,900 price-moved + 155,127 sportsbook = 449,027 traded, plus 298,001
 *    untraded = 747,028 resolved outcomes."
 *
 * So the page publishes 449,027 traded and heads a column "Traded" over 293,900
 * of them. 155,127 outcomes — 35% of the page's own traded population — are in
 * NEITHER column, and nothing on the visible surface said so. Confirmed against
 * `GET /api/calibration` rather than inferred from the render: summing
 * `buckets[].n` by `price_moved` gives true 293,900 / false 298,001 / null
 * 155,127 (all four `odds_api*` shapes), total 747,028 = `total_outcomes`. The
 * rendered column sums match `true`/`false` exactly, so this is the partition.
 *
 * ═══ WHAT IS *NOT* THE DEFECT, SO NO FIX GOES THERE ═══
 *
 * UX-P080 item 3 (Alex, round 2) ruled that sportsbook lines are traded BY
 * CONSTRUCTION — a sportsbook moves its line with money — and the 449,027
 * default cohort is correct. #7335 then renamed these columns from "Price
 * moved"/"Price unchanged" to the cohort nouns so the page would stop naming
 * two cohorts three ways (UX-P075 item (c), Alex 2026-08-13). Both are right.
 * What they left behind is that this section is the ONE place where
 * `price_moved` is the SUBJECT rather than a filter, so the shared noun names a
 * population its two columns do not hold. The fix states the population; it
 * does not re-split the vocabulary the rename deliberately joined, and this
 * file must not be satisfied by a revert to "Price moved".
 *
 * ═══ WHAT THIS FILE GUARDS, AND WHY IN THIS SHAPE ═══
 *
 *   1. POLARITY — the count called "in neither column" is `notApplicableN`.
 *      The fixture's four numbers (moved, unchanged, not-applicable, and the
 *      traded total) are pairwise distinct AND asserted distinct before
 *      anything is read, so substituting any one for any other is caught. This
 *      is the arm that matters: a caption naming `unchangedN` reads perfectly
 *      and is the exact inversion of the truth.
 *   2. THE RECONCILIATION IS A RECONCILIATION — it states the page's traded
 *      total (moved + not-applicable) *and* the column's own total, because the
 *      reader's question is not "how many are missing" but "is this the Traded
 *      I was reading about two screens up". A sentence carrying only one of the
 *      two numbers cannot answer it, and is failed here.
 *   3. CONDITIONAL, NOT FURNITURE — a payload with no flagless rows gets no
 *      note, because then the two columns ARE the whole traded population.
 *      Asserted as `null`, and asserted absent from the rendered page, so the
 *      disclosure cannot degrade into boilerplate that is true of nothing.
 *   4. LOCATION (notice 34 / D102) — the one-sentence caption is body copy,
 *      because it is what a reader must know to read the column at all; the
 *      arithmetic is a method note and sits inside the section's existing
 *      "What 'traded' means here" fold. Both halves asserted, on the rendered
 *      markup, against the `<details>` boundary — a caption that drifts INTO
 *      the fold silently restores the defect for every reader who never taps.
 *   5. THE NUMBERS ARE THE PAYLOAD'S — read off the frozen production fixture
 *      the rest of the suite grades against, never hardcoded in the copy. A
 *      literal in `describeActivityScope` would be right today and wrong at the
 *      next rebuild, which is how the 1,000-bar defect in #7515 happened.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import {
  describeActivityScope,
  partitionByActivity,
} from "@/lib/calibrationCohort";
import { PROD_BUCKETS } from "../lib/calibrationProdFixture";

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
 * Four numbers that cannot be confused for one another.
 *
 * MOVED + NOT_APPLICABLE = 48 is the page's traded total; MOVED + UNCHANGED =
 * 33 is the pair a plausible mutation reaches for instead. 11 / 22 / 37 / 48 /
 * 33 are pairwise distinct, which arm 1 asserts rather than assumes — the
 * first draft of this fixture used 33 for the flagless rows and 11+22 for the
 * wrong sum, and those collide, so a real mutation would have survived.
 */
const MOVED = 11;
const UNCHANGED = 22;
const NOT_APPLICABLE = 37;
const TRADED_TOTAL = MOVED + NOT_APPLICABLE; // 48
const WRONG_SUM = MOVED + UNCHANGED; // 33

function bucket(source: string, idx: number, n: number, priceMoved: boolean | null) {
  return {
    bucket_idx: idx,
    source,
    category: "baseball",
    price_moved: priceMoved,
    n,
    winners: Math.round(n * 0.5),
    avg_prob: 0.5,
    sum_prob: 0.5 * n,
    sum_sq_err: n * 0.25,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

/**
 * Both the moved and the unchanged side need outcomes in at least two buckets,
 * or the page falls back to the single-cohort curve and the whole section —
 * caption included — never renders. Splitting each side across two bucket
 * indices keeps the section on screen without changing any of the four counts.
 */
function buckets(notApplicableN: number) {
  const out = [
    bucket("kalshi", 3, MOVED - 5, true),
    bucket("kalshi", 6, 5, true),
    bucket("polymarket", 3, UNCHANGED - 10, false),
    bucket("polymarket", 6, 10, false),
  ];
  if (notApplicableN > 0) out.push(bucket("odds_api", 3, notApplicableN, null));
  return out;
}

function payload(notApplicableN: number): CalibrationData {
  const rows = buckets(notApplicableN);
  const total = rows.reduce((s, b) => s + b.n, 0);
  return {
    buckets: rows,
    total_markets: total,
    total_outcomes: total,
    total_winners: rows.reduce((s, b) => s + b.winners, 0),
    mce_ci_lower: 0.33,
    mce_ci_upper: 1.19,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-20T07:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-20" },
    by_source: [
      { source: "kalshi", ece: 1.0, mce: 1.3, n: MOVED },
      { source: "polymarket", ece: 0.9, mce: 1.1, n: UNCHANGED },
      { source: "odds_api", ece: 1.5, mce: 1.6, n: notApplicableN },
    ],
    by_category: [{ category: "baseball", ece: 0.9, n: total }],
  } as unknown as CalibrationData;
}

function render(notApplicableN: number): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload =
    payload(notApplicableN);
  return renderToStaticMarkup(<CalibrationPage />);
}

const SCOPE = describeActivityScope({
  movedN: MOVED,
  unchangedN: UNCHANGED,
  notApplicableN: NOT_APPLICABLE,
});

/* ─────────────────────────────── arm 1 ─────────────────────────────── */

describe("the count named as outside both columns is the flagless one", () => {
  test("the fixture's four numbers are pairwise distinct", () => {
    // Arm 1 is worthless if two of them collide: a swapped term would print the
    // same string and every assertion below would pass against broken code.
    const all = [MOVED, UNCHANGED, NOT_APPLICABLE, TRADED_TOTAL, WRONG_SUM];
    expect(new Set(all).size).toBe(all.length);
  });

  test("the caption names the not-applicable count and no other", () => {
    expect(SCOPE).not.toBeNull();
    const caption = SCOPE!.caption;
    expect(caption).toContain(String(NOT_APPLICABLE));
    // The inversion this guard exists for: `unchangedN` is the OTHER side of
    // the comparison, which IS in a column. Naming it reads perfectly.
    expect(caption).not.toContain(String(UNCHANGED));
    expect(caption).not.toContain(String(MOVED));
  });

  test("the caption says those rows are in neither column, not that they are untraded", () => {
    // `lib/calibrationCohort.ts` bans, on the emitted strings, any word that
    // asserts activity rather than naming a cohort. The flagless rows are
    // traded under UX-P080 item 3; a caption that implies otherwise trades one
    // wrong claim for a worse one.
    expect(SCOPE!.caption.toLowerCase()).toContain("neither");
    expect(SCOPE!.caption.toLowerCase()).not.toContain("untraded");
    expect(SCOPE!.caption.toLowerCase()).not.toContain("thinly traded");
    expect(SCOPE!.caption.toLowerCase()).not.toContain("well-traded");
  });
});

/* ─────────────────────────────── arm 2 ─────────────────────────────── */

describe("the reconciliation puts the column's total beside the page's", () => {
  test("it states all three parts of the partition", () => {
    for (const n of [MOVED, UNCHANGED, NOT_APPLICABLE]) {
      expect(SCOPE!.reconciliation).toContain(String(n));
    }
  });

  test("it states the traded total the rest of the page publishes", () => {
    // Without this number the note explains the gap and never names the thing
    // the reader is holding in their head from two screens up.
    expect(SCOPE!.reconciliation).toContain(String(TRADED_TOTAL));
  });

  test("it does not reach for moved + unchanged, which is a different sum", () => {
    // The plausible mutation: `movedN + unchangedN` is the table's own total and
    // is NOT what the page calls traded.
    expect(SCOPE!.reconciliation).not.toContain(String(WRONG_SUM));
  });

  test("the totals are formatted the way the rest of the page formats counts", () => {
    const big = describeActivityScope({
      movedN: 293_900,
      unchangedN: 298_001,
      notApplicableN: 155_127,
    })!;
    expect(big.caption).toContain("155,127");
    expect(big.reconciliation).toContain("293,900");
    expect(big.reconciliation).toContain("298,001");
    expect(big.reconciliation).toContain("449,027");
  });
});

/* ─────────────────────────────── arm 3 ─────────────────────────────── */

describe("a payload with nothing outside the two columns gets no note", () => {
  test("describeActivityScope returns null", () => {
    expect(
      describeActivityScope({ movedN: MOVED, unchangedN: UNCHANGED, notApplicableN: 0 })
    ).toBeNull();
  });

  test("neither half renders on such a payload", () => {
    const html = render(0);
    // The section itself must still be there, or this arm passes for the wrong
    // reason — an absent section trivially contains no note.
    expect(html).toContain('data-testid="calibration-activity-section"');
    expect(html).not.toContain('data-testid="calibration-activity-scope-note"');
    expect(html).not.toContain('data-testid="calibration-activity-scope-reconciliation"');
  });
});

/* ─────────────────────────────── arm 4 ─────────────────────────────── */

describe("the caption is body copy and the arithmetic is folded", () => {
  const HTML = render(NOT_APPLICABLE);

  test("both halves render", () => {
    expect(HTML).toContain('data-testid="calibration-activity-scope-note"');
    expect(HTML).toContain('data-testid="calibration-activity-scope-reconciliation"');
  });

  test("the caption is NOT inside a disclosure", () => {
    // The whole point. A reader who never taps must not be left reading
    // "Traded" as the page's 449,027 cohort.
    const section = HTML.indexOf('data-testid="calibration-activity-section"');
    const note = HTML.indexOf('data-testid="calibration-activity-scope-note"');
    expect(section).toBeGreaterThan(-1);
    expect(note).toBeGreaterThan(section);
    // No disclosure may OPEN between the section and the caption without
    // closing again before it.
    const between = HTML.slice(section, note);
    const opens = between.split("<details").length - 1;
    const closes = between.split("</details>").length - 1;
    expect(opens).toBe(closes);
  });

  test("the arithmetic IS inside a disclosure", () => {
    const recon = HTML.indexOf('data-testid="calibration-activity-scope-reconciliation"');
    const open = HTML.lastIndexOf("<details", recon);
    const close = HTML.indexOf("</details>", recon);
    expect(open).toBeGreaterThan(-1);
    expect(close).toBeGreaterThan(recon);
    // Nothing may close that disclosure between its start and the note, or the
    // note is back in the body while `lastIndexOf` still finds an earlier open.
    expect(HTML.slice(open, recon)).not.toContain("</details>");
  });

  test("it is folded beside the proxy note, not into a fold of its own", () => {
    // The section already has a fold whose label is the reader's question. A
    // second fold under the same heading is the shape notice 34 was written
    // against — more taps, not fewer.
    const recon = HTML.indexOf('data-testid="calibration-activity-scope-reconciliation"');
    const open = HTML.lastIndexOf("<details", recon);
    expect(HTML.slice(open, recon)).toContain("receive trading volume for most of these markets");
  });

  test("the counts travel as attributes, so a rail reads them without the prose", () => {
    const recon = HTML.indexOf('data-testid="calibration-activity-scope-reconciliation"');
    const tag = HTML.slice(recon, HTML.indexOf(">", recon));
    expect(tag).toContain(`data-moved-n="${MOVED}"`);
    expect(tag).toContain(`data-unchanged-n="${UNCHANGED}"`);
    expect(tag).toContain(`data-not-applicable-n="${NOT_APPLICABLE}"`);
  });
});

/* ─────────────────────────────── arm 5 ─────────────────────────────── */

describe("the numbers come from the payload", () => {
  test("the frozen production fixture drives them, with no literal in the copy", () => {
    const partition = partitionByActivity(PROD_BUCKETS);
    const scope = describeActivityScope(partition)!;
    expect(scope).not.toBeNull();
    // Whatever the frozen payload says, the strings say — so a rebuild that
    // moves the partition moves the copy with it.
    expect(scope.caption).toContain(partition.notApplicableN.toLocaleString("en-US"));
    expect(scope.reconciliation).toContain(partition.movedN.toLocaleString("en-US"));
    expect(scope.reconciliation).toContain(partition.unchangedN.toLocaleString("en-US"));
    expect(scope.reconciliation).toContain(
      (partition.movedN + partition.notApplicableN).toLocaleString("en-US")
    );
    // And they are NOT the synthetic fixture's numbers, which is what a
    // hardcoded literal would leave behind.
    expect(scope.caption).not.toContain(String(NOT_APPLICABLE));
  });
});
