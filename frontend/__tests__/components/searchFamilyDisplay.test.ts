// #993 L2-42: composed search family row display logic (D1: probabilities only).

import {
  leaderLabel,
  movementArrow,
  resolutionLabel,
  cleanName,
  familyShownIds,
} from "../../components/searchFamilyDisplay";

const mkMarket = (over: Record<string, unknown> = {}) => ({
  id: 1,
  name: "NBA: LeBron James Next Team",
  outcome_count: 5,
  resolution_date: null,
  top_outcomes: [
    { id: 1, name: "Cleveland Cavaliers", probability: 0.27, movement: 0.05, american_odds: -160 },
    { id: 2, name: "Other", probability: 0.5, movement: null, american_odds: null },
  ],
  ...over,
}) as any;

describe("searchFamilyDisplay", () => {
  test("leaderLabel shows leader name + probability, NEVER odds (D1)", () => {
    const label = leaderLabel(mkMarket());
    expect(label).toBe("Cleveland Cavaliers 27%");
    // no odds strings (american_odds -160 must not appear)
    expect(label).not.toMatch(/-?\d{3}|\+\d/); // no american-odds patterns
  });

  test("leaderLabel null when no probability outcomes", () => {
    expect(leaderLabel(mkMarket({ top_outcomes: [{ id: 1, name: "x", probability: null }] }))).toBeNull();
  });

  test("movementArrow only fires at >= 2 points", () => {
    expect(movementArrow(0.05)).toEqual({ up: true, points: 5 });
    expect(movementArrow(-0.03)).toEqual({ up: false, points: 3 });
    expect(movementArrow(0.01)).toBeNull(); // below 2pt threshold
    expect(movementArrow(null)).toBeNull();
  });

  test("resolutionLabel only within 30 days", () => {
    const soon = new Date(Date.now() + 5 * 86_400_000).toISOString();
    const far = new Date(Date.now() + 100 * 86_400_000).toISOString();
    const past = new Date(Date.now() - 5 * 86_400_000).toISOString();
    expect(resolutionLabel(soon)).not.toBeNull();
    expect(resolutionLabel(far)).toBeNull();
    expect(resolutionLabel(past)).toBeNull();
    expect(resolutionLabel(null)).toBeNull();
  });

  test("cleanName strips trailing year / question mark", () => {
    expect(cleanName("Democratic Presidential Nominee 2028")).toBe("Democratic Presidential Nominee");
    expect(cleanName("Who will be confirmed as Fed Chair?")).toBe("Who will be confirmed as Fed Chair");
  });

  test("familyShownIds collects headline + member ids (for flat-list dedup)", () => {
    const fam = {
      family_key: "entity:lebron james",
      label: "Lebron James",
      headline: mkMarket({ id: 10 }),
      members: [mkMarket({ id: 11 }), mkMarket({ id: 12 })],
      more_count: 3,
      member_count: 6,
    } as any;
    const ids = familyShownIds([fam]);
    expect([...ids].sort()).toEqual([10, 11, 12]);
  });
});
