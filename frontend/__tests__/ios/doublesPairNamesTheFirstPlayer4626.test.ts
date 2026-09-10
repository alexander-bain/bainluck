/**
 * #4626 — the two clients name the SAME player in a doubles pair.
 *
 * #3110 ruled a pair is shown whole and its tile is three glyphs of the FIRST
 * surname, and gave the browser `isDoublesPair`. `TeamShortName.swift` never got
 * it, so for six months the site badged "Siniakova / Townsend" `SIN` and the
 * iPhone badged `TOW`, and "Milutinovic / Van de Peer" reached the doubles
 * surface reading `PEE` during the US Open.
 *
 * This file lives in jest because jest is a deploy gate here and the Swift test
 * target is not reachable from CI (standing notice 10) — the same reason
 * `teamShortNameSingleSource` and `ladderFooterComposesWithItsRung4645` do. The
 * Swift-side behaviour is asserted by
 * `ios/Bain Luck/BainLuckTests/DoublesPairNamesTheFirstPlayer4626Tests.swift`;
 * what CI can enforce is that the rule EXISTS on the Swift side and that the
 * values the Swift fixtures pin are the values the browser actually computes.
 *
 * WHY THE FIXTURES ARE READ OUT OF SOURCE RATHER THAN TRANSCRIBED. A copy of a
 * table that nothing checks is the third implementation this pair of modules
 * exists to prevent (`teamDesignatorParityAcrossClients.test.ts` makes the same
 * argument about the designator set). Reading the Swift expectations and running
 * the same inputs through the browser catches drift in EITHER direction: a Swift
 * fixture edited to match a broken Swift rule reds here, and a browser change
 * that moves pair handling reds here too.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { isDoublesPair, teamCrestBadge, teamShortName } from "@/lib/teamShortName";

const IOS_TESTS = join(__dirname, "../../../ios/Bain Luck/BainLuckTests");
const SWIFT_RULE = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Utilities/TeamShortName.swift",
);
const CREST_FIXTURES = join(IOS_TESTS, "CrestBadgeInitialsTests.swift");
const PAIR_FIXTURES = join(IOS_TESTS, "TeamShortNamePairTests.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/^[ \t]*\/\/\/.*$/gm, "");
}

/** The body of `static func <name>(` up to its matching closing brace. */
function swiftFuncBody(source: string, name: string): string {
  const at = source.search(new RegExp(`static func ${name}\\s*[(<]`));
  if (at === -1) return "";
  const open = source.indexOf("{", at);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(open + 1, i);
    }
  }
  return source.slice(open + 1);
}

describe("#4626 the doubles rule exists on the Swift side", () => {
  const swift = stripComments(readFileSync(SWIFT_RULE, "utf8"));

  it("declares isDoublesPair, and it tests a SPACED slash", () => {
    const body = swiftFuncBody(swift, "isDoublesPair");
    expect(body).not.toBe("");
    // An unspaced slash is part of one entity's own name ("Bodo/Glimt"), so a
    // rule that matched any slash would take a club's name apart. Pin the
    // separator, not the whole expression, so the body may be rewritten.
    expect(body).toContain('" / "');
  });

  /**
   * THE ASSERTION THAT REFUSES A BADGE-ONLY FIX. `abbreviation` already guarded
   * pairs before this issue (#4539 kept them out of the initials fork), so every
   * badge expectation can be satisfied while `short` — which also drives the
   * pair LABELS — still returns one player. The guard has to be in `short`.
   */
  it("guards `short`, not only the badge", () => {
    expect(swiftFuncBody(swift, "short")).toContain("isDoublesPair");
    expect(swiftFuncBody(swift, "abbreviation")).toContain("isDoublesPair");
  });
});

