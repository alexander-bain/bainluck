// CAL-P025 — exit-exam items 2 and 4, graded on the frozen production payload.
//
// Item 2 asks the trading section to LEAD with the matched-bucket comparison
// instead of the two cross-cohort tiles. The reason is not presentational: the
// two cohorts have different predicted-probability mixes, so the difference
// between their headline ECEs is part composition. `calibrationMath`'s own
// `describeActivityComparison` comment already says so ("C111 [P2] showed this
// aggregate is composition sensitive"), and then, correctly, declines to do
// anything about it — stating an ordering was all it could honestly do.
//
// This suite's job is to prove the matched comparison says something the
// aggregate cannot, on real bytes. It does, and the shape is specific: on the
// 2026-08-02 payload nine of ten matched buckets land within 2pp of each other
// and one — the 40-50% mid-band — opens to 4.3pp. A reader given only the two
// tiles learns neither half of that.
//
// Item 4 is the per-source panels. Its numbers are pinned here too, because the
// legibility argument is quantitative (28x in n across five sources) and a
// panel that loses its own n is just a smaller overlay.
//
// Fixture discipline, following `calibrationCohort.test.ts`: the expectations
// are computed by an INDEPENDENT implementation of the aggregation inside this
// file, never read back from `calibrationMath`. A shared bug would otherwise
// agree with itself.

import {
  buildSourcePanels,
  compareMatchedBuckets,
  describeActivityComparison,
  ece,
  MATCHED_BUCKET_CLOSE_BAND_PP,
  MATCHED_BUCKET_MIN_SIDE_N,
  MatchedBucketInput,
} from "@/lib/calibrationMath";
import {
  PROD_BUCKETS,
  PROD_TOTAL_OUTCOMES,
  ProdFixtureBucket,
} from "./calibrationProdFixture";

// ---------------------------------------------------------------------------
// L2-231's frozen partition, the same three constants `calibrationCohort`
// grades against. Repeated rather than imported so a change to that suite's
// expectations cannot quietly move this one's.
// ---------------------------------------------------------------------------
const PROD = {
  fullN: 652_407,
  movedN: 349_310,
  unchangedN: 263_022,
  notApplicableN: 40_075,
};

/** Independent per-(bucket, cohort) rollup. Deliberately not the module's. */
function rollup(rows: ProdFixtureBucket[], moved: boolean) {
  const out: Record<number, { n: number; winners: number; sumProb: number }> = {};
  for (const r of rows) {
    if (r.price_moved !== moved) continue;
    const a = (out[r.bucket_idx] ||= { n: 0, winners: 0, sumProb: 0 });
    a.n += r.n;
    a.winners += r.winners;
    a.sumProb += r.sum_prob;
  }
  return out;
}

/** actual - predicted in pp, one decimal — the page's display precision. */
function errPp(a: { n: number; winners: number; sumProb: number }): number {
  return Math.round((a.winners / a.n - a.sumProb / a.n) * 1000) / 10;
}

const FIXTURE = PROD_BUCKETS as MatchedBucketInput[];

describe("the fixture is the payload this suite thinks it is", () => {
  test("it reconciles to the frozen population", () => {
    // If this drifts, every number below is grading different bytes and the
    // failure should say so here rather than as a confusing mid-band miss.
    expect(PROD_TOTAL_OUTCOMES).toBe(PROD.fullN);
    expect(PROD_BUCKETS.reduce((s, b) => s + b.n, 0)).toBe(PROD.fullN);
  });
});

