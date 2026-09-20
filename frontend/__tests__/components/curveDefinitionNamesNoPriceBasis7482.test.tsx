/**
 * #7482 — THE BULLET THAT DEFINES THE CURVE NAMES NO PRICE BASIS.
 *
 * ── WHAT A READER SAW, MEASURED ON PRODUCTION ───────────────────────────────
 *
 * `https://bainluck.com/calibration` at 390px, 2026-09-20, payload q271
 * (`generated_at 2026-09-15T11:16:10Z`). "How We Measure This", first bullet:
 *
 *   "What's a calibration curve? We group every resolved prediction by its
 *    OPENING PROBABILITY (0-10%, 10-20%, etc.) and check what percentage
 *    actually came true. …"
 *
 * and the THIRD bullet of the same list, on the same screen:
 *
 *   "Which probability do we use? For events with a known start time (sports
 *    games, tournaments), we use CLOSING LINE PRICES — the last traded price
 *    before the event begins. … For sports, we use vig-removed consensus
 *    closing odds across 20+ sportsbooks."
 *
 * Two bases for one curve, and the wrong one is the sentence that defines what
 * the whole page is showing.
 *
 * The third bullet is the right one. The curve price is
 * `COALESCE(calibration_probability, opening_probability)` — closing preferred,
 * opening as the fallback (ruling 103 / gotcha #144):
 *
 *   `_BOOKMAKER_CHUNK_SQL`   `DISTINCT ON (ee.id, os.bookmaker) … WHERE
 *   backfill_winners.py:9701 os.captured_at < ee.commence_time ORDER BY …
 *                            os.captured_at DESC` — the last snapshot before
 *                            kickoff. All 106,030 `odds_api_bookmaker` outcomes
 *                            of the 747,028 published on q271 are a closing
 *                            line by the query's own construction.
 *
 *   `closing_line_coverage`  has_closing 17,077 / needs_closing 3,068 /
 *   (served payload)         total 20,145 on the events path. Opening is the
 *                            fallback there, not the rule.
 *
 * ── WHAT THIS FILE PINS ─────────────────────────────────────────────────────
 *
 * Not the wording. Three properties:
 *
 *   (1) the definition bullet NAMES NO BASIS — neither "opening probability"
 *       nor "closing line"/"closing price"/"opening price" survives in it. It
 *       is a definition of the grouping, and the basis is not uniform enough
 *       for one clause to state;
 *
 *   (2) it STILL DEFINES THE CURVE — the grouping, the diagonal and the worked
 *       "30% happens 30% of the time" all reach the reader, so gutting or
 *       deleting the bullet is not a passing fix;
 *
 *   (3) the page STILL ANSWERS the question somewhere — "Which probability do
 *       we use?" is still on the page and still names the bases. Arm (1) must
 *       not be satisfiable by deleting the answer from the page as well as the
 *       definition.
 *
 * Non-vacuity — the reason arm (1) cannot pass by finding nothing to match:
 *
 *   a. `PRE_FIX_SENTENCE` is the production text, VERBATIM, snapshotted while
 *      the defect was live (notice 50 — it is never refreshed; its entire
 *      content is the defect). The test applies arm (1)'s own predicate to it
 *      and requires it to FAIL. A predicate that matched nothing would be
 *      caught here rather than passing quietly on the fixed page;
 *
 *   b. arm (1) reads a bullet located by `data-testid`, and `noteMarkup` fails
 *      loudly when that testid is absent — so "delete the attribute" reads as a
 *      broken test, not a pass;
 *
 *   c. arm (3) pins the answer's presence, so the basis vocabulary must still
 *      exist on the page. Arms (1) and (3) cannot both be satisfied by a
 *      find-and-delete over the whole file.
 *
 * Mutation-tested on the committed fix: restoring `PRE_FIX_SENTENCE` verbatim
 * fails (1); shortening the bullet to its heading fails (2); deleting the
 * "Which probability do we use?" bullet fails (3); removing the testid fails
 * (b).
 *
 * ── WHY THERE IS NO CLICK ───────────────────────────────────────────────────
 *
 * `testEnvironment: 'node'` and `renderToStaticMarkup`, so no control can be
 * pressed. Nothing here needs one: the methodology list is cohort-free and
 * renders unconditionally.
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

/**
 * THE DEFECT, VERBATIM, AS PRODUCTION SERVED IT ON 2026-09-20 (payload q271).
 *
 * A frozen control under notice 50: its entire content IS the defect, so it is
 * never re-snapshotted from a fixed tree — a refreshed copy would contain no
 * defect and the strawman check below would pass on nothing. It retires with
 * this file.
 */
const PRE_FIX_SENTENCE =
  "What’s a calibration curve? We group every resolved prediction by its opening " +
  "probability (0-10%, 10-20%, etc.) and check what percentage actually came true. If " +
  "markets are well-calibrated, the points follow the diagonal line — a 30% prediction " +
  "happens 30% of the time.";

/**
 * Every way the page names a price basis. Matched case-insensitively against
 * the definition bullet only; the rest of the page is required to keep them
 * (arm 3).
 */
const BASIS_PHRASES = [
  "opening probability",
  "opening price",
  "closing line",
  "closing price",
  "last traded price",
];

