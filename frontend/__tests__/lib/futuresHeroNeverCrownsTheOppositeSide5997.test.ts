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
// The rule this file pinned: "Yes" is a substitution for names that carry NO
// answer — "May 18", "2026", "Option A", a bare number. A name that states its
// own side is printed as served.
//
// ═══ AMENDED BY #7256 (ux/1374) — THE SECOND HALF OF THAT RULE IS GONE ═══
//
// The substitution is retired entirely: the hero prints the outcome's own name,
// always. #5997's ship — the half this file is named for — is unchanged and
// still asserted below; it simply holds a fortiori now, because nothing is
// substituted for anything.
//
// What changed is the fallback #5997 preserved. Measured over 43,510 open
// markets, it fired on 984 heroes, 933 of them on boards carrying no Yes/No row
// at all, and its justifying family (`Option A`/`Choice 1`/`Bucket 3`) had ZERO
// members. The arms that actually fired were `USA`, `TCU`, `PSG`, `BTS`,
// `October 1 - 31, 2026`, `$92` — real answers, overwritten with one the board
// did not carry. Full table and both production specimens: the block comment on
// `heroOutcomeLabel`.

import {
  heroOutcomeLabel,
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

  it("no longer substitutes for a name that carries no answer either (#7256)", () => {
    // ⚠️ THIS ASSERTION IS INVERTED FROM WHAT #5997 WROTE, DELIBERATELY.
    //
    // It used to read `expect(heroOutcomeLabel("May 18")).toBe("Yes")` and was
    // labelled THE CONTROL — the thing that would go red if anyone deleted the
    // substitution wholesale. #7256 deleted it wholesale, because the behaviour
    // this control protected is the behaviour Alex filed as a bug: a 3-rung date
    // ladder on `/futures/58776433` printed "55% / Yes" over the rung
    // `October 1 - 31, 2026`, and a 23-way field on `/futures/55674185` printed
    // "41% / Yes" over `USA`.
    //
    // "62% / May 18" — the reading the old control called the failure mode — is
    // CORRECT. It is the answer the board carries. "62% / Yes" is the failure.
    //
    // #5997's actual ship is untouched and is asserted above: a name that states
    // its own side is never replaced. That now holds a fortiori.
    expect(heroOutcomeLabel("May 18")).toBe("May 18");
    expect(heroOutcomeLabel("2026")).toBe("2026");
    expect(heroOutcomeLabel("Option A")).toBe("Option A");
    expect(heroOutcomeLabel("Q3 2026")).toBe("Q3 2026");
    expect(heroOutcomeLabel("42.5")).toBe("42.5");
  });

  it("never touches a real entity name", () => {
    expect(heroOutcomeLabel("Kendrick Lamar")).toBe("Kendrick Lamar");
    expect(heroOutcomeLabel("Manchester City")).toBe("Manchester City");
  });

  it("keeps `statesItsOwnSide` itself unchanged", () => {
    // #5997 pinned `isGenericOutcomeName` here to prove its wide predicate had
    // been MOVED rather than edited. #7256 deleted that predicate (it had no
    // caller left), so the pin moves to the one #5997 introduced and that is
    // still load-bearing — `leaderLabel` reads it on the movement caption.
    expect(statesItsOwnSide("No")).toBe(true);
    expect(statesItsOwnSide("Under 100")).toBe(true);
    expect(statesItsOwnSide("May 18")).toBe(false);
    expect(statesItsOwnSide("Kendrick Lamar")).toBe(false);
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