describe("#4626 the Swift fixtures agree with the browser", () => {
  /**
   * Every `XCTAssertEqual(TeamShortName.abbreviation("<pair>"), "<badge>")` in
   * the iOS test target, found by shape so a fixture moving file or method still
   * gets checked.
   */
  function pinnedBadges(path: string): [string, string][] {
    const source = stripComments(readFileSync(path, "utf8"));
    const re =
      /XCTAssertEqual\(\s*TeamShortName\.abbreviation\("([^"]*\s\/\s[^"]*)"\)\s*,\s*"([^"]*)"\s*\)/g;
    return [...source.matchAll(re)].map(m => [m[1], m[2]] as [string, string]);
  }

  /** The `clean` golden rows of `TeamShortNamePairTests` that hold a pair. */
  function pinnedPairRows(): {
    away: string;
    home: string;
    labels: [string, string];
    badges: [string, string];
  }[] {
    const source = stripComments(readFileSync(PAIR_FIXTURES, "utf8"));
    const re =
      /\("([^"]*)",\s*"([^"]*)",\s*\("([^"]*)",\s*"([^"]*)"\),\s*\("([^"]*)",\s*"([^"]*)"\)\)/g;
    return [...source.matchAll(re)]
      .filter(m => isDoublesPair(m[1]) || isDoublesPair(m[2]))
      .map(m => ({
        away: m[1],
        home: m[2],
        labels: [m[3], m[4]] as [string, string],
        badges: [m[5], m[6]] as [string, string],
      }));
  }

  it("finds the pair fixtures it is written to check", () => {
    // A regex that silently matches nothing is a green test that examined no
    // rows — the failure mode this repo has been bitten by often enough to
    // assert the denominator.
    expect(pinnedBadges(CREST_FIXTURES).length).toBeGreaterThanOrEqual(3);
    expect(pinnedPairRows().length).toBeGreaterThanOrEqual(4);
  });

  it("every pinned iOS badge is the badge the browser draws", () => {
    for (const [name, badge] of pinnedBadges(CREST_FIXTURES)) {
      expect([name, badge]).toEqual([name, teamCrestBadge(name)]);
    }
  });

  it("every pinned golden pair row matches the browser, label and badge", () => {
    for (const row of pinnedPairRows()) {
      for (const [i, name] of [row.away, row.home].entries()) {
        if (!isDoublesPair(name)) continue;
        expect([name, row.labels[i]]).toEqual([name, teamShortName(name)]);
        expect([name, row.badges[i]]).toEqual([name, teamCrestBadge(name)]);
      }
    }
  });

  it("names the FIRST player, which is the whole point of #3110", () => {
    for (const [name, badge] of pinnedBadges(CREST_FIXTURES)) {
      const [first, second] = name.split(" / ");
      expect(badge[0]).toBe(first.trim()[0].toUpperCase());
      // And not the second — stated separately so deleting either client's
      // guard reds on the thing a reader complained about.
      expect(badge).not.toBe(
        teamCrestBadge(second.trim().split(/\s+/).slice(-1)[0]),
      );
    }
  });
});

/**
 * THE ONE PLACE THE TWO CLIENTS STILL DISAGREE, on the record so nobody reads
 * the tests above as total parity.
 *
 * The browser's large badge is `teamShortName(full).slice(0, 3)`, three
 * CHARACTERS of the whole pair including the space; Swift's `glyphs(ofLabel:)`
 * takes three ALPHANUMERICS across word boundaries. They agree on every name
 * whose first side is three or more characters, which is all but three of the
 * 388 distinct pairs measured on production 2026-09-10 — the exceptions are
 * "Ho / Liutarevich", "Ho / Stalder" and "Li / Tauson", where the browser draws
 * `HO ` and `LI `: two glyphs and a hole on a crest.
 *
 * Swift is the correct one here (`CrestBadgeInitialsTests` has asserted a
 * three-real-glyph invariant since #4539), so this is not copied over. It is the
 * browser-side sibling of #4625 and is filed rather than fixed in an iOS ship.
 */
describe("#4626 the known divergence is named, not assumed away", () => {
  it("the browser pads a two-character first side; Swift does not", () => {
    expect(teamCrestBadge("Ho / Liutarevich")).toBe("HO ");
    expect(teamCrestBadge("Li / Tauson")).toBe("LI ");
    // If the browser is ever repaired, this reds and the comment above — and the
    // issue it points at — get revisited rather than quietly rotting.
    expect(teamCrestBadge("Ho / Liutarevich").trim().length).toBe(2);
  });
});
