/**
 * #9000 — Source Comparison and the By Source panel print ONE number per source.
 *
 * Production /calibration, 390px, "Exclude untraded" off, 2026-09-27 01:12Z:
 * Source Comparison printed `Polymarket 419,094 1.9pp` and the Polymarket panel
 * a screen below printed `2.0pp ECE` over the same 419,094 outcomes.
 *
 * The panel prints the server's `by_source[].ece` (1.96, ruling 003 / #7422).
 * The row is `ece(aggregateBuckets(...))` in the browser, and `aggregateBuckets`
 * rounds each bucket's `error` to 0.1pp. Averaging the rounded errors gave
 * 1.950 → "1.9"; the unrounded gap gives 1.963 → "2.0", the server's figure.
 * Two changes, two arms:
 *   - the metric averages `errorExact`, so every figure the browser (and the
 *     iPhone, which ports this) computes is the unrounded one;
 *   - a single-source provider's ROW, in the all-outcomes view, reads the same
 *     served figure its panel prints (`servedEceForRow`). Even computed exactly,
 *     the browser's number and the server's 2dp figure can land on different
 *     digits: `odds_api_bookmaker` is 1.152 exact, served 1.15, which prints
 *     "1.1". Sharing the number is the only way the pair cannot disagree.
 *
 * Fixture: the served payload pooled on (source, bucket_idx, price_moved) —
 * see `fixtures/calibrationServedSourceBuckets9000.ts`.
 */
import { aggregateBuckets } from "../lib/calibrationParity";
import { ece } from "../lib/calibrationMath";
import { groupSourcesByProvider } from "../lib/calibrationProviders";
import { eceInputsForPanel, servedEceForRow } from "../lib/calibrationProviderPanels";
import * as fs from "fs";
import * as path from "path";
import {
  SERVED_SOURCE_BUCKETS_20260926 as ROWS,
  BY_SOURCE_ECE_20260926 as BY_SOURCE,
} from "./fixtures/calibrationServedSourceBuckets9000";

const bySource = (keys: readonly string[]) =>
  aggregateBuckets(ROWS, b => keys.includes(b.source));

describe("#9000 browser ECE averages the unrounded bucket gap", () => {
  it("Polymarket, all outcomes: the browser's own figure is 1.963 → 2.0, the panel's digit", () => {
    const agg = bySource(["polymarket"]);
    expect(agg.reduce((s, b) => s + b.n, 0)).toBe(419094);
    expect(ece(agg)).toBeCloseTo(1.963, 3);
    expect(ece(agg).toFixed(1)).toBe("2.0");
    expect(BY_SOURCE.polymarket.toFixed(1)).toBe("2.0");
  });

  it("strawman: the same buckets averaged off the ROUNDED error print 1.9 — the fixture carries the defect", () => {
    const rounded = bySource(["polymarket"]).map(({ errorExact: _drop, ...b }) => b);
    expect(ece(rounded)).toBeCloseTo(1.95, 3);
    expect(ece(rounded).toFixed(1)).toBe("1.9");
  });

  it("every source key's browser ECE sits within the served 2dp figure's rounding", () => {
    for (const [source, served] of Object.entries(BY_SOURCE)) {
      const got = ece(bySource([source]));
      expect({ source, off: Math.abs(got - served) <= 0.005 + 1e-9 }).toEqual({ source, off: true });
    }
  });

  it("the served 2dp figure can still print a different digit than the exact one — why the row must SHARE the panel's number", () => {
    const exact = ece(bySource(["odds_api_bookmaker"]));
    expect(exact.toFixed(1)).toBe("1.2");
    expect(BY_SOURCE.odds_api_bookmaker.toFixed(1)).toBe("1.1");
  });

  it("Source Comparison row = By Source panel for every provider, all-outcomes view", () => {
    const sources = Array.from(new Set(ROWS.map(r => r.source)));
    const groups = groupSourcesByProvider(sources);
    expect(groups.filter(g => g.sources.length === 1).map(g => g.sources[0]).sort())
      .toEqual(["datagolf", "kalshi", "polymarket"]);
    for (const g of groups) {
      const pooled = ece(bySource(g.sources));
      const served = BY_SOURCE[g.sources[0]];
      const row = servedEceForRow(g.sources.length, false, served, pooled);
      const inputs = eceInputsForPanel(g.sources.length, false, served, row);
      const panel = inputs.publishedEce ?? inputs.pooledEce;
      expect({ provider: g.provider, row: row.toFixed(1) })
        .toEqual({ provider: g.provider, row: (panel as number).toFixed(1) });
    }
    // The production specimen, by name.
    const poly = servedEceForRow(1, false, BY_SOURCE.polymarket, ece(bySource(["polymarket"])));
    expect(poly.toFixed(1)).toBe("2.0");
  });

  it("a single-source row in the all-outcomes view takes the SERVED figure even where its own exact figure prints another digit", () => {
    // odds_api_bookmaker's real pair, as if it were a one-key provider:
    // exact 1.152 prints "1.2", served 1.15 prints "1.1" — the panel's digit.
    expect(servedEceForRow(1, false, 1.15, 1.152)).toBe(1.15);
    expect(servedEceForRow(1, false, 1.15, 1.152).toFixed(1)).toBe("1.1");
  });

  it("the row keeps its own pooled figure wherever the server did not measure its population", () => {
    // cohort-filtered: by_source is whole-population, so it is not this row's number
    expect(servedEceForRow(1, true, 1.96, 2.254)).toBe(2.254);
    // multi-key provider: no served row describes the pool
    expect(servedEceForRow(4, false, 1.15, 0.935)).toBe(0.935);
    // served row absent or not a number
    expect(servedEceForRow(1, false, undefined, 1.5)).toBe(1.5);
    expect(servedEceForRow(1, false, null, 1.5)).toBe(1.5);
    expect(servedEceForRow(1, false, Number.NaN, 1.5)).toBe(1.5);
  });

  it("the page's Source Comparison memo routes its ECE through servedEceForRow (the all-outcomes view is behind useState, so a static render cannot reach it)", () => {
    const src = fs.readFileSync(path.join(__dirname, "../app/calibration/page.tsx"), "utf8");
    const memo = src.slice(src.indexOf("const providerMetrics = useMemo("), src.indexOf("const sourceRows = useMemo("));
    expect(memo.length).toBeGreaterThan(0);
    expect(memo).toMatch(/ece:\s*servedEceForRow\(/);
    expect(memo).not.toMatch(/ece:\s*ece\(groupBuckets\)/);
  });

  it("aggregateBuckets keeps the displayed error at 0.1pp and carries the unrounded gap beside it", () => {
    for (const b of bySource(["polymarket"])) {
      expect(Math.round(b.error * 10) / 10).toBe(b.error);
      expect(typeof b.errorExact).toBe("number");
      expect(Math.abs(b.error - (b.errorExact as number))).toBeLessThanOrEqual(0.05 + 1e-9);
    }
  });
});
