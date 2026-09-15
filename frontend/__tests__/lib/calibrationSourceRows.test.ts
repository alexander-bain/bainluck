import {
  censoredSourceRows,
  censoringVerdict,
  orderSourceRows,
  sourceRowsExcludedFromRollup,
  withheldSourcesNote,
  type SourceRowInput,
} from "@/lib/calibrationSourceRows";
import { providerLabel } from "@/lib/calibrationProviders";
import { ece, mce } from "@/lib/calibrationMath";
import { brierScore, cohortFilterFor, aggregateBuckets } from "@/lib/calibrationParity";

// ---------------------------------------------------------------------------
// UX-P128. The specimen is production's, not a convenient example.
//
// `GET /api/calibration` on 2026-08-24 published seven source keys. Six carry
// outcomes in the default cohort. `datagolf` carries 171 outcomes across 9
// buckets with a SERVER ECE of 11.88pp — the worst-calibrated source on the
// page — and every one of its 9 bucket rows has `price_moved: false`, so the
// default cohort (`price_moved !== false`) empties it completely.
//
// The page then rendered it as `0 | 0.0pp | 0.0pp | 0.0000`, in green, in FIRST
// place. These numbers are pinned so a regression has to argue with the payload
// that produced the bug.
// ---------------------------------------------------------------------------

// CAL-P1024 (#1865): every `label` below is DERIVED by the same call the page
// makes, never written out beside the row.
//
// It used to be written out, and that is why the `datagolf` bug lived here for
// three weeks in plain sight. `withheldSourcesNote` has asserted
// `toContain("DataGolf")` since UX-P128 and passed the whole time, because the
// fixture handed it the capital letters. Production, deriving the label through
// `providerLabel`, printed a sentence that began "datagolf has no outcomes in
// this cohort". A fixture that supplies the value under test cannot refute the
// code that computes it — the same defect shape as CAL-P1023's `retry_after`
// fixture, one session earlier.
const labelFor = (provider: string) => providerLabel(provider);

// #6211 added `buckets` as a REQUIRED input. Every row below carries a
// two-sided population at roughly the win rate that source really runs at
// (#6211's own by-source table: kalshi 37.5%, polymarket 34.4%, odds api
// 55.7%), because a row whose buckets are all-winners is now `censored` and
// these three must stay `measured` for the ordering assertions to mean
// anything.
const twoSided = (n: number, winRate: number) => [{ n, winners: Math.round(n * winRate) }];

const LIVE: SourceRowInput[] = [
  { provider: "kalshi", label: labelFor("kalshi"), sources: ["kalshi"], n: 287922, ece: 1.25, mce: 1.25, brier: 0.1712, buckets: twoSided(287922, 0.375) },
  { provider: "polymarket", label: labelFor("polymarket"), sources: ["polymarket"], n: 112663, ece: 2.6, mce: 2.6, brier: 0.1904, buckets: twoSided(112663, 0.344) },
  {
    provider: "odds_api_family",
    label: labelFor("odds_api_family"),
    sources: ["odds_api", "odds_api_bookmaker", "odds_api_spreads", "odds_api_totals"],
    n: 136173, ece: 1.4, mce: 1.4, brier: 0.2011, buckets: twoSided(136173, 0.557),
  },
  // The specimen. Every metric is the identity element of an empty reduction.
  { provider: "datagolf", label: labelFor("datagolf"), sources: ["datagolf"], n: 0, ece: 0, mce: 0, brier: 0, buckets: [] },
];

