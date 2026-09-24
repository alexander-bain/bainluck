/**
 * #5634 — a two-word nickname keeps both words.
 *
 * WHAT THE READER SAW: `/events/15317515`, Guardians 0 – 1 Red Sox, Final, 390px,
 * 2026-09-24 (`artifacts/ux-1479/rs-0.png`). The hero read **"Sox · WON"** and the
 * chart axis **"SOX"** — a word that is also the White Sox. The last-word rule in
 * `lib/teamShortName.ts` drops the first half of every two-word nickname: "Tide",
 * "Irish", "Heels", and three different clubs as "Devils".
 *
 * `PRODUCTION_NAMES` is DATA, not a copy of the rule: every name below was read
 * verbatim from production `events` (60 days, MLB/NHL/NBA/WNBA/NFL/NCAAF, 372
 * names, 2026-09-24) and each one printed only its last word before this fix.
 */

import {
  TWO_WORD_NICKNAMES,
  teamShortName,
  teamShortNames,
  twoWordNickname,
} from "@/lib/teamShortName";

const PRODUCTION_NAMES: ReadonlyArray<[string, string]> = [
  ["americanfootball_ncaaf", "Alabama Crimson Tide"],
  ["americanfootball_ncaaf", "Arizona State Sun Devils"],
  ["americanfootball_ncaaf", "Arkansas Pine Bluff Golden Lions"],
  ["americanfootball_ncaaf", "Arkansas State Red Wolves"],
  ["americanfootball_ncaaf", "Army Black Knights"],
  ["baseball_mlb", "Boston Red Sox"],
  ["americanfootball_ncaaf", "California Golden Bears"],
  ["americanfootball_ncaaf", "Campbell Fighting Camels"],
  ["americanfootball_ncaaf", "Central Connecticut Blue Devils"],
  ["baseball_mlb", "Chicago White Sox"],
  ["icehockey_nhl", "Columbus Blue Jackets"],
  ["americanfootball_ncaaf", "Delaware Blue Hens"],
  ["icehockey_nhl", "Detroit Red Wings"],
  ["americanfootball_ncaaf", "Duke Blue Devils"],
  ["americanfootball_ncaaf", "Gardner-Webb Runnin Bulldogs"],
  ["americanfootball_ncaaf", "Georgia Tech Yellow Jackets"],
  ["americanfootball_ncaaf", "Hawaii Rainbow Warriors"],
  ["americanfootball_ncaaf", "Illinois Fighting Illini"],
  ["americanfootball_ncaaf", "Kent State Golden Flashes"],
  ["americanfootball_ncaaf", "Louisiana Ragin Cajuns"],
  ["americanfootball_ncaaf", "Maine Black Bears"],
  ["americanfootball_ncaaf", "Marshall Thundering Herd"],
  ["americanfootball_ncaaf", "Middle Tennessee Blue Raiders"],
  ["americanfootball_ncaaf", "Minnesota Golden Gophers"],
  ["americanfootball_ncaaf", "Mississippi Valley State Delta Devils"],
  ["americanfootball_ncaaf", "Nevada Wolf Pack"],
  ["americanfootball_ncaaf", "North Carolina Tar Heels"],
  ["americanfootball_ncaaf", "North Dakota Fighting Hawks"],
  ["americanfootball_ncaaf", "North Texas Mean Green"],
  ["americanfootball_ncaaf", "Notre Dame Fighting Irish"],
  ["americanfootball_ncaaf", "Penn State Nittany Lions"],
  ["basketball_nba", "Portland Trail Blazers"],
  ["americanfootball_ncaaf", "Rutgers Scarlet Knights"],
  ["americanfootball_ncaaf", "Southern Mississippi Golden Eagles"],
  ["americanfootball_ncaaf", "TCU Horned Frogs"],
  ["americanfootball_ncaaf", "Texas Tech Red Raiders"],
  ["baseball_mlb", "Toronto Blue Jays"],
  ["icehockey_nhl", "Toronto Maple Leafs"],
  ["americanfootball_ncaaf", "Tulane Green Wave"],
  ["americanfootball_ncaaf", "Tulsa Golden Hurricane"],
  ["icehockey_nhl", "Vegas Golden Knights"],
  ["americanfootball_ncaaf", "Wake Forest Demon Deacons"],
];

describe("#5634 — a two-word nickname keeps both words", () => {
  it("the specimen: the Red Sox hero names the Red Sox", () => {
    expect(teamShortName("Boston Red Sox", null, "baseball_mlb")).toBe("Red Sox");
    expect(
      teamShortNames(
        { name: "Boston Red Sox" },
        { name: "Cleveland Guardians" },
        "baseball_mlb",
      ),
    ).toEqual({ home: "Red Sox", away: "Guardians" });
  });

  it.each(PRODUCTION_NAMES)("%s · %s keeps its last two words", (sport, name) => {
    const lastTwo = name.split(/\s+/).slice(-2).join(" ");
    expect(teamShortName(name, null, sport)).toBe(lastTwo);
    expect(teamShortName(name)).toBe(lastTwo);
  });

  it("every entry is reached by at least one production name — no dead keys", () => {
    const reached = new Set(
      PRODUCTION_NAMES.map(([, n]) =>
        n.split(/\s+/).slice(-2).join(" ").toLowerCase().replace(/[^a-z0-9 ]/g, ""),
      ),
    );
    for (const key of TWO_WORD_NICKNAMES) expect(reached).toContain(key);
    expect(TWO_WORD_NICKNAMES.size).toBe(41);
  });

  it("every key is two lower-case words, the form the lookup produces", () => {
    for (const key of TWO_WORD_NICKNAMES) expect(key).toMatch(/^[a-z0-9]+ [a-z0-9]+$/);
  });

  it("clubs that were one word apart stop colliding", () => {
    expect(
      teamShortNames({ name: "Boston Red Sox" }, { name: "Chicago White Sox" }),
    ).toEqual({ home: "Red Sox", away: "White Sox" });
    expect(
      teamShortNames({ name: "Duke Blue Devils" }, { name: "Arizona State Sun Devils" }),
    ).toEqual({ home: "Blue Devils", away: "Sun Devils" });
  });

  it("punctuation in the stored spelling reaches the same entry and is kept as written", () => {
    expect(teamShortName("Louisiana Ragin' Cajuns")).toBe("Ragin' Cajuns");
  });

  it("a name that IS the nickname is compact, not a give-up that reaches for the abbreviation", () => {
    expect(twoWordNickname(["Red", "Sox"])).toBe("Red Sox");
    expect(
      teamShortNames(
        { name: "Red Sox", abbreviation: "BOS" },
        { name: "Yankees", abbreviation: "NYY" },
      ),
    ).toEqual({ home: "Red Sox", away: "Yankees" });
  });

  it("CONTROL: one-word nicknames behind a two-word place are untouched", () => {
    expect(teamShortName("Golden State Warriors")).toBe("Warriors");
    expect(teamShortName("Golden State Valkyries")).toBe("Valkyries");
    expect(teamShortName("Tampa Bay Rays")).toBe("Rays");
    expect(teamShortName("Kansas City Royals")).toBe("Royals");
    expect(teamShortName("New Jersey Devils")).toBe("Devils");
    expect(teamShortName("Miami (OH) RedHawks")).toBe("RedHawks");
  });

  it("CONTROL: a person's name never reaches the list", () => {
    expect(teamShortName("Mean Green", null, "tennis_atp_us_open")).toBe("Green");
  });
});
