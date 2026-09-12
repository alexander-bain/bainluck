// #4285 — THE WIN-PROBABILITY CHART STOPS NAMING BOTH CLUBS THE SAME WORD.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `bainluck.com/events/15305095` (Mansfield Town v Huddersfield Town, League
// One, Final), 390px, 2026-09-12 09:4x PT — `artifacts/ux-1218/`:
//
//     hero      Mansfield Town        FINAL · TIED        Huddersfield Town
//     chart     ← TOWN                                    → TOWN
//
// The hero names both clubs correctly and the chart directly beneath it labels
// BOTH ENDS OF ITS Y-AXIS `TOWN`. A reader cannot tell which direction is which
// club, on a chart whose entire job is to say which way the line is going.
//
// The issue was filed from the milder symptom: `Cádiz CF` in the hero and `CF`
// on the axis, `Manchester City` -> `FC`, `Sunderland AFC` -> `AFC`.
//
// ── THE MECHANISM ────────────────────────────────────────────────────────────
//
// `OddsChart.tsx` and `ScoreDifferentialChart.tsx` each carried their own copy
// of a THIRD shortening rule, with no designator list at all — no list of any
// kind:
//
//     const homeShort = homeTeamAbbrev || homeTeam.split(" ").pop() || homeTeam;
//
// #4250 fixed the designator rule in `lib/teamShortName.ts` AND in Swift, with a
// parity guard across the two clients. It could not reach here, because neither
// chart calls either implementation. The parity guard compares the two
// designator SETS, so it is structurally blind to a component that consults no
// set — the same lesson #4250 itself recorded, one rung further out.
//
// ── THE MEASUREMENT THAT SET THE PRIORITY ────────────────────────────────────
//
// All 13,630 distinct `home_team_name`/`away_team_name` values on `events` in 45
// days, each run through the REAL `lib/teamShortName.ts` (jest, not a Python
// approximation of it) against the literal last-word rule above:
//
//   * 2,221 names / 20,505 team-slots label the axis differently from the hero
//   * 20,001 of those 20,505 have no `*Abbrev` to rescue them — the abbreviation
//     escape hatch covers 2.9% of slots and is not one
//   * 1,367 names / 8,199 slots render a ONE- OR TWO-GLYPH axis (`FC`, `CF`,
//     `GF`, `SE`, `FK`)
//   * 3,390 events (3.4%) give BOTH axes the SAME label — 5.6% once esports is
//     excluded, and it reaches the EPL (Coventry City v Hull City), the
//     Championship, MLS (Atlanta United FC v Charlotte FC) and the FA Cup.
//
// ── WHY THE PAIR FORM ────────────────────────────────────────────────────────
//
// `teamShortNames`, not `teamShortName`. The collision is the worst of the three
// symptoms and ONE SIDE ALONE CANNOT SEE IT — which is precisely why the pair
// form exists. Its docstring names this exact failure ("otherwise the card says
// 'FC' beat 'FC'"), so the helper that prevents the class was sitting one import
// away while the chart produced the class. The adoption is the fix; the census
// is why it is p2 rather than a tidy-up.
//
// ── WHY A SOURCE SCAN FOR HALF OF IT ─────────────────────────────────────────
//
// Same reasoning as #4083 and #3427 on this same file: the subject is JSX inside
// a component, jsdom does not lay out, and there is no value to call. So the
// adoption is scanned and the RULE is tested as arithmetic — and every scan below
// carries a POSITIVE CONTROL built from the line that actually shipped, so a
// rule that has stopped describing the bug fails here rather than passing quietly.

import { readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";
import { teamCrestBadge, teamShortNames } from "@/lib/teamShortName";

const COMPONENTS = join(process.cwd(), "components");

/** The exact line that shipped, kept verbatim as the positive control. */
const THE_DEFECT =
  'const homeShort = homeTeamAbbrev || homeTeam.split(" ").pop() || homeTeam;';

/**
 * A team's short name derived on the spot, rather than asked for.
 *
 * NARROW ON PURPOSE. `split(" ").pop()` on its own is a sibling concept in this
 * tree and firing on it would make this guard a nuisance that the next person
 * deletes: `RelatedFutures` and `PlayerPropsGrid` use it to MATCH names (never
 * to print one), and the golf surfaces use it for a PLAYER's last name, which is
 * the right answer for a person. What is banned is deriving the label for a
 * `home`/`away` TEAM, so the pattern is anchored on that variable.
 */
const DERIVES_A_TEAM_LABEL = /(?:home|away)Team\w*\??\.split\(" "\)\.pop\(\)/;

/** JSX with comments stripped — this file's own prose quotes the banned line. */
function rendered(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

function tsxFilesUnder(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...tsxFilesUnder(path));
    else if (entry.endsWith(".tsx") || entry.endsWith(".ts")) out.push(path);
  }
  return out;
}

