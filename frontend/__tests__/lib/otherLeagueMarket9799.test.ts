/**
 * #9799 — the rule that keeps American League awards off an NL game's rail.
 * The rendered rail is pinned in `__tests__/components/relatedByTagOtherLeague9799.test.tsx`.
 */
import { namesOnlyTheOtherLeague, sharedLeague } from "@/lib/otherLeagueMarket";

const AL = "American League";
const NL = "National League";

describe("sharedLeague", () => {
  it("names the league when both sides play in it", () => {
    expect(sharedLeague([NL, NL])).toBe(NL);
    expect(sharedLeague([AL, AL])).toBe(AL);
  });

  it("is null for an interleague game — both leagues are its business", () => {
    expect(sharedLeague([NL, AL])).toBeNull();
  });

  it("is null when either side is unknown", () => {
    expect(sharedLeague([NL, null])).toBeNull();
    expect(sharedLeague([undefined, NL])).toBeNull();
    expect(sharedLeague([])).toBeNull();
  });

  it("is null for a conference it has no names for", () => {
    expect(sharedLeague(["Eastern Conference", "Eastern Conference"])).toBeNull();
  });
});

describe("namesOnlyTheOtherLeague", () => {
  it.each([
    "AL Reliever of the Year Winner?",
    "MLB: AL Platinum Glove Winner",
    "American League Champion",
    "MLB: 2026 AL Central Champion",
    "ALCS MVP",
  ])("drops %s beside an NL game", (name) => {
    expect(namesOnlyTheOtherLeague(name, NL)).toBe(true);
  });

  it.each([
    "National League Champion",
    "MLB World Series Winner",
    "MLB Postseason: World Series MVP",
    "MLB Postseason: RBI Leader",
    "NLCS MVP",
    "AL or NL: which league wins the World Series?",
  ])("keeps %s beside an NL game", (name) => {
    expect(namesOnlyTheOtherLeague(name, NL)).toBe(false);
  });

  it("drops the NL pennant beside an AL game, keeps the AL one", () => {
    expect(namesOnlyTheOtherLeague("National League Champion", AL)).toBe(true);
    expect(namesOnlyTheOtherLeague("American League Champion", AL)).toBe(false);
  });

  it("does not read `al` inside a word as the league", () => {
    expect(namesOnlyTheOtherLeague("Will Dallas win the title?", NL)).toBe(false);
    expect(namesOnlyTheOtherLeague("Total runs over 8.5", NL)).toBe(false);
  });

  it("drops nothing without a shared league", () => {
    expect(namesOnlyTheOtherLeague("AL Reliever of the Year Winner?", null)).toBe(false);
  });
});
