// L2-236 Item 0 — freeze the cohorts the calibration page actually renders.
//
// The page defaults to `price_moved !== false` and called that set "well-traded
// markets — where real trading moved the price". `price_moved` is a tri-state:
// on the frozen production payload below, 40,075 of the 389,385 rows that
// sentence described are sportsbook lines carrying no price-moved flag at all.
// The claim was false for 10.3% of its own cohort, and those rows were named
// nowhere — the activity section's two cards summed to 612,332 against a stated
// population of 652,407.
//
// So this suite freezes three things, in this order:
//
//   1. The PARTITION. moved + unchanged + not-applicable must reconcile to the
//      full population exactly, and the default cohort must be the two halves
//      it actually selects — never inferred from the label.
//   2. The COPY, per state: not-applicable present and absent, cohort on and
//      off. Every label names its predicate; none imports a liquidity claim the
//      predicate does not measure.
//   3. The DIRECTION grammar, across moved-worse, moved-better, tie, zero and
//      unavailable — the states that produced "0.6x more accurately calibrated"
//      beside cards reading 1.7pp and 1.0pp.
//
// Metrics are asserted against L2-231's native constants over the SAME bytes,
// computed here by an independent implementation of the page's aggregation
// rather than read back from `calibrationMath` — a shared bug would otherwise
// agree with itself.

import * as fs from "fs";
import * as path from "path";
import { describeCohort, partitionByActivity } from "@/lib/calibrationCohort";
import { describeActivityComparison, ece, mce } from "@/lib/calibrationMath";
import {
  PROD_BUCKETS,
  PROD_TOTAL_OUTCOMES,
  ProdFixtureBucket,
} from "./calibrationProdFixture";

// ---------------------------------------------------------------------------
// L2-231's frozen expectations, copied from
// `ios/Bain Luck/BainLuckTests/CalibrationAvailabilityTests.swift`. These are
// the numbers native ships against; web has to land on them or the two surfaces
// are describing different data while claiming the same population.
// ---------------------------------------------------------------------------
const PROD = {
  fullN: 652_407,
  movedN: 349_310,
  unchangedN: 263_022,
  notApplicableN: 40_075,
  /** moved + not-applicable — the default cohort. */
  cohortN: 389_385,
  cohortECE: 1.5425470934935861,
  cohortMCE: 1.45,
  allECE: 1.2614602541051827,
  allMCE: 1.24,
  movedECE: 1.716231141393032,
  unchangedECE: 1.0341499950574478,
  notApplicableECE: 0.28600873362445417,
  /** source -> (n, ece, mce) within the default cohort. */
  sourceRows: {
    kalshi: { n: 267_121, ece: 1.0553928743902576, mce: 1.1400000000000001 },
    polymarket: { n: 82_189, ece: 4.8175351932740389, mce: 4.29 },
    odds_api: { n: 14_960, ece: 1.3532018716577541, mce: 1.1199999999999999 },
    odds_api_spreads: { n: 12_410, ece: 0.64699435938759065, mce: 11.029999999999999 },
    odds_api_totals: { n: 12_705, ece: 1.1074065328610783, mce: 16.4375 },
  } as Record<string, { n: number; ece: number; mce: number }>,
};

/** Float sums differ by association order between languages; 1e-12 is exact enough. */
const TOL = 1e-12;

/**
 * The page's aggregation, reimplemented from its definition: sum `n`,
 * `winners` and `sum_prob` into `bucket_idx` bins, then difference the two
 * rates and round to the tenth the reader sees.
 */
