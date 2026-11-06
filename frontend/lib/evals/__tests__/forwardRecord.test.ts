/**
 * #12102 S3 — the forward record on /evals is /about's figure and
 * /calibration's curve, computed by their code, on the same payload.
 *
 * The plan's acceptance: on a fixture payload the figure equals /about's proof
 * figure and the curve equals /calibration's default series; the outcome count
 * is the cohort's, never `total_outcomes`; an older payload renders the
 * staleness sentence (the render half is in evalsPage.test.tsx).
 */

import { readFileSync } from "fs";
import { join } from "path";

import { normalizeCat } from "@/lib/calibrationCategories";
import { compactOutcomeCount, proofCohortFigures } from "@/lib/calibrationProofFigures";
import { aggregateBuckets, cohortFilterFor } from "@/lib/calibrationParity";
import { calibrationFixture, calibrationFixtureBuckets } from "@/lib/evals/fixtures/calibration";
import {
  CHART_THIN_FLOOR,
  DEFAULT_CURVE_COLOR,
  barPointsText,
  forwardRecordView,
} from "@/lib/evals/forwardRecord";

const CALIBRATION_PAGE = readFileSync(join(__dirname, "..", "..", "..", "app", "calibration", "page.tsx"), "utf8");

describe("the figure is /about's", () => {
  const view = forwardRecordView(calibrationFixture());
  const about = proofCohortFigures(calibrationFixtureBuckets());

  it("same cohort, same error, same count, printed the way /about prints them", () => {
    expect(about).not.toBeNull();
    expect(view.proof?.errorPp).toBe(about?.errorPp);
    expect(view.proof?.outcomes).toBe(about?.outcomes);
    // app/about/page.tsx: `figures.errorPp.toFixed(1)` and `compactOutcomeCount(figures.outcomes)`.
    expect(view.proof?.errorText).toBe(about?.errorPp.toFixed(1));
    expect(view.proof?.outcomesText).toBe(compactOutcomeCount(about?.outcomes));
  });

  it("the count is the traded cohort's, never the payload's total_outcomes", () => {
    const traded = calibrationFixtureBuckets()
      .filter((b) => b.price_moved !== false)
      .reduce((s, b) => s + b.n, 0);
    expect(view.proof?.outcomes).toBe(traded);
    expect(view.proof?.outcomes).not.toBe(calibrationFixture().total_outcomes);
  });

  it("a payload with nothing measurable gives no figure rather than a zero", () => {
    expect(forwardRecordView(calibrationFixture({ buckets: [] })).proof).toBeNull();
    expect(forwardRecordView(null).proof).toBeNull();
  });
});

describe("the curve is /calibration's default series", () => {
  it("equals aggregateBuckets over the page's normalized rows with the default cohort filter", () => {
    const rows = calibrationFixtureBuckets();
    // app/calibration/page.tsx: `normalized` renames categories, then
    // `aggregateBuckets(normalized, cohortFilterFor(includeNeverMoved=false))`.
    const normalized = rows.map((b) => ({ ...b, category: normalizeCat(b.category) }));
    const page = aggregateBuckets(normalized, cohortFilterFor(false));
    expect(forwardRecordView(calibrationFixture()).curve?.data).toEqual(page);
  });

  it("is labelled the way /calibration labels it: the cohort's short label and its count", () => {
    const view = forwardRecordView(calibrationFixture());
    expect(view.curve?.label).toBe(`Traded (${view.proof?.outcomes.toLocaleString()})`);
  });

  it("is drawn with /calibration's thin-bucket floor and its default colour", () => {
    const floor = /const MIN_CHART_BUCKET_N = (\d+);/.exec(CALIBRATION_PAGE);
    expect(floor).not.toBeNull();
    expect(CHART_THIN_FLOOR).toBe(Number(floor?.[1]));
    expect(CALIBRATION_PAGE).toContain(`includeNeverMoved ? "#2563eb" : "${DEFAULT_CURVE_COLOR}"`);
  });
});

describe("the categories meter reads the scorecard, all three numbers", () => {
  it("at the bar, out of the total, and the bar in points", () => {
    expect(forwardRecordView(calibrationFixture()).categories).toEqual({ atBar: 24, total: 53, barPp: 3 });
    expect(barPointsText(3)).toBe("3");
    expect(barPointsText(2.5)).toBe("2.5");
  });

  it("an unreadable or impossible scorecard shows no meter", () => {
    for (const scorecard of [
      undefined,
      {},
      { categories_at_bar: 24, categories_total: 53 },
      { categories_at_bar: 60, categories_total: 53, categories_bar_pp: 3 },
      { categories_at_bar: "24", categories_total: 53, categories_bar_pp: 3 },
    ]) {
      expect(forwardRecordView(calibrationFixture({ scorecard })).categories).toBeNull();
    }
  });
});

describe("the LIVE stamp and the staleness notice come from the payload", () => {
  it("as of the payload's own generated_at", () => {
    expect(forwardRecordView(calibrationFixture()).generatedAt).toBe("2026-11-06T03:28:13.171793+00:00");
    expect(forwardRecordView(calibrationFixture({ generated_at: undefined })).generatedAt).toBeNull();
  });

  it("frozen inputs under a current curve give the accuracy page's notice; a fresh payload gives none", () => {
    const stale = forwardRecordView(calibrationFixture()).staleness;
    expect(stale?.kind).toBe("frozen-inputs");
    expect(stale?.stagedAt).toBe("2026-10-27T20:54:56+00:00");
    expect(forwardRecordView(calibrationFixture({ availability: "fresh" })).staleness).toBeNull();
  });
});
