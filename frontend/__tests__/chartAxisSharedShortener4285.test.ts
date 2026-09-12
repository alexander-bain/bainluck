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
import { teamShortNames } from "@/lib/teamShortName";

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

  it("no NEW component grows a fourth implementation", () => {
    // A RATCHET, not a clean sweep. These three still derive a team label
    // themselves and are recorded on #4285 rather than fixed here — widening
    // this ship to a badge rule (`PlayerPropsDashboard` slices to three letters,
    // which is #4466/#4537 territory and carries UNSHIPPABLE_BADGES with it)
    // would be a different change on another issue's evidence. The list may
    // SHRINK freely; anything new in it is a fourth copy of a rule that has now
    // been wrong four times.
    const known = [
      "SeriesProbability.tsx",
      "BookmakerTable.tsx",
      "PlayerPropsDashboard.tsx",
    ];
    const offenders = files
      .filter((f) => DERIVES_A_TEAM_LABEL.test(rendered(readFileSync(f, "utf8"))))
      .map((f) => f.split("/").pop()!)
      .sort();
    expect(offenders).toEqual([...known].sort());
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
