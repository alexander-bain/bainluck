/**
 * #7718 — THE METHODOLOGY DOES NOT CALL A PER-SPORTSBOOK CURVE A CONSENSUS.
 *
 * ── WHAT A READER SAW, MEASURED ON PRODUCTION ───────────────────────────────
 *
 * `https://bainluck.com/calibration` at 390px, 2026-09-21 06:05Z, payload q271
 * (`generated_at 2026-09-15T11:16:10Z`). "How We Measure This", the bullet that
 * answers where the number comes from:
 *
 *   "Which probability do we use? … For sports, we use vig-removed CONSENSUS
 *    closing odds across 20+ sportsbooks."
 *
 * and, on the same screen, the same curve named three times by the server's own
 * `source_labels.odds_api_bookmaker.label` (`declared: true`):
 *
 *   hero SOURCES card    "Sportsbooks (Odds API: PER-SPORTSBOOK, Moneylines,
 *                         Totals, Spreads)"
 *   Source Comparison    "Sportsbooks (Odds API)" / "PER-SPORTSBOOK · Moneylines
 *                         · Totals · Spreads"
 *   shape breakout       "PER-SPORTSBOOK (Odds API)" — its own curve, n=106,030
 *
 * A consensus is ONE prediction per game. Per-sportsbook is the same game
 * counted once per sportsbook — 106,030 of the 155,127 outcomes in the
 * Sportsbooks row, 68% — which is a different meaning for `n` and a reason the
 * errors inside a bucket correlate. The page claimed the first and did the
 * second.
 *
 * `_BOOKMAKER_CHUNK_SQL`, `backend/app/tasks/backfill_winners.py:10004`:
 *
 *   SELECT DISTINCT ON (ee.id, os.bookmaker) …
 *     FROM … JOIN odds_snapshots os ON os.event_id = ee.id
 *    WHERE os.captured_at < ee.commence_time
 *    ORDER BY ee.id, os.bookmaker, os.captured_at DESC
 *
 * One row per (event, sportsbook), then `COUNT(*)`. No averaging step exists.
 * "vig-removed" is TRUE and is deliberately NOT pinned against here — the same
 * query devigs each sportsbook on its own two-way, `home/(home+away)`. Only the
 * relationship was false.
 *
 * ── WHAT THIS FILE PINS ─────────────────────────────────────────────────────
 *
 * Not the wording. Four properties:
 *
 *   (1) the price-basis bullet does not tell a reader the sportsbook prices are
 *       a CONSENSUS — no consensus/averaged/blended/aggregated claim survives
 *       in it;
 *
 *   (2) it still says the sportsbooks are measured SEPARATELY, so arm (1) is not
 *       satisfiable by deleting the sportsbook clause and saying nothing;
 *
 *   (3) it still answers its own question and keeps #7482's closing-line basis,
 *       so arm (1) is not satisfiable by gutting the bullet;
 *
 *   (4) THE JOIN THAT MAKES THIS A CLASS AND NOT A TYPO: while the served
 *       payload declares `odds_api_bookmaker` as "Per-sportsbook", the page may
 *       not claim a consensus for it. Arms (1)-(3) pin today's sentence; (4)
 *       pins the CONTRADICTION, and is what fails if a later edit reintroduces
 *       the claim in words this file's phrase list never anticipated.
 *
 * Non-vacuity — why none of these can pass by matching nothing:
 *
 *   a. `PRE_FIX_SENTENCE` is the production text, VERBATIM, snapshotted while
 *      the defect was live (notice 50 — never refreshed; its entire content IS
 *      the defect, and it retires with this file). Arm (1)'s own predicate is
 *      applied to it and REQUIRED to flag it. A predicate that matched nothing
 *      would be caught here rather than passing quietly on the fixed page;
 *   b. the bullet is located by `data-testid`, and `basisMarkup` fails loudly
 *      when it is absent — "delete the attribute" reads as a broken test;
 *   c. arm (4) asserts the label side is PRESENT before it draws any
 *      conclusion, so it cannot pass by having no antecedent. THE PREMISE IS
 *      READ FROM THE RIGHT PLACE, and the first draft of this file read it
 *      from the wrong one: it asserted "Per-sportsbook" appeared in the
 *      rendered page while varying `source_labels` in the payload — and the
 *      mutation PASSED, because `makeSourceLabeller` gives the LOCAL map
 *      precedence over the server's `label` by design (CAL-P1025 / #3357), so
 *      the string was arriving from `calibrationProviders.ts` no matter what
 *      the payload said. A premise that cannot vary is not a premise. It now
 *      reads `sourceLabel("odds_api_bookmaker")` — the function that actually
 *      decides the word the reader sees.
 *
 * Mutation-tested on the committed fix: restoring `PRE_FIX_SENTENCE` verbatim
 * fails (1), (2) and (4); deleting the count clause fails (2); removing the
 * testid fails (b) on three arms at once; renaming the local label away from
 * "Per-sportsbook" fails (c) instead of passing.
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
// Arm (4)'s premise. The page's own labeller, not the payload field — see
// non-vacuity note (c).
import { sourceLabel } from "@/lib/calibrationProviders";

/**
 * THE DEFECT, VERBATIM, AS PRODUCTION SERVED IT ON 2026-09-21 (payload q271).
 *
 * A frozen control under notice 50: its entire content IS the defect, so it is
 * never re-snapshotted from a fixed tree — a refreshed copy would contain no
 * defect and the strawman check below would pass on nothing. It retires with
 * this file.
 */
