/**
 * #7472 — THE PRICE-BASIS NOTE MAKES A METHOD STATEMENT AND STATES NO QUANTITY.
 *
 * ── WHAT A READER SAW, MEASURED ON PRODUCTION ───────────────────────────────
 *
 * `https://bainluck.com/calibration` at 390px, 2026-09-20, payload q271
 * (`generated_at 2026-09-15T11:16:10Z`). "How We Measure This", the bullet
 * headed "Not every row is a closing price, and we say which":
 *
 *   "… Sportsbook rows use the closing line where one exists and fall back to
 *    the opening price where it does not — 17,077 of 20,145 sportsbook rows
 *    have a close (3,068 do not). The two bases do not measure the same, and we
 *    publish both figures rather than one blended number: 1.5pp on closing-line
 *    rows against 1.3pp on opening-price rows. A closing line is the stronger
 *    test, so the gap is the cost of the fallback, not a finding about the
 *    sportsbooks."
 *
 * Three quantities, none of them about sportsbook rows.
 *
 *   17,077 / 20,145 / 3,068   `closing_line_coverage`, which counts `events`
 *                             rows — completed or closed, both scores set, NO
 *                             source filter. Every graded game. The same screen
 *                             sizes the sportsbook population at 155,127
 *                             outcomes in three other places.
 *
 *   1.5pp vs 1.3pp            `mce_closing_line` / `mce_opening_price`, which
 *                             are `_cohort_mce(buckets, true/false)` — a filter
 *                             on `price_moved`, i.e. whether the price left its
 *                             opening line, not which basis was read.
 *                             Recomputed off the served payload:
 *
 *                               price_moved=true   293,900 rows   1.49pp
 *                               price_moved=false  298,001 rows   1.32pp
 *                               price_moved=null   155,127 rows   1.53pp
 *
 *                             The null rows ARE the sportsbook rows. All
 *                             155,127 of them sit outside both published
 *                             figures, so the pair cannot be the closing-vs-
 *                             opening comparison the sentence made of it.
 *
 *   "the cost of the fallback"  reads a cause into that same pair — the reading
 *                             #6176 withdrew, and which "Does a price that
 *                             moves predict better?" disclaims four cards
 *                             higher ("not evidence about what trading does to
 *                             a forecast").
 *
 * ── WHAT THIS FILE PINS ─────────────────────────────────────────────────────
 *
 * Not the wording. Two properties of the rendered bullet:
 *
 *   (1) it STATES NO QUANTITY. The payload carries no per-basis error and no
 *       sportsbook-row closing coverage, so there is no corrected number to
 *       print and notice 34 / D102 leaves the space empty. Asserted twice: no
 *       digit survives in the note at all, AND none of the fixture's own
 *       `closing_line_coverage` / MCE values appear in it — read off the
 *       fixture, so the specific arm cannot go vacuous when those values move.
 *
 *   (2) its GATE is the population it speaks about. It renders exactly when the
 *       payload has sportsbook rows (`price_moved === null`, the page's
 *       `partition.notApplicableN`) and not otherwise — independent of
 *       `closing_line_coverage`, the field it used to be gated on and no longer
 *       reads.
 *
 * Three things keep it non-vacuous:
 *
 *   a. the production-shaped fixture REPRODUCES the defect — it carries all
 *      five numbers the pre-fix bullet printed, at their production values, so
 *      a revert of the prose fails arm (1) rather than finding nothing to
 *      match;
 *   b. `noCoverageField` and `noSportsbookRows` pull the OLD gate and the NEW
 *      gate apart — a payload with sportsbook rows and no coverage field, and
 *      one with a coverage field and no sportsbook rows. Under the old gate the
 *      first renders nothing and the second renders the bullet; under the new
 *      one it is the other way round. A single fixture could not tell them
 *      apart;
 *   c. the METHOD statement is asserted present, so "delete the bullet" is not
 *      a passing fix.
 *
 * Mutation-tested on the committed fix (see the issue): restoring each of the
 * three quantities fails arm (1); restoring the old gate fails arm (2) on both
 * of its fixtures; deleting the bullet fails (c).
 *
 * ── WHY THERE IS NO CLICK ───────────────────────────────────────────────────
 *
 * `testEnvironment: 'node'` and `renderToStaticMarkup`, so no control can be
 * pressed. Nothing here needs one: the bullet is cohort-free and every arm is
 * reached by shaping the payload.
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

/** The production values of every number the pre-fix bullet printed. */
const PROD_COVERAGE = { has_closing: 17_077, needs_closing: 3_068, total: 20_145 };
const PROD_MCE_CLOSING = 1.49;
const PROD_MCE_OPENING = 1.32;

