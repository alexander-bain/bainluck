// #883 L2-46: futures-detail blend-only movement-explanation logic.

import {
  isGenericOutcomeLabel,
  leaderLabel,
  movementExplanation,
  pickHeroOutcome,
  futuresTitleText,
  gradedWinner,
} from "../../lib/futuresDetailDisplay";

describe("leaderLabel", () => {
  // #5997 AMENDED THIS EXPECTATION, and the amendment is the ship: "No", "over"
  // and "UNDER" used to render as "Yes" here, which is how the hero came to
  // print "39% / Yes" over the No row on /futures/20571021. A name that states
  // its own side is now returned as served; only a name that carries NO answer
  // is substituted. The empty-name case below is untouched and is why the
  // substitution still exists at all. Full reasoning: `statesItsOwnSide`.
  test("a name that states its own side is kept", () => {
    for (const n of ["Yes", "No", "over", "UNDER"]) {
      expect(leaderLabel({ name: n, probability: 0.5 })).toBe(n);
    }
  });
  test("a name that carries no answer renders as Yes", () => {
    expect(leaderLabel({ name: "", probability: 0.5 })).toBe("Yes");
  });
  test("real names are kept", () => {
    expect(leaderLabel({ name: "Gavin Newsom", probability: 0.3 })).toBe("Gavin Newsom");
  });
  test("null leader -> null", () => {
    expect(leaderLabel(null)).toBeNull();
  });
});

describe("isGenericOutcomeLabel", () => {
  test("catches binaries, keeps names", () => {
    expect(isGenericOutcomeLabel("Yes")).toBe(true);
    expect(isGenericOutcomeLabel("No")).toBe(true);
    expect(isGenericOutcomeLabel("Cleveland Cavaliers")).toBe(false);
  });
});

describe("movementExplanation", () => {
  test("prefers opening->current, 'up X pts from opening'", () => {
    const s = movementExplanation({
      name: "Gavin Newsom",
      probability: 0.42,
      opening_probability: 0.30,
    });
    expect(s).toBe("Gavin Newsom up 12.0 pts from opening.");
  });

  test("down when current < opening", () => {
    const s = movementExplanation({
      name: "Arsenal",
      probability: 0.55,
      opening_probability: 0.70,
    });
    expect(s).toBe("Arsenal down 15.0 pts from opening.");
  });

  test("roughly flat for sub-1pt moves", () => {
    const s = movementExplanation({
      name: "Yes",
      probability: 0.503,
      opening_probability: 0.500,
    });
    expect(s).toBe("Yes roughly flat since opening.");
  });

  test("falls back to 24h change when no opening", () => {
    const s = movementExplanation({
      name: "Dodgers",
      probability: 0.28,
      opening_probability: null,
      probability_change_24h: 0.05,
    });
    expect(s).toBe("Dodgers up 5.0 pts in the last 24h.");
  });

  test("null when there is nothing to say", () => {
    expect(
      movementExplanation({ name: "X", probability: 0.5, opening_probability: null, probability_change_24h: null })
    ).toBeNull();
    expect(movementExplanation(null)).toBeNull();
  });

  test("generic binary leader shows as Yes in the explanation", () => {
    const s = movementExplanation({
      name: "Yes",
      probability: 0.20,
      opening_probability: 0.08,
    });
    expect(s).toBe("Yes up 12.0 pts from opening.");
  });
});

describe("pickHeroOutcome (resolved edge state)", () => {
  const leader = { name: "Favorite", probability: 0.58, is_winner: false };
  const winner = { name: "Underdog", probability: 0.30, is_winner: true };
  const other = { name: "Third", probability: 0.12, is_winner: false };

  test("live market -> the leader", () => {
    expect(pickHeroOutcome([leader, winner, other], leader, false)).toBe(leader);
  });

  test("resolved market -> the actual winner (not the highest-probability)", () => {
    expect(pickHeroOutcome([leader, winner, other], leader, true)).toBe(winner);
  });

  test("resolved with no winner flagged -> falls back to the leader", () => {
    const none = [
      { name: "A", probability: 0.5, is_winner: false },
      { name: "B", probability: 0.5, is_winner: null },
    ];
    expect(pickHeroOutcome(none, none[0], true)).toBe(none[0]);
  });

  test("empty outcomes -> leader (or null)", () => {
    expect(pickHeroOutcome([], null, true)).toBeNull();
  });
});