function aggregate(
  buckets: ProdFixtureBucket[],
  filter?: (b: ProdFixtureBucket) => boolean
): Array<{ n: number; error: number }> {
  const bins = new Map<number, { n: number; winners: number; sumProb: number }>();
  for (const b of buckets) {
    if (filter && !filter(b)) continue;
    const bin = bins.get(b.bucket_idx) ?? { n: 0, winners: 0, sumProb: 0 };
    bin.n += b.n;
    bin.winners += b.winners;
    bin.sumProb += b.sum_prob;
    bins.set(b.bucket_idx, bin);
  }
  return [...bins.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, bin]) => ({
      n: bin.n,
      error: Math.round((bin.winners / bin.n - bin.sumProb / bin.n) * 1000) / 10,
    }));
}

const totalN = (filter?: (b: ProdFixtureBucket) => boolean): number =>
  PROD_BUCKETS.filter((b) => !filter || filter(b)).reduce((s, b) => s + b.n, 0);

const inDefaultCohort = (b: ProdFixtureBucket) => b.price_moved !== false;

/** Every cohort-facing string the page renders, for a given state. */
const copyOf = (c: ReturnType<typeof describeCohort>): string[] => [
  c.headline,
  c.detail,
  c.toggleLabel,
  c.statDetail,
  c.heroClause,
  c.shortLabel,
  c.partitionNote ?? "",
];

// ===========================================================================
// 1. The partition
// ===========================================================================

describe("the activity partition reconciles to the population it claims", () => {
  const partition = partitionByActivity(PROD_BUCKETS);

  test("the frozen fixture is the payload L2-231 froze", () => {
    // If this drifts, every constant below is being graded against different
    // bytes than native's and "parity" means nothing.
    expect(PROD_TOTAL_OUTCOMES).toBe(PROD.fullN);
    expect(totalN()).toBe(PROD.fullN);
    expect(PROD_BUCKETS).toHaveLength(68);
  });

  test("price_moved is a TRI-state and all three sides are counted", () => {
    expect(partition.movedN).toBe(PROD.movedN);
    expect(partition.unchangedN).toBe(PROD.unchangedN);
    expect(partition.notApplicableN).toBe(PROD.notApplicableN);
  });

  test("moved + unchanged + not-applicable === the full population", () => {
    // The invariant the shipped surface violated: its two rendered cohorts summed
    // to 612,332 against a stated 652,407, and the 40,075-row gap had no label.
    const sum = partition.movedN + partition.unchangedN + partition.notApplicableN;
    expect(sum).toBe(PROD.fullN);
    expect(partition.movedN + partition.unchangedN).toBe(612_332);
    expect(describeCohort(partition, PROD.fullN, false).reconciles).toBe(true);
  });

  test("a payload whose parts do not add up says so instead of rendering anyway", () => {
    const copy = describeCohort(
      { movedN: 10, unchangedN: 10, notApplicableN: 0 },
      99,
      false
    );
    expect(copy.reconciles).toBe(false);
  });

  test("the default cohort is moved + not-applicable, never inferred from a label", () => {
    expect(totalN(inDefaultCohort)).toBe(PROD.cohortN);
    expect(partition.movedN + partition.notApplicableN).toBe(PROD.cohortN);
    expect(describeCohort(partition, PROD.fullN, false).cohortN).toBe(PROD.cohortN);
    expect(describeCohort(partition, PROD.fullN, true).cohortN).toBe(PROD.fullN);
  });

  test("the headline cohort and the comparison denominator are named separately", () => {
    // Item 0. The page leads with the cohort count and compares against the
    // full population; one number standing in for both is how a filtered view
    // gets read as the whole dataset.
    const c = describeCohort(partition, PROD.fullN, false);
    expect(c.cohortN).not.toBe(c.fullN);
    expect(c.heroClause).toContain("389,385");
    expect(c.heroClause).toContain("652,407");
    expect(c.statDetail).toContain("652,407");
  });

  test("an unreadable n contributes nothing rather than poisoning the partition", () => {
    // Gotcha #42 on the client: one bad row must not wipe the whole pass.
    const p = partitionByActivity([
      { price_moved: true, n: 5 },
      { price_moved: true, n: Number.NaN },
      { price_moved: false, n: 3 },
    ]);
    expect(p).toEqual({ movedN: 5, unchangedN: 3, notApplicableN: 0 });
  });

  test("absent price_moved counts as not-applicable, not as false", () => {
    // `undefined` reaches here from a lean payload; treating it as `false` would
    // move sportsbook rows into the excluded set and silently shrink the curve.
    const p = partitionByActivity([{ n: 7 }, { price_moved: null, n: 3 }]);
    expect(p).toEqual({ movedN: 0, unchangedN: 0, notApplicableN: 10 });
  });
});

