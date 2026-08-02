// #999 L2-75: pure calibration math (extracted from the /calibration page).

import { describeActivityComparison, ece, mce, monthYear } from "../../lib/calibrationMath";

describe("mce (equal-weighted)", () => {
  test("mean of |error| regardless of n", () => {
    // errors 2, 4 → mean 3.0; n is ignored.
    expect(mce([{ n: 10000, error: 2 }, { n: 3, error: 4 }])).toBeCloseTo(3.0);
  });
  test("uses absolute error", () => {
    expect(mce([{ n: 1, error: -6 }, { n: 1, error: 2 }])).toBeCloseTo(4.0);
  });
  test("empty → 0", () => {
    expect(mce([])).toBe(0);
  });
});

describe("ece (n-weighted)", () => {
  test("n-weighted mean of |error| — big bucket dominates", () => {
    // 10000*2 + 3*40 = 20120; /10003 ≈ 2.01 (a thin 40pp bucket barely moves it).
    expect(ece([{ n: 10000, error: 2 }, { n: 3, error: 40 }])).toBeCloseTo(2.01, 1);
  });
  test("differs from MCE when sizes are lopsided", () => {
    const buckets = [{ n: 10000, error: 1 }, { n: 2, error: 20 }];
    expect(ece(buckets)).toBeLessThan(mce(buckets)); // ECE stays honest; MCE over-reacts
  });
  test("empty / zero-n → 0", () => {
    expect(ece([])).toBe(0);
    expect(ece([{ n: 0, error: 5 }])).toBe(0);
  });
});

