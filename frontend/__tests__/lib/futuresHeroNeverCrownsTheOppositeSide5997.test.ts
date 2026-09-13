// THE HERO MUST NOT PRINT "Yes" OVER THE `No` ROW'S NUMBER — #5997, lane1b/224.
//
// The futures hero features whichever outcome LEADS, and on a binary market that
// is routinely the `No` row — 3,768 unresolved binary markets have a leading (or
// sole-priced) `No` (measured 2026-09-13). Every label on the page then went
// through a "generic names read better as Yes" substitution, so:
//
//   /futures/20571021   payload Yes: null, No: 0.39    hero read "39% / Yes"
//   /futures/16634786   payload Yes: null, No: 0.664   hero read "66% / Yes"
//
// and the caption read "Yes down 14.6 pts from opening" about the No row's
// journey (81 → 66). The number was right and the name above it was the opposite
// side of the question.
//
// The rule this file pins: "Yes" is a substitution for names that carry NO
// answer — "May 18", "2026", "Option A", a bare number. A name that states its
// own side is printed as served. Both halves are asserted here, because a fix
// that simply stopped substituting would take the readable hero off every
// date-named outcome in the process.

import {
  heroOutcomeLabel,
  isGenericOutcomeName,
  leaderLabel,
  movementExplanation,
  statesItsOwnSide,
} from "@/lib/futuresDetailDisplay";

describe("a name that states its own side is never replaced by \"Yes\"", () => {
  it.each([
    ["No", "No"],
    ["no", "no"],
    ["No team scores a TD", "No team scores a TD"],
    ["Under 100", "Under 100"],
    ["under", "under"],
    ["Below 5.5", "Below 5.5"],
    ["Less than 3", "Less than 3"],
    ["Fewer than 3", "Fewer than 3"],
    ["At most 2", "At most 2"],
    ["<=50", "<=50"],
  ])("heroOutcomeLabel(%p) is %p", (served, expected) => {
    expect(heroOutcomeLabel(served)).toBe(expected);
  });

  it.each([
    ["Yes", "Yes"],
    ["Over 5.5", "Over 5.5"],
    ["At least 2", "At least 2"],
  ])("leaves the affirmative side alone too: %p stays %p", (served, expected) => {
    // Not a no-op assertion: "Yes" and "Over 5.5" reached the old substitution
    // by different rungs (the <=3-char rule and the threshold rule), and a fix
    // written as "only stop for negatives" would print "Yes" over "Over 5.5"
    // while the row beside it said "Under 5.5". Both sides state a side.
    expect(heroOutcomeLabel(served)).toBe(expected);
  });

  it("still substitutes for a name that carries no answer at all", () => {
    // THE CONTROL (gotcha #43). Without these, a fix that deleted the
    // substitution entirely would pass every assertion above and leave a hero
    // reading "62% / May 18".
    expect(heroOutcomeLabel("May 18")).toBe("Yes");
    expect(heroOutcomeLabel("2026")).toBe("Yes");
    expect(heroOutcomeLabel("Option A")).toBe("Yes");
    expect(heroOutcomeLabel("Q3 2026")).toBe("Yes");
    expect(heroOutcomeLabel("42.5")).toBe("Yes");
  });

  it("never touches a real entity name", () => {
    expect(heroOutcomeLabel("Kendrick Lamar")).toBe("Kendrick Lamar");
    expect(heroOutcomeLabel("Manchester City")).toBe("Manchester City");
  });

  it("keeps `isGenericOutcomeName` itself unchanged", () => {
    // The wide predicate was MOVED by this ship, not edited. It still answers
    // true for a side-stating name; `heroOutcomeLabel` is what declines to act
    // on that answer. Asserting it here is what makes the move provable.
    expect(isGenericOutcomeName("No")).toBe(true);
    expect(isGenericOutcomeName("Under 100")).toBe(true);
    expect(isGenericOutcomeName("May 18")).toBe(true);
    expect(isGenericOutcomeName("Kendrick Lamar")).toBe(false);
  });
});

describe("the movement caption names the same side the hero does", () => {
  it("says `No` about the No row's journey", () => {
    // lane1b/224's `/futures/16634786`: 0.81 → 0.664 on the No row, printed as
    // "Yes down 14.6 pts from opening."
    expect(
      movementExplanation({ name: "No", probability: 0.664, opening_probability: 0.81 }),
    ).toBe("No down 14.6 pts from opening.");
  });

  it("still says `Yes` when the leader has no name at all", () => {
    // The empty-name case is the one the substitution was written for and it is
    // unchanged: `statesItsOwnSide("")` is false by an explicit guard, not by a
    // regex accident.
    expect(statesItsOwnSide("")).toBe(false);
    expect(statesItsOwnSide(null)).toBe(false);
    expect(leaderLabel({ name: "", probability: 0.4 })).toBe("Yes");
  });

  it("still names an entity leader", () => {
    expect(
      movementExplanation({ name: "Amazon", probability: 0.5, opening_probability: 0.365 }),
    ).toBe("Amazon up 13.5 pts from opening.");
  });
});