describe("#4285 one team-shortening rule, and the chart uses it", () => {
  const files = tsxFilesUnder(COMPONENTS);

  it("the scan has a population (a broken walk makes every rule below vacuous)", () => {
    expect(files.length).toBeGreaterThan(40);
    expect(files.some((f) => f.endsWith("OddsChart.tsx"))).toBe(true);
    expect(files.some((f) => f.endsWith("ScoreDifferentialChart.tsx"))).toBe(true);
  });

  it("the pattern still describes the bug", () => {
    // POSITIVE CONTROL. Without this, narrowing the regex until it matches
    // nothing would turn every rule below green, which is the failure mode a
    // source scan has and an assertion on a value does not.
    expect(THE_DEFECT).toMatch(DERIVES_A_TEAM_LABEL);
    // And it must NOT fire on the two sibling concepts, or it gets deleted.
    expect('const lastName = golfer.name.split(" ").pop() || golfer.name;').not.toMatch(
      DERIVES_A_TEAM_LABEL,
    );
    expect('home_team.split(" ").pop()!.toLowerCase()').not.toMatch(DERIVES_A_TEAM_LABEL);
  });

  it.each(["OddsChart.tsx", "ScoreDifferentialChart.tsx"])(
    "%s derives no team label of its own",
    (name) => {
      const source = rendered(
        readFileSync(files.find((f) => f.endsWith(name))!, "utf8"),
      );
      expect(source).not.toMatch(DERIVES_A_TEAM_LABEL);
      // Adoption, not just absence: a file that simply deleted the line would
      // pass the rule above and render nothing.
      expect(source).toContain("teamShortNames(");
      expect(source).toMatch(/name:\s*homeTeam/);
      expect(source).toMatch(/name:\s*awayTeam/);
    },
  );

  it("no component derives a team label of its own", () => {
    // THE RATCHET IS NOW EMPTY (#5671). It shipped holding the three sites
    // #4285 deliberately left — `SeriesProbability` and `BookmakerTable` (the
    // pair form) and `PlayerPropsDashboard` (the badge ladder, #4466/#4537
    // territory, which is why it was a separate change and not a wider #4285).
    // The list was allowed to shrink freely and has shrunk to nothing, so the
    // assertion is now the flat one: there is ONE team-shortening rule in this
    // tree and every component asks for it.
    const offenders = files
      .filter((f) => DERIVES_A_TEAM_LABEL.test(rendered(readFileSync(f, "utf8"))))
      .map((f) => f.split("/").pop()!)
      .sort();
    expect(offenders).toEqual([]);
  });
});

