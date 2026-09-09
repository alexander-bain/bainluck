// #993 L2-42: composed search family row display logic (D1: probabilities only).

import {
  leaderLabel,
  movementArrow,
  resolutionLabel,
  cleanName,
  familyShownIds,
  familyRowTitles,
  FAMILY_ROW_VISIBLE_CHARS,
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

// #4136: two rows in one card that read the same and answer differently.
describe("familyRowTitles (#4136)", () => {
  /** What a reader actually sees: the head is what CSS may cut, the tail never
   *  is. Anything past the visible budget in the head is simply not there. */
  const visible = (t: { head: string; tail: string }) =>
    t.head.slice(0, FAMILY_ROW_VISIBLE_CHARS) + t.tail;

  // The production specimen, verbatim from GET /api/events/search?q=yank
  // (api.bainluck.com, master 81db1afb, 2026-09-09).
  const YANK = [
    "M15 Hurghada: Mayank Sharma vs Luis Klaus",
    "Istanbul 3: Timofey Skatov vs Yanki Erel",
    "Istanbul 3: Yanki Erel vs Radu Albot",
    "Colorado Rockies vs. New York Yankees - First 5 Innings Winner",
    "Colorado Rockies vs. New York Yankees - 9th Inning Winner",
  ];

  test("the filed defect: no two rows of the live `yank` card render the same text", () => {
    const seen = YANK.map((n, i) => visible(familyRowTitles(YANK)[i]));
    expect(new Set(seen).size).toBe(YANK.length);
  });

  test("the two Rockies rows keep the words that tell them apart", () => {
    const t = familyRowTitles(YANK);
    expect(t[3].tail).toBe("First 5 Innings Winner");
    expect(t[4].tail).toBe("9th Inning Winner");
    // and the shared run is what became elidable, in full
    expect(t[3].head).toBe("Colorado Rockies vs. New York Yankees - ");
    expect(t[4].head).toBe("Colorado Rockies vs. New York Yankees - ");
  });

  test("rows that diverge EARLY are left completely alone", () => {
    // `Istanbul 3: ` is 12 shared characters — inside what a row shows, so these
    // two need no help. A separator-keyed rule would have split them for nothing.
    const t = familyRowTitles(YANK);
    expect(t[1]).toEqual({ head: YANK[1], tail: "" });
    expect(t[2]).toEqual({ head: YANK[2], tail: "" });
    // and a row with no sibling at all
    expect(t[0]).toEqual({ head: YANK[0], tail: "" });
  });

  test("a single-row card is never split", () => {
    expect(familyRowTitles([YANK[3]])).toEqual([{ head: YANK[3], tail: "" }]);
  });

  test("a tail too long to reserve is refused rather than eating the row", () => {
    // Shares exactly the 40-char matchup, then diverges immediately into a
    // 46-char suffix. Reserving that would push the matchup off the row —
    // trading one unreadable row for another — so it is refused.
    const long = [
      "Colorado Rockies vs. New York Yankees - Winner Of The Ninth Inning By Any Margin At All",
      "Colorado Rockies vs. New York Yankees - Loser Of The Ninth Inning By Any Margin At All",
    ];
    for (const t of familyRowTitles(long)) expect(t.tail).toBe("");
  });

  test("a reserved tail never starts mid-word", () => {
    // Shared run ends inside "Winner"; the snap must fall back to the space.
    const mid = [
      "Colorado Rockies vs. New York Yankees - Winner A",
      "Colorado Rockies vs. New York Yankees - Winner B",
    ];
    for (const t of familyRowTitles(mid)) {
      expect(t.tail).toMatch(/^Winner [AB]$/);
      expect(t.head.endsWith(" ")).toBe(true);
    }
  });

  test("identical names produce no split (nothing distinguishes them)", () => {
    const same = ["Colorado Rockies vs. New York Yankees", "Colorado Rockies vs. New York Yankees"];
    for (const t of familyRowTitles(same)) expect(t.tail).toBe("");
  });

  test("head + tail always reconstruct the cleaned name — no bytes invented or lost", () => {
    for (const names of [YANK, ["A", "B"], []]) {
      familyRowTitles(names).forEach((t, i) => {
        expect(t.head + t.tail).toBe(cleanName(names[i]));
      });
    }
  });

  test("cleanName still applies through the split", () => {
    const years = [
      "Colorado Rockies vs. New York Yankees - First 5 Innings Winner 2026",
      "Colorado Rockies vs. New York Yankees - 9th Inning Winner 2026",
    ];
    const t = familyRowTitles(years);
    expect(t[0].head + t[0].tail).not.toMatch(/2026/);
    expect(t[1].tail).toBe("9th Inning Winner");
  });
});