describe("the matched-bucket comparison, on the 2026-08-02 production payload", () => {
  const cmp = compareMatchedBuckets(FIXTURE);

  test("it partitions exactly as the cohort suite does, and names the excluded rows", () => {
    // The `price_moved === null` sportsbook rows are the L2-236 finding: 40,075
    // outcomes that both cards excluded and neither mentioned. They must be
    // reported as their own number, never folded in and never silently dropped.
    expect(cmp.notApplicableN).toBe(PROD.notApplicableN);
    expect(cmp.comparedN).toBe(PROD.movedN + PROD.unchangedN);
    expect(cmp.comparedN + cmp.notApplicableN).toBe(PROD.fullN);
  });

  test("every bucket is matched, and each side matches an independent rollup", () => {
    const m = rollup(PROD_BUCKETS, true);
    const u = rollup(PROD_BUCKETS, false);
    expect(cmp.rows).toHaveLength(10);
    for (const row of cmp.rows) {
      expect(row.moved).not.toBeNull();
      expect(row.unchanged).not.toBeNull();
      expect(row.moved!.n).toBe(m[row.bucketIdx].n);
      expect(row.unchanged!.n).toBe(u[row.bucketIdx].n);
      expect(row.moved!.errorPp).toBeCloseTo(errPp(m[row.bucketIdx]), 5);
      expect(row.unchanged!.errorPp).toBeCloseTo(errPp(u[row.bucketIdx]), 5);
    }
  });

  test("THE FINDING: nine of ten buckets track within 2pp; the mid-band opens to 4.3pp", () => {
    // This is the sentence the section now leads with, as data. It is the whole
    // justification for demoting the tiles: the aggregate hides both that the
    // cohorts mostly agree AND where they don't.
    expect(cmp.closeCount).toBe(9);
    expect(cmp.rows.filter(r => r.comparable)).toHaveLength(10);

    expect(cmp.widest).not.toBeNull();
    expect(cmp.widest!.bucketIdx).toBe(4);
    expect(cmp.widest!.label).toBe("40-50%");
    expect(cmp.widest!.gapPp).toBeCloseTo(-4.3, 5);
    expect(cmp.widest!.moved!.errorPp).toBeCloseTo(-5.7, 5);
    expect(cmp.widest!.unchanged!.errorPp).toBeCloseTo(-1.4, 5);
    expect(cmp.widest!.moved!.n).toBe(42_067);
    expect(cmp.widest!.unchanged!.n).toBe(33_516);
  });

  test("the mid-band is where the divergence lives — 35-50%, not everywhere", () => {
    // Buckets 3 and 4 are the exam's named finding. Pinning the neighbours too
    // stops a future change from reporting a mid-band that has quietly widened
    // into "the whole curve", which would be a different (and bigger) claim.
    const by = Object.fromEntries(cmp.rows.map(r => [r.bucketIdx, r.gapPp]));
    expect(by[3]).toBeCloseTo(-1.8, 5);
    expect(by[4]).toBeCloseTo(-4.3, 5);
    expect(Math.abs(by[5] as number)).toBeLessThanOrEqual(MATCHED_BUCKET_CLOSE_BAND_PP);
    expect(Math.abs(by[6] as number)).toBeLessThanOrEqual(MATCHED_BUCKET_CLOSE_BAND_PP);
  });

  test("the sentence states the observation and never a cause", () => {
    const s = cmp.sentence as string;
    expect(s).toContain("40-50%");
    expect(s).toContain("4.3pp");
    expect(s).toContain("9 of 10");
    // Same rule the module's aggregate comparison holds itself to.
    expect(s).not.toMatch(/\bbecause\b|\bcauses?\b|\bcaused\b|\bdue to\b|\bdrives?\b/i);
  });

  test("it disagrees with the aggregate reading, which is the reason it exists", () => {
    // The tiles compare two whole cohorts. Grade the same bytes both ways and
    // the aggregate gap is NOT the story the buckets tell: the per-bucket
    // divergence is concentrated in one band, four times the aggregate spread.
    const aggMoved = ece(
      Object.values(rollup(PROD_BUCKETS, true)).map(a => ({ n: a.n, error: errPp(a) }))
    );
    const aggUnchanged = ece(
      Object.values(rollup(PROD_BUCKETS, false)).map(a => ({ n: a.n, error: errPp(a) }))
    );
    const aggregateGap = Math.abs(aggMoved - aggUnchanged);

    expect(Math.abs(cmp.widest!.gapPp as number)).toBeGreaterThan(aggregateGap * 2);
    // And the aggregate still renders — this demotes it, it does not delete it.
    expect(
      describeActivityComparison({ ece: aggMoved, n: PROD.movedN }, { ece: aggUnchanged, n: PROD.unchangedN })
        .sentence
    ).not.toBeNull();
  });
});

describe("rule 3 — an absent side is null, never a zero-error agreement", () => {
  // The failure this prevents: a one-sided bucket rendering "0.0pp gap", which
  // reads as "the cohorts agree here" when the truth is "one cohort is not
  // here at all". Gotcha #53's shape, in a table cell.
  const oneSided: MatchedBucketInput[] = [
    { bucket_idx: 2, price_moved: true, n: 5000, winners: 1000, sum_prob: 1250 },
    { bucket_idx: 7, price_moved: true, n: 4000, winners: 3000, sum_prob: 2960 },
    { bucket_idx: 7, price_moved: false, n: 4000, winners: 2900, sum_prob: 2960 },
  ];
  const cmp = compareMatchedBuckets(oneSided);

  test("the one-sided bucket keeps its present side and nulls the other", () => {
    const b2 = cmp.rows.find(r => r.bucketIdx === 2)!;
    expect(b2.moved).not.toBeNull();
    expect(b2.unchanged).toBeNull();
    expect(b2.gapPp).toBeNull();
    expect(b2.comparable).toBe(false);
  });

  test("a one-sided bucket can never be the widest gap or reach the sentence", () => {
    expect(cmp.widest!.bucketIdx).toBe(7);
    expect(cmp.comparedN).toBe(8000);
    expect(cmp.sentence).toContain("70-80%");
  });

  test("a bucket present on neither side simply is not a row", () => {
    expect(cmp.rows.map(r => r.bucketIdx)).toEqual([2, 7]);
  });
});

