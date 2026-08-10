// UX-P040 (#1638) — `is_winner: false` is a column default, not a verdict.
// UX-P044 (#1642) — and neither is a generic `resolution_source`.
//
// The rows below are the real shape production returned for event 15191121
// (Mariners @ Rays, final 4-1): 25 of 25 player props carrying
// `actual: null, hit: null, is_winner: false, resolution_source: null`.
//
// ONE ASSERTION BELOW WAS DELIBERATELY REVERSED. UX-P040 shipped a test named
// "believes is_winner once a resolution source proves grading happened". That
// is the exact inference #1642 [P1] rules out: a source proves that settlement
// TOUCHED the row, never what the verdict was, and it cannot express void or
// push. It is now asserted in the opposite direction, by name.

import {
  isGraded,
  readPropGrade,
  SETTLED_NO_GRADE_LABEL,
  type PropGradeFields,
} from "../../lib/propGrade";

/** Production row, 15191121 — never graded. */
const NEVER_GRADED: PropGradeFields = {
  actual: null,
  hit: null,
  is_winner: false,
  resolution_source: null,
};

// ---------------------------------------------------------------------------
// THE GATE. The ten cases below are transcribed VERBATIM from the landed corpus
// `backend/tests/evals/fixtures/settled_prop_grade_authority_contract.json`
// (commit `e33cf7aa`, oracle in
// `backend/scripts/evals/settled_prop_grade_authority_contract.py`).
//
// They are inlined rather than read across the package boundary on purpose:
// `e33cf7aa` is not on origin/master yet, and a gate that reads a file which
// may be absent is a gate that silently skips. Keep the two in sync by id.
// ---------------------------------------------------------------------------
type CorpusCase = {
  id: string;
  rows: PropGradeFields[];
  same_player_stat?: boolean;
  expected: { state: string; reason: string };
};

const CORPUS: CorpusCase[] = [
  {
    id: "ungraded_default_false",
    rows: [{ actual: null, hit: null, is_winner: false, resolution_source: null }],
    expected: { state: "WITHHOLD", reason: "no_typed_grade" },
  },
  {
    id: "generic_source_default_false",
    rows: [{ actual: null, hit: null, is_winner: false, resolution_source: "api_settlement" }],
    expected: { state: "WITHHOLD", reason: "no_typed_grade" },
  },
  {
    id: "void_source",
    rows: [{ actual: null, hit: null, is_winner: false, resolution_source: "void" }],
    expected: { state: "WITHHOLD", reason: "no_typed_grade" },
  },
  {
    id: "explicit_hit",
    rows: [{ actual: 2, hit: true, is_winner: true, resolution_source: "box_score" }],
    expected: { state: "HIT", reason: "explicit_hit" },
  },
  {
    id: "explicit_miss",
    rows: [{ actual: 0, hit: false, is_winner: false, resolution_source: "box_score" }],
    expected: { state: "MISS", reason: "explicit_hit" },
  },
  {
    id: "actual_zero_only",
    rows: [{ actual: 0, hit: null, is_winner: false, resolution_source: null }],
    expected: { state: "ACTUAL_ONLY", reason: "no_explicit_verdict" },
  },
  {
    id: "partial_ladder_one_explicit",
    rows: [
      { actual: 2, hit: true },
      { actual: 2, hit: null },
    ],
    expected: { state: "HIT", reason: "explicit_hit" },
  },
  {
    id: "ladder_thresholds_disagree",
    rows: [
      { actual: 2, hit: true },
      { actual: 2, hit: false },
    ],
    expected: { state: "WITHHOLD", reason: "conflicting_rung_verdicts" },
  },
  {
    id: "mixed_players_one_graded",
    same_player_stat: false,
    rows: [
      { actual: 1, hit: true },
      { actual: null, hit: null },
    ],
    expected: { state: "WITHHOLD", reason: "mixed_entity_group" },
  },
  {
    id: "empty_group",
    rows: [],
    expected: { state: "WITHHOLD", reason: "no_typed_grade" },
  },
];

describe("readPropGrade — the settled prop grade authority corpus (e33cf7aa)", () => {
  it.each(CORPUS.map((c) => [c.id, c] as const))("%s", (_id, c) => {
    const grade = readPropGrade(c.rows, { samePlayerStat: c.same_player_stat ?? true });
    expect({ state: grade.state, reason: grade.reason }).toEqual(c.expected);
  });

  it("covers every case in the fixture", () => {
    expect(CORPUS).toHaveLength(10);
    expect(new Set(CORPUS.map((c) => c.id)).size).toBe(10);
  });
});