// ===========================================================================
// 2. The copy
// ===========================================================================

describe("every cohort label names the predicate it actually selects", () => {
  const partition = partitionByActivity(PROD_BUCKETS);
  const dflt = describeCohort(partition, PROD.fullN, false);
  const all = describeCohort(partition, PROD.fullN, true);

  test("the shipped false clause is gone, verbatim and by prefix", () => {
    expect(dflt.detail).not.toContain("where real trading moved the price");
    expect(dflt.headline).not.toContain("well-traded");
  });

  test("no label sells a liquidity claim the predicate does not measure", () => {
    // "well-traded" is about volume; the predicate is about MOVEMENT. "thin /
    // untraded" is false twice over — those rows traded, they just never moved,
    // and zero-bid outcomes are already excluded upstream.
    const banned = /well[- ]traded|thinly[- ]traded|thin\b|untraded/i;
    for (const copy of [...copyOf(dflt), ...copyOf(all)]) {
      expect(copy).not.toMatch(banned);
    }
  });

  test("no label claims trading CAUSED a calibration difference", () => {
    const causal = /more accurately calibrated|dramatically better|because .*trading/i;
    for (const copy of [...copyOf(dflt), ...copyOf(all)]) {
      expect(copy).not.toMatch(causal);
    }
  });

  test("the default cohort names BOTH halves, with their counts", () => {
    expect(dflt.headline).toBe(
      "Showing markets whose price moved, plus sportsbook lines (389,385)"
    );
    expect(dflt.detail).toContain("349,310 outcomes whose price real trading moved");
    expect(dflt.detail).toContain("40,075 sportsbook lines where that test doesn't apply");
  });

  test("the excluded side is described by what it is, with its count", () => {
    expect(dflt.detail).toContain(
      "Excluded: 263,022 outcomes whose price never moved off its opening line."
    );
    expect(dflt.toggleLabel).toBe("Include never-moved (+263,022)");
  });

  test("the all-markets view publishes the whole partition", () => {
    expect(all.headline).toBe("Showing all markets (652,407)");
    expect(all.detail).toBe(
      "349,310 price moved · 263,022 price unchanged · 40,075 not applicable (sportsbook lines)."
    );
    expect(all.toggleLabel).toBe("Exclude never-moved");
  });

  test("the activity note reconciles the two cards to the page total", () => {
    // Identical arithmetic, and identical shape, to native's partition note.
    expect(dflt.partitionNote).toBe(
      "Sportsbook lines (40,075 outcomes) carry no price-moved flag, so they sit in " +
        "neither cohort: 349,310 + 263,022 + 40,075 = 652,407 resolved outcomes."
    );
    expect(all.partitionNote).toBe(dflt.partitionNote);
  });

  test("with no sportsbook rows the plain trading claim is measured, so it stands", () => {
    // A caveat that appears on payloads it does not describe is noise. Here the
    // cohort IS exactly `price_moved === true`, so saying so is accurate.
    const c = describeCohort({ movedN: 200, unchangedN: 100, notApplicableN: 0 }, 300, false);
    expect(c.headline).toBe("Showing markets whose price moved (200)");
    expect(c.detail).toBe(
      "Every outcome whose price real trading moved. " +
        "Excluded: 100 outcomes whose price never moved off its opening line."
    );
    expect(c.partitionNote).toBeNull();
    expect(c.shortLabel).toBe("Price moved");
  });

  test("with no sportsbook rows the all-markets partition drops the third term", () => {
    const c = describeCohort({ movedN: 200, unchangedN: 100, notApplicableN: 0 }, 300, true);
    expect(c.detail).toBe("200 price moved · 100 price unchanged.");
    expect(c.partitionNote).toBeNull();
  });

  test("counts are formatted for a reader in every state", () => {
    for (const copy of [...copyOf(dflt), ...copyOf(all)]) {
      expect(copy).not.toMatch(/\b\d{4,}\b/); // no unseparated 349310
    }
  });

  test("the cohort publishes a machine-readable key, not just prose", () => {
    expect(dflt.key).toBe("excluding_never_moved");
    expect(all.key).toBe("all");
  });
});