const PRE_FIX_SENTENCE =
  "For sports, we use vig-removed consensus closing odds across 20+ sportsbooks.";

/**
 * Every way the page could tell a reader the sportsbook rows are one blended
 * number. Matched case-insensitively against the price-basis bullet only.
 *
 * `vig-removed` is deliberately ABSENT: it is true of this curve (each
 * sportsbook is devigged on its own two-way) and banning it would make the
 * honest sentence unwritable.
 */
const CONSENSUS_PHRASES = [
  "consensus",
  "averaged across",
  "average across",
  "blended line",
  "aggregated across",
  "combined line",
];

/** The production source keys and outcome counts, 2026-09-21 / q271. */
const PROD_SOURCES = [
  { source: "kalshi", n: 326_909 },
  { source: "polymarket", n: 264_956 },
  { source: "odds_api_bookmaker", n: 106_030 },
  { source: "odds_api", n: 18_440 },
  { source: "odds_api_totals", n: 15_537 },
  { source: "odds_api_spreads", n: 15_120 },
  { source: "datagolf", n: 36 },
];

/**
 * The served labels, as production declares them.
 *
 * Carried so the page under test is shaped like production, NOT because arm
 * (4) reads its premise here — it does not, and note (c) records why: the
 * local map wins over this field, so varying it changes nothing a reader sees.
 */
const PROD_SOURCE_LABELS = {
  kalshi: { label: "Kalshi", declared: true },
  polymarket: { label: "Polymarket", declared: true },
  odds_api_bookmaker: { label: "Per-sportsbook (Odds API)", declared: true },
  odds_api: { label: "Moneylines (Odds API)", declared: true },
  odds_api_totals: { label: "Totals (Odds API)", declared: true },
  odds_api_spreads: { label: "Spreads (Odds API)", declared: true },
  datagolf: { label: "DataGolf", declared: true },
};

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
 * A production-shaped payload carrying the declared `source_labels` arm (4)
 * reads, so the page under test is the page whose own data makes "consensus"
 * the wrong word.
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
    generated_at: "2026-09-15T11:16:10Z",
    date_range: { start: "2021-09-01", end: "2026-09-21" },
    source_labels: PROD_SOURCE_LABELS,
    by_source: PROD_SOURCES.map(s => ({ source: s.source, ece: 0.01, mce: 0.02, n: s.n })),
    by_category: [{ category: "golf", ece: 0.01, n: 400_000 }],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

const TESTID = 'data-testid="calibration-price-basis-answer"';

/**
 * The price-basis bullet's markup.
 *
 * Sliced from its `data-testid` to the first `</li>` after it. The bullet holds
 * `<strong>` and `<a>` and no nested list item, so the boundary is exact.
 * Absence is a hard failure, not an empty string: a removed testid must read as
 * a broken guard rather than a silent pass (non-vacuity note b).
 */
