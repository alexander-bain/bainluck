import {
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

const LIVE: SourceRowInput[] = [
  { provider: "kalshi", label: labelFor("kalshi"), sources: ["kalshi"], n: 287922, ece: 1.25, mce: 1.25, brier: 0.1712 },
  { provider: "polymarket", label: labelFor("polymarket"), sources: ["polymarket"], n: 112663, ece: 2.6, mce: 2.6, brier: 0.1904 },
  {
    provider: "odds_api_family",
    label: labelFor("odds_api_family"),
    sources: ["odds_api", "odds_api_bookmaker", "odds_api_spreads", "odds_api_totals"],
    n: 136173, ece: 1.4, mce: 1.4, brier: 0.2011,
  },
  // The specimen. Every metric is the identity element of an empty reduction.
  { provider: "datagolf", label: labelFor("datagolf"), sources: ["datagolf"], n: 0, ece: 0, mce: 0, brier: 0 },
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
      { provider: "zzz", label: "Aardvark", sources: ["zzz"], n: 0, ece: 0, mce: 0, brier: 0 },
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
      { provider: "zzz", label: "Aardvark", sources: ["zzz"], n: 0, ece: 0, mce: 0, brier: 0 },
    ]);
    const note = withheldSourcesNote(two, "Include never-moved")!;
    expect(note).toContain("Aardvark, DataGolf");
    expect(note).toContain("have no outcomes");
    expect(note).toContain("panels are not drawn");
  });
});