// ===========================================================================
// 3. The direction grammar
// ===========================================================================

describe("the activity comparison states the observed ordering and nothing more", () => {
  test("production: moved 1.7pp vs unchanged 1.0pp reads as moved-worse", () => {
    const a = describeActivityComparison(
      { ece: PROD.movedECE, n: PROD.movedN },
      { ece: PROD.unchangedECE, n: PROD.unchangedN }
    );
    expect(a.direction).toBe("moved_higher");
    expect(a.movedText).toBe("1.7");
    expect(a.unchangedText).toBe("1.0");
    expect(a.ratioText).toBe("1.7");
    expect(a.sentence).toContain("price-moved cohort carries the higher calibration error");
    // The shipped bug, in one line: 1.0/1.7 = 0.6 printed as "more accurately".
    expect(a.sentence).not.toMatch(/more accurately calibrated/i);
    expect(a.sentence).not.toContain("0.6x");
  });

  test("the reversed ordering names the other cohort", () => {
    const a = describeActivityComparison({ ece: 1.0, n: 10 }, { ece: 1.7, n: 10 });
    expect(a.direction).toBe("unchanged_higher");
    expect(a.sentence).toContain("price-unchanged cohort carries the higher calibration error");
  });

  test("a tie at display precision is stated as a tie", () => {
    const a = describeActivityComparison({ ece: 1.04, n: 10 }, { ece: 1.02, n: 10 });
    expect(a.direction).toBe("tied");
    expect(a.ratioText).toBeNull();
    expect(a.sentence).toContain("effectively the same calibration error");
  });

  test("a zero denominator suppresses the ratio rather than dividing by it", () => {
    const a = describeActivityComparison({ ece: 1.2, n: 10 }, { ece: 0.04, n: 10 });
    expect(a.direction).toBe("moved_higher");
    expect(a.ratioText).toBeNull();
    expect(a.sentence).not.toContain("Infinity");
    expect(a.sentence).not.toContain("NaN");
  });

  test.each([
    ["an empty cohort", { ece: 1.2, n: 0 }, { ece: 1.0, n: 10 }],
    ["a missing metric", { ece: null, n: 10 }, { ece: 1.0, n: 10 }],
    ["NaN", { ece: Number.NaN, n: 10 }, { ece: 1.0, n: 10 }],
    ["Infinity", { ece: 1.0, n: 10 }, { ece: Number.POSITIVE_INFINITY, n: 10 }],
  ])("%s renders no comparison at all", (_name, moved, unchanged) => {
    const a = describeActivityComparison(moved, unchanged);
    expect(a.direction).toBe("unknown");
    expect(a.sentence).toBeNull();
  });
});

// ===========================================================================
// 4. Parity with L2-231's native constants, on the same bytes
// ===========================================================================