/** The production source keys and outcome counts, 2026-09-20 / q271. */
const PROD_SOURCES = [
  { source: "kalshi", n: 326_909 },
  { source: "polymarket", n: 264_956 },
  { source: "odds_api_bookmaker", n: 106_030 },
  { source: "odds_api", n: 18_440 },
  { source: "odds_api_totals", n: 15_537 },
  { source: "odds_api_spreads", n: 15_120 },
  { source: "datagolf", n: 36 },
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

/**
 * A production-shaped payload. It carries the closing-line coverage split the
 * fix's reasoning rests on (17,077 of 20,145 have a close), so the page under
 * test is the page whose data makes "opening probability" the wrong word.
 */
function makePayload(): CalibrationData {
  const buckets = PROD_SOURCES.flatMap(s => {
    const flag: boolean | null = s.source.startsWith("odds_api") ? null : true;
    const rows = [];
    for (let i = 0; i < 5; i++) rows.push(bucket(s.source, i, flag, Math.round(s.n / 5)));
    return rows;
  });
  return {
    buckets,
    total_markets: 1_004_032,
    total_outcomes: buckets.reduce((t, b) => t + b.n, 0),
    total_winners: 300_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 1.49,
    mce_opening_price: 1.32,
    closing_line_coverage: { has_closing: 17_077, needs_closing: 3_068, total: 20_145 },
    generated_at: "2026-09-20T09:00:00Z",
    date_range: { start: "2021-09-01", end: "2026-09-20" },
    by_source: PROD_SOURCES.map(s => ({ source: s.source, ece: 0.01, mce: 0.02, n: s.n })),
    by_category: [{ category: "golf", ece: 0.01, n: 400_000 }],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

const TESTID = 'data-testid="calibration-curve-definition"';

/**
 * The definition bullet's markup.
 *
 * Sliced from its `data-testid` to the first `</li>` after it. The bullet holds
 * a `<strong>` and no nested list item, so the boundary is exact. Absence is a
 * hard failure, not an empty string: a removed testid must read as a broken
 * guard rather than a silent pass (non-vacuity note b).
 */
function definitionMarkup(html: string): string {
  const at = html.indexOf(TESTID);
  expect(at).toBeGreaterThan(-1);
  const end = html.indexOf("</li>", at);
  expect(end).toBeGreaterThan(at);
  return html.slice(at, end);
}

/**
 * Markup as a READER meets it: tags dropped, entities resolved.
 *
 * Deliberately not a general HTML-to-text helper — a `.replace` chain over
 * arbitrary markup is two HIGH CodeQL alerts
 * (`js/incomplete-multi-character-sanitization`). Tags are removed once,
 * non-greedily, and only the entities this page emits are resolved.
 */
function toText(markup: string): string {
  return markup
    .split(/<[^>]*>/)
    .join("")
    .replace(/&mdash;/g, "—")
    .replace(/&rsquo;/g, "’")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** Arm (1)'s predicate, isolated so the frozen control can be run through it. */
function basisPhrasesIn(text: string): string[] {
  const haystack = text.toLowerCase();
  return BASIS_PHRASES.filter(p => haystack.includes(p));
}

describe("#7482 — the curve definition names no price basis", () => {
  test("the frozen control reproduces the defect: the predicate FLAGS the pre-fix sentence", () => {
    // Non-vacuity arm (a). Without this, arm (1) could pass because the
    // predicate matches nothing anywhere, and would prove nothing about the
    // fix. The production sentence must trip it, on the phrase it shipped.
    expect(basisPhrasesIn(PRE_FIX_SENTENCE)).toContain("opening probability");
  });

  test("the definition bullet names no price basis", () => {
    // Arm (1).
    const text = toText(definitionMarkup(render()));
    expect(basisPhrasesIn(text)).toEqual([]);
  });

  test("the definition still defines the curve", () => {
    // Arm (2): gutting or deleting the bullet is not a passing fix.
    const text = toText(definitionMarkup(render()));
    expect(text).toContain("What’s a calibration curve?");
    expect(text).toContain("We group every resolved prediction by");
    expect(text).toContain("the points follow the diagonal line");
    expect(text).toContain("a 30% prediction happens 30% of the time");
  });

  test("the page still answers which probability it uses", () => {
    // Arm (3): arm (1) must not be satisfiable by deleting the answer too. The
    // bullet that OWNS the basis question keeps it, so a reader who wants the
    // basis is two bullets away rather than nowhere.
    const html = render();
    const page = toText(html);
    expect(page).toContain("Which probability do we use?");
    expect(page).toContain("closing line prices");
    expect(page).toContain("opening price after initial trading settles");
  });

  test("the basis vocabulary lives OUTSIDE the definition, not nowhere", () => {
    // Arms (1) and (3) held together: the phrases the definition may not use
    // are present on the page, just not in the sentence that defines the curve.
    // A find-and-delete over the file fails this.
    const html = render();
    const definition = toText(definitionMarkup(html));
    const rest = toText(html).replace(definition, "");
    expect(basisPhrasesIn(definition)).toEqual([]);
    expect(basisPhrasesIn(rest).length).toBeGreaterThan(0);
  });
});
