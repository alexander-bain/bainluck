/**
 * #994 — a DataGolf bucket opens the exact outcomes the published chart counted.
 *
 * When the backend proves a sample came from the chart's own published
 * membership, the footer says so plainly; a grade corrected since the chart was
 * built is shown as corrected, never as today's grade; and the page tells the
 * backend which chart is on screen so a page left open across a publish is not
 * answered from a newer chart's membership.
 */

import { readFileSync } from "fs";
import { join } from "path";

import type { CalibrationExample } from "@/lib/api";
import {
  EXAMPLES_FOOTER_CURRENT_ROWS,
  EXAMPLES_FOOTER_DEFAULT,
  EXAMPLES_FOOTER_PUBLISHED,
  correctedGradeNote,
  examplesFooterCopy,
} from "@/lib/calibrationExamples";

const base: CalibrationExample = {
  market_name: "Open - Make the Cut",
  outcome_name: "Player",
  price: 0.61,
  result: "No",
  settle_date: null,
};

describe("the published-membership footer", () => {
  it("says the rows are the chart's own when the backend verified it", () => {
    expect(
      examplesFooterCopy({ basis: "published_generation", published_generation_membership: "verified" }),
    ).toBe(EXAMPLES_FOOTER_PUBLISHED);
  });

  it("never claims it without the verification", () => {
    expect(
      examplesFooterCopy({ basis: "published_generation", published_generation_membership: "unverified" }),
    ).toBe(EXAMPLES_FOOTER_DEFAULT);
    expect(
      examplesFooterCopy({ basis: "live_canonical_population", published_generation_membership: "unverified" }),
    ).toBe(EXAMPLES_FOOTER_CURRENT_ROWS);
  });

  it("is short, plain and free of implementation words", () => {
    expect(EXAMPLES_FOOTER_PUBLISHED).toMatch(/not the full bucket/);
    for (const word of ["generation", "canonical", "population", "membership", "cohort", "verified"]) {
      expect(EXAMPLES_FOOTER_PUBLISHED.toLowerCase()).not.toContain(word);
    }
    expect(EXAMPLES_FOOTER_PUBLISHED.length).toBeLessThan(100);
  });
});

describe("correctedGradeNote", () => {
  it("is silent when the published grade still stands", () => {
    expect(correctedGradeNote({ ...base, result_basis: "published", grade_changed_since_publish: false })).toBeNull();
  });

  it("names today's grade when it was corrected since", () => {
    expect(
      correctedGradeNote({
        ...base, result_basis: "published", current_result: "Yes", grade_changed_since_publish: true,
      }),
    ).toBe("now Yes");
  });

  it("says ungraded when the grade was withdrawn", () => {
    expect(
      correctedGradeNote({
        ...base, result_basis: "published", current_result: null, grade_changed_since_publish: true,
      }),
    ).toBe("now ungraded");
  });

  it("does nothing for a live example, which has no published grade", () => {
    expect(correctedGradeNote({ ...base, grade_changed_since_publish: true })).toBeNull();
  });
});

describe("the calibration page wires it", () => {
  const page = readFileSync(join(__dirname, "../../app/calibration/page.tsx"), "utf8");
  const api = readFileSync(join(__dirname, "../../lib/api.ts"), "utf8");

  it("sends the on-screen chart's generated_at with the drill-in request", () => {
    expect(page).toMatch(/fetchCalibrationExamples\(\s*source, bucketIdx, !includeNeverMoved, data\?\.generated_at \?\? null,/);
    expect(api).toContain('if (generation) params.set("generation", generation);');
  });

  it("renders the corrected-grade note in both the phone list and the table", () => {
    expect(page.match(/correctedGradeNote\(ex\) && \(/g)?.length).toBe(2);
  });
});