describe("web lands on the numbers native ships against", () => {
  test("the default cohort's ECE and MCE match", () => {
    const agg = aggregate(PROD_BUCKETS, inDefaultCohort);
    expect(ece(agg)).toBeCloseTo(PROD.cohortECE, 12);
    expect(mce(agg)).toBeCloseTo(PROD.cohortMCE, 12);
  });

  test("the all-markets cohort's ECE and MCE match", () => {
    const agg = aggregate(PROD_BUCKETS);
    expect(ece(agg)).toBeCloseTo(PROD.allECE, 12);
    expect(mce(agg)).toBeCloseTo(PROD.allMCE, 12);
  });

  test("each activity cohort's ECE matches, including the unlabelled third", () => {
    expect(ece(aggregate(PROD_BUCKETS, (b) => b.price_moved === true)))
      .toBeCloseTo(PROD.movedECE, 12);
    expect(ece(aggregate(PROD_BUCKETS, (b) => b.price_moved === false)))
      .toBeCloseTo(PROD.unchangedECE, 12);
    // The rows that had no name. They are the best-calibrated cohort on this
    // payload, which is the other reason folding them in silently was wrong.
    expect(ece(aggregate(PROD_BUCKETS, (b) => b.price_moved == null)))
      .toBeCloseTo(PROD.notApplicableECE, 12);
  });

  test("every per-source row inside the cohort matches, and they sum to it", () => {
    let sum = 0;
    for (const [source, expected] of Object.entries(PROD.sourceRows)) {
      const f = (b: ProdFixtureBucket) => b.source === source && inDefaultCohort(b);
      const agg = aggregate(PROD_BUCKETS, f);
      expect(totalN(f)).toBe(expected.n);
      expect(ece(agg)).toBeCloseTo(expected.ece, 12);
      expect(mce(agg)).toBeCloseTo(expected.mce, 12);
      sum += expected.n;
    }
    // Rows are the cohort's, so they add up to the cohort — not the total.
    expect(sum).toBe(PROD.cohortN);
    expect(sum).not.toBe(PROD.fullN);
  });

  test("Math.abs is real: no cohort's ECE is negative or non-finite", () => {
    for (const f of [
      undefined,
      inDefaultCohort,
      (b: ProdFixtureBucket) => b.price_moved === true,
      (b: ProdFixtureBucket) => b.price_moved === false,
      (b: ProdFixtureBucket) => b.price_moved == null,
    ]) {
      const v = ece(aggregate(PROD_BUCKETS, f));
      expect(Number.isFinite(v)).toBe(true);
      expect(v).toBeGreaterThanOrEqual(0);
    }
  });
});

// ===========================================================================
// 5. The page consumes this module — the copy cannot regrow beside it
// ===========================================================================

describe("the calibration page renders these strings and not its own", () => {
  const SOURCE: string = fs.readFileSync(
    path.join(__dirname, "..", "..", "app", "calibration", "page.tsx"),
    "utf8"
  );
  /** Comments explain the retired claim on purpose; only rendered copy counts. */
  const RENDERED: string = SOURCE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  test("it imports the cohort copy rather than writing it inline", () => {
    expect(SOURCE).toContain('from "@/lib/calibrationCohort"');
    expect(SOURCE).toContain("describeCohort(");
    expect(SOURCE).toContain("partitionByActivity(");
  });

  test("the false clause is not rendered anywhere on the page", () => {
    expect(RENDERED).not.toContain("where real trading moved the price");
    expect(RENDERED).not.toMatch(/well[- ]traded/i);
    expect(RENDERED).not.toMatch(/thinly[- ]traded|thin\/untraded/i);
  });

  test("the activity partition note reaches the DOM under its own hook", () => {
    expect(SOURCE).toContain('data-testid="calibration-activity-partition"');
  });

  test("the toggle publishes the partition as data, not only as prose", () => {
    const i = SOURCE.indexOf('data-testid="calibration-cohort-toggle"');
    expect(i).toBeGreaterThan(-1);
    const block = SOURCE.slice(i, i + 400);
    expect(block).toContain("data-cohort-key=");
    expect(block).toContain("data-moved-n=");
    expect(block).toContain("data-unchanged-n=");
    expect(block).toContain("data-not-applicable-n=");
  });
});
