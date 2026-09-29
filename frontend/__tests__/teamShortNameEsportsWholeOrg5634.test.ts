/**
 * #5634 — an esports organisation is not its type.
 *
 * WHAT THE READER SAW: `/events/15319232`, G2 Esports v Paper Rex, 390px,
 * 2026-09-29 — the hero read **"Esports"** and **"Rex"**. The served payload
 * carries `sport: "esports"` and the hero passes it, so the rule had the sport
 * in hand and no esports arm to use it.
 *
 * `PRODUCTION_COLLAPSES` is DATA, not a copy of the rule: each group was read
 * verbatim from production `events` (esports, 60 days, the 1,000 most-used
 * names, 2026-09-29) and every name in a group printed the SAME word before
 * this fix.
 */

import { keepsWholeOrgName, teamCrestBadge, teamShortName, teamShortNames } from "@/lib/teamShortName";

const ESPORTS = "esports";

const PRODUCTION_COLLAPSES: ReadonlyArray<[string, string[]]> = [
  ["Esports", ["G2 Esports", "Top Esports", "FURIA Esports", "Hanwha Life Esports", "KRÜ Esports"]],
  ["Gaming", ["JD Gaming", "SK Gaming", "Bilibili Gaming", "EDward Gaming"]],
  ["Esport", ["Insiders Esport", "Partizan Esport", "Falcons Esport"]],
  ["Phoenix", ["Black Phoenix", "FunPlus Phoenix", "Team Phoenix"]],
];

describe("#5634 — an esports organisation keeps its whole name", () => {
  it.each(PRODUCTION_COLLAPSES)(
    "the organisations that all printed %s are told apart under an esports key",
    (word, names) => {
      for (const n of names) expect(teamShortName(n)).toBe(word);
      const labels = names.map((n) => teamShortName(n, null, ESPORTS));
      expect(labels).toEqual(names);
      for (const l of labels) expect(l).not.toBe(word);
    },
  );

  it.each([
    ["G2 Esports", "G2 Esports"],
    ["Paper Rex", "Paper Rex"],
    ["Natus Vincere", "Natus Vincere"],
    ["Dplus KIA", "Dplus KIA"],
    // Leading short tokens are the org here, not a designator to drop.
    ["KT Rolster Challengers", "KT Rolster Challengers"],
    ["SK Gaming", "SK Gaming"],
    ["Fnatic", "Fnatic"],
    // Past three words, a type-word ending still keeps the name whole ...
    ["Gamespace Mediterranean College Esports", "Gamespace Mediterranean College Esports"],
    ["Fukuoka SoftBank Hawks Gaming", "Fukuoka SoftBank Hawks Gaming"],
    ["E WIE EINFACH E-SPORTS", "E WIE EINFACH E-SPORTS"],
    ["EDward Gaming Youth Team", "EDward Gaming Youth Team"],
    // ... and any other long name takes the shipped rule.
    ["Unicorns Of Love Sexy Edition", "Edition"],
  ])("%s → %s", (name, label) => {
    expect(teamShortName(name, null, "esports_valorant")).toBe(label);
  });

  it("the specimen pair reads both whole names", () => {
    expect(teamShortNames({ name: "G2 Esports" }, { name: "Paper Rex" }, ESPORTS)).toEqual({
      home: "G2 Esports",
      away: "Paper Rex",
    });
  });

  it("a whole name is chosen, not given up on: no abbreviation rescue", () => {
    expect(
      teamShortNames(
        { name: "G2 Esports", abbreviation: "G2" },
        { name: "Paper Rex", abbreviation: "PRX" },
        ESPORTS,
      ),
    ).toEqual({ home: "G2 Esports", away: "Paper Rex" });
  });

  it("the gate is the first key segment, and fails closed", () => {
    expect(keepsWholeOrgName("esports")).toBe(true);
    expect(keepsWholeOrgName("esports_lol")).toBe(true);
    expect(keepsWholeOrgName("ESPORTS")).toBe(true);
    expect(keepsWholeOrgName("soccer_esports_cup")).toBe(false);
    expect(keepsWholeOrgName("basketball_nba")).toBe(false);
    expect(keepsWholeOrgName(null)).toBe(false);
    expect(keepsWholeOrgName(undefined)).toBe(false);
    expect(keepsWholeOrgName("")).toBe(false);
    expect(keepsWholeOrgName(3 as unknown as string)).toBe(false);
  });

  it("other sports keep the shipped rule (control)", () => {
    expect(teamShortName("Boston Red Sox", null, "baseball_mlb")).toBe("Red Sox");
    expect(teamShortName("Los Angeles Lakers", null, "basketball_nba")).toBe("Lakers");
    expect(teamShortName("G2 Esports", null, "basketball_nba")).toBe("Esports");
    expect(teamShortName("G2 Esports")).toBe("Esports");
  });

  it("the crest badge does not move", () => {
    expect(teamCrestBadge("G2 Esports", ESPORTS)).toBe(teamCrestBadge("G2 Esports"));
    expect(teamCrestBadge("Paper Rex", ESPORTS)).toBe(teamCrestBadge("Paper Rex"));
  });
});
