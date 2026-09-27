/**
 * #5634 — a national team's name is the country, and is never cut to its last word.
 *
 * WHAT THE READER SAW: 390px, `/search?q=czechia`, Games, the finished UEFA
 * Nations League card for `/events/15195324` (Czech Republic 1–2 Croatia,
 * 2026-09-26). The score strip read **"REPUBLIC"** beside **"CROATIA"**; the
 * rows under it printed "Czech Republic" (lane1's frame, issue comment
 * 2026-09-27). The strip calls `teamShortNames` with no sport, so the soccer
 * whole-club rule never ran and the last-word rule did.
 *
 * The specimen's payload is quoted verbatim: both sides carry an abbreviation
 * (`CZE`, `CRO`), which is why the pair assertion below passes them — a country
 * must not be treated as a name the rule "gave up" on and swapped for codes.
 */

import {
  MULTI_WORD_COUNTRIES,
  isMultiWordCountry,
  teamCrestBadge,
  teamShortName,
  teamShortNames,
} from "@/lib/teamShortName";

describe("#5634 — a country keeps its whole name", () => {
  it("the specimen: the finished card's strip names Czech Republic", () => {
    expect(
      teamShortNames(
        { name: "Czech Republic", abbreviation: "CZE" },
        { name: "Croatia", abbreviation: "CRO" },
      ),
    ).toEqual({ home: "Czech Republic", away: "Croatia" });
    expect(teamShortName("Czech Republic")).toBe("Czech Republic");
  });

  it.each([
    ["rugbyunion_international", "New Zealand"],
    ["cricket_test_match", "West Indies"],
    ["icehockey_olympics", "United States"],
    ["basketball_fiba_world_cup", "South Korea"],
    ["soccer_fifa_world_cup", "Saudi Arabia"],
    ["soccer_fifa_world_cup", "Côte d'Ivoire"],
    ["soccer_uefa_nations_league", "Northern Ireland"],
    ["soccer_uefa_nations_league", "Bosnia & Herzegovina"],
    ["soccer_concacaf_nations_league", "St. Lucia"],
    ["soccer_concacaf_nations_league", "Saint Vincent and the Grenadines"],
  ])("%s · %s is not shortened, with or without the sport", (sport, name) => {
    expect(teamShortName(name)).toBe(name);
    expect(teamShortName(name, null, sport)).toBe(name);
  });

  it("every entry is a multi-word key in the form the lookup produces", () => {
    // A key written "Côte d'Ivoire" or "St. Lucia" would be a DEAD entry.
    for (const key of MULTI_WORD_COUNTRIES) {
      expect(key).toMatch(/^[a-z0-9]+( [a-z0-9]+)+$/);
      expect(isMultiWordCountry(key)).toBe(true);
    }
  });

  it("controls: a club that starts with a country's name still shortens", () => {
    expect(teamShortName("New Zealand Breakers")).toBe("Breakers");
    expect(teamShortName("South Africa Rhinos")).toBe("Rhinos");
    expect(isMultiWordCountry("Republic")).toBe(false);
  });

  it("the crest badge is not re-lettered by the label change", () => {
    // Pinned so the iPhone's CrestBadgeInitialsTests.swift mirror stays true.
    expect(teamCrestBadge("Czech Republic")).toBe("REP");
    expect(teamCrestBadge("New Zealand")).toBe("ZEA");
  });
});