describe("orderSourceRows — the n=0 render", () => {
  it("never lets an empty reduction reach a formatter", () => {
    const dg = orderSourceRows(LIVE).find(r => r.provider === "datagolf")!;
    expect(dg.state).toBe("no-cohort-data");
    // Not 0 — null. A `0` here is what `(0).toFixed(1)` turns into "0.0pp".
    expect(dg.ece).toBeNull();
    expect(dg.mce).toBeNull();
    expect(dg.brier).toBeNull();
    expect(dg.n).toBe(0);
  });

  it("keeps the row rather than dropping it — the payload did publish this source", () => {
    // Dropping would leave the Sources KPI saying 4 above a table showing 3,
    // and would hide a source the cohort toggle brings back in one click.
    expect(orderSourceRows(LIVE).map(r => r.provider)).toContain("datagolf");
    expect(orderSourceRows(LIVE)).toHaveLength(4);
  });

  it("does not rank an unmeasured row — it goes last, not first", () => {
    const order = orderSourceRows(LIVE).map(r => r.provider);
    // THE BUG, pinned: sorting raw `a.ece - b.ece` put datagolf's fabricated
    // 0.0 ahead of Kalshi's real 1.25 under a subhead reading "lower is better".
    const naive = [...LIVE].sort((a, b) => a.ece - b.ece).map(r => r.provider);
    expect(naive[0]).toBe("datagolf");
    expect(order[0]).toBe("kalshi");
    expect(order[order.length - 1]).toBe("datagolf");
  });

  it("orders the measured rows by ECE ascending, unchanged", () => {
    const measured = orderSourceRows(LIVE).filter(r => r.state === "measured");
    expect(measured.map(r => r.provider)).toEqual([
      "kalshi",            // 1.25
      "odds_api_family",   // 1.4
      "polymarket",        // 2.6
    ]);
  });

  it("orders several unmeasured rows stably by label, not by payload order", () => {
    const extra: SourceRowInput[] = [
      ...LIVE,
      { provider: "zzz", label: "Aardvark", sources: ["zzz"], n: 0, ece: 0, mce: 0, brier: 0, buckets: [] },
    ];
    const tail = orderSourceRows(extra).filter(r => r.state === "no-cohort-data");
    expect(tail.map(r => r.label)).toEqual(["Aardvark", "DataGolf"]);
    // Reversing the input must not reorder the tail — an unstable tail would
    // read to a reader as the data having changed.
    expect(orderSourceRows([...extra].reverse()).filter(r => r.state === "no-cohort-data").map(r => r.label))
      .toEqual(["Aardvark", "DataGolf"]);
  });

  it("treats a negative or non-finite n as unmeasured, not as a small sample", () => {
    for (const n of [-1, NaN, Infinity]) {
      const [row] = orderSourceRows([{ ...LIVE[3], n }]);
      expect(row.state).toBe("no-cohort-data");
      expect(row.n).toBe(0);
    }
  });

  it("leaves a genuinely-zero-error measured source alone", () => {
    // The whole point of the distinction: 0.0pp with outcomes behind it is a
    // real, publishable result and must still rank first.
    const perfect: SourceRowInput = {
      provider: "oracle", label: "Oracle", sources: ["oracle"], n: 5000, ece: 0, mce: 0, brier: 0,
      buckets: twoSided(5000, 0.5),
    };
    const order = orderSourceRows([...LIVE, perfect]);
    expect(order[0].provider).toBe("oracle");
    expect(order[0].state).toBe("measured");
    expect(order[0].ece).toBe(0);
  });

  it("returns [] for absent input rather than throwing", () => {
    expect(orderSourceRows(null)).toEqual([]);
    expect(orderSourceRows(undefined)).toEqual([]);
    expect(orderSourceRows([])).toEqual([]);
  });
});

describe("the metric guards this exists to contain", () => {
  it("ece/mce/brier all report 0 on empty input — the reason the row lied", () => {
    // Each guard is individually correct; none of them can report its own
    // absence, which is why the count has to decide and not the metric.
    expect(ece([])).toBe(0);
    expect(mce([])).toBe(0);
    expect(brierScore([])).toBe(0);
  });

  it("the default cohort really does empty a 100%-never-moved source", () => {
    // The 9 real datagolf bucket rows from the 2026-08-24 payload, n-exact.
    const dgBuckets = [1, 6, 7, 28, 36, 42, 34, 14, 3].map((n, i) => ({
      bucket_idx: i, n, winners: 0, sum_prob: 0, sum_sq_err: 0,
      source: "datagolf", category: "golf", price_moved: false as const,
    }));
    expect(dgBuckets.reduce((s, b) => s + b.n, 0)).toBe(171);

    const keep = cohortFilterFor(false);
    // The narrowing IS an assertion: the default cohort must be a real
    // predicate. `cohortFilterFor(true)`, asserted below, deliberately is not.
    if (!keep) throw new Error("the default cohort must carry a predicate");
    expect(dgBuckets.filter(keep)).toHaveLength(0);
    expect(aggregateBuckets(dgBuckets, keep)).toHaveLength(0);
    expect(ece(aggregateBuckets(dgBuckets, keep))).toBe(0);

    // And with the toggle on, all 171 come back — the absence is recoverable,
    // which is exactly why the row must say so instead of vanishing.
    // `cohortFilterFor(true)` is `undefined` by design: no predicate at all,
    // which is how the callers spell "keep everything".
    const keepAll = cohortFilterFor(true);
    expect(keepAll).toBeUndefined();
    expect(aggregateBuckets(dgBuckets, keepAll)).toHaveLength(9);
    expect(aggregateBuckets(dgBuckets, keepAll).reduce((s, b) => s + b.n, 0)).toBe(171);
  });
});