describe("the thin-sample floor keeps faded dots out of the headline", () => {
  const thin: MatchedBucketInput[] = [
    // A huge gap on a tiny sample — exactly what would hijack the sentence.
    { bucket_idx: 1, price_moved: true, n: 40, winners: 40, sum_prob: 6 },
    { bucket_idx: 1, price_moved: false, n: 40, winners: 0, sum_prob: 6 },
    { bucket_idx: 6, price_moved: true, n: 20_000, winners: 13_400, sum_prob: 13_000 },
    { bucket_idx: 6, price_moved: false, n: 20_000, winners: 13_200, sum_prob: 13_000 },
  ];
  const cmp = compareMatchedBuckets(thin);

  test("the thin bucket is shown but is not comparable", () => {
    const b1 = cmp.rows.find(r => r.bucketIdx === 1)!;
    expect(b1.moved!.n).toBeLessThan(MATCHED_BUCKET_MIN_SIDE_N);
    expect(b1.gapPp).not.toBeNull();     // it HAS a gap
    expect(b1.comparable).toBe(false);   // it just cannot carry the finding
    expect(cmp.widest!.bucketIdx).toBe(6);
    expect(cmp.comparedN).toBe(40_000);
  });

  test("with every bucket thin there is no claim at all, rather than a weak one", () => {
    const allThin = compareMatchedBuckets(thin.slice(0, 2));
    expect(allThin.rows).toHaveLength(1);
    expect(allThin.widest).toBeNull();
    expect(allThin.sentence).toBeNull();
    expect(allThin.comparedN).toBe(0);
  });
});

