// L2-158 Item 3 (frontend half): team-name queries rank team pages first.
import { rankTeamsFirst } from "../../components/SearchBar";
import type { TypeaheadSuggestion } from "../../lib/api";

const team = (text: string, abbr?: string): TypeaheadSuggestion => ({
  type: "team",
  text,
  abbreviation: abbr,
});
const other = (type: TypeaheadSuggestion["type"], text: string): TypeaheadSuggestion => ({
  type,
  text,
});

describe("rankTeamsFirst", () => {
  test("promotes a prefix-matching team above non-team results", () => {
    const list = [
      other("futures", "Celtics to win the title"),
      other("event", "Celtics @ Lakers"),
      team("Boston Celtics"),
    ];
    const ranked = rankTeamsFirst(list, "celtics");
    expect(ranked[0].type).toBe("team");
    expect(ranked[0].text).toBe("Boston Celtics");
  });

  test("matches on abbreviation exactly", () => {
    const list = [other("event", "some game"), team("Boston Celtics", "BOS")];
    expect(rankTeamsFirst(list, "bos")[0].type).toBe("team");
  });

  test("preserves order when nothing matches", () => {
    const list = [other("event", "Lakers @ Suns"), team("Golden State Warriors")];
    const ranked = rankTeamsFirst(list, "lakers");
    // No team matches "lakers", so the original order is untouched.
    expect(ranked).toEqual(list);
  });

  test("stable within promoted and non-promoted groups", () => {
    const list = [
      other("hub", "NBA hub"),
      team("Boston Celtics"),
      team("Boston College"),
      other("event", "Boston game"),
    ];
    const ranked = rankTeamsFirst(list, "boston");
    expect(ranked.map((s) => s.text)).toEqual([
      "Boston Celtics",
      "Boston College",
      "NBA hub",
      "Boston game",
    ]);
  });

  test("empty query returns the list unchanged", () => {
    const list = [team("Boston Celtics")];
    expect(rankTeamsFirst(list, "")).toBe(list);
  });

  test.each([
    ["chiefs", "Kansas City Chiefs"],
    ["patroits", "New England Patriots"],
    ["niners", "San Francisco 49ers"],
  ])("%s puts the server-resolved team before a collection", (query, name) => {
    const resolved = { ...team(name), query_names_team: true };
    const collection = other("hub", "NFL Week 10");
    expect(rankTeamsFirst([collection, resolved], query)).toEqual([resolved, collection]);
  });

  test.each(["new", "york", "celtics next three games"])(
    "%s respects a server refusal even when the old prefix heuristic would promote",
    (query) => {
      const incidental = { ...team(query === "york" ? "York City" : query === "new" ? "New York Yankees" : "Celtics"), query_names_team: false };
      const list = [other("hub", "Requested collection"), incidental];
      expect(rankTeamsFirst(list, query)).toEqual(list);
    },
  );
});
