/**
 * #5634 — a football club is not its city.
 *
 * WHAT THE READER SAW: `/events/15309604`, 1. FC Köln 3-0 Union Berlin, Final,
 * 390px, 2026-09-12 — the hero read **"Köln · WON — Berlin"**, and "Berlin" is
 * also Hertha, Croatia and Füchse. `/events/15313874` (Seattle v Real Salt Lake)
 * headed its Bigger Picture card **"Lake"**. The last-word rule in
 * `lib/teamShortName.ts` assumes the distinctive word comes last; in football
 * it is very often the city.
 *
 * `PRODUCTION_COLLAPSES` is DATA, not a copy of the rule: each group was read
 * verbatim from production `events` (soccer, 60 days, first 1,000 distinct
 * names, 2026-09-24) and every name in a group printed the SAME last word
 * before this fix.
 */

import * as fs from "fs";
import * as path from "path";
import { resolveEventOutcome } from "@/lib/eventOutcome";
import { keepsWholeClubName, teamShortName, teamShortNames } from "@/lib/teamShortName";

const SOCCER = "soccer_germany_bundesliga";

const PRODUCTION_COLLAPSES: ReadonlyArray<[string, string[]]> = [
  // "Boca Juniors de Cali" also printed "Cali"; at four words it keeps the
  // shipped rule (see the formal-name block below), so it is not listed here.
  ["Cali", ["AD Cali", "America Cali", "América de Cali", "Atletico FC Cali"]],
  ["Juniors", ["Argentinos Juniors", "Boca Juniors"]],
  ["Central", ["Atletico Central", "Barracas Central", "CA Rosario Central"]],
  ["Munich", ["1860 Munich", "Bayern Munich"]],
  ["Athens", ["AEK Athens", "Atromitos Athens"]],
];

describe("#5634 — a football club keeps its whole name", () => {
  it.each(PRODUCTION_COLLAPSES)(
    "the clubs that all printed %s are told apart under a soccer key",
    (word, names) => {
      for (const n of names) expect(teamShortName(n)).toBe(word);
      const labels = names.map((n) => teamShortName(n, null, SOCCER));
      expect(new Set(labels).size).toBe(names.length);
      for (const l of labels) expect(l).not.toBe(word);
    },
  );

  it.each([
    ["1. FC Union Berlin", "Union Berlin"],
    ["Union Berlin", "Union Berlin"],
    ["Hertha Berlin", "Hertha Berlin"],
    ["Real Salt Lake", "Real Salt Lake"],
    ["1. FC Köln", "FC Köln"],
    ["CA Boca Juniors", "Boca Juniors"],
    ["AD Cali", "AD Cali"],
    ["AC Milan", "AC Milan"],
    ["Sporting Kansas City", "Sporting Kansas City"],
    ["Atletico Madrid", "Atletico Madrid"],
    ["Arsenal", "Arsenal"],
  ])("%s → %s", (name, label) => {
    expect(teamShortName(name, null, "soccer_epl")).toBe(label);
  });

  it("drops leading designators only down to two words, and never a club word", () => {
    // "1." and "FC" go; "Köln" alone would be the floor breached.
    expect(teamShortName("1. FC Köln", null, SOCCER)).toBe("FC Köln");
    // "Sporting" is in CLUB_TYPE_SUFFIXES as a TRAILING word; leading, it is the name.
    expect(teamShortName("Sporting Kansas City", null, "soccer_usa_mls")).toBe("Sporting Kansas City");
  });

  it("the hand-picked label still wins", () => {
    expect(teamShortName("Paris Saint-Germain", null, "soccer_france_ligue_one")).toBe("PSG");
  });

  it("every label is a tail of the club's own name", () => {
    for (const [, names] of PRODUCTION_COLLAPSES) {
      for (const n of names) expect(n.endsWith(teamShortName(n, null, SOCCER))).toBe(true);
    }
  });
});

