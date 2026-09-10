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
  teamCrestBadge,
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

const swiftSource = readFileSync(SWIFT, "utf8");
const webSource = readFileSync(WEB, "utf8");

/** Swift source with line comments and block comments removed. Control below. */
function stripSwiftComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}
const swiftCode = stripSwiftComments(swiftSource);

const swiftDesignators = tokensInLiteral(
  swiftSource,
  /private static let designators\s*:\s*Set<String>\s*=/,
);
const webSuffixes = tokensInLiteral(
  webSource,
  /const CLUB_TYPE_SUFFIXES\s*:\s*ReadonlySet<string>\s*=/,
);
const swiftUnshippable = tokensInLiteral(
  swiftSource,
  /private static let unshippableBadges\s*:\s*Set<String>\s*=/,
);
const webUnshippable = tokensInLiteral(
  webSource,
  /const UNSHIPPABLE_BADGES\s*:\s*ReadonlySet<string>\s*=/,
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

/**
 * #4539 — the parity that mattered was never only the SET.
 *
 * #4466 gave the browser a badge rule the iPhone did not have: a name whose
 * distinctive part is three or more words takes their initials, so PSG stops
 * being "GER". It shipped to the browser alone, and for a day the two clients
 * disagreed on the badge for roughly a fifth of all names — this file was green
 * throughout, because it compared the designator sets and the badge rule is not
 * a set.
 *
 * So the checks below are on the RULE. They still read both files out of source
 * rather than transcribing either, for the same reason as everything above: a
 * transcribed copy is a third implementation.
 *
 * WHY THE SWIFT SIDE IS CHECKED STRUCTURALLY AND NOT BY OUTPUT. CI compiles no
 * Swift (#4302), so jest cannot call `TeamShortName.abbreviation` and diff it
 * against `teamCrestBadge` — the only honest output comparison lives in
 * `BainLuckTests/CrestBadgeInitialsTests.swift`, whose every expectation was read
 * off THIS module before being written down. What jest can prove is that the
 * iPhone still has the rule at all, and that the two halves it shares with the
 * browser — the token filter's source set and the unshippable backstop — have
 * not drifted apart again.
 */
describe("#4539 — one badge rule, two clients", () => {
  it("both unshippable-badge sets were actually found and read", () => {
    // The reachability check. A regex that matches nothing yields [], and every
    // assertion below then passes having compared two empty sets — the exact
    // way the set-only version of this file stayed green through #4466.
    expect(swiftUnshippable.length).toBeGreaterThanOrEqual(15);
    expect(webUnshippable.length).toBeGreaterThanOrEqual(15);
    expect(swiftUnshippable).toContain("wtf");
    expect(webUnshippable).toContain("wtf");
  });

  it("the two unshippable-badge sets are identical", () => {
    // A badge banned on one client and not the other is a badge that ships.
    const swift = new Set(swiftUnshippable);
    const web = new Set(webUnshippable);
    expect([...web].filter((t) => !swift.has(t))).toEqual([]);
    expect([...swift].filter((t) => !web.has(t))).toEqual([]);
  });

  it("the comment stripper is load-bearing and works", () => {
    // The scans below read CODE. The Swift's own doc comment names
    // `CLUB_TYPE_SUFFIXES` to explain why it borrows `designators` instead, so a
    // raw scan for that identifier fires on the CORRECT file — which is
    // `discoverCrestBadge4466.test.tsx`'s lesson arriving here by experiment: a
    // guard that reads its target's prose is measuring the prose.
    expect(stripSwiftComments("/// mentions CLUB_TYPE_SUFFIXES\n")).not.toMatch(
      /CLUB_TYPE_SUFFIXES/,
    );
    expect(stripSwiftComments("let x = CLUB_TYPE_SUFFIXES")).toMatch(
      /CLUB_TYPE_SUFFIXES/,
    );
    // …and it must not eat the code it is meant to keep.
    expect(swiftCode).toMatch(/static func abbreviation/);
    expect(swiftCode.length).toBeGreaterThan(1500);
  });

  it("the iPhone still forks on three or more distinctive tokens", () => {
    // Structural, and deliberately narrow: the fork's THRESHOLD and the fact
    // that it filters before counting. Deleting either — the failure mode that
    // silently reopens #4539 — changes both of these.
    expect(swiftCode).toMatch(/distinctiveTokens\s*\(/);
    expect(swiftCode).toMatch(/distinctive\.count\s*>=\s*3/);
    // …and the filter is the one this file already guarantees agrees with the
    // browser, rather than a second transcribed copy of CLUB_TYPE_SUFFIXES.
    expect(swiftCode).toMatch(/designators\.contains\(lower\)/);
    expect(swiftCode).not.toMatch(/CLUB_TYPE_SUFFIXES/);
  });

  it("the browser's own fork is still there to be matched", () => {
    // The other half of the same assertion. If #4466's rule is reverted or
    // rewritten on the web, the iPhone's port is the thing that is now wrong,
    // and this is the line that says so.
    expect(webSource).toMatch(/export function teamCrestBadge/);
    expect(webSource).toMatch(/distinctive\.length\s*<\s*3/);
  });

  it("the token filter agrees with the browser's predicate on the fork corpus", () => {
    // The Swift borrows `designators` in place of CLUB_TYPE_SUFFIXES, which is
    // only sound because containment is asserted BOTH ways above. This pins the
    // clauses that are NOT the set — length, squad marker, bare number, roman
    // numeral — against the browser's predicate, since the Swift restates them
    // rather than sharing them.
    for (const token of ["fc", "u20", "1846", "iii", "al", "sc"]) {
      expect(isNonDistinctiveTrailingWord(token)).toBe(true);
    }
    for (const token of ["paris", "saint", "germain", "lakers", "sadd"]) {
      expect(isNonDistinctiveTrailingWord(token)).toBe(false);
    }
  });

  it("the browser badges the photographed club correctly, under both spellings", () => {
    // The reader-visible anchor, and the pair is the point: the stored name is
    // an input and both spellings were live on production the same afternoon.
    // `CrestBadgeInitialsTests` asserts the identical pair on the iPhone.
    expect(teamCrestBadge("Paris Saint Germain")).toBe("PSG");
    expect(teamCrestBadge("Paris Saint-Germain")).toBe("PSG");
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