describe("futuresTitleText (#883 L2-55 — no % on settled titles)", () => {
  test("resolved -> '<winner> won - <market>' with NO percentage", () => {
    const t = futuresTitleText({
      marketName: "2026 NBA Draft Pick 1",
      isResolved: true,
      winnerName: "Brayden Burries",
      leaderName: "Brayden Burries",
      probabilityLabel: "10%",
    });
    expect(t).toBe("Brayden Burries won - 2026 NBA Draft Pick 1");
    expect(t).not.toMatch(/%/);
  });

  test("live -> '<leader> <prob>% - <market>'", () => {
    const t = futuresTitleText({
      marketName: "NBA MVP",
      isResolved: false,
      leaderName: "Shai Gilgeous-Alexander",
      probabilityLabel: "58%",
    });
    expect(t).toBe("Shai Gilgeous-Alexander 58% - NBA MVP");
  });

  test("resolved without a winner falls back to market name (no %)", () => {
    const t = futuresTitleText({
      marketName: "Some Market",
      isResolved: true,
      winnerName: null,
      leaderName: "X",
      probabilityLabel: "10%",
    });
    // #6079 — this expectation FLIPPED, and the test's own name is why: it always
    // said "falls back to market name (no %)" while asserting a percentage. The
    // branch fell through to the live form, so a settled market with nothing
    // graded got the one shape L2-55 exists to keep out of a settled title.
    expect(t).toBe("Some Market");
    expect(t).not.toMatch(/%/);
    expect(t).not.toMatch(/won/);
  });

  test("no leader/prob -> just the market name", () => {
    expect(futuresTitleText({ marketName: "Bare", isResolved: false })).toBe("Bare");
  });
});

describe("gradedWinner (#6079 — the word 'won' comes from the grade)", () => {
  /** As served: Kalshi rows arrive with no `is_winner` key at all, not with false. */
  type Row = { name: string; probability: number; is_winner?: boolean | null };
  const graded: Row = { name: "Kai Havertz", probability: 0.21, is_winner: true };
  const frozenHigh: Row = { name: "No", probability: 0.91, is_winner: false };
  const ungraded: Row = { name: "Yes", probability: 0.09 };

  test("returns the GRADED row even when it is not the price leader", () => {
    // UX-P232's case: settlement freezes prices, so the winner is routinely not
    // the top of the board. `frozenHigh` is the leader and must not be returned.
    expect(gradedWinner([frozenHigh, graded], frozenHigh, "resolved")).toBe(graded);
  });

  test("returns null when NOTHING is graded, where pickHeroOutcome returns the leader", () => {
    // The whole defect in one comparison: the two questions have different
    // answers on this input, and the title was asking the wrong one.
    expect(pickHeroOutcome([frozenHigh, ungraded], frozenHigh, true)).toBe(frozenHigh);
    expect(gradedWinner([frozenHigh, ungraded], frozenHigh, "resolved")).toBeNull();
  });

  test("never grades a market that is not resolved, however it is flagged", () => {
    // A live row carrying a stray `is_winner` must not crown anything: `status`
    // is the gate, exactly as the page's settled rule reads it.
    for (const status of ["open", "closed", "settled", "", null, undefined]) {
      expect(gradedWinner([graded], graded, status)).toBeNull();
    }
  });

  test("an empty board resolves to no winner rather than to the leader", () => {
    expect(gradedWinner([], null, "resolved")).toBeNull();
  });
});