describe("#5634 — the other direction: nothing outside football moves", () => {
  it.each([
    [undefined, "Bayern Munich", "Munich"],
    [null, "Union Berlin", "Berlin"],
    ["", "Union Berlin", "Berlin"],
    ["basketball_nba", "Los Angeles Lakers", "Lakers"],
    ["baseball_mlb", "Boston Red Sox", "Red Sox"],
    ["americanfootball_nfl", "Kansas City Chiefs", "Chiefs"],
    ["tennis_atp_us_open", "Carlos Alcaraz", "Alcaraz"],
    // A key that merely CONTAINS the word is not football.
    ["esports_soccer_sim", "Team Berlin", "Berlin"],
  ])("sport %p: %s → %s", (sport, name, label) => {
    expect(teamShortName(name, null, sport as string | null | undefined)).toBe(label);
  });

  it("keepsWholeClubName matches the first segment only and fails closed", () => {
    expect(keepsWholeClubName("soccer_epl")).toBe(true);
    expect(keepsWholeClubName("SOCCER_usa_mls")).toBe(true);
    expect(keepsWholeClubName("soccer")).toBe(true);
    expect(keepsWholeClubName("esports_soccer_sim")).toBe(false);
    expect(keepsWholeClubName(undefined)).toBe(false);
    expect(keepsWholeClubName(null)).toBe(false);
    // `names.map(fn)` hands an index in; a number is "sport unknown".
    expect(keepsWholeClubName(3 as unknown as string)).toBe(false);
  });
});

describe("#5634 — the pair: the specimens, and the abbreviation rescue unchanged", () => {
  it("Köln v Union Berlin names both clubs", () => {
    expect(
      teamShortNames(
        { name: "1. FC Köln" },
        { name: "Union Berlin", abbreviation: "FCU" },
        "soccer_germany_bundesliga_women",
      ),
    ).toEqual({ home: "FC Köln", away: "Union Berlin" });
  });

  it("Seattle Sounders FC v Real Salt Lake keeps SEA / RSL — the rescue is asked as before", () => {
    const pair = teamShortNames(
      { name: "Seattle Sounders FC", abbreviation: "SEA" },
      { name: "Real Salt Lake", abbreviation: "RSL" },
      "soccer_usa_mls",
    );
    expect(pair).toEqual({ home: "SEA", away: "RSL" });
  });

  it("without abbreviations the same pair prints both whole names, not 'Lake'", () => {
    expect(
      teamShortNames({ name: "Seattle Sounders FC" }, { name: "Real Salt Lake" }, "soccer_usa_mls"),
    ).toEqual({ home: "Seattle Sounders FC", away: "Real Salt Lake" });
  });

  it("a city-last pair with abbreviations does NOT reach for them", () => {
    // Before, neither side gave up ("Munich" / "Berlin"), so no rescue; the
    // whole names must not newly trigger one.
    expect(
      teamShortNames(
        { name: "Bayern Munich", abbreviation: "FCB" },
        { name: "Union Berlin", abbreviation: "FCU" },
        SOCCER,
      ),
    ).toEqual({ home: "Bayern Munich", away: "Union Berlin" });
  });
});

describe("#5634 — the event page hands the sport to every name it paints", () => {
  const root = path.resolve(__dirname, "..");
  const read = (p: string) => fs.readFileSync(path.join(root, p), "utf8");

  it("both OddsChart mounts on the event page pass the sport", () => {
    const page = read("app/events/[id]/page.tsx");
    const mounts = page.split("<OddsChart").slice(1).map((m) => m.slice(0, m.indexOf("/>")));
    expect(mounts.length).toBe(2);
    for (const m of mounts) expect(m).toMatch(/sportKey=\{event\.sport\}/);
  });

  it.each([
    ["components/OddsChart.tsx"],
    ["components/ScoreDifferentialChart.tsx"],
  ])("%s derives its axis names with the sport", (file) => {
    expect(read(file)).toMatch(
      /teamShortNames\(\s*\{ name: homeTeam, abbreviation: homeTeamAbbrev \},\s*\{ name: awayTeam, abbreviation: awayTeamAbbrev \},\s*sportKey,\s*\)/,
    );
  });

  it("the Bigger Picture section derives its names with the sport", () => {
    const src = read("components/RelatedFutures.tsx");
    const at = src.indexOf('printed "Town" against "Liverpool"');
    expect(at).toBeGreaterThan(-1);
    expect(src.slice(at, at + 400)).toMatch(/\{ name: awayTeam \},\s*sportKey,\s*\)/);
  });
});

