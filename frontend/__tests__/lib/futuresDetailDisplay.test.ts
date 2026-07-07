// #883 L2-46: futures-detail blend-only movement-explanation logic.

import {
  isGenericOutcomeLabel,
  leaderLabel,
  movementExplanation,
  pickHeroOutcome,
} from "../../lib/futuresDetailDisplay";

describe("leaderLabel", () => {
  test("generic binary names render as Yes", () => {
    for (const n of ["Yes", "No", "over", "UNDER", ""]) {
      expect(leaderLabel({ name: n, probability: 0.5 })).toBe("Yes");
    }
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
