/**
 * #7390 — WEB SEARCH'S TEAM ROW PRINTED THE DATABASE KEY. #5780's web twin.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Production, 390px, 2026-09-20 07:04Z, `/search?q=red sox`
 * (`artifacts/ux-1380/BEFORE-redsox-top.png`): a filter pill reading
 * **`MiLB (6)`**, and 350 pixels under it the Worcester Red Sox card reading
 * **`MILB`**. Same payload, same screen, two spellings. `?q=bayern` is the same
 * shape twice over: pill `Bundesliga - Germany (5)` over a card saying
 * **`GERMANY BUNDESLIGA`**, pill `EuroLeague (1)` over **`EUROLEAGUE`**.
 *
 * The line:
 *
 *     // frontend/app/search/page.tsx:171 (TeamCard)
 *     const sportLabel = team.sport_key
 *       ? team.sport_key.split("_").slice(1).join(" ").toUpperCase()
 *       : null;
 *
 * `baseball_milb` → `milb` → `MILB`. The GAME cards on the same screen were
 * already right — this was the team card alone.
 *
 * ═══ 🪤 THE OBVIOUS FIX IS NOT THE FIX ═══
 *
 * `getLeagueDisplay` has no `baseball_milb` entry, the key does not end
 * `_other`, and it is not a bare category — so it falls through to its own
 * parse, `parts.slice(1).map(toUpperCase).join(" ")`, which is byte-identical
 * to the deleted line and returns `MILB` too. Routing the call site onto the
 * shared helper would have passed review, moved nothing on the specimen, and
 * banked a false fix. `pillAndRowAgreeWherever…` below is the arm that fails
 * for that mutant.
 *
 * ═══ SCALE, MEASURED ═══
 *
 * Production `sports ⋈ teams`, 2026-09-19 (178 rows, 9,917 teams). Through the
 * real helper over the real rows: **157 of 178 keys change**, covering **8,402
 * of 9,917 teams**. The largest are `soccer_usa_mls` (697 teams, served "MLS",
 * printed "USA MLS"), `mma_mixed_martial_arts` (1,246, "MMA" vs "MIXED MARTIAL
 * ARTS") and `baseball_ncaa` (455, "NCAA Baseball" vs "NCAA").
 *
 * ═══ THE RULE ═══
 *
 * 1. the served facet name — `results.sports`, the array the PILLS are built
 *    from, read through `getSportLabel`, the pills' own rule, so the two cannot
 *    disagree rather than merely happening to agree;
 * 2. no facet (a team whose sport has no game on the page) or a row that stores
 *    its own key where a brand belongs: the curated name, else the SPORT FAMILY
 *    ("Baseball"). Coarse deliberately — native's note on why holds for web.
 *
 * No arm parses a key, and the tree scan at the bottom keeps it that way.
 */

import { readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

import { TeamCard } from "@/app/search/page";
import {
  getSportLabel,
  getTeamRowSportLabel,
} from "@/lib/sportCategories";
import type { SearchSportFacet, SearchTeam } from "@/lib/types";

// ---------------------------------------------------------------------------
// The corpus — production rows, not a sample somebody could have written
// ---------------------------------------------------------------------------

/**
 * `SELECT s.key, s.name, COUNT(t.id) FROM sports s LEFT JOIN teams t ON
 * t.sport_id = s.id GROUP BY 1,2`, production, 2026-09-19. The keys a
 * hand-written list would never have held — a Swedish hockey league, an FCS
 * football tier, a handball league whose family this repo has no category for
 * — are the ones this ship is about, so the corpus is drawn from the table.
 *
 * `noFacet` is the label when the page holds no served name for the key, which
 * is a REAL case: the facet is tallied over the matched EVENTS, so a team whose
 * sport has no game among the results is absent from it.
 */
const CORPUS: {
  key: string;
  served: string;
  teams: number;
  want: string;
  noFacet: string;
}[] = [
  { key: "mma_mixed_martial_arts", served: "MMA", teams: 1246, want: "MMA", noFacet: "MMA" },
  { key: "boxing_boxing", served: "Boxing", teams: 919, want: "Boxing", noFacet: "Boxing" },
  { key: "soccer_usa_mls", served: "MLS", teams: 697, want: "MLS", noFacet: "Soccer" },
  { key: "baseball_ncaa", served: "NCAA Baseball", teams: 455, want: "NCAA Baseball", noFacet: "NCAA Baseball" },
  { key: "basketball_ncaab", served: "NCAAB", teams: 366, want: "NCAAB", noFacet: "NCAAB" },
  { key: "americanfootball_ncaaf_fcs", served: "NCAAF FCS", teams: 115, want: "NCAAF FCS", noFacet: "Football" },
  { key: "soccer_england_efl_cup", served: "EFL Cup", teams: 73, want: "EFL Cup", noFacet: "Soccer" },
  { key: "soccer_uefa_champs_league", served: "UEFA Champions League", teams: 44, want: "UEFA Champions League", noFacet: "Soccer" },
  { key: "tennis_atp_queens_club_champ", served: "ATP Queen's Club Championships", teams: 34, want: "ATP Queen's Club Championships", noFacet: "Tennis" },
  { key: "soccer_germany_bundesliga", served: "Bundesliga - Germany", teams: 32, want: "Bundesliga - Germany", noFacet: "Soccer" },
  { key: "baseball_milb", served: "MiLB", teams: 30, want: "MiLB", noFacet: "Baseball" },
  { key: "soccer_spain_la_liga", served: "La Liga - Spain", teams: 27, want: "La Liga - Spain", noFacet: "Soccer" },
  { key: "cricket_odi", served: "One Day Internationals", teams: 26, want: "One Day Internationals", noFacet: "Cricket" },
  { key: "soccer_netherlands_eredivisie", served: "Dutch Eredivisie", teams: 21, want: "Dutch Eredivisie", noFacet: "Soccer" },
  { key: "basketball_euroleague", served: "Basketball Euroleague", teams: 21, want: "EuroLeague", noFacet: "EuroLeague" },
  { key: "handball_germany_bundesliga", served: "Handball-Bundesliga", teams: 20, want: "Handball-Bundesliga", noFacet: "Handball" },
  { key: "icehockey_sweden_hockey_league", served: "SHL", teams: 20, want: "SHL", noFacet: "SHL" },
];

/** The deleted line, kept verbatim in behaviour so the arms below test the
 *  defect rather than a sentence describing it. */
const shoutedKey = (key: string) =>
  key.split("_").slice(1).join(" ").toUpperCase();

const facetsFor = (rows: { key: string; served: string }[]): SearchSportFacet[] =>
  rows.map((r) => ({ key: r.key, name: r.served, count: 1 }));

// ---------------------------------------------------------------------------
// Part 1 — the served name wins
// ---------------------------------------------------------------------------

describe("#7390 the team row prints the name the server gave the league", () => {
  const allFacets = facetsFor(CORPUS);

  it("prints the served name for every production key, never the shouted key", () => {
    for (const row of CORPUS) {
      expect(getTeamRowSportLabel(row.key, allFacets)).toBe(row.want);
    }
  });

  it("the row and the filter pill built from the same payload say one thing", () => {
    // This is the screenshot as an assertion. Worcester Red Sox sat under a
    // pill reading "MiLB" and said "MILB" itself.
    const facets = facetsFor([
      { key: "baseball_mlb", served: "MLB" },
      { key: "baseball_milb", served: "MiLB" },
    ]);
    const pills = facets.map((f) => getSportLabel(f.key, f.name));
    const row = getTeamRowSportLabel("baseball_milb", facets);

    expect(row).toBe("MiLB");
    expect(pills).toContain(row);
    expect(row).not.toBe(shoutedKey("baseball_milb"));
  });

  it("agrees with the pill on every corpus row the page has a served name for", () => {
    // 🪤 THE ANTI-`getLeagueDisplay` ARM. A "fix" that routes the card onto
    // `getLeagueDisplay` returns "MILB", "GERMANY BUNDESLIGA" and "USA MLS"
    // while the pill beside it says "MiLB", "Bundesliga - Germany" and "MLS",
    // so it dies here on 14 of 17 rows.
    for (const row of CORPUS) {
      expect(getTeamRowSportLabel(row.key, allFacets)).toBe(
        getSportLabel(row.key, row.served),
      );
    }
  });

  it("keeps the hand-written name when the server's own is a machine spelling", () => {
    // `basketball_euroleague` is served as "Basketball Euroleague" — the key,
    // title-cased. The curated map's "EuroLeague" beats it, which is #4381's
    // rule and the reason this delegates to `getSportLabel` rather than taking
    // the served string raw.
    expect(
      getTeamRowSportLabel("basketball_euroleague", [
        { key: "basketball_euroleague", name: "Basketball Euroleague", count: 1 },
      ]),
    ).toBe("EuroLeague");
  });

  it("treats a blank served name as no name rather than drawing an empty line", () => {
    for (const blank of ["", "   "]) {
      expect(
        getTeamRowSportLabel("baseball_milb", [
          { key: "baseball_milb", name: blank, count: 1 },
        ]),
      ).toBe("Baseball");
    }
  });

  it("matches on the key, so a facet for a different sport is not borrowed", () => {
    expect(
      getTeamRowSportLabel("baseball_milb", [
        { key: "baseball_mlb", name: "MLB", count: 1 },
      ]),
    ).toBe("Baseball");
  });
});

// ---------------------------------------------------------------------------
// Part 2 — the fallback, when the page holds no name for the key
// ---------------------------------------------------------------------------

describe("#7390 with no served name the row still names a sport", () => {
  it("falls through to the exact values the shared rules answer with", () => {
    // Written out rather than asserted by property: "contains no underscore"
    // passes for the word "Market" too.
    for (const row of CORPUS) {
      expect(getTeamRowSportLabel(row.key, [])).toBe(row.noFacet);
    }
  });

  it("never prints a key, a fragment of one, or a shout", () => {
    for (const row of CORPUS) {
      const label = getTeamRowSportLabel(row.key, []) as string;
      expect(label).not.toContain("_");
      expect(label.length).toBeGreaterThan(0);
      // "NCAAF FCS", "NCAAB" and "SHL" are brands that are legitimately
      // all-caps — and `basketball_ncaab` is why this is a property and not
      // `not.toBe(shoutedKey(key))`: the deleted line produced "NCAAB" too, by
      // coincidence, on the one-token keys. A SHOUT is the multi-word
      // upper-casing of a key, which none of these are.
      if (label.includes(" ")) {
        expect(label).not.toBe(label.toUpperCase());
      }
    }
  });

  it("names the family for the one sport this repo has no category for", () => {
    // `handball_germany_bundesliga`, 20 teams. `getLeagueDisplay` answers
    // "GERMANY BUNDESLIGA" here — the defect, from the sanctioned helper — so
    // the last arm takes the key's family token instead.
    expect(getTeamRowSportLabel("handball_germany_bundesliga", [])).toBe("Handball");
    expect(getTeamRowSportLabel("handball_germany_bundesliga", [])).not.toBe(
      shoutedKey("handball_germany_bundesliga"),
    );
  });

  it("names a sport for the catch-all buckets and the bare categories", () => {
    expect(getTeamRowSportLabel("mma_other", [])).toBe("MMA");
    expect(getTeamRowSportLabel("basketball_other", [])).toBe("Basketball");
    expect(getTeamRowSportLabel("esports", [])).toBe("Esports");
  });

  it("returns nothing for no key, so the card draws no grey line at all", () => {
    expect(getTeamRowSportLabel(null, [])).toBeNull();
    expect(getTeamRowSportLabel(undefined, [])).toBeNull();
    expect(getTeamRowSportLabel("", [])).toBeNull();
    expect(getTeamRowSportLabel("   ", [])).toBeNull();
    expect(getTeamRowSportLabel("baseball_milb", undefined)).toBe("Baseball");
  });
});

// ---------------------------------------------------------------------------
// Part 3 — ANTI-VACUITY
// ---------------------------------------------------------------------------

describe("#7390 the corpus still contains the defect", () => {
  it("disagrees with the deleted line on most of it", () => {
    // If the corpus is ever refreshed from a fixed tree it proves nothing: a
    // BEFORE taken after the fix contains no defect (notice 50).
    const disagreements = CORPUS.filter((r) => shoutedKey(r.key) !== r.want);
    expect(disagreements.length).toBeGreaterThanOrEqual(13);
    const teams = disagreements.reduce((n, r) => n + r.teams, 0);
    expect(teams).toBeGreaterThan(3000);
  });

  it("reproduces the three labels the issue was filed on", () => {
    expect(shoutedKey("baseball_milb")).toBe("MILB");
    expect(shoutedKey("soccer_germany_bundesliga")).toBe("GERMANY BUNDESLIGA");
    expect(shoutedKey("soccer_usa_mls")).toBe("USA MLS");
  });
});

// ---------------------------------------------------------------------------
// Part 4 — the card itself, rendered
// ---------------------------------------------------------------------------

/**
 * A unit test of the helper passes on every day this bug was live: the rule was
 * never the problem, the CARD not asking for it was. So the specimen is
 * rendered with the payload production served.
 */
describe("#7390 the rendered team card", () => {
  const worcester: SearchTeam = {
    id: 8642,
    name: "Worcester Red Sox",
    slug: "worcester-red-sox",
    abbreviation: "WOR",
    logo: null,
    record: null,
    sport_key: "baseball_milb",
  };
  const redSoxFacets: SearchSportFacet[] = [
    { key: "baseball_mlb", name: "MLB", count: 38 },
    { key: "baseball_milb", name: "MiLB", count: 6 },
  ];

  it("prints MiLB under a pill saying MiLB", () => {
    const html = renderToStaticMarkup(
      <TeamCard team={worcester} sports={redSoxFacets} />,
    );
    expect(html).toContain("Worcester Red Sox");
    expect(html).toContain("MiLB");
    expect(html).not.toContain("MILB");
  });

  it("prints a sport, not a key, when the card is handed no facets", () => {
    const html = renderToStaticMarkup(<TeamCard team={worcester} />);
    expect(html).toContain("Baseball");
    expect(html).not.toContain("MILB");
    expect(html).not.toContain("baseball_milb");
  });

  it("puts the record and the league on one line, separated", () => {
    const html = renderToStaticMarkup(
      <TeamCard
        team={{ ...worcester, name: "Boston Red Sox", sport_key: "baseball_mlb", record: "84-71" }}
        sports={redSoxFacets}
      />,
    );
    expect(html).toContain("84-71");
    expect(html).toContain("·");
    expect(html).toContain("MLB");
  });

  it("renders no card at all for a team with no sport key", () => {
    // Stated because it is the reason there is no "record with no label" arm
    // above: `buildTeamPageUrl` needs the key to build a URL and returns null
    // without one, so the card returns null before it reaches a label.
    expect(
      renderToStaticMarkup(
        <TeamCard team={{ ...worcester, sport_key: null, record: "84-71" }} sports={redSoxFacets} />,
      ),
    ).toBe("");
  });
});

// ---------------------------------------------------------------------------
// Part 5 — the wiring pin
// ---------------------------------------------------------------------------

const PAGE_PATH = join(process.cwd(), "app/search/page.tsx");
const PAGE_SOURCE = readFileSync(PAGE_PATH, "utf8");

describe("#7390 the page hands the card the pills' own payload", () => {
  it("renders the card with `sports={results.sports}`", () => {
    // Without this the render above is a test of a component nothing calls
    // that way: `<TeamCard team={team} />` compiles, renders "Baseball", and
    // throws away the "MiLB" the page is holding.
    expect(PAGE_SOURCE).toMatch(/<TeamCard[^>]*sports=\{results\.sports\}/);
  });

  it("asks the shared rule for the label exactly once", () => {
    const calls = PAGE_SOURCE.split("\n").filter(
      (line) =>
        (line.split("//")[0] ?? line).includes("getTeamRowSportLabel("),
    );
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("team.sport_key");
  });
});

// ---------------------------------------------------------------------------
// Part 6 — the tree scan: nobody shortens a sport key into a label again
// ---------------------------------------------------------------------------

/**
 * The class is "someone derives a league label from a key on the spot". The
 * shape, not the vocabulary: splitting a key on `_` and casing the result is
 * not a label, wherever it appears.
 *
 * Matched by INDEX WINDOW rather than one screen-wide regex: a chain like
 * `key\n  .split("_")\n  .slice(1)\n  .toUpperCase()` is one expression over
 * four lines, which a line-by-line scan walks straight past, and a
 * newline-spanning regex over a 700-line page is the ReDoS shape CodeQL stops.
 * Comments are stripped first — a guard that cannot tell a defect from a
 * description of one applies its pressure to the explanation, and this very
 * file quotes the deleted line twice.
 */
const ROOT = process.cwd();
const SCANNED_DIRS = ["app", "components", "lib", "hooks"];

/**
 * `app/admin/**` is out of scope, named rather than quietly skipped: it is a
 * staff surface behind an admin token, no reader reaches it, and its one site
 * (`app/admin/source-intelligence/page.tsx`, `SPORT_NAMES[key] || key.split("_")
 * .pop()?.toUpperCase()`) cannot be routed onto the shared helper without
 * changing two of its labels — `soccer_usa_mls` renders "MLS" from its local
 * map and "USA MLS" from `getLeagueDisplay`. The control below proves the
 * matcher SEES that line, so this is scope and not blindness.
 *
 * `lib/sportCategories.ts` is the single source the scan funnels people into;
 * its own arms are tested by value above, not by shape.
 */
const EXCLUDED = ["app/admin/", "lib/sportCategories.ts"];

/** The exact line this ship deleted, kept as the positive control. */
const THE_DEFECT =
  'const sportLabel = team.sport_key\n    ? team.sport_key.split("_").slice(1).join(" ").toUpperCase()\n    : null;';

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/**
 * Offsets where a key is split on `_` and the result is cased within the next
 * 200 characters. 200 covers a four-line fluent chain and stops well short of
 * the next statement.
 */
function shoutedKeySites(source: string): string[] {
  const code = withoutComments(source);
  const hits: string[] = [];
  for (const token of ['split("_")', "split('_')"]) {
    let at = code.indexOf(token);
    while (at !== -1) {
      const window = code.slice(at, at + 200);
      if (/\.toUpperCase\(\)|\.toLocaleUpperCase\(\)/.test(window)) {
        hits.push(code.slice(at, at + 90).replace(/\s+/g, " "));
      }
      at = code.indexOf(token, at + 1);
    }
  }
  return hits;
}

function sourceFilesUnder(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next") continue;
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...sourceFilesUnder(path));
    else if (entry.endsWith(".ts") || entry.endsWith(".tsx")) out.push(path);
  }
  return out;
}