describe("exclusion from the rollups", () => {
  it("names the withheld rows from the rendered rows, not a second condition", () => {
    const withheld = sourceRowsExcludedFromRollup(orderSourceRows(LIVE));
    expect(withheld.map(r => r.provider)).toEqual(["datagolf"]);
  });

  it("contributes nothing to the n-weighted Combined figure", () => {
    // The Combined row was never flattered — it is n-weighted off pooled
    // buckets — and this keeps saying so rather than assuming it.
    const measuredBuckets = [{ n: 287922, error: 1.25 }, { n: 112663, error: 2.6 }];
    const withEmptySource = [...measuredBuckets, { n: 0, error: 999 }];
    expect(ece(withEmptySource)).toBeCloseTo(ece(measuredBuckets), 10);
  });
});

describe("withheldSourcesNote", () => {
  it("names the provider and the remedy", () => {
    const note = withheldSourcesNote(orderSourceRows(LIVE), "Include never-moved");
    expect(note).toContain("DataGolf");
    expect(note).toContain("no outcomes in this cohort");
    expect(note).toContain("Include never-moved");
  });

  it("says nothing when nothing was withheld", () => {
    const allMeasured = orderSourceRows(LIVE.filter(r => r.n > 0));
    expect(withheldSourcesNote(allMeasured, "Include never-moved")).toBeNull();
  });

  it("agrees in number with how many were withheld", () => {
    const two = orderSourceRows([
      ...LIVE,
      { provider: "zzz", label: "Aardvark", sources: ["zzz"], n: 0, ece: 0, mce: 0, brier: 0, buckets: [] },
    ]);
    const note = withheldSourcesNote(two, "Include never-moved")!;
    expect(note).toContain("Aardvark, DataGolf");
    expect(note).toContain("have no outcomes");
    expect(note).toContain("panels are not drawn");
  });
});

// ---------------------------------------------------------------------------
// #6211 — THE THIRD STATE. A population with only one outcome class.
//
// Same row, other direction. With the cohort toggle ON, `datagolf` published
// **36 outcomes at 36.5pp ECE** beside Kalshi's 318,956 at 0.9pp, same table,
// same columns, no caveat — a published accuracy verdict on a named
// third-party provider. Every one of those 36 outcomes is a winner.
//
// The buckets below are the five real ones from the production payload as
// recorded on #6211 (walked at 390px, 2026-09-14 ~19:55Z). They are not
// illustrative: the suite RE-DERIVES 36.5pp and 0.1424 from them through the
// page's own `aggregateBuckets`/`ece`/`brierScore`, so if these numbers were
// wrong the derivation would not land on what production printed.
// ---------------------------------------------------------------------------

/** bucket_idx, n, avg_prob, winners, sum_sq_err — production, #6211. */
const DATAGOLF_PUBLISHED = [
  { idx: 4, n: 3, avgProb: 0.4367, winners: 3, sumSqErr: 0.9550 },
  { idx: 5, n: 9, avgProb: 0.5552, winners: 9, sumSqErr: 1.7875 },
  { idx: 6, n: 14, avgProb: 0.6504, winners: 14, sumSqErr: 1.7213 },
  { idx: 7, n: 9, avgProb: 0.7355, winners: 9, sumSqErr: 0.6335 },
  { idx: 8, n: 1, avgProb: 0.8326, winners: 1, sumSqErr: 0.0280 },
];

const dgParityBuckets = DATAGOLF_PUBLISHED.map(b => ({
  bucket_idx: b.idx,
  n: b.n,
  winners: b.winners,
  sum_prob: b.n * b.avgProb,
  sum_sq_err: b.sumSqErr,
  source: "datagolf",
  category: "golf",
  price_moved: false as const,
}));

/** datagolf as `providerMetrics` hands it over with the toggle ON. */
const DATAGOLF_CENSORED: SourceRowInput = {
  provider: "datagolf",
  label: labelFor("datagolf"),
  sources: ["datagolf"],
  n: 36,
  ece: ece(aggregateBuckets(dgParityBuckets)),
  mce: mce(aggregateBuckets(dgParityBuckets)),
  brier: brierScore(dgParityBuckets),
  buckets: aggregateBuckets(dgParityBuckets),
};

