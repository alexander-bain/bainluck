/**
 * #4250 — the browser and the iPhone shorten a club's name by ONE rule, so
 * their designator sets have to agree, and until this file nothing checked.
 *
 * The defect that bought this guard: `https://bainluck.com/events/15306788` at
 * 390px printed the away side as **"AFC"** beside a full-length "Manchester
 * City FC", while the API served `away_team: "Sunderland AFC"` and the iPhone
 * app rendered it correctly. `TeamShortName.swift` has listed `afc` since
 * #3374; `frontend/lib/teamShortName.ts` relied on its `length <= 2` clause,
 * which is one letter too short for a three-letter club initial. 68 distinct
 * production names end in "AFC".
 *
 * Why the existing guard could not see it: `__tests__/ios/…SingleSource.test.ts`
 * is named for single-sourcing but reads the SWIFT only — it discovers Swift
 * re-implementations and never opens the browser's module. A guard scoped to
 * one client is a guard on one client (standing notice 33's lesson, arrived at
 * independently here).
 *
 * So this file reads BOTH definitions out of source and compares them. It is
 * deliberately not a transcription: a transcribed copy of a set is a third
 * implementation, and a third implementation is the bug this guards.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  isNonDistinctiveTrailingWord,
  teamShortName,
  teamShortNames,
} from "@/lib/teamShortName";

const SWIFT = join(
  __dirname,
  "../../ios/Bain Luck/Bain Luck/Utilities/TeamShortName.swift",
);
const WEB = join(__dirname, "../lib/teamShortName.ts");
const SWIFT_PAIR_FIXTURES = join(
  __dirname,
  "../../ios/Bain Luck/BainLuckTests/TeamShortNamePairTests.swift",
);

/** Every `"token"` inside the named bracketed literal, comments stripped. */
function tokensInLiteral(source: string, opener: RegExp): string[] {
  const start = source.search(opener);
  if (start === -1) return [];
  const from = source.indexOf("[", start);
  let depth = 0;
  let end = -1;
  for (let i = from; i < source.length; i += 1) {
    if (source[i] === "[") depth += 1;
    if (source[i] === "]") {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === -1) return [];
  const body = source
    .slice(from, end)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
  return Array.from(body.matchAll(/"([^"]+)"/g), (m) => m[1].toLowerCase());
}

const swiftDesignators = tokensInLiteral(
  readFileSync(SWIFT, "utf8"),
  /private static let designators\s*:\s*Set<String>\s*=/,
);
const webSuffixes = tokensInLiteral(
  readFileSync(WEB, "utf8"),
  /const CLUB_TYPE_SUFFIXES\s*:\s*ReadonlySet<string>\s*=/,
);

describe("#4250 — one team-short-name rule, two clients", () => {
  /**
   * The parser is the part of this file that can fail SILENTLY: a regex that
   * matches nothing yields an empty set, and every `for (const t of [])`
   * assertion below then passes having examined nothing. These two are the
   * reachability check, not a fact about football.
   */
  it("both definitions were actually found and read", () => {
    expect(swiftDesignators.length).toBeGreaterThanOrEqual(60);
    expect(webSuffixes.length).toBeGreaterThanOrEqual(30);
    // Anchors that must survive any future edit to either list.
    expect(swiftDesignators).toContain("afc");
    expect(webSuffixes).toContain("afc");
    // The comment-stripping must not eat the tokens themselves.
    expect(new Set(swiftDesignators).size).toBe(swiftDesignators.length);
    expect(new Set(webSuffixes).size).toBe(webSuffixes.length);
  });

  it("every designator the iPhone catches, the browser catches too", () => {
    const missed = swiftDesignators.filter(
      (token) => !isNonDistinctiveTrailingWord(token),
    );
    expect(missed).toEqual([]);
  });

  it("every club word the browser catches is in the iPhone's set", () => {
    const swift = new Set(swiftDesignators);
    const missed = webSuffixes.filter((token) => !swift.has(token));
    expect(missed).toEqual([]);
  });

  /**
   * The browser reaches most short tokens by LENGTH rather than by listing
   * them, which is the right design and also the reason a three-letter club
   * initial slipped through. This pins where each half of the coverage comes
   * from, so shortening the length clause cannot quietly re-open #4250.
   */
  it("the three-letter club initials are listed, not left to the length clause", () => {
    for (const token of ["afc", "wfc", "lfc", "pfk", "nps", "sad", "cfc"]) {
      expect(token.length).toBeGreaterThan(2);
      expect(webSuffixes).toContain(token);
      expect(isNonDistinctiveTrailingWord(token)).toBe(true);
    }
  });
});

/**
 * #4271 — the class this file could not see, and now can.
 *
 * #4250 added `state`, `calcio`, `academy`, `sporting` and `wfc` to the Swift
 * designator set. `TeamShortNamePairTests.swift` carries 234 production fixture
 * rows whose expected strings were captured BEFORE that, so 22 of them went on
 * asserting the pre-#4250 outputs and the Swift suite went red the moment #4250
 * landed on master (`ae83f1d1`). Nothing stopped it: **CI compiles no Swift**,
 * so every gate in the merge path — notices 13, 18, 28 and 32 alike — passed a
 * commit whose own test suite was failing 44 assertions.
 *
 * Compiling Swift in CI is the real repair and is not this ship. What IS
 * available is that the defect is a property of the fixture TEXT, checkable by
 * a source scan in jest, which CI does run:
 *
 *     if a fixture's team NAME ends in a Swift designator, that side's expected
 *     label must be the whole name — never a truncation of it
 *
 * because `TeamShortName.short` returns the full name for exactly those, and a
 * pair rule that only ever GROWS a label can never hand back less. Every one of
 * the 21 stale label expectations violates this ("Hove Albion WFC" for
 * "Brighton and Hove Albion WFC", "Calcio" for "Sassuolo Calcio", "Diego State"
 * for "San Diego State"); every corrected one satisfies it.
 *
 * The designator set is READ FROM THE SWIFT, never transcribed — a transcribed
 * copy is the third implementation this whole file exists to prevent — and the
 * check is deliberately scoped to LISTED tokens, so it re-implements no part of
 * `isDesignator` (the trailing-founding-year clause is not mirrored here, and
 * rows like "US Catanzaro 1929" are simply not examined).
 */
interface PairFixture {
  away: string;
  home: string;
  awayLabel: string;
  homeLabel: string;
}

/** Every `(…)` fixture row of the two tables in `TeamShortNamePairTests.swift`. */
function pairFixtures(source: string): PairFixture[] {
  const rows: PairFixture[] = [];
  for (const line of source.split("\n")) {
    if (!line.trim().startsWith('("')) continue;
    const s = Array.from(line.matchAll(/"([^"]*)"/g), (m) => m[1]);
    // `colliding` rows carry the historical shared label in slot 2; `clean`
    // rows do not. Both put the two expected LABELS immediately before the two
    // expected badges, so the labels are always slots -4 and -3.
    if (s.length !== 7 && s.length !== 6) continue;
    rows.push({
      away: s[0],
      home: s[1],
      awayLabel: s[s.length - 4],
      homeLabel: s[s.length - 3],
    });
  }
  return rows;
}

/** The rows that violate the invariant, as readable strings. */
function truncatedDesignatorNames(
  fixtures: PairFixture[],
  designators: ReadonlySet<string>,
): string[] {
  const endsInDesignator = (name: string) => {
    const words = name.trim().split(/\s+/);
    if (words.length < 2) return false;
    const last = words[words.length - 1].replace(/^[().,]+|[().,]+$/g, "");
    return designators.has(last.toLowerCase());
  };
  const bad: string[] = [];
  for (const row of fixtures) {
    if (endsInDesignator(row.away) && row.awayLabel !== row.away) {
      bad.push(`${row.away} → ${row.awayLabel}`);
    }
    if (endsInDesignator(row.home) && row.homeLabel !== row.home) {
      bad.push(`${row.home} → ${row.homeLabel}`);
    }
  }
  return bad;
}

describe("#4271 — the iPhone's pair fixtures agree with the iPhone's designator set", () => {
  const fixtureSource = readFileSync(SWIFT_PAIR_FIXTURES, "utf8");
  const fixtures = pairFixtures(fixtureSource);
  const swift = new Set(swiftDesignators);

  /**
   * The reachability check. A row parser that matches nothing returns `[]`, and
   * the invariant below then passes having examined no fixture at all — the
   * failure mode that let the stale rows survive in the first place.
   */
  it("the fixture tables were actually found and parsed", () => {
    expect(fixtures.length).toBeGreaterThanOrEqual(230);
    expect(fixtures).toContainEqual({
      away: "Clemson Tigers",
      home: "LSU Tigers",
      awayLabel: "Clemson Tigers",
      homeLabel: "LSU Tigers",
    });
    // …and the invariant must have real work to do, or it proves nothing.
    const examined = fixtures.filter((r) =>
      [r.away, r.home].some((n) => {
        const w = n.trim().split(/\s+/);
        return w.length > 1 && swift.has(w[w.length - 1].toLowerCase());
      }),
    );
    expect(examined.length).toBeGreaterThanOrEqual(40);
  });

  it("no fixture expects a designator-ending club to render as a truncation of itself", () => {
    expect(truncatedDesignatorNames(fixtures, swift)).toEqual([]);
  });

  /**
   * The control. An invariant that cannot fail is not an invariant, so the
   * three shapes that actually shipped red are fed back through the same
   * predicate and must all be caught.
   */
  it("catches the rows that shipped red", () => {
    const stale: PairFixture[] = [
      {
        away: "Arsenal WFC",
        home: "Brighton and Hove Albion WFC",
        awayLabel: "Arsenal WFC",
        homeLabel: "Hove Albion WFC",
      },
      {
        away: "Sassuolo Calcio",
        home: "FC Augsburg",
        awayLabel: "Calcio",
        homeLabel: "Augsburg",
      },
      {
        away: "San Diego State",
        home: "Portland State",
        awayLabel: "Diego State",
        homeLabel: "Portland State",
      },
    ];
    expect(truncatedDesignatorNames(stale, swift)).toEqual([
      "Brighton and Hove Albion WFC → Hove Albion WFC",
      "Sassuolo Calcio → Calcio",
      "San Diego State → Diego State",
    ]);
  });
});

describe("#4250 — the names a reader sees", () => {
  it("the photographed event hero names the club, not its initials", () => {
    expect(teamShortName("Sunderland AFC")).toBe("Sunderland AFC");
    expect(teamShortNames({ name: "Manchester City FC" }, { name: "Sunderland AFC" })).toEqual({
      home: "Manchester City FC",
      away: "Sunderland AFC",
    });
  });

  it("the rest of the measured population keeps its name", () => {
    for (const name of [
      "Barrow AFC", // AFC, 68 distinct names
      "Ashington AFC",
      "Athlone Town AFC",
      "Arsenal WFC", // WFC, 8
      "Manchester City WFC",
      "Liverpool LFC", // LFC, 2
      "Neftçi PFK", // PFK, 2
      "Volos NPS", // NPS, 2
      "Portimonense SAD", // SAD, 8
      "Ludogorets III", // III, 6 — a reserve side
      "Kai Kamaka III", // and a person's generational suffix
    ]) {
      expect(teamShortName(name)).toBe(name);
    }
  });

  /**
   * The controls. A set that grows without a floor eventually swallows the
   * 90% of names where the last word IS the team, so these have to fail if
   * the change went too far — including the two cases that look like club
   * initials and are not.
   */
  it("a name whose last word identifies the team still shortens", () => {
    expect(teamShortName("Los Angeles Lakers")).toBe("Lakers");
    expect(teamShortName("Baltimore Orioles")).toBe("Orioles");
    expect(teamShortName("Houston Dynamo")).toBe("Dynamo");
    // "FC RFS" and "FK RFS" are Riga Football School's own name (2 distinct
    // names on production), so RFS is deliberately absent from both sets.
    expect(teamShortName("FC RFS")).toBe("RFS");
    expect(isNonDistinctiveTrailingWord("rfs")).toBe(false);
    // Trailing "USA" (8) names somebody.
    expect(isNonDistinctiveTrailingWord("usa")).toBe(false);
  });
});
