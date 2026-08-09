import {
  collapseDuplicateRungs,
  parseSpreadOutcome,
} from "@/lib/marketMapUtils";
import { AGREEMENT_TOLERANCE } from "@/lib/otherMarketGroups";

/**
 * UX-P039 — the market-map ladders stop painting the same rung four times.
 *
 * The fixture below is a VERBATIM production capture, taken 2026-08-09 from
 * `GET /api/events/15191147/game-markets` (Athletics @ Boston Red Sox, final).
 * Its `period_markets` bucket carried 28 `half_total` rows across only 7 real
 * thresholds, because four different games' Kalshi tickers were linked to the
 * one event — note the `26JUL27` / `26JUL28` / `26JUL29` / `26JUL30` cohorts
 * on a game played on August 9.
 *
 * The `_external_id`s are retained deliberately: they are the evidence that
 * these are four games' markets and not one game's multi-source quotes, and
 * they are what a future reader needs to tell those two cases apart.
 */
const PRODUCTION_1H_TOTALS_15191147 = [
  { threshold: 0.5, over_probability: 0.99, _external_id: "KXMLBF5TOTAL-26JUL302140BOSATH" },
  { threshold: 0.5, over_probability: 0.99, _external_id: "KXMLBF5TOTAL-26JUL282140BOSATH" },
  { threshold: 0.5, over_probability: 0.99, _external_id: "KXMLBF5TOTAL-26JUL272140BOSATH" },
  { threshold: 0.5, over_probability: 0.99, _external_id: "KXMLBF5TOTAL-26JUL292140BOSATH" },
  { threshold: 1.5, over_probability: 0.99, _external_id: "KXMLBF5TOTAL-26JUL302140BOSATH" },
  { threshold: 1.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL282140BOSATH" },
  { threshold: 1.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL272140BOSATH" },
  { threshold: 1.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL292140BOSATH" },
  { threshold: 2.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL302140BOSATH" },
  { threshold: 2.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL282140BOSATH" },
  { threshold: 2.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL272140BOSATH" },
  { threshold: 2.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL292140BOSATH" },
  { threshold: 3.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL302140BOSATH" },
  { threshold: 3.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL282140BOSATH" },
  { threshold: 3.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL272140BOSATH" },
  { threshold: 3.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL292140BOSATH" },
  { threshold: 4.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL302140BOSATH" },
  { threshold: 4.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL282140BOSATH" },
  { threshold: 4.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL272140BOSATH" },
  { threshold: 4.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL292140BOSATH" },
  { threshold: 5.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL302140BOSATH" },
  { threshold: 5.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL282140BOSATH" },
  { threshold: 5.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL272140BOSATH" },
  { threshold: 5.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL292140BOSATH" },
  { threshold: 6.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL302140BOSATH" },
  { threshold: 6.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL282140BOSATH" },
  { threshold: 6.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL272140BOSATH" },
  { threshold: 6.5, over_probability: 0.01, _external_id: "KXMLBF5TOTAL-26JUL292140BOSATH" },
];

/**
 * Also a verbatim capture, same slate, event 15191145 (Blue Jays @ Phillies).
 * Seven rows, seven thresholds, no duplication — the HEALTHY case that must
 * come through completely untouched. Every suppression needs a guard in both
 * directions (gotcha #43); this is the other direction.
 */
const PRODUCTION_1H_TOTALS_15191145 = [
  { threshold: 0.5, over_probability: 0.99 },
  { threshold: 1.5, over_probability: 0.99 },
  { threshold: 2.5, over_probability: 0.99 },
  { threshold: 3.5, over_probability: 0.99 },
  { threshold: 4.5, over_probability: 0.99 },
  { threshold: 5.5, over_probability: 0.99 },
  { threshold: 6.5, over_probability: 0.01 },
];

const totalKey = (t: { threshold: number }) => String(t.threshold);
const totalProb = (t: { over_probability: number }) => t.over_probability;

describe("collapseDuplicateRungs — the production defect", () => {
  it("collapses the 28-row Aug 9 ladder to its 7 real thresholds", () => {
    const result = collapseDuplicateRungs(
      PRODUCTION_1H_TOTALS_15191147,
      totalKey,
      totalProb,
    );

    // 7 thresholds exist. One of them (1.5) carries irreconcilable values and
    // is withheld rather than guessed at, leaving 6 rungs on screen.
    expect(result.rows).toHaveLength(6);
    expect(result.withheld).toBe(1);
    expect(result.rows.map((r) => r.threshold)).toEqual([
      0.5, 2.5, 3.5, 4.5, 5.5, 6.5,
    ]);
  });

  it("withholds the rung whose duplicates disagree, and never picks a side", () => {
    const result = collapseDuplicateRungs(
      PRODUCTION_1H_TOTALS_15191147,
      totalKey,
      totalProb,
    );

    // `Over 1.5` arrived as both 0.99 and 0.01. Neither may be rendered: this
    // is exactly the "pick the more extreme value" bug UX-P037 removed from
    // the Additional Markets section.
    const rung15 = result.rows.filter((r) => r.threshold === 1.5);
    expect(rung15).toHaveLength(0);
  });

  it("reports the redundant rows it removed, so the drop is never silent", () => {
    const result = collapseDuplicateRungs(
      PRODUCTION_1H_TOTALS_15191147,
      totalKey,
      totalProb,
    );

    // 6 agreeing groups of 4 → 18 redundant rows removed; the 4 rows of the
    // disagreeing group are counted under `withheld`, not `collapsed`.
    expect(result.collapsed).toBe(18);
    expect(result.collapsed + result.withheld * 4 + result.rows.length).toBe(
      PRODUCTION_1H_TOTALS_15191147.length,
    );
  });

  it("makes the ladder monotone, which the downstream filter could not", () => {
    // The bug the monotonicity pass structurally cannot catch: equal
    // duplicates satisfy `prob <= lastProb`, so all 28 rows slid through it.
    const beforeSorted = [...PRODUCTION_1H_TOTALS_15191147].sort(
      (a, b) => a.threshold - b.threshold,
    );
    let kept = 0;
    let last = 1.0;
    for (const t of beforeSorted) {
      if (t.over_probability <= last) {
        kept += 1;
        last = t.over_probability;
      }
    }
    expect(kept).toBe(28); // the old guard removed nothing at all

    const after = collapseDuplicateRungs(
      PRODUCTION_1H_TOTALS_15191147,
      totalKey,
      totalProb,
    ).rows;
    const thresholds = after.map((r) => r.threshold);
    expect(new Set(thresholds).size).toBe(thresholds.length);
  });
});

describe("collapseDuplicateRungs — the healthy direction must not regress", () => {
  it("passes a clean 7-rung production ladder through unchanged", () => {
    const result = collapseDuplicateRungs(
      PRODUCTION_1H_TOTALS_15191145,
      totalKey,
      totalProb,
    );

    expect(result.rows).toEqual(PRODUCTION_1H_TOTALS_15191145);
    expect(result.collapsed).toBe(0);
    expect(result.withheld).toBe(0);
  });

  it("keeps a single row, which trivially agrees with itself", () => {
    const rows = [{ threshold: 2.5, over_probability: 0.44 }];
    const result = collapseDuplicateRungs(rows, totalKey, totalProb);
    expect(result.rows).toEqual(rows);
    expect(result.withheld).toBe(0);
  });

  it("preserves input order rather than sorting", () => {
    const rows = [
      { threshold: 6.5, over_probability: 0.1 },
      { threshold: 0.5, over_probability: 0.9 },
      { threshold: 2.5, over_probability: 0.5 },
    ];
    const result = collapseDuplicateRungs(rows, totalKey, totalProb);
    expect(result.rows.map((r) => r.threshold)).toEqual([6.5, 0.5, 2.5]);
  });

  it("empties nothing when given nothing", () => {
    const none: Array<{ threshold: number; over_probability: number }> = [];
    const result = collapseDuplicateRungs(none, totalKey, totalProb);
    expect(result.rows).toEqual([]);
    expect(result.collapsed).toBe(0);
    expect(result.withheld).toBe(0);
  });
});

describe("collapseDuplicateRungs — the agreement boundary", () => {
  it("collapses duplicates sitting EXACTLY at tolerance", () => {
    // The IEEE-754 trap otherMarketGroups documents: 0.52 - 0.5 is
    // 0.020000000000000018, so a bare `>` would withhold this pair.
    const rows = [
      { threshold: 1.5, over_probability: 0.5 },
      { threshold: 1.5, over_probability: 0.5 + AGREEMENT_TOLERANCE },
    ];
    const result = collapseDuplicateRungs(rows, totalKey, totalProb);
    expect(result.rows).toHaveLength(1);
    expect(result.withheld).toBe(0);
  });

  it("withholds duplicates just beyond tolerance", () => {
    const rows = [
      { threshold: 1.5, over_probability: 0.5 },
      { threshold: 1.5, over_probability: 0.5 + AGREEMENT_TOLERANCE + 0.001 },
    ];
    const result = collapseDuplicateRungs(rows, totalKey, totalProb);
    expect(result.rows).toHaveLength(0);
    expect(result.withheld).toBe(1);
  });

  it("uses the same tolerance as the Additional Markets section", () => {
    // One agreement policy on the event page, not two. If this constant is
    // ever forked, this assertion is the thing that says so out loud.
    expect(AGREEMENT_TOLERANCE).toBe(0.02);
  });
});

describe("collapseDuplicateRungs — spread ladders key on side AND threshold", () => {
  const parse = (name: string, prob: number) =>
    parseSpreadOutcome(name, prob, "kalshi", "Boston Red Sox", "Athletics");

  const spreadKey = (p: { isHome: boolean; threshold: number }) =>
    `${p.isHome ? "H" : "A"}|${p.threshold}`;
  const spreadProb = (p: { probability: number }) => p.probability;

  it("does not merge the two teams' rungs at the same threshold", () => {
    // Home +1.5 and Away +1.5 are different questions with legitimately
    // different prices; keying on threshold alone would destroy one of them.
    const rows = [
      parse("Boston Red Sox +1.5", 0.7),
      parse("Athletics +1.5", 0.3),
    ].filter((p): p is NonNullable<typeof p> => p != null);
    expect(rows).toHaveLength(2);

    const result = collapseDuplicateRungs(rows, spreadKey, spreadProb);
    expect(result.rows).toHaveLength(2);
    expect(result.withheld).toBe(0);
  });

  it("collapses a genuine same-side duplicate", () => {
    const rows = [
      parse("Boston Red Sox +1.5", 0.7),
      parse("Boston Red Sox +1.5", 0.7),
    ].filter((p): p is NonNullable<typeof p> => p != null);

    const result = collapseDuplicateRungs(rows, spreadKey, spreadProb);
    expect(result.rows).toHaveLength(1);
    expect(result.collapsed).toBe(1);
  });
});
