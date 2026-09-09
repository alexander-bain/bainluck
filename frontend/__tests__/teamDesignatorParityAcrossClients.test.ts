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
