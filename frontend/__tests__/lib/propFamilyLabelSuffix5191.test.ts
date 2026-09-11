// #5191 — the rung that spends its whole width restating its own header.
//
// WHAT A READER SAW (`/events/15308050`, Tampa Bay @ Atlanta, 390px):
//
//     FIRST 5 INNINGS TOTAL
//     Over 0.5 runs in the first 5 inn…      7 runs — hit
//     Over 1.5 runs in the first 5 inn…      7 runs — hit
//     …
//
// MEASURED, not eyeballed: `artifacts/ux-1200/truncation-probe.mjs` asks the
// browser which labels are actually clipped (`scrollWidth > clientWidth` on the
// span that carries `truncate`) at 390px. On production before this change,
// 7 of 7 rungs of that family clipped, 23 of 269 labels page-wide.
//
// And on the real payload of `/api/events/15308050/game-markets`: 19 of 91
// families / 54 of 269 rows carry a shared trailing phrase, and NO player-prop
// family does — "Under", "Griffin Jax: 6+" share no suffix at all.
//
// THE TEST THAT EARNS ITS PLACE IS "the spread keeps its handicap". The obvious
// reading of the bug — strip whatever the siblings share — passes every other
// test in this file and quietly deletes the line from `Atlanta -1.5 first 5
// innings`. Sharedness cannot tell boilerplate from meaning; only the header
// can, which is why the rule is keyed on what the header already says. That is
// the same lesson #4866 wrote down one function up, from the other direction.

// MUTANTS. Anchoring removed → 1 killed. The load-bearing-token check removed →
// 2 killed. The word-boundary walk started at index 0 → 8 killed. The early
// `if (!head) return ""` removed → SURVIVED, and it is an EQUIVALENT mutant, not
// a hole: with no header the token set is empty, so the anchoring clause can
// never be satisfied and the function returns "" by the longer road. Proven by
// removing BOTH — that compound mutant is killed by "NO HEADER, NO STRIP" below.
// The early return is a fast path and a statement of intent; the rule it looks
// like it enforces is enforced one clause down.

import { sharedLabelSuffix, stripSharedLabelSuffix } from "@/lib/propFamily";