describe("#6211 — the specimen is real, and the figure is price-determined", () => {
  it("re-derives the 36.5pp and 0.1424 production printed", () => {
    // If this drifts, the fixture stopped being the payload and every
    // assertion below is about a number we invented.
    expect(DATAGOLF_CENSORED.ece).toBeCloseTo(36.5, 1);
    expect(DATAGOLF_CENSORED.brier).toBeCloseTo(0.1424, 4);
    expect(dgParityBuckets.reduce((s, b) => s + b.n, 0)).toBe(36);
    expect(dgParityBuckets.reduce((s, b) => s + b.winners, 0)).toBe(36);
  });

  it("the ECE is a function of the PRICES ALONE — the reason it is not a measurement", () => {
    // The theorem the gate rests on. With every outcome a winner, observed
    // frequency is 1 in every bucket, so ECE collapses to the n-weighted mean
    // distance from price to certainty. Computed here WITHOUT reference to
    // `winners` at all, and it lands on the published figure.
    const totalN = DATAGOLF_PUBLISHED.reduce((s, b) => s + b.n, 0);
    const priceOnly =
      DATAGOLF_PUBLISHED.reduce((s, b) => s + b.n * (1 - b.avgProb), 0) / totalN;
    expect(priceOnly * 100).toBeCloseTo(DATAGOLF_CENSORED.ece, 1);

    // And therefore: nothing about how the questions resolved can move it.
    // Re-price the same population and the figure moves; re-resolve it and it
    // cannot, because there is nothing left to re-resolve.
    const shifted = dgParityBuckets.map(b => ({ ...b, sum_prob: b.n * 0.99 }));
    expect(ece(aggregateBuckets(shifted))).not.toBeCloseTo(DATAGOLF_CENSORED.ece, 1);
  });
});

describe("#6211 — the gate", () => {
  it("calls the all-winner population censored, not measured", () => {
    const dg = orderSourceRows([...LIVE.slice(0, 3), DATAGOLF_CENSORED])
      .find(r => r.provider === "datagolf")!;
    expect(dg.state).toBe("censored");
    expect(dg.winners).toBe(36);
    expect(dg.n).toBe(36);
  });

  it("stops the price-determined figure reaching a formatter", () => {
    const dg = orderSourceRows([DATAGOLF_CENSORED])[0];
    // THE DEFECT, pinned: the input really does carry a printable 36.5.
    expect(DATAGOLF_CENSORED.ece).toBeCloseTo(36.5, 1);
    expect(dg.ece).toBeNull();
    expect(dg.mce).toBeNull();
    expect(dg.brier).toBeNull();
  });

  it("catches the all-LOSER population too — the gate is symmetric", () => {
    // D112's `TestLoneClaimSymmetryGate` is scoped to the loser-only ingest
    // arm; DataGolf is the winner direction of the same defect. A gate that
    // caught only the direction we happened to find would be the same
    // asymmetry one layer up.
    const allLost = orderSourceRows([
      { ...DATAGOLF_CENSORED, buckets: [{ n: 36, winners: 0 }] },
    ])[0];
    expect(allLost.state).toBe("censored");
    expect(allLost.winners).toBe(0);
    expect(allLost.ece).toBeNull();
  });

  it("leaves a two-sided population measured, however extreme its error", () => {
    // The gate must not become a quiet min-sample floor or a bad-number
    // filter. One loser in 36 is still a measurement, and a badly-calibrated
    // source must keep being publishable as badly calibrated.
    const oneLoser = orderSourceRows([
      { ...DATAGOLF_CENSORED, buckets: [{ n: 36, winners: 35 }] },
    ])[0];
    expect(oneLoser.state).toBe("measured");
    expect(oneLoser.ece).toBeCloseTo(36.5, 1);
  });

  it("is exact, not a threshold — 99% one-sided is still a measurement", () => {
    // If someone later reaches for a tunable constant here, this is the line
    // that argues with them: at 99% the figure responds to resolutions, so it
    // measures something. At 100% it cannot.
    const ninetyNine = orderSourceRows([
      { ...DATAGOLF_CENSORED, n: 1000, buckets: [{ n: 1000, winners: 990 }] },
    ])[0];
    expect(ninetyNine.state).toBe("measured");
  });

  it("does not rank a censored row — it leaves the ordering entirely", () => {
    const order = orderSourceRows([...LIVE.slice(0, 3), DATAGOLF_CENSORED]);
    // Position is a published claim under "sorted by ECE, lower is better".
    // Ranked on its raw 36.5 the row takes LAST place, which reads as "the
    // worst source we carry" — a verdict on a named third party that our
    // censored population cannot support.
    const naive = [...LIVE.slice(0, 3), DATAGOLF_CENSORED]
      .sort((a, b) => a.ece - b.ece).map(r => r.provider);
    expect(naive[naive.length - 1]).toBe("datagolf");

    expect(order.filter(r => r.state === "measured").map(r => r.provider))
      .toEqual(["kalshi", "odds_api_family", "polymarket"]);
    expect(order[order.length - 1].provider).toBe("datagolf");
  });

  it("keeps the row and its real outcome count — item 3, do not hide it", () => {
    // The issue is explicit that a min-sample floor which drops the row
    // "would delete the alarm and keep the defect". 36 is a real count.
    const order = orderSourceRows([...LIVE.slice(0, 3), DATAGOLF_CENSORED]);
    expect(order).toHaveLength(4);
    expect(order.map(r => r.provider)).toContain("datagolf");
    expect(order.find(r => r.provider === "datagolf")!.n).toBe(36);
  });

  it("treats an empty bucket list as absence, not as a one-sided population", () => {
    // `n === 0` must keep winning: the remedy `withheldSourcesNote` names is
    // the true one for a withheld row and a false one for a censored row.
    const dg = orderSourceRows(LIVE).find(r => r.provider === "datagolf")!;
    expect(dg.state).toBe("no-cohort-data");
    expect(dg.winners).toBeNull();
  });
});

