/**
 * ux/1070 item 4 — the Awards section is nominees under an award, with faces.
 *
 * Alex, 2026-09-04: "Awards section: badly formatted, no player images."
 *
 * The group rendered the flat "Other Markets" row, so the Red Sox block printed
 * the award's name once per nominee and the team crest three times:
 *
 *     [BOS] Trevor Story      AL MVP Winner? · 2026 · #22 of 30      1%
 *     [BOS] Garrett Crochet   AL MVP Winner? · 2026 · #24 of 30      1%
 *
 * Card contract (#2910): the row is the nominee, the number, the movement. What
 * the rows share is a heading, said once.
 *
 * Every market name below is one production actually carries for the Red Sox
 * (measured 2026-09-04 via /api/admin/db-query).
 */
import {
  awardTitle,
  groupAwardRows,
  nomineeShowsFace,
  type AwardRowInput,
} from "@/lib/myStuffAwards";

function row(over: Partial<AwardRowInput> = {}): AwardRowInput {
  return {
    key: "1-1",
    marketId: 216,
    marketName: "AL MVP Winner?",
    outcomeName: "Trevor Story",
    teamName: "Boston Red Sox",
    seasonLabel: "2026",
    probability: 0.01,
    change: null,
    rank: 22,
    totalOutcomes: 30,
    sources: [],
    ...over,
  };
}

describe("groupAwardRows", () => {
  it("says the award once and the nominees under it", () => {
    const groups = groupAwardRows([
      row({ key: "a", outcomeName: "Trevor Story", probability: 0.01 }),
      row({ key: "b", outcomeName: "Roman Anthony", probability: 0.04 }),
      row({
        key: "c",
        marketId: 214,
        marketName: "AL Rookie of the Year Winner?",
        outcomeName: "Connelly Early",
        probability: 0.01,
      }),
    ]);
    expect(groups.map((g) => g.title)).toEqual([
      "AL MVP",
      "AL Rookie of the Year",
    ]);
    expect(groups[0].nominees.map((n) => n.outcomeName)).toEqual([
      // Ordered by probability, best first — not by arrival.
      "Roman Anthony",
      "Trevor Story",
    ]);
    expect(groups[1].nominees).toHaveLength(1);
  });

  it("keeps the section's own ordering of awards", () => {
    const groups = groupAwardRows([
      row({ key: "a", marketId: 218, marketName: "AL Hank Aaron Award Winner?" }),
      row({ key: "b", marketId: 216, marketName: "AL MVP Winner?" }),
    ]);
    expect(groups.map((g) => g.marketId)).toEqual([218, 216]);
  });

  it("carries the season on the heading, not on every row", () => {
    const [group] = groupAwardRows([row(), row({ key: "b" })]);
    expect(group.seasonLabel).toBe("2026");
  });

  it("keeps an unpriced nominee last rather than dropping it", () => {
    const [group] = groupAwardRows([
      row({ key: "a", outcomeName: "No Price", probability: null }),
      row({ key: "b", outcomeName: "Roman Anthony", probability: 0.04 }),
    ]);
    expect(group.nominees.map((n) => n.outcomeName)).toEqual([
      "Roman Anthony",
      "No Price",
    ]);
  });
});

describe("nomineeShowsFace", () => {
  it.each([
    "Trevor Story",
    "Roman Anthony",
    "Garrett Crochet",
    "Ceddanne Rafaela",
    "Masataka Yoshida",
  ])("gives %s a face", (name) => {
    expect(nomineeShowsFace(name, "Boston Red Sox")).toBe(true);
  });

  it.each([
    // The team itself, in both the forms our sources use.
    ["Boston", "Boston Red Sox"],
    ["Boston Red Sox", "Boston Red Sox"],
    ["boston red sox", "Boston Red Sox"],
  ])("keeps the crest for %s", (outcome, team) => {
    expect(nomineeShowsFace(outcome, team)).toBe(false);
  });

  it("never looks up a market outcome", () => {
    expect(nomineeShowsFace("Over 16.5", "Boston Red Sox")).toBe(false);
    expect(nomineeShowsFace("Yes", "Boston Red Sox")).toBe(false);
    expect(nomineeShowsFace("", "Boston Red Sox")).toBe(false);
  });

  it("rejects rather than guesses when a name carries a colon", () => {
    // "The Clubhouse: A Year with the Red Sox" is a real production outcome —
    // a documentary, not a player. Rejecting costs a face; guessing fetches a
    // wrong one.
    expect(
      nomineeShowsFace("The Clubhouse: A Year with the Red Sox", "Boston Red Sox"),
    ).toBe(false);
  });
});

describe("awardTitle", () => {
  it.each([
    ["AL MVP Winner?", "AL MVP"],
    ["AL Cy Young Winner?", "AL Cy Young"],
    ["AL Rookie of the Year Winner?", "AL Rookie of the Year"],
    ["MLB: 2026 AL Cy Young Winner", "MLB: AL Cy Young"],
    ["AL Hank Aaron Award Winner?", "AL Hank Aaron Award"],
  ])("trims %s to %s", (name, expected) => {
    expect(awardTitle(name)).toBe(expected);
  });

  it("never returns an empty heading for a real market", () => {
    expect(groupAwardRows([row({ marketName: "Winner?" })])[0].title).toBe(
      "Winner?",
    );
  });
});
