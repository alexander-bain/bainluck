import { relatedRailQuery } from "@/lib/relatedRailQuery";

const KEY = "soccer_italy_serie_a_women";
const TAGS = ["sport:soccer", "league:serie_a_femminile", "gender:women"];

describe("#10319 — Serie A Femminile asks for its own competition", () => {
  it("uses exact soccer/league/women tags, honest heading and no broad fallback", () => {
    expect(relatedRailQuery(KEY, [...TAGS, "status:scheduled"])).toEqual({
      tags: TAGS,
      title: "More Serie A Femminile (Women)",
    });
  });

  it.each([undefined, null, [], ["sport:soccer"],
    ["sport:soccer", "league:serie_a_femminile"],
    ["league:serie_a_femminile", "gender:women"],
    ["sport:soccer", "league:serie_a", "gender:women"],
    [...TAGS, "league:serie_a"], [...TAGS, "gender:men"],
    [...TAGS, "sport:basketball"], [...TAGS, "gender:unknown"],
  ])("refuses missing or contradictory competition identity: %j", (tags) => {
    expect(relatedRailQuery(KEY, tags)).toBeNull();
  });

  it.each([
    ["soccer_italy_serie_a", ["sport:soccer", "league:serie_a", "gender:men"], "soccer", "More Soccer"],
    ["basketball_wnba", ["sport:basketball", "league:wnba", "gender:women"], "basketball", "More WNBA"],
    ["soccer_fifa_womens_world_cup", ["sport:soccer", "league:fifa_world_cup", "gender:women"], "soccer", "More Soccer"],
  ])("preserves existing league query and fallback for %s", (key, tags, category, title) => {
    const identity = tags as string[];
    expect(relatedRailQuery(key as string, identity)).toEqual({
      tags: [`sport:${category}`, identity[1]],
      fallbackTags: [`sport:${category}`],
      title,
      fallbackTitle: category === "basketball" ? "More Basketball" : "More Soccer",
    });
  });

  it("keeps generic soccer's existing no-league behavior", () => {
    expect(relatedRailQuery("soccer_italy_serie_a", undefined)).toEqual({
      tags: ["sport:soccer"], title: "More Soccer",
    });
  });
});