describe("#5634 — a formal name of four words or more keeps its shipped label", () => {
  it.each([
    ["Sport Lisboa e Benfica", "Benfica"],
    ["Futebol Clube do Porto", "Porto"],
    ["Tigres de la UANL", "UANL"],
    ["Deportivo de La Coruna", "Coruna"],
  ])("%s → %s under a soccer key, as without one", (name, label) => {
    expect(teamShortName(name)).toBe(label);
    expect(teamShortName(name, null, "soccer_portugal_primeira_liga")).toBe(label);
  });

  it("the word count is taken AFTER leading designators go", () => {
    // Four words as written, two once "1." and "FC" are dropped.
    expect(teamShortName("1. FC Union Berlin", null, SOCCER)).toBe("Union Berlin");
    expect(teamShortName("BV Borussia 09 Dortmund", null, SOCCER)).toBe("Borussia 09 Dortmund");
  });
});

describe("#5634 — the settled hero crowns the club, not the city", () => {
  const union = { isFinished: true, homeTeam: "1. FC Köln", awayTeam: "Union Berlin", homeScore: 0, awayScore: 2 };

  it("a soccer key names the winner 'Union Berlin'", () => {
    expect(resolveEventOutcome({ ...union, sportKey: "soccer_germany_bundesliga_women" })?.winnerName).toBe(
      "Union Berlin",
    );
  });

  it("without a sport it is exactly the shipped label", () => {
    expect(resolveEventOutcome(union)?.winnerName).toBe("Berlin");
  });

  it("the event page, its share title and its preview image all pass the sport", () => {
    const root = path.resolve(__dirname, "..");
    for (const file of ["app/events/[id]/page.tsx", "app/events/[id]/layout.tsx", "app/events/[id]/opengraph-image.tsx"]) {
      const src = fs.readFileSync(path.join(root, file), "utf8");
      const call = src.slice(src.indexOf("resolveEventOutcome({"));
      expect(call.slice(0, call.indexOf("});"))).toMatch(/sportKey: event\.sport/);
    }
  });
});

describe("#5634 — the #7163 club corpus under a soccer key", () => {
  // The names #7163 pins as clubs its particle walk must never touch. Under a
  // soccer key the three-word ones are now whole — each a truer label than the
  // fragment ("Gama", "Midlothian", and "Manchester" for the club founded in
  // protest at the other Manchester one) — and the four-word ones are as shipped.
  it.each([
    ["Defensa y Justicia", "Defensa y Justicia"],
    ["Heart of Midlothian", "Heart of Midlothian"],
    ["Wingate and Finchley", "Wingate and Finchley"],
    ["Vasco da Gama", "Vasco da Gama"],
    ["2 de Mayo", "2 de Mayo"],
    ["Bourg en Bresse", "Bourg en Bresse"],
    ["FC United of Manchester", "United of Manchester"],
    ["Aldosivi Mar del Plata", "Plata"],
    ["Churriana de la Vega", "Vega"],
  ])("%s → %s", (name, label) => {
    expect(teamShortName(name, null, SOCCER)).toBe(label);
  });

  it("a person's name under a soccer key never takes the particle walk", () => {
    // Two words, kept whole by the club rule — not hoisted by the person rule.
    expect(teamShortName("Alex de Minaur", null, SOCCER)).toBe("Alex de Minaur");
  });
});