// L2-230 / C111 [P1]. The bug this locks down: the page rendered an
// unconditional "active trading is dramatically better calibrated" plus
// `unchangedECE / movedECE` labelled "more accurately calibrated". With the
// live 2026-08-02 payload (moved 1.7pp, unchanged 1.0pp) that printed the
// literal string "0.6x more accurately calibrated" — a ratio below one sold as
// superiority, directly contradicting the two stat cards above it.
describe("describeActivityComparison", () => {
  const cohort = (ece: number, n = 10_000) => ({ ece, n });

  describe("the reported production state", () => {
    // Reproduced from GET /api/calibration on 2026-08-02T03:23Z with the page's
    // own aggregation: moved n=349,310 ECE=1.7162; unchanged n=263,022 ECE=1.0341.
    const live = describeActivityComparison(
      cohort(1.7162, 349_310),
      cohort(1.0341, 263_022)
    );

    test("names the moved cohort as the WORSE one, not the better one", () => {
      expect(live.direction).toBe("moved_higher");
      expect(live.sentence).toContain("price-moved cohort carries the higher calibration error");
    });
    test("leads with both displayed values", () => {
      expect(live.sentence).toContain("1.7pp");
      expect(live.sentence).toContain("1.0pp");
    });
    test("the ratio is higher ÷ lower, so it is never below 1", () => {
      expect(live.ratioText).toBe("1.7");
      expect(Number(live.ratioText)).toBeGreaterThan(1);
    });
    test("the exact shipped-bug string cannot be produced", () => {
      expect(live.sentence).not.toContain("0.6x");
      expect(live.sentence).not.toMatch(/more accurately calibrated/);
    });
  });

  // Every state the section can reach, and what each must say.
  const cases: Array<{
    name: string;
    moved: { ece: unknown; n: unknown };
    unchanged: { ece: unknown; n: unknown };
    direction: string;
    hasSentence: boolean;
    ratio: string | null;
  }> = [
    { name: "changed worse", moved: cohort(2.4), unchanged: cohort(1.2), direction: "moved_higher", hasSentence: true, ratio: "2.0" },
    { name: "changed better", moved: cohort(1.2), unchanged: cohort(2.4), direction: "unchanged_higher", hasSentence: true, ratio: "2.0" },
    { name: "exactly equal", moved: cohort(1.5), unchanged: cohort(1.5), direction: "tied", hasSentence: true, ratio: null },
    // Tolerance boundary: display precision IS the tolerance. 1.44 and 1.54 both
    // print as different values; 1.44 and 1.4999 both print "1.5" and must tie.
    { name: "tie by rounding (1.4499 vs 1.5001 → 1.4 vs 1.5, still ordered)", moved: cohort(1.4499), unchanged: cohort(1.5001), direction: "unchanged_higher", hasSentence: true, ratio: "1.1" },
    { name: "tie by rounding (1.4501 vs 1.5000 → both 1.5)", moved: cohort(1.4501), unchanged: cohort(1.5), direction: "tied", hasSentence: true, ratio: null },
    // Ordered but the ratio would print "1.0x", which reads as "the same".
    { name: "ordered, ratio rounds to 1.0 → ratio suppressed", moved: cohort(9.9), unchanged: cohort(9.8), direction: "moved_higher", hasSentence: true, ratio: null },
    // Zero denominator: a real 0.0pp side makes higher/lower infinite.
    { name: "zero lower side → ordering kept, ratio suppressed", moved: cohort(1.3), unchanged: cohort(0), direction: "moved_higher", hasSentence: true, ratio: null },
    { name: "both zero", moved: cohort(0), unchanged: cohort(0), direction: "tied", hasSentence: true, ratio: null },
    // Missing / empty cohorts: the comparison is suppressed entirely.
    { name: "missing moved ECE", moved: { ece: null, n: 10_000 }, unchanged: cohort(1.0), direction: "unknown", hasSentence: false, ratio: null },
    { name: "missing unchanged ECE", moved: cohort(1.0), unchanged: { ece: undefined, n: 10_000 }, direction: "unknown", hasSentence: false, ratio: null },
    { name: "empty moved cohort (n=0)", moved: cohort(0, 0), unchanged: cohort(1.0), direction: "unknown", hasSentence: false, ratio: null },
    { name: "missing n", moved: cohort(1.0), unchanged: { ece: 1.0, n: null }, direction: "unknown", hasSentence: false, ratio: null },
    // Non-finite: NaN/Infinity render as plausible text if they ever reach copy.
    { name: "NaN moved", moved: cohort(NaN), unchanged: cohort(1.0), direction: "unknown", hasSentence: false, ratio: null },
    { name: "Infinity unchanged", moved: cohort(1.0), unchanged: cohort(Infinity), direction: "unknown", hasSentence: false, ratio: null },
    { name: "-Infinity moved", moved: cohort(-Infinity), unchanged: cohort(1.0), direction: "unknown", hasSentence: false, ratio: null },
    // Poison: ECE is a mean of absolute errors, so a negative one is corrupt
    // input. Refuse it rather than ranking it as "best calibrated".
    { name: "poison negative ECE", moved: cohort(-3.0), unchanged: cohort(1.0), direction: "unknown", hasSentence: false, ratio: null },
    { name: "poison negative n", moved: cohort(1.0, -5), unchanged: cohort(1.0), direction: "unknown", hasSentence: false, ratio: null },
    { name: "poison non-numeric ECE", moved: { ece: "1.0", n: 10_000 }, unchanged: cohort(2.0), direction: "unknown", hasSentence: false, ratio: null },
  ];

  test.each(cases)("$name", ({ moved, unchanged, direction, hasSentence, ratio }) => {
    const r = describeActivityComparison(
      moved as { ece: number; n: number },
      unchanged as { ece: number; n: number }
    );
    expect(r.direction).toBe(direction);
    expect(r.ratioText).toBe(ratio);
    expect(r.sentence === null).toBe(!hasSentence);
  });

  describe("invariants across every case", () => {
    test("no case ever claims superiority or causation", () => {
      for (const c of cases) {
        const s = describeActivityComparison(
          c.moved as { ece: number; n: number },
          c.unchanged as { ece: number; n: number }
        ).sentence;
        if (!s) continue;
        expect(s).not.toMatch(/more accurately|better calibrated|dramatically|improves?\b/i);
      }
    });
    test("a rendered sentence never leaks a non-finite token", () => {
      for (const c of cases) {
        const s = describeActivityComparison(
          c.moved as { ece: number; n: number },
          c.unchanged as { ece: number; n: number }
        ).sentence;
        if (!s) continue;
        expect(s).not.toMatch(/NaN|Infinity|undefined|null/);
      }
    });
    test("a shown ratio is always >= 1 and matches the two displayed values", () => {
      for (const c of cases) {
        const r = describeActivityComparison(
          c.moved as { ece: number; n: number },
          c.unchanged as { ece: number; n: number }
        );
        if (!r.ratioText) continue;
        const hi = Math.max(Number(r.movedText), Number(r.unchangedText));
        const lo = Math.min(Number(r.movedText), Number(r.unchangedText));
        expect(Number(r.ratioText)).toBeGreaterThanOrEqual(1);
        expect(r.ratioText).toBe((hi / lo).toFixed(1));
      }
    });
    test("argument order decides only which label is named, never the ordering", () => {
      const a = describeActivityComparison(cohort(2.4), cohort(1.2));
      const b = describeActivityComparison(cohort(1.2), cohort(2.4));
      expect(a.direction).toBe("moved_higher");
      expect(b.direction).toBe("unchanged_higher");
      expect(a.ratioText).toBe(b.ratioText);
      // Both must name 2.4pp as the higher one, whichever slot it sat in.
      expect(a.sentence).toContain("price-moved cohort carries the higher");
      expect(b.sentence).toContain("price-unchanged cohort carries the higher");
    });
  });
});

describe("monthYear", () => {
  test("formats ISO to Mon YYYY", () => {
    expect(monthYear("2026-07-09T00:00:00Z")).toMatch(/Jul 2026/);
  });
  test("echoes unparseable input", () => {
    expect(monthYear("not-a-date")).toBe("not-a-date");
  });
});
