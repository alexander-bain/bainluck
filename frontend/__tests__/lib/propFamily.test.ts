// UX-P036 (gap K14) — prop-family recovery from the props_script key.
//
// The backend builds `key = f"{market_name}|{outcome_name}"` and sets
// `label = outcome_name` (backend/app/routes/events.py:4707), so the statistic
// is on the wire and the label drops it. These tests pin the recovery, and —
// just as importantly — pin the DEGRADED path that keeps the golf/combat
// concept page rendering exactly as it does today.

import {
  propFamilyName,
  sharedFamilyPrefix,
  stripSharedFamilyPrefix,
  groupByPropFamily,
} from "@/lib/propFamily";

describe("propFamilyName", () => {
  test("recovers the market name from a real production key", () => {
    expect(
      propFamilyName("Boston vs A's: Hits + Runs + RBIs|Carlos Cortes: 3+"),
    ).toBe("Boston vs A's: Hits + Runs + RBIs");
  });

  test("a NUMERIC key has no family — the golf/combat concept-page shape", () => {
    expect(propFamilyName(90210)).toBeNull();
  });

  test("a string key with no separator has no family", () => {
    expect(propFamilyName("Anytime touchdown scorer")).toBeNull();
  });

  test("a leading separator is not a family (never an empty header)", () => {
    expect(propFamilyName("|Carlos Cortes: 3+")).toBeNull();
    expect(propFamilyName("   |Carlos Cortes: 3+")).toBeNull();
  });

  test("only the FIRST separator splits — outcome names may contain one", () => {
    expect(propFamilyName("Hits|Cortes: 3+|extra")).toBe("Hits");
  });
});

describe("sharedFamilyPrefix", () => {
  test("strips the matchup boilerplate shared by every family", () => {
    expect(
      sharedFamilyPrefix([
        "Boston vs A's: Hits + Runs + RBIs",
        "Boston vs A's: Hits",
        "Boston vs A's: Home Runs",
      ]),
    ).toBe("Boston vs A's: ");
  });

  test("a SINGLE family is never stripped — sharedness is the only evidence", () => {
    // Otherwise "Best Picture: Winner" would be cut down to "Winner".
    expect(sharedFamilyPrefix(["Best Picture: Winner"])).toBe("");
    expect(sharedFamilyPrefix(["Boston vs A's: Hits"])).toBe("");
  });

  test("no shared prefix → nothing stripped", () => {
    expect(sharedFamilyPrefix(["Hits", "Home Runs"])).toBe("");
  });

  test("a common prefix that is not a ': ' boundary is not stripped", () => {
    // "Total" is shared but cutting it would maim the words.
    expect(sharedFamilyPrefix(["Total bases", "Total hits"])).toBe("");
  });

  test("never strips a name down to nothing", () => {
    expect(sharedFamilyPrefix(["Game: Hits", "Game: "])).toBe("");
  });

  test("stripSharedFamilyPrefix applies it across the list", () => {
    expect(
      stripSharedFamilyPrefix([
        "Boston vs A's: Hits + Runs + RBIs",
        "Boston vs A's: Home Runs",
      ]),
    ).toEqual(["Hits + Runs + RBIs", "Home Runs"]);
  });
});

describe("groupByPropFamily", () => {
  const keyOf = (x: { key: string | number }) => x.key;

  test("groups the measured production shape into its three families", () => {
    const items = [
      { key: "Boston vs A's: Hits + Runs + RBIs|Tommy White: 4+" },
      { key: "Boston vs A's: Hits|Anthony Seigler: 2+" },
      { key: "Boston vs A's: Hits + Runs + RBIs|Nick Kurtz: 2+" },
      { key: "Boston vs A's: Home Runs|Nick Sogard: 1+" },
    ];
    const groups = groupByPropFamily(items, keyOf);
    expect(groups.map((g) => g.name)).toEqual([
      "Hits + Runs + RBIs",
      "Hits",
      "Home Runs",
    ]);
    expect(groups[0].items).toHaveLength(2);
  });

  test("group order follows FIRST APPEARANCE, so a pre-ranked list keeps its ranking", () => {
    const items = [
      { key: "G: Home Runs|a" },
      { key: "G: Hits|b" },
      { key: "G: Home Runs|c" },
    ];
    expect(groupByPropFamily(items, keyOf).map((g) => g.name)).toEqual([
      "Home Runs",
      "Hits",
    ]);
  });

  test("DEGRADED PATH: no families → ONE unnamed group holding the original array", () => {
    // This is the branch the concept page relies on; the component checks for
    // exactly this shape before emitting its pre-grouping markup.
    const items = [{ key: 1 }, { key: 2 }, { key: 3 }];
    const groups = groupByPropFamily(items, keyOf);
    expect(groups).toHaveLength(1);
    expect(groups[0].name).toBeNull();
    expect(groups[0].items).toBe(items);
  });

  test("a mixed payload never drops the family-less remainder", () => {
    const items = [{ key: "G: Hits|a" }, { key: 7 }];
    const groups = groupByPropFamily(items, keyOf);
    expect(groups.map((g) => g.name)).toEqual(["G: Hits", null]);
    expect(groups[1].items).toEqual([{ key: 7 }]);
  });

  test("every input item survives grouping — nothing is filtered away", () => {
    const items = Array.from({ length: 81 }, (_, i) => ({
      key: `M: F${i % 3}|row ${i}`,
    }));
    const groups = groupByPropFamily(items, keyOf);
    expect(groups.flatMap((g) => g.items)).toHaveLength(81);
  });
});