/**
 * Production source keys and outcome counts, 2026-09-20. Per SOURCE, because
 * that is what the payload carries — the `price_moved` flag rides on the
 * bucket, and it is the flag, not the key, that the gate reads.
 */
const PROD_SOURCES = [
  { source: "kalshi", n: 326_909, untraded: 112_287 },
  { source: "polymarket", n: 264_956, untraded: 185_678 },
  { source: "odds_api_bookmaker", n: 106_030, untraded: 0 },
  { source: "odds_api", n: 18_440, untraded: 0 },
  { source: "odds_api_totals", n: 15_537, untraded: 0 },
  { source: "odds_api_spreads", n: 15_120, untraded: 0 },
  { source: "datagolf", n: 36, untraded: 36 },
];

function bucket(source: string, idx: number, priceMoved: boolean | null, n: number) {
  const p = 0.05 + idx * 0.1;
  return {
    bucket_idx: idx,
    source,
    category: "golf",
    price_moved: priceMoved,
    n,
    winners: Math.round(n * p),
    avg_prob: p,
    sum_prob: n * p,
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

interface Shape {
  /** Drop `closing_line_coverage` — the field the bullet used to be gated on. */
  noCoverageField?: boolean;
  /**
   * Give the Odds API rows a real `price_moved` flag, so the payload has NO
   * `null` row and therefore no sportsbook rows in the page's partition.
   */
  noSportsbookRows?: boolean;
}

function makePayload(shape: Shape = {}): CalibrationData {
  const buckets = PROD_SOURCES.flatMap(s => {
    const traded = s.n - s.untraded;
    // `null` is the sportsbook flag in production; the page's partition counts
    // exactly these into `notApplicableN`.
    const flag: boolean | null = s.source.startsWith("odds_api")
      ? shape.noSportsbookRows
        ? true
        : null
      : true;
    const rows = [];
    for (let i = 0; i < 5; i++) {
      if (traded > 0) rows.push(bucket(s.source, i, flag, Math.round(traded / 5)));
      if (s.untraded > 0) rows.push(bucket(s.source, i, false, Math.round(s.untraded / 5)));
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
    mce_closing_line: PROD_MCE_CLOSING,
    mce_opening_price: PROD_MCE_OPENING,
    ...(shape.noCoverageField ? {} : { closing_line_coverage: PROD_COVERAGE }),
    generated_at: "2026-09-20T09:00:00Z",
    date_range: { start: "2021-09-01", end: "2026-09-20" },
    by_source: PROD_SOURCES.map(s => ({ source: s.source, ece: 0.01, mce: 0.02, n: s.n })),
    by_category: [{ category: "golf", ece: 0.01, n: 400_000 }],
  } as unknown as CalibrationData;
}

function render(shape: Shape = {}): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload(shape);
  return renderToStaticMarkup(<CalibrationPage />);
}

const TESTID = 'data-testid="calibration-price-basis-note"';

/**
 * The bullet's own markup, or null when it is not on the page.
 *
 * Sliced from its `data-testid` to the first `</li>` after it. The bullet
 * contains `<strong>` and `<em>` and no nested list item, so that boundary is
 * exact; a nested `<li>` would make this read too far and is worth failing on.
 */
function noteMarkup(html: string): string | null {
  const at = html.indexOf(TESTID);
  if (at === -1) return null;
  const end = html.indexOf("</li>", at);
  expect(end).toBeGreaterThan(at);
  return html.slice(at, end);
}

/**
 * The bullet as a READER meets it: tags dropped, entities resolved.
 *
 * Deliberately not a general HTML-to-text helper — a `.replace` chain over
 * arbitrary markup is two HIGH CodeQL alerts
 * (`js/incomplete-multi-character-sanitization`) and this input is our own
 * render of one known element. Tags are removed once, non-greedily, and only
 * the entities this bullet can contain are resolved.
 */
function noteText(html: string): string {
  const markup = noteMarkup(html);
  if (markup === null) return "";
  return markup
    .split(/<[^>]*>/)
    .join("")
    .replace(/&mdash;/g, "—")
    .replace(/&rsquo;/g, "’")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

describe("#7472 — the price-basis note states no quantity", () => {
  test("the fixture reproduces the defect: every pre-fix number is in the payload", () => {
    // Arm (a). Without this the "no digits" assertion could pass on a payload
    // that simply had nothing to print, and would prove nothing about the fix.
    const payload = makePayload();
    expect(payload.closing_line_coverage).toEqual(PROD_COVERAGE);
    expect(payload.mce_closing_line).toBe(PROD_MCE_CLOSING);
    expect(payload.mce_opening_price).toBe(PROD_MCE_OPENING);
  });

  test("the method statement still reaches the reader", () => {
    // Arm (c): deleting the bullet is not a passing fix. The bullet exists to
    // say the basis is not uniform; that sentence is true and stays.
    const text = noteText(render());
    expect(text).toContain("Not every row is a closing price");
    expect(text).toContain("Kalshi and Polymarket are measured on their closing line");
    expect(text).toMatch(/[Ss]portsbook\s+rows use the closing line/);
    expect(text).toContain("fall back to the opening price");
  });

  test("no digit survives in the bullet", () => {
    // Arm (1), general form. The payload carries no honest quantity for this
    // sentence, so any digit here is a number describing some other
    // population — which is the whole of #7472.
    const text = noteText(render());
    expect(text.length).toBeGreaterThan(80);
    expect(text).not.toMatch(/\d/);
  });

  test("none of the payload's own coverage or MCE values appear in the bullet", () => {
    // Arm (1), specific form, read OFF THE FIXTURE so it tracks the values
    // rather than pinning today's spellings.
    const html = render();
    const text = noteText(html);
    const markup = noteMarkup(html) ?? "";

    const banned = [
      ...Object.values(PROD_COVERAGE).flatMap(v => [String(v), v.toLocaleString("en-US")]),
      // As the bullet used to print them: `toFixed(1)`.
      PROD_MCE_CLOSING.toFixed(1),
      PROD_MCE_OPENING.toFixed(1),
      String(PROD_MCE_CLOSING),
      String(PROD_MCE_OPENING),
    ];
    for (const value of banned) {
      expect(text).not.toContain(value);
      // Not in an attribute either: `data-has-closing` carried the same event
      // count under the same wrong noun, and a hook is not a hiding place.
      expect(markup).not.toContain(value);
    }
  });

  test("the withdrawn causal reading does not come back", () => {
    // #6176 removed the verdict from this number pair. The bullet was still
    // narrating it ("the gap is the cost of the fallback").
    const text = noteText(render());
    expect(text).not.toMatch(/cost of the fallback/i);
    expect(text).not.toMatch(/\bthe gap\b/i);
    expect(text).not.toMatch(/blended number/i);
  });

  describe("the gate is the population the bullet speaks about", () => {
    test("renders when the payload has sportsbook rows but no coverage field", () => {
      // Arm (b), half one. Under the OLD gate this renders nothing.
      const html = render({ noCoverageField: true });
      expect(html).toContain(TESTID);
      expect(noteText(html)).toContain("Not every row is a closing price");
    });

    test("absent when the payload has a coverage field but no sportsbook rows", () => {
      // Arm (b), half two. Under the OLD gate this renders the bullet — a
      // sentence about sportsbook rows on a page that has none.
      const html = render({ noSportsbookRows: true });
      expect(html).not.toContain(TESTID);
      expect(noteMarkup(html)).toBeNull();
    });

    test("the two gate fixtures really do disagree on both fields", () => {
      // Guards the guard: if `noSportsbookRows` stopped removing the null rows,
      // the pair above would both be the same case and pass for free.
      const withRows = makePayload({ noCoverageField: true });
      const withoutRows = makePayload({ noSportsbookRows: true });
      expect(withRows.closing_line_coverage).toBeUndefined();
      expect(withRows.buckets.some(b => b.price_moved === null)).toBe(true);
      expect(withoutRows.closing_line_coverage).toEqual(PROD_COVERAGE);
      expect(withoutRows.buckets.some(b => b.price_moved === null)).toBe(false);
    });
  });
});