describe("#6211 — censoringVerdict, on its own", () => {
  it("pools the buckets rather than judging them one at a time", () => {
    // A per-bucket test would call a source censored the moment ANY bucket
    // came out one-sided, which is ordinary in a thin bucket and is not this
    // defect. Two one-sided buckets pointing opposite ways are a two-sided
    // population.
    expect(censoringVerdict([{ n: 10, winners: 10 }, { n: 10, winners: 0 }]))
      .toEqual({ n: 20, winners: 10, censored: false });
  });

  it("reports no population rather than a censored one for empty input", () => {
    for (const empty of [[], null, undefined]) {
      expect(censoringVerdict(empty).censored).toBe(false);
      expect(censoringVerdict(empty).n).toBe(0);
    }
  });

  it("fails CLOSED on a corrupt bucket claiming more winners than outcomes", () => {
    // Clamped to its own `n`, so it reads as all-winners: the row states its
    // population instead of publishing a number. Recoverable. The other
    // direction publishes the lie.
    expect(censoringVerdict([{ n: 5, winners: 9 }])).toEqual({ n: 5, winners: 5, censored: true });
  });

  it("floors non-finite and negative fields instead of propagating NaN", () => {
    // A NaN total would make `winners === n` false and the row would publish.
    expect(censoringVerdict([{ n: NaN, winners: 3 }, { n: 10, winners: 10 }]).censored).toBe(true);
    expect(censoringVerdict([{ n: 10, winners: -4 }])).toEqual({ n: 10, winners: 0, censored: true });
  });
});

describe("#6211 — the two absences stay two sentences", () => {
  it("withheldSourcesNote never claims a censored row has no outcomes", () => {
    // It has 36, and with the toggle already on, "use the toggle to measure
    // it" names the control the reader just used. The sentence would be false
    // twice over.
    const rows = orderSourceRows([...LIVE.slice(0, 3), DATAGOLF_CENSORED]);
    expect(withheldSourcesNote(rows, "Include never-moved")).toBeNull();
    expect(sourceRowsExcludedFromRollup(rows)).toEqual([]);
  });

  it("censoredSourceRows names them, from the same rows the table renders", () => {
    const rows = orderSourceRows([...LIVE.slice(0, 3), DATAGOLF_CENSORED]);
    expect(censoredSourceRows(rows).map(r => r.label)).toEqual(["DataGolf"]);
    // And the withheld case stays the withheld case.
    expect(censoredSourceRows(orderSourceRows(LIVE))).toEqual([]);
    expect(sourceRowsExcludedFromRollup(orderSourceRows(LIVE)).map(r => r.label))
      .toEqual(["DataGolf"]);
  });
});