// ---------------------------------------------------------------------------
describe("readPropGrade — the production regressions", () => {
  it("withholds for the 15191121 shape (#1638)", () => {
    expect(readPropGrade([NEVER_GRADED]).state).toBe("WITHHOLD");
  });

  it("withholds for a whole ladder of them", () => {
    const ladder = [0.5, 1.5, 2.5].map(() => ({ ...NEVER_GRADED }));
    expect(readPropGrade(ladder).state).toBe("WITHHOLD");
  });

  it("withholds for an empty stat", () => {
    expect(readPropGrade([]).state).toBe("WITHHOLD");
  });

  // REVERSED from UX-P040. This is the 70-card production defect: a generic
  // source plus the column default rendered a confident red MISS.
  it("does NOT believe is_winner just because a resolution source exists (#1642)", () => {
    const g = readPropGrade([
      { hit: null, actual: null, is_winner: false, resolution_source: "api_settlement" },
    ]);
    expect(g.state).toBe("WITHHOLD");
    expect(g.reason).toBe("no_typed_grade");
    expect(g.hit).toBeNull();
  });

  it("does not manufacture a HIT from is_winner: true either", () => {
    const g = readPropGrade([
      { hit: null, actual: null, is_winner: true, resolution_source: "api_settlement" },
    ]);
    expect(g.state).toBe("WITHHOLD");
  });

  it("withholds the group verdict when a ladder's rungs disagree (#1642 P2)", () => {
    // Order must not decide it: a real player with exactly 1 hit is HIT at 1+
    // and MISS at 2+.
    const asc: PropGradeFields[] = [
      { hit: true, actual: 1 },
      { hit: false, actual: 1 },
    ];
    const desc = [...asc].reverse();
    expect(readPropGrade(asc).state).toBe("WITHHOLD");
    expect(readPropGrade(desc).state).toBe("WITHHOLD");
    expect(readPropGrade(asc).reason).toBe("conflicting_rung_verdicts");
  });

  it("refuses a group whose rows are not one player+stat (#1642 P1b)", () => {
    const g = readPropGrade([{ hit: true, actual: 4 }], { samePlayerStat: false });
    expect(g.state).toBe("WITHHOLD");
    expect(g.reason).toBe("mixed_entity_group");
    // The borrowed evidence must not leak out with the refusal.
    expect(g.actual).toBeNull();
  });
});

// The other direction, per gotcha #43: suppression is the sharp edge, so a
// genuinely graded prop must survive exactly as before. On the measured
// production cohort this is the majority — 367 of 561 rows.
describe("readPropGrade — genuinely graded props still grade", () => {
  it("believes an explicit hit", () => {
    expect(readPropGrade([{ hit: true, actual: 3, is_winner: false }])).toEqual({
      state: "HIT",
      reason: "explicit_hit",
      hit: true,
      actual: 3,
    });
  });

  it("believes an explicit miss", () => {
    expect(readPropGrade([{ hit: false, actual: 0, is_winner: false }])).toEqual({
      state: "MISS",
      reason: "explicit_hit",
      hit: false,
      actual: 0,
    });
  });

  it("returns the actual with no verdict when only the actual landed", () => {
    expect(readPropGrade([{ actual: 0, hit: null, is_winner: false }])).toEqual({
      state: "ACTUAL_ONLY",
      reason: "no_explicit_verdict",
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
    expect(readPropGrade(rungs)).toEqual({
      state: "HIT",
      reason: "explicit_hit",
      hit: true,
      actual: 2,
    });
  });

  it("treats actual: 0 as a real actual, not a falsy absence", () => {
    expect(readPropGrade([{ actual: 0, hit: false, is_winner: false }]).actual).toBe(0);
  });

  it("agreeing rungs are not a conflict", () => {
    const g = readPropGrade([{ hit: true, actual: 5 }, { hit: true, actual: 5 }]);
    expect(g.state).toBe("HIT");
  });

  it("samePlayerStat defaults to true, so existing call sites are unaffected", () => {
    expect(readPropGrade([{ hit: true, actual: 1 }]).state).toBe("HIT");
  });
});

describe("isGraded / SETTLED_NO_GRADE_LABEL", () => {
  it("is false only for WITHHOLD", () => {
    expect(isGraded(readPropGrade([{ hit: true }]))).toBe(true);
    expect(isGraded(readPropGrade([{ actual: 3 }]))).toBe(true);
    expect(isGraded(readPropGrade([NEVER_GRADED]))).toBe(false);
  });

  // #1650: the phrase has ONE definition so two surfaces cannot drift apart.
  it("exports one settled-state phrase", () => {
    expect(SETTLED_NO_GRADE_LABEL).toBe("Resolved · grading unavailable");
  });
});
