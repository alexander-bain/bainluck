/**
 * #1930 regression guard — the /daily category label must never lowercase a
 * capital the source supplied.
 *
 * `category` on a /daily question is `data.sport_name || data.llm_sport_category`
 * (app/daily/page.tsx:154,175). The `llm_sport_category` half is a lowercase
 * slug ("mma") and wants shouting; the `sport_name` half is `sports.name`,
 * which is ALREADY human-cased — "MiLB", "FA Cup", "Liga MX", "DFB-Pokal",
 * "HockeyAllsvenskan", "AFL". A caser that re-cases every word fixes the first
 * half and breaks the second: measured against the live `sports.name` rows
 * below, `toTitleCaseAcronymSafe` loses a supplied capital on 24 of 179.
 *
 * LIVE_SPORT_NAMES is a snapshot of `SELECT name FROM sports` taken
 * 2026-09-22 (artifacts/ux-1437/pop-sport-names.json). It is a specimen, not
 * the contract: the property asserted holds for any input, and the snapshot
 * only proves the property has real work to do. The last test is the control
 * — it fails if the rejected caser ever stops losing capitals, which would
 * mean this guard had gone vacuous.
 */

import { categoryLabel } from "../components/daily/TodaysSetCard";
import {
  toAcronymSafePreservingCase,
  toTitleCaseAcronymSafe,
} from "../lib/titleCase";
import { CATEGORY_ACRONYMS } from "../lib/categoryAcronyms.generated";

const LIVE_SPORT_NAMES: readonly string[] = [
  "3. Liga - Germany",
  "AFL",
  "AFL Women's",
  "AHL",
  "A-League",
  "Allsvenskan - Sweden",
  "americanfootball_other",
  "ATP Australian Open",
  "ATP Barcelona Open",
  "ATP Canadian Open",
  "ATP Cincinnati Open",
  "ATP Dubai",
  "ATP French Open",
  "ATP Halle Open",
  "ATP Hamburg Open",
  "ATP Indian Wells",
  "ATP Italian Open",
  "ATP Madrid Open",
  "ATP Miami Open",
  "ATP Monte-Carlo Masters",
  "ATP Munich",
  "ATP Qatar Open",
  "ATP Queen's Club Championships",
  "ATP US Open",
  "ATP Washington Open",
  "ATP Wimbledon",
  "Austrian Football Bundesliga",
  "baseball_other",
  "Basketball Euroleague",
  "basketball_other",
  "Belgium First Div",
  "Boxing",
  "boxing_other",
  "Brazil S\u00e9rie A",
  "Brazil S\u00e9rie B",
  "Bundesliga 2 - Germany",
  "Bundesliga - Germany",
  "CFL",
  "Championship",
  "Copa del Rey",
  "Copa Libertadores",
  "Copa Sudamericana",
  "Coppa Italia",
  "Coupe de France",
  "CPLT20",
  "cricket_other",
  "Denmark Superliga",
  "DFB-Pokal",
  "Dutch Eredivisie",
  "EFL Cup",
  "Ekstraklasa - Poland",
  "Eliteserien - Norway",
  "EPL",
  "esports",
  "esports_other",
  "FA Cup",
  "FIFA World Cup",
  "FIFA World Cup Qualifiers - Europe",
  "FIFA World Cup Winner",
  "Frauen-Bundesliga",
  "golf_other",
  "Handball-Bundesliga",
  "HockeyAllsvenskan",
  "Icehockey Ncaa",
  "Ice Hockey - Olympics",
  "icehockey_other",
  "International Twenty20",
  "IPL",
  "J League",
  "KBO",
  "K League 1",
  "lacrosse_other",
  "La Liga 2 - Spain",
  "La Liga - Spain",
  "League 1",
  "League 2",
  "League of Ireland",
  "Leagues Cup",
  "Liga MX",
  "Ligue 1 - France",
  "Ligue 2 - France",
  "Liiga",
  "Masters Tournament Winner",
  "Mestis",
  "MiLB",
  "MLB",
  "MLB Preseason",
  "MLB World Series Winner",
  "MLS",
  "MMA",
  "mma_other",
  "motorsport_other",
  "NBA",
  "NBA All Star",
  "NBA Championship Winner",
  "NBA Summer League",
  "NBL",
  "NCAAB",
  "NCAA Baseball",
  "NCAAB Championship Winner",
  "NCAAF",
  "NCAAF Championship Winner",
  "NCAAF FCS",
  "NCAA Lacrosse",
  "NFL",
  "NFL Preseason",
  "NFL Super Bowl Winner",
  "NHL",
  "NHL Championship Winner",
  "NHL Preseason",
  "NPB",
  "NRL",
  "NRLW",
  "One Day Internationals",
  "Pakistan Super League",
  "PGA Championship Winner",
  "PLL",
  "Premier League - Russia",
  "Premiership - Scotland",
  "Primeira Liga - Portugal",
  "Primera Divisi\u00f3n - Argentina",
  "Primera Divisi\u00f3n - Chile",
  "rugby_other",
  "Saudi Pro League",
  "Serie A - Italy",
  "Serie B - Italy",
  "SHL",
  "Six Nations",
  "soccer_other",
  "State of Origin",
  "Superettan - Sweden",
  "Super League - China",
  "Super League - Greece",
  "Swiss Superleague",
  "T20 Blast",
  "T20 Women's World Cup",
  "T20 World Cup",
  "Tennis Atp",
  "tennis_other",
  "Tennis Wta",
  "Test Matches",
  "The Hundred",
  "The Hundred - Women's",
  "The Open Winner",
  "Turkey Super League",
  "UEFA Champions League",
  "UEFA Champions League Qualification",
  "UEFA Champions League Women",
  "UEFA Europa Conference League",
  "UEFA Europa League",
  "UEFA Nations League",
  "UFL",
  "US Open Winner",
  "US Presidential Elections Winner",
  "Veikkausliiga - Finland",
  "WNBA",
  "WNCAAB",
  "WTA Australian Open",
  "WTA Bad Homburg Open",
  "WTA Canadian Open",
  "WTA Charleston Open",
  "WTA Cincinnati Open",
  "WTA Dubai Championships",
  "WTA French Open",
  "WTA German Open",
  "WTA Guadalajara Open",
  "WTA Indian Wells",
  "WTA Internationaux de Strasbourg",
  "WTA Italian Open",
  "WTA Madrid Open",
  "WTA Miami Open",
  "WTA Monterrey Open",
  "WTA Qatar Open",
  "WTA Queen's Club Championships",
  "WTA Singapore Open",
  "WTA Stuttgart Open",
  "WTA US Open",
  "WTA Washington Open",
  "WTA Wimbledon",
];

