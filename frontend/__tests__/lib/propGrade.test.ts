// UX-P040 (#1638) — `is_winner: false` is a column default, not a verdict.
//
// The rows below are the real shape production returned for event 15191121
// (Mariners @ Rays, final 4-1): 25 of 25 player props carrying
// `actual: null, hit: null, is_winner: false, resolution_source: null`.
// The old test (`is_winner != null`) read every one of them as a graded loss.

import { hasGradeEvidence, readPropGrade, type PropGradeFields } from "../../lib/propGrade";

/** Production row, 15191121 — never graded. */
const NEVER_GRADED: PropGradeFields = {
  actual: null,
  hit: null,
  is_winner: false,
  resolution_source: null,
};

describe("hasGradeEvidence", () => {
  it("does not accept a defaulted is_winner as evidence", () => {
    expect(hasGradeEvidence(NEVER_GRADED)).toBe(false);
    expect(hasGradeEvidence({ is_winner: true })).toBe(false);
  });

  it("accepts a published actual, hit, or resolution source", () => {
    expect(hasGradeEvidence({ actual: 2 })).toBe(true);
    expect(hasGradeEvidence({ hit: false })).toBe(true);
    expect(hasGradeEvidence({ resolution_source: "kalshi_api" })).toBe(true);
  });

  it("treats a blank resolution source as absent", () => {
    expect(hasGradeEvidence({ resolution_source: "   " })).toBe(false);
    expect(hasGradeEvidence({ resolution_source: "" })).toBe(false);
  });

  it("is not fooled by a row that is empty apart from is_winner", () => {
    expect(hasGradeEvidence({})).toBe(false);
  });
});

describe("readPropGrade — the production regression", () => {
  it("reports NOT graded for the 15191121 shape", () => {
    expect(readPropGrade([NEVER_GRADED])).toEqual({ graded: false });
  });

  it("reports NOT graded for a whole ladder of them", () => {
    const ladder = [0.5, 1.5, 2.5].map(() => ({ ...NEVER_GRADED }));
    expect(readPropGrade(ladder)).toEqual({ graded: false });
  });

  it("reports NOT graded for an empty stat", () => {
    expect(readPropGrade([])).toEqual({ graded: false });
  });
});

// The other direction, per gotcha #43: suppression is the sharp edge, so a
// genuinely graded prop must survive exactly as before.
describe("readPropGrade — genuinely graded props still grade", () => {
  it("believes an explicit hit", () => {
    expect(readPropGrade([{ hit: true, actual: 3, is_winner: false }])).toEqual({
      graded: true,
      hit: true,
      actual: 3,
    });
  });

  it("believes is_winner once a resolution source proves grading happened", () => {
    expect(
      readPropGrade([{ hit: null, actual: null, is_winner: false, resolution_source: "kalshi_api" }]),
    ).toEqual({ graded: true, hit: false, actual: null });
  });

  it("returns the actual with no verdict when only the actual landed", () => {
    expect(readPropGrade([{ actual: 0, hit: null, is_winner: false }])).toEqual({
      graded: true,
      hit: null,
      actual: 0,
    });
  });

  it("finds the actual and the verdict on different rungs of one ladder", () => {
    const rungs: PropGradeFields[] = [
      { actual: null, hit: null, is_winner: false, resolution_source: null },
      { actual: 2, hit: null, is_winner: false, resolution_source: null },
      { actual: null, hit: true, is_winner: true, resolution_source: null },
    ];
    expect(readPropGrade(rungs)).toEqual({ graded: true, hit: true, actual: 2 });
  });

  it("treats actual: 0 as a real actual, not a falsy absence", () => {
    const g = readPropGrade([{ actual: 0, hit: false, is_winner: false }]);
    expect(g).toEqual({ graded: true, hit: false, actual: 0 });
  });
});