describe("sharedLabelSuffix", () => {
  test("THE FILED DEFECT: the words the header already says", () => {
    const rungs = [
      "Over 0.5 runs in the first 5 innings",
      "Over 1.5 runs in the first 5 innings",
      "Over 2.5 runs in the first 5 innings",
    ];
    expect(sharedLabelSuffix(rungs, "First 5 Innings Total")).toBe(
      " runs in the first 5 innings",
    );
    expect(stripSharedLabelSuffix(rungs, "First 5 Innings Total")).toEqual([
      "Over 0.5",
      "Over 1.5",
      "Over 2.5",
    ]);
  });

  test("THE GUARD: a spread keeps its handicap and loses only the window", () => {
    expect(
      stripSharedLabelSuffix(
        [
          "Atlanta -1.5 first 5 innings",
          "Atlanta -2.5 first 5 innings",
          "Tampa Bay -1.5 first 5 innings",
        ],
        "First 5 Spread",
      ),
    ).toEqual(["Atlanta -1.5", "Atlanta -2.5", "Tampa Bay -1.5"]);
  });

  test("THE GUARD: a number the header does not name is never dropped", () => {
    // Both legs on the same handicap, so the raw common suffix reaches `-1.5`.
    // The rule retreats to the boundary the header covers instead of taking it.
    expect(
      stripSharedLabelSuffix(
        ["Atlanta -1.5 first 5 innings", "Tampa Bay -1.5 first 5 innings"],
        "First 5 Spread",
      ),
    ).toEqual(["Atlanta -1.5", "Tampa Bay -1.5"]);
  });

  test("THE GUARD: a team name in the suffix that the header does not carry stays", () => {
    const legs = ["Over 4.5 Atlanta runs in the 1st", "Under 4.5 Atlanta runs in the 1st"];
    // "1st" anchors the suffix, but "Atlanta" is load-bearing and the header
    // does not name it — so the rule retreats past it instead of taking it.
    expect(stripSharedLabelSuffix(legs, "1st Inning Total")).toEqual([
      "Over 4.5 Atlanta",
      "Under 4.5 Atlanta",
    ]);
    // Named by the header, it goes.
    expect(stripSharedLabelSuffix(legs, "Atlanta 1st Inning Total")).toEqual([
      "Over 4.5",
      "Under 4.5",
    ]);
  });

  test("never cuts a number in half — the boundary is a whole word", () => {
    // The raw longest common suffix here is ".5 runs in the 6th inning".
    expect(
      stripSharedLabelSuffix(
        ["Over 0.5 runs in the 6th inning", "Over 1.5 runs in the 6th inning"],
        "6th Inning Total",
      ),
    ).toEqual(["Over 0.5", "Over 1.5"]);
  });

  test("an inning winner keeps the side and drops the inning", () => {
    expect(
      stripSharedLabelSuffix(
        ["Tie 5th inning", "Atlanta wins 5th inning", "Tampa Bay wins 5th inning"],
        "5th Inning Winner",
      ),
    ).toEqual(["Tie", "Atlanta wins", "Tampa Bay wins"]);
  });

  test("PLAYER PROPS ARE UNTOUCHED — they share no suffix", () => {
    const player = ["Over", "Under"];
    expect(sharedLabelSuffix(player, "Drake Baldwin: Hits O/U 2.5")).toBe("");
    const plusRungs = ["Griffin Jax: 6+", "Griffin Jax: 7+", "Griffin Jax: 9+"];
    expect(stripSharedLabelSuffix(plusRungs, "Strikeouts")).toEqual(plusRungs);
  });

  test("an odd one out protects the whole family", () => {
    // "Tie" shares nothing with the other two, so there is no common suffix and
    // the family is left alone — the fail-safe, not a special case.
    const legs = ["Tampa Bay wins first 5 innings", "Tie", "Atlanta wins first 5 innings"];
    expect(stripSharedLabelSuffix(legs, "First 5 Innings")).toEqual(legs);
  });

  test("NO HEADER, NO STRIP — the words must have somewhere to land", () => {
    const rungs = [
      "Over 0.5 runs in the first 5 innings",
      "Over 1.5 runs in the first 5 innings",
    ];
    expect(sharedLabelSuffix(rungs, null)).toBe("");
    expect(sharedLabelSuffix(rungs, "   ")).toBe("");
    expect(stripSharedLabelSuffix(rungs, null)).toEqual(rungs);
  });

  test("one label is never evidence of boilerplate", () => {
    expect(sharedLabelSuffix(["Over 0.5 runs in the first 5 innings"], "First 5 Innings Total")).toBe("");
    // Two ROWS, one distinct label, is still one label.
    expect(
      sharedLabelSuffix(
        ["Over 0.5 runs in the 6th inning", "Over 0.5 runs in the 6th inning"],
        "6th Inning Total",
      ),
    ).toBe("");
  });

  test("a label that IS the shared phrase leaves the whole family alone", () => {
    // Not parallel labels. Every retreat from here yields fragments ("first" /
    // "Over 0.5 first"), so the family is refused outright rather than shortened.
    const legs = ["first 5 innings", "Over 0.5 first 5 innings"];
    expect(sharedLabelSuffix(legs, "First 5 Innings Total")).toBe("");
    expect(stripSharedLabelSuffix(legs, "First 5 Innings Total")).toEqual(legs);
  });

  test("ANCHORED: a shared phrase the header never says is not boilerplate", () => {
    // ` runs` carries nothing load-bearing, so the token guard alone would drop
    // it — but TEAM TOTAL does not say "runs", so dropping it costs the reader
    // the unit and gains them nothing.
    const legs = ["Over 4.5 Atlanta runs", "Under 4.5 Atlanta runs"];
    expect(sharedLabelSuffix(legs, "Team Total")).toBe("");
    expect(stripSharedLabelSuffix(legs, "Team Total")).toEqual(legs);
  });

  test("index-preserving, so a caller can zip against its own ordering", () => {
    const legs = [
      "Over 1.5 runs in the 3rd inning",
      "Over 0.5 runs in the 3rd inning",
    ];
    const out = stripSharedLabelSuffix(legs, "3rd Inning Total");
    expect(out).toHaveLength(2);
    expect(out[0]).toBe("Over 1.5");
    expect(out[1]).toBe("Over 0.5");
  });

  test("distinct labels stay distinct — a strip can never merge two rows", () => {
    const legs = [
      "Over 0.5 runs in the 2nd inning",
      "Over 1.5 runs in the 2nd inning",
    ];
    const out = stripSharedLabelSuffix(legs, "2nd Inning Total");
    expect(new Set(out).size).toBe(out.length);
  });
});