/** Tokens the source supplied with a capital that the output lowercased. */
function suppliedCapitalsLost(source: string, output: string): string[] {
  const src = source.replace(/_/g, " ").trim().split(/\s+/);
  const out = output.split(/\s+/);
  return src.filter((token, i) => {
    const got = out[i] ?? "";
    return [...token].some((ch, j) => ch >= "A" && ch <= "Z" && got[j] !== ch);
  });
}

describe("#1930 the /daily category label keeps the casing it was given", () => {
  it("loses no supplied capital across every live sports.name", () => {
    const broken = LIVE_SPORT_NAMES.map((name) => [
      name,
      categoryLabel({ category: name }),
    ])
      .filter(([name, label]) => suppliedCapitalsLost(name, label).length > 0)
      .map(([name, label]) => `${name} -> ${label}`);
    expect(broken).toEqual([]);
  });

  it("leaves the names the rejected caser mangled exactly as they arrived", () => {
    expect(categoryLabel({ category: "AFL" })).toBe("AFL");
    expect(categoryLabel({ category: "MiLB" })).toBe("MiLB");
    expect(categoryLabel({ category: "FA Cup" })).toBe("FA Cup");
    expect(categoryLabel({ category: "Liga MX" })).toBe("Liga MX");
    expect(categoryLabel({ category: "DFB-Pokal" })).toBe("DFB-Pokal");
    expect(categoryLabel({ category: "NCAAF FCS" })).toBe("NCAAF FCS");
    expect(categoryLabel({ category: "HockeyAllsvenskan" })).toBe(
      "HockeyAllsvenskan",
    );
    expect(categoryLabel({ category: "ATP Monte-Carlo Masters" })).toBe(
      "ATP Monte-Carlo Masters",
    );
  });

  it("still shouts every shared-authority token from a bare slug", () => {
    for (const token of CATEGORY_ACRONYMS) {
      expect(categoryLabel({ category: token.toLowerCase() })).toBe(token);
    }
  });

  it("still capitalises a leading lower-case letter and splits underscores", () => {
    expect(categoryLabel({ category: "politics" })).toBe("Politics");
    expect(categoryLabel({ category: "table_tennis" })).toBe("Table Tennis");
    expect(categoryLabel({ category: "soccer_spain_la_liga" })).toBe(
      "Soccer Spain La Liga",
    );
  });

  it("shouts an acronym even when the rest of the name is already cased", () => {
    expect(toAcronymSafePreservingCase("Tennis Atp")).toBe("Tennis ATP");
    expect(toAcronymSafePreservingCase("Icehockey Ncaa")).toBe("Icehockey NCAA");
  });

  // CONTROL — not a test of the product. If this goes green, the guard above
  // is no longer distinguishing the two casers and has stopped protecting
  // anything; fix the control, never delete it.
  it("control: the rejected caser really does lose capitals on this population", () => {
    const mangled = LIVE_SPORT_NAMES.filter(
      (name) => suppliedCapitalsLost(name, toTitleCaseAcronymSafe(name)).length > 0,
    );
    expect(mangled.length).toBeGreaterThan(20);
    expect(mangled).toContain("AFL");
    expect(mangled).toContain("MiLB");
    expect(mangled).toContain("FA Cup");
  });
});
