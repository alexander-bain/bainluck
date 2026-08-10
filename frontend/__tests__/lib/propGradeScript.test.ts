// UX-P044 (#1650) — the WHAT HIT row and the Player Props card describe one
// backend state with one vocabulary.
//
// The event page shows the same settled prop twice, graded by two different
// deciders: the card by `readPropGrade` (client), the WHAT HIT row by
// `_build_props_script` (backend, `app/routes/events.py`). The backend builder
// carries the identical defect UX-P044 removed from the client:
//
//     if hit is None and pp.get("resolution_source"):
//         hit = bool(is_winner)
//
// so on a settled game the card said "Resolved · grading unavailable" while the
// row underneath said "Miss" about the same prop. `routes/events.py` belongs to
// the latency lane (#1494), so the page re-derives the row's verdict from the
// raw typed rows that ride the SAME payload — reading `hit`, never deriving it.

import {
  indexPropRowsByScriptKey,
  verifyScriptGrade,
  type RawPropRow,
  type ScriptGradeMark,
} from "../../lib/propGrade";

const MARKET = "Tampa Bay Rays vs. Seattle Mariners - Player Props";
const key = (outcome: string) => `${MARKET}|${outcome}`;

const row = (outcome: string, fields: Partial<RawPropRow> = {}): RawPropRow => ({
  market_name: MARKET,
  outcome_name: outcome,
  actual: null,
  hit: null,
  is_winner: false,
  resolution_source: null,
  ...fields,
});

describe("indexPropRowsByScriptKey", () => {
  it("keys on `market_name|outcome_name`, exactly as _build_props_script does", () => {
    const index = indexPropRowsByScriptKey([row("Cole Young: Hits O/U 0.5")]);
    expect(index.has(key("Cole Young: Hits O/U 0.5"))).toBe(true);
  });

  it("keeps every row under a colliding key instead of letting the last one win", () => {
    const index = indexPropRowsByScriptKey([
      row("Cole Young: Hits O/U 0.5", { hit: true }),
      row("Cole Young: Hits O/U 0.5", { hit: false }),
    ]);
    expect(index.get(key("Cole Young: Hits O/U 0.5"))).toHaveLength(2);
  });

  it("tolerates a null/absent list and null name fields", () => {
    expect(indexPropRowsByScriptKey(null).size).toBe(0);
    expect(indexPropRowsByScriptKey(undefined).size).toBe(0);
    expect(indexPropRowsByScriptKey([{ hit: true }]).get("|")).toHaveLength(1);
  });
});

describe("verifyScriptGrade — the backend twin of #1642", () => {
  const mark = (outcome: string, over: Partial<ScriptGradeMark> = {}): ScriptGradeMark => ({
    key: key(outcome),
    graded_result: "miss",
    graded_label: null,
    ...over,
  });

  it("drops a 'miss' the backend built from a source plus a defaulted false", () => {
    const index = indexPropRowsByScriptKey([
      row("Cole Young: Hits O/U 0.5", { resolution_source: "api_settlement", is_winner: false }),
    ]);
    expect(verifyScriptGrade(mark("Cole Young: Hits O/U 0.5"), index)).toEqual({
      graded_result: null,
      graded_label: null,
    });
  });

  it("drops the label with the verdict, so '0 — miss' cannot survive it", () => {
    const index = indexPropRowsByScriptKey([
      row("Cole Young: Hits O/U 0.5", { resolution_source: "api_settlement" }),
    ]);
    const out = verifyScriptGrade(
      mark("Cole Young: Hits O/U 0.5", { graded_label: "0 — miss" }),
      index,
    );
    expect(out.graded_label).toBeNull();
  });

  it("withholds when the rows carrying that key disagree", () => {
    const index = indexPropRowsByScriptKey([
      row("Cole Young: Hits O/U 0.5", { hit: true, actual: 1 }),
      row("Cole Young: Hits O/U 0.5", { hit: false, actual: 1 }),
    ]);
    expect(verifyScriptGrade(mark("Cole Young: Hits O/U 0.5", { graded_result: "hit" }), index)
      .graded_result).toBeNull();
  });

  // Both directions (gotcha #43): the majority case must pass through untouched.
  it("keeps a verdict the backend derived from a real box-score hit", () => {
    const index = indexPropRowsByScriptKey([
      row("Cole Young: Hits O/U 0.5", { hit: true, actual: 2, resolution_source: "box_score" }),
    ]);
    expect(
      verifyScriptGrade(
        mark("Cole Young: Hits O/U 0.5", { graded_result: "hit", graded_label: "2 — hit" }),
        index,
      ),
    ).toEqual({ graded_result: "hit", graded_label: "2 — hit" });
  });

  it("keeps a real miss", () => {
    const index = indexPropRowsByScriptKey([
      row("Cole Young: Hits O/U 1.5", { hit: false, actual: 1, resolution_source: "box_score" }),
    ]);
    expect(verifyScriptGrade(mark("Cole Young: Hits O/U 1.5"), index).graded_result).toBe("miss");
  });

  it("leaves an already-ungraded mark alone", () => {
    const index = indexPropRowsByScriptKey([row("Cole Young: Hits O/U 0.5")]);
    expect(
      verifyScriptGrade(mark("Cole Young: Hits O/U 0.5", { graded_result: null }), index),
    ).toEqual({ graded_result: null, graded_label: null });
  });

  it("passes 'push' through — a typed verdict this module does not model", () => {
    const index = indexPropRowsByScriptKey([
      row("Cole Young: Hits O/U 0.5", { resolution_source: "api_settlement" }),
    ]);
    expect(
      verifyScriptGrade(mark("Cole Young: Hits O/U 0.5", { graded_result: "push" }), index)
        .graded_result,
    ).toBe("push");
  });

  // Conservative on the edge: a lookup failure must not blank a real grade.
  it("passes through unchanged when the raw rows cannot be found", () => {
    const empty = indexPropRowsByScriptKey([]);
    expect(
      verifyScriptGrade(mark("Cole Young: Hits O/U 0.5", { graded_result: "hit" }), empty)
        .graded_result,
    ).toBe("hit");
  });

  it("passes through unchanged when the mark carries no key", () => {
    const index = indexPropRowsByScriptKey([row("Cole Young: Hits O/U 0.5")]);
    expect(
      verifyScriptGrade({ key: null, graded_result: "hit", graded_label: null }, index)
        .graded_result,
    ).toBe("hit");
  });

  it("accepts a numeric key, which the page falls back to", () => {
    const index = indexPropRowsByScriptKey([row("Cole Young: Hits O/U 0.5")]);
    expect(verifyScriptGrade({ key: 3, graded_result: "hit" }, index).graded_result).toBe("hit");
  });
});