function basisMarkup(html: string): string {
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

/**
 * The page's rendered TEXT NODES, one string per node.
 *
 * Arm (4) needs a unit of text smaller than the page, and a sentence is not
 * available: `toText` strips tags without inserting anything, so
 * "…measured separately.SourceOutcomesECE…" arrives with no space after the
 * period and `split(/(?<=[.!?])\s+/)` returns the whole page as one "sentence".
 * That is not a tuning problem — there is genuinely no sentence boundary in the
 * markup to find, because the boundaries are ELEMENTS.
 *
 * So the unit is the element's own text. It separates the two things arm (4)
 * must tell apart — the price-basis clause, and the "Academic consensus range
 * (Arrow et al. 2008)" benchmark label — into different nodes, which is exactly
 * the distinction the arm is about.
 *
 * Entities are resolved and whitespace collapsed per node, same as `toText`,
 * and empty nodes are dropped.
 */
function textNodes(html: string): string[] {
  return html
    .split(/<[^>]*>/)
    .map(t =>
      t
        .replace(/&mdash;/g, "—")
        .replace(/&rsquo;/g, "’")
        .replace(/&amp;/g, "&")
        .replace(/\s+/g, " ")
        .trim()
    )
    .filter(t => t.length > 0);
}

/** Arm (1)'s predicate, isolated so the frozen control can be run through it. */
function consensusClaimsIn(text: string): string[] {
  const haystack = text.toLowerCase();
  return CONSENSUS_PHRASES.filter(p => haystack.includes(p));
}

describe("#7718 — the price-basis bullet does not claim a consensus", () => {
  test("the frozen control reproduces the defect: the predicate FLAGS the pre-fix sentence", () => {
    // Non-vacuity arm (a). Without this, arm (1) could pass because the
    // predicate matches nothing anywhere, and would prove nothing about the
    // fix. The production sentence must trip it, on the word it shipped.
    expect(consensusClaimsIn(PRE_FIX_SENTENCE)).toContain("consensus");
  });

  test("the bullet makes no consensus claim", () => {
    // Arm (1), over the WHOLE bullet. The predicate cannot tell an assertion
    // from a denial, so the shipped sentence states the positive fact and does
    // not reach for "rather than a consensus line" to say it. That is the
    // right trade: a guard that had to parse the negation would be the fragile
    // half of this file, and the positive sentence is the clearer one anyway.
    const text = toText(basisMarkup(render()));
    expect(consensusClaimsIn(text)).toEqual([]);
  });

  test("the bullet still says the sportsbooks are measured separately", () => {
    // Arm (2): arm (1) must not be satisfiable by deleting the clause. The
    // reader is still told what the sportsbook number is made of, and what
    // that means for the count — a game ten sportsbooks priced is ten
    // observations, which is the fact "consensus" was hiding.
    //
    // The clause says "each sportsbook … its own last price" and NOT "its own
    // closing moneyline", which is what the first draft wrote: `moneyline` is
    // a banned reader word (#2442 — the reader gets the probability, not the
    // price format), and `shippedCopyBans` caught it in the built bundle. The
    // pinned phrases are therefore the ones that survive that rule.
    const text = toText(basisMarkup(render()));
    expect(text).toContain("we measure each sportsbook separately");
    expect(text).toContain("its own last price before kickoff");
    expect(text).toContain("counts once for each of them");
  });

  test("the bullet still answers its question and keeps #7482's basis", () => {
    // Arm (3): gutting the bullet is not a passing fix, and the neighbouring
    // ship stays paid — #7482 moved the basis answer HERE, so a fix to this
    // bullet that dropped it would silently undo that one.
    const text = toText(basisMarkup(render()));
    expect(text).toContain("Which probability do we use?");
    expect(text).toContain("closing line prices");
    expect(text).toContain("opening price after initial trading settles");
  });

  test("while we label the curve Per-sportsbook, NO text about sportsbooks claims a consensus", () => {
    // Arm (4) — the class, not the sentence. Scoped to sentences that mention
    // a sportsbook rather than to the whole page, because the page says
    // "consensus" legitimately elsewhere: "Academic consensus range (Arrow et
    // al. 2008)" is a benchmark row in How We Compare, and it is somebody
    // else's consensus, not a claim about how we price. A whole-page ban would
    // fail on true copy, and this file's own neighbours record what happens to
    // a rule that does that — it gets switched off within a week.
    const html = render();
    const page = toText(html);

    // Non-vacuity (c), the premise, CHECKED rather than assumed — both halves,
    // and read from the function that DECIDES the reader's word rather than
    // from the rendered output it produces. Asserting the string is on the page
    // would be circular: the page is where the conclusion is measured too.
    expect(sourceLabel("odds_api_bookmaker")).toContain("Per-sportsbook");
    const sportsbookBlocks = textNodes(html).filter(t =>
      t.toLowerCase().includes("sportsbook")
    );
    expect(sportsbookBlocks.length).toBeGreaterThan(0);

    // The conclusion.
    const offenders = sportsbookBlocks.filter(t => consensusClaimsIn(t).length > 0);
    expect(offenders).toEqual([]);
  });
});