describe("#5671 the three sites #4285 left behind", () => {
  const files = tsxFilesUnder(COMPONENTS);
  const sourceOf = (name: string) =>
    rendered(readFileSync(files.find((f) => f.endsWith(name))!, "utf8"));

  // ADOPTION, NOT ABSENCE. Every rule here has an absence half already covered
  // by the ratchet above, and an absence assertion passes on a DELETION — a
  // component that stopped labelling its two sides at all would satisfy it
  // while rendering nothing. So each site is also asserted to ASK for the
  // helper it should be asking for, and for the right one: the two that print
  // a NAME take the pair form, the one that prints a BADGE takes the badge.
  it.each(["SeriesProbability.tsx", "BookmakerTable.tsx"])(
    "%s names both sides through the pair helper",
    (name) => {
      const source = sourceOf(name);
      expect(source).toContain("teamShortNames(");
      expect(source).toMatch(/name:\s*homeTeam/);
      expect(source).toMatch(/name:\s*awayTeam/);
      // The pair form specifically — `teamShortName` twice cannot see the
      // collision, which is the whole reason the pair form exists. `\(` cannot
      // match `teamShortNames(`, so this catches the singular at any argument
      // (a negative lookahead on the ARGUMENT would miss `teamShortName(side)`).
      expect(source).not.toMatch(/\bteamShortName\(/);
    },
  );

  it("PlayerPropsDashboard takes the badge ladder, not the name helper", () => {
    const source = sourceOf("PlayerPropsDashboard.tsx");
    expect(source).toContain("teamCrestBadge(");
    // A three-glyph chip is not a name slot: `teamShortName` FAILS SAFE by
    // returning the full name, and slicing that to three prints a fragment
    // with a space in it ("AC Milan U20" -> "AC "). That is #4466 by name.
    expect(source).not.toContain("teamShortNames(");
    expect(source).not.toMatch(/slice\(0,\s*3\)\.toUpperCase\(\)/);
  });

  it("the pair helper answers the three sites' own production specimens", () => {
    // Not examples — rows these three components actually draw. The series bar
    // and the sportsbook table both render on MLB and EFL event pages.
    const { home, away } = teamShortNames(
      { name: "Boston Red Sox" },
      { name: "Kansas City Royals" },
    );
    expect(home).toBe("Sox");
    expect(away).toBe("Royals");

    // The collision the column headers could not see. Both sides fall back to
    // their full names rather than heading two columns with one word.
    const towns = teamShortNames(
      { name: "Mansfield Town" },
      { name: "Huddersfield Town" },
    );
    expect(towns.home.toLowerCase()).not.toEqual(towns.away.toLowerCase());

    // And the designator case, which the last-word rule gets wrong on one side
    // while looking fine on the other.
    const cf = teamShortNames({ name: "Cádiz CF" }, { name: "Arsenal" });
    expect(cf.home).not.toBe("CF");
    expect("Cádiz CF".split(" ").pop()).toBe("CF"); // the specimen is a specimen
  });

  it("the badge helper answers PlayerPropsDashboard's own specimens", () => {
    // Three glyphs kept, so the filter chips do not change width.
    expect(teamCrestBadge("Boston Red Sox")).toHaveLength(3);
    expect(teamCrestBadge("Kansas City Royals")).toHaveLength(3);

    // The spelling-independence the shipped rule did not have. Both of these
    // were live on production the same afternoon (#4466).
    expect(teamCrestBadge("Paris Saint-Germain")).toEqual(
      teamCrestBadge("Paris Saint Germain"),
    );
    // ...and the shipped rule disagreed with itself on them, which is why the
    // assertion above is not trivially true.
    const shipped = (n: string) => n.split(" ").pop()!.slice(0, 3).toUpperCase();
    expect(shipped("Paris Saint-Germain")).not.toEqual(
      shipped("Paris Saint Germain"),
    );

    // An empty name gets a readable chip rather than an empty one.
    expect(teamCrestBadge("") || "HOME").toBe("HOME");
    expect(teamCrestBadge(null) || "AWAY").toBe("AWAY");
  });
});

describe("#4285 the rule the chart now asks", () => {
  // The production collision pairs from the census, by name. These are the rows
  // that drew `← TOWN` over `→ TOWN`; they are the test's evidence, not examples.
  const collisions: Array<[string, string]> = [
    ["Mansfield Town", "Huddersfield Town"],
    ["Coventry City", "Hull City"],
    ["Atlanta United FC", "Charlotte FC"],
    ["Cheltenham Town", "Grimsby Town"],
    ["Oxford United", "Cambridge United"],
    ["Tianjin Jinmen Tiger FC", "Liaoning Tieren FC"],
  ];

  it.each(collisions)("%s v %s gets two labels a reader can tell apart", (home, away) => {
    const { home: h, away: a } = teamShortNames({ name: home }, { name: away });
    expect(h.toLowerCase()).not.toEqual(a.toLowerCase());
    expect(h).toBeTruthy();
    expect(a).toBeTruthy();
  });

  it("the last-word rule these replace produced the collision", () => {
    // The other half of the positive control: proof the specimens above are
    // specimens. If the shipped rule had never collided on them, the assertions
    // above would be testing nothing.
    for (const [home, away] of collisions) {
      expect(home.split(" ").pop()!.toLowerCase()).toEqual(
        away.split(" ").pop()!.toLowerCase(),
      );
    }
  });

  it("a club whose name ends in a designator keeps its name on the axis", () => {
    // The milder symptom the issue was filed from, and the 8,199-slot one.
    for (const [name, wrong] of [
      ["Cádiz CF", "CF"],
      ["Manchester City FC", "FC"],
      ["Sunderland AFC", "AFC"],
      ["Atalanta BC", "BC"],
      ["Viking FK", "FK"],
    ] as Array<[string, string]>) {
      const { home } = teamShortNames({ name }, { name: "Arsenal" });
      expect(home).not.toEqual(wrong);
      expect(name.split(" ").pop()).toEqual(wrong); // the specimen is a specimen
    }
  });
});