describe("#7390 no reader-facing file shortens a sport key into a label", () => {
  const files = SCANNED_DIRS.flatMap((d) => sourceFilesUnder(join(ROOT, d)))
    .map((p) => p.slice(ROOT.length + 1))
    .filter((p) => !EXCLUDED.some((x) => p.startsWith(x) || p === x));

  it("the scan reaches the tree it is about", () => {
    // A broken walk makes every rule below vacuous.
    expect(files.length).toBeGreaterThan(300);
    for (const control of [
      "app/search/page.tsx",
      "components/EventCard.tsx",
      "lib/teamUrls.ts",
    ]) {
      expect(files).toContain(control);
    }
  });

  it("the matcher still describes the defect, and not its neighbours", () => {
    expect(shoutedKeySites(THE_DEFECT)).toHaveLength(1);
    // The fixed form is not a defect.
    expect(
      shoutedKeySites("const sportLabel = getTeamRowSportLabel(team.sport_key, sports);"),
    ).toHaveLength(0);
    // A key split for a LOOKUP is not a label.
    expect(shoutedKeySites('const family = key.split("_")[0];')).toHaveLength(0);
    // The same defect written as a fluent chain over four lines — the shape a
    // line-by-line scan misses.
    expect(
      shoutedKeySites(
        'const label = team.sport_key\n  .split("_")\n  .slice(1)\n  .join(" ")\n  .toUpperCase();',
      ),
    ).toHaveLength(1);
    // And the admin site, to show the exclusion above is scope, not blindness.
    expect(
      shoutedKeySites('return SPORT_NAMES[key] || key.split("_").pop()?.toUpperCase() || key;'),
    ).toHaveLength(1);
  });

  it("finds no site in the reader-facing tree", () => {
    const offenders: string[] = [];
    for (const file of files) {
      for (const site of shoutedKeySites(readFileSync(join(ROOT, file), "utf8"))) {
        offenders.push(`${file} — ${site}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