describe("degenerate payloads produce no claim instead of a wrong one", () => {
  test.each([
    ["null", null],
    ["undefined", undefined],
    ["empty", [] as MatchedBucketInput[]],
  ])("%s", (_label, input) => {
    const cmp = compareMatchedBuckets(input as MatchedBucketInput[] | null | undefined);
    expect(cmp.rows).toEqual([]);
    expect(cmp.sentence).toBeNull();
    expect(cmp.widest).toBeNull();
  });

  test("a sportsbook-only payload reports its exclusion and claims nothing", () => {
    // Every row `price_moved: null`. The section must be able to tell the
    // reader "the test does not apply to any of this", not render an empty table.
    const cmp = compareMatchedBuckets([
      { bucket_idx: 5, price_moved: null, n: 12_000, winners: 6_100, sum_prob: 6_000 },
    ]);
    expect(cmp.notApplicableN).toBe(12_000);
    expect(cmp.rows).toEqual([]);
    expect(cmp.sentence).toBeNull();
  });

  test("zero-n rows never create a side", () => {
    const cmp = compareMatchedBuckets([
      { bucket_idx: 3, price_moved: true, n: 0, winners: 0, sum_prob: 0 },
      { bucket_idx: 3, price_moved: false, n: 2_000, winners: 700, sum_prob: 700 },
    ]);
    expect(cmp.rows[0].moved).toBeNull();
    expect(cmp.rows[0].gapPp).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Item 4 — per-source panels.
// ---------------------------------------------------------------------------

/** Independent per-source rollup into error buckets. */
function sourceBuckets(src: string) {
  const agg: Record<number, { n: number; winners: number; sumProb: number }> = {};
  for (const r of PROD_BUCKETS) {
    if (r.source !== src) continue;
    const a = (agg[r.bucket_idx] ||= { n: 0, winners: 0, sumProb: 0 });
    a.n += r.n;
    a.winners += r.winners;
    a.sumProb += r.sum_prob;
  }
  return Object.values(agg).map(a => ({ n: a.n, error: errPp(a) }));
}

const PROD_SOURCES = Array.from(new Set(PROD_BUCKETS.map(b => b.source)));

/**
 * `by_source` as the server published it on 2026-08-02, from this document's
 * own evidence log. These are the numbers the panels must RENDER — ruling 003
 * forbids the client deriving its own.
 */
const PROD_PUBLISHED_ECE: Record<string, number> = {
  kalshi: 0.82,
  polymarket: 2.72,
  odds_api: 1.35,
  odds_api_totals: 1.1,
  odds_api_spreads: 0.67,
};

describe("per-source panels keep the size difference the overlay conveyed by accident", () => {
  const panels = buildSourcePanels(
    PROD_SOURCES.map(s => ({
      source: s,
      buckets: sourceBuckets(s),
      publishedEce: PROD_PUBLISHED_ECE[s],
    }))
  );

  test("every source gets a panel, largest first", () => {
    expect(panels.map(p => p.source)).toEqual([
      "kalshi", "polymarket", "odds_api", "odds_api_totals", "odds_api_spreads",
    ]);
  });

  test("each panel carries its own n, and they reconcile to the population", () => {
    // The measured legibility problem: 28x between the largest and smallest.
    // Equal-area panels erase that unless each states its n.
    const byName = Object.fromEntries(panels.map(p => [p.source, p.n]));
    expect(byName.kalshi).toBe(420_594);
    expect(byName.polymarket).toBe(191_738);
    expect(byName.odds_api).toBe(14_960);
    expect(byName.odds_api_totals).toBe(12_705);
    expect(byName.odds_api_spreads).toBe(12_410);
    expect(panels.reduce((s, p) => s + p.n, 0)).toBe(PROD.fullN);
    expect(byName.kalshi / byName.odds_api_spreads).toBeGreaterThan(28);
  });

  test("shares sum to 1, so a panel can state its weight honestly", () => {
    expect(panels.reduce((s, p) => s + p.share, 0)).toBeCloseTo(1, 10);
    expect(panels[0].share).toBeGreaterThan(0.6);
  });

  test("each panel RENDERS the server's ECE — it never derives one", () => {
    // Ruling 003, named failure: "dual ECE derivations — the same calibration
    // number computed twice, in two languages, which guarantees they drift".
    // The panel prints exactly what `by_source` published, rounded to the
    // page's display precision and nothing more.
    for (const p of panels) {
      expect(p.ece).toBe(Math.round(PROD_PUBLISHED_ECE[p.source] * 10) / 10);
    }
  });

  test("the two derivations ALREADY disagree on this payload — the drift is live", () => {
    // This is the whole case for ruling 003 being an absolute rather than a
    // judgement call, measured on the bytes production is serving right now:
    //
    //   source            published   client-derived
    //   kalshi                  0.8              0.8   agree
    //   polymarket              2.7              2.7   agree
    //   odds_api                1.4              1.4   agree
    //   odds_api_totals         1.1              1.1   agree
    //   odds_api_spreads        0.7              0.6   DISAGREE
    //
    // Four of five agree, which is exactly how a dual derivation survives
    // review — it looks fine until it doesn't, on one source, at one moment.
    // The panel must show the server's 0.7.
    const spreadsDerived = Math.round(ece(sourceBuckets("odds_api_spreads")) * 10) / 10;
    expect(spreadsDerived).toBe(0.6);
    expect(panels.find(p => p.source === "odds_api_spreads")!.ece).toBe(0.7);
    expect(panels.find(p => p.source === "odds_api_spreads")!.ece).not.toBe(spreadsDerived);
  });

  test("the published spread is what makes the overlay illegible: 3.3x in ECE", () => {
    const kalshi = panels.find(p => p.source === "kalshi")!;
    const poly = panels.find(p => p.source === "polymarket")!;
    expect((poly.ece as number) / (kalshi.ece as number)).toBeGreaterThan(3);
  });

  test("a source the payload published no ECE for prints nothing, not a guess", () => {
    // The honest state is "the backend did not publish one". Backfilling it
    // with a client derivation is exactly the drift ruling 003 forbids.
    const out = buildSourcePanels([
      { source: "kalshi", buckets: [{ n: 100, error: 1 }], publishedEce: 0.8 },
      { source: "newsource", buckets: [{ n: 50, error: 4 }] },
      { source: "nulled", buckets: [{ n: 40, error: 9 }], publishedEce: null },
    ]);
    expect(out.find(p => p.source === "newsource")!.ece).toBeNull();
    expect(out.find(p => p.source === "nulled")!.ece).toBeNull();
    expect(out.find(p => p.source === "kalshi")!.ece).toBe(0.8);
  });

  test("a source with no buckets is dropped, not drawn as an empty frame", () => {
    // An empty panel asserts "measured, found nothing". That is not what a
    // missing source means, and the difference matters on a page about honesty.
    const out = buildSourcePanels([
      { source: "kalshi", buckets: [{ n: 100, error: 1 }] },
      { source: "ghost", buckets: [] },
    ]);
    expect(out.map(p => p.source)).toEqual(["kalshi"]);
  });

  test("degenerate input yields no panels", () => {
    expect(buildSourcePanels(null)).toEqual([]);
    expect(buildSourcePanels([])).toEqual([]);
    expect(buildSourcePanels([{ source: "x", buckets: [{ n: 0, error: 0 }] }])).toEqual([]);
  });
});
