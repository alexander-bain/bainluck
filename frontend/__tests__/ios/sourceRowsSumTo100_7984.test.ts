/**
 * #7984 — the event page's two source lists round a row's PAIR as one decision,
 * asserted by reading the Swift and by re-running the arithmetic.
 *
 * Photographed on iPhone 17 against production, 2026-09-22 01:59 PDT,
 * `bainluck://events/15316315` — `artifacts-native-020/n293-live-wta.png`:
 *
 *     Sportsbooks (7)   3%   97%
 *     Polymarket        42%  59%      <- 101
 *
 * The payload serves that source as ONE number, `0.585`. `sourceContent` derives
 * the away side as an exact complement and `probabilityBarAndNumbers` then
 * formatted the two sides independently, so a venue on the half-percent grid put
 * BOTH on `.5` and half-up rounded both up. Measured over 408 production events
 * that morning: 122 of 332 source rows printing a numeric pair summed to 101, on
 * 113 distinct events, plus 6 of 557 bookmaker rows. Every failure was 101 and
 * none 99.
 *
 * 🔴 WHY THIS FILE EXISTS AND `SourceRowsSumTo100_7984Tests` DOES NOT SUFFICE.
 * The Swift tests prove `duelProbabilityStrings`. They cannot prove the VIEW
 * calls it, and the view is where the defect lived — three inline expressions
 * inside `probabilityBarAndNumbers` and the two `EventSourceLabelColumn.columns`
 * arrays, none of them reachable from XCTest. Reverting any one of those call
 * sites leaves every Swift test green. The assertions below are what kill that
 * mutant, and they run in CI, which compiles no Swift.
 *
 * 🔴 AND THE SIZING ARRAYS ARE NOT DECORATION. `EventSourceLabelColumn` measures
 * the numeric column from the strings the rows will actually print (#4208,
 * #5271). A pair rule applied at draw time only would size the column against
 * text no row draws — the same defect from the other side — so all three call
 * sites are asserted, not just the one a reader's eye lands on.
 *
 * Comments are stripped before scanning: this fix documents the defect by quoting
 * it, and a scanner that reads prose as code reports the cure as the disease.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

import { swiftCode } from "../helpers/swiftSource";

const REPO_ROOT = join(__dirname, "../../..");
const APP_ROOT = join(REPO_ROOT, "ios/Bain Luck/Bain Luck");

const EVENT_DETAIL = join(APP_ROOT, "Views/EventDetailView.swift");
const FORMATTING = join(APP_ROOT, "Utilities/FormattingUtilities.swift");
const CONTRACT_ARM = join(APP_ROOT, "Utilities/RenderedPercent.swift");

const read = (path: string) => readFileSync(path, "utf8");

/**
 * The banned shapes, as constants, because the capability test below exercises
 * THE SAME predicates the production scan does. A capability test written
 * against its own private copy proves the copy works and says nothing about the
 * guard.
 *
 * Each is one side of a row formatted with no `renderedPercent:` — i.e. an
 * opinion about this row's percentage formed without reference to its other half.
 */
/** `formatProbabilityOrDash(probabilities.away)` — the away cell, decided alone. */
const LONE_AWAY_CELL = /formatProbabilityOrDash\(\s*probabilities\.away\s*\)/;
/** `formatProbability(probabilities.home)` — the home cell, decided alone. */
const LONE_HOME_CELL = /formatProbability\(\s*probabilities\.home\s*\)/;
/** Either sizing array measuring one side on its own, via the `printable` closure. */
const LONE_SIZING_CELL = /formatProbabilityOrDash\(\s*printable\([^)]*\)\?\.away\s*\)/;

/** THE PRODUCTION SCAN. Takes RAW Swift so no call site can choose a read. */
function loneCellShapes(swiftSrc: string): string[] {
  const code = swiftCode(swiftSrc);
  return [LONE_AWAY_CELL, LONE_HOME_CELL, LONE_SIZING_CELL]
    .map((re) => code.match(re)?.[0])
    .filter((m): m is string => Boolean(m));
}

/** How many times raw Swift source asks for a jointly-decided pair. */
function jointDecisions(swiftSrc: string): number {
  return (swiftCode(swiftSrc).match(/duelProbabilityStrings\(/g) ?? []).length;
}

// ---------------------------------------------------------------------------
// The suite is meaningless pointed at nothing. A path typo would otherwise read
// as a clean pass, so the paths are asserted as a TEST rather than used to skip.
// ---------------------------------------------------------------------------

describe("#7984 — the files this guard reads all exist", () => {
  it.each([EVENT_DETAIL, FORMATTING, CONTRACT_ARM])("%s", (path) => {
    expect(existsSync(path)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 0. THE GUARD'S OWN CAPABILITY.
//
// The production scan is a negative assertion over a tree that is now clean, so
// it passes whether or not it can see anything. Its subject here is the SCAN,
// fed a specimen — deliberately not "the tree still contains a case", which is a
// liveness assertion that dies the moment the population is correct.
// ---------------------------------------------------------------------------

describe("#7984 — the scan can see the defect it bans", () => {
  /** `probabilityBarAndNumbers` exactly as it read before this ship. */
  const DEFECTIVE = [
    "    ) -> some View {",
    "        Text(formatProbabilityOrDash(probabilities.away))",
    "            .font(.caption2.monospacedDigit())",
    "        Text(formatProbability(probabilities.home))",
    "    }",
  ].join("\n");

  /** A sizing array that measures each side on its own. */
  const DEFECTIVE_SIZING = [
    "            values: entries.flatMap {",
    "                [formatProbabilityOrDash(printable($0)?.away),",
    "                 formatProbability($0.homeProbability)]",
    "            },",
  ].join("\n");

  it("the specimens really do contain the defect before any strip", () => {
    // Without this the rest of the describe could pass on a typo'd specimen — a
    // fixture that misrepresents the defect makes every assertion below vacuous.
    expect(DEFECTIVE).toMatch(LONE_AWAY_CELL);
    expect(DEFECTIVE).toMatch(LONE_HOME_CELL);
    expect(DEFECTIVE_SIZING).toMatch(LONE_SIZING_CELL);
  });

  it("THE PRODUCTION SCAN sees them", () => {
    // 🔴 The one that matters: the exact function the ban below calls, not a
    // copy of its regexes.
    expect(loneCellShapes(DEFECTIVE)).toHaveLength(2);
    expect(loneCellShapes(DEFECTIVE_SIZING)).toHaveLength(1);
    expect(jointDecisions(DEFECTIVE)).toBe(0);
  });

  it("the scan still strips comments, so the fix may document itself", () => {
    // The original reason for any strip at all. If this regressed, the file
    // would red on its own explanatory comment and someone would revert the lot.
    const documented = [
      "// Was: Text(formatProbabilityOrDash(probabilities.away)) — see #7984.",
      "/* and formatProbability(probabilities.home) beside it. */",
      "let printed = duelProbabilityStrings(away: a, home: h)",
    ].join("\n");
    expect(loneCellShapes(documented)).toHaveLength(0);
    expect(jointDecisions(documented)).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 1. THE BAN, on the file that draws both lists.
// ---------------------------------------------------------------------------

describe("#7984 — EventDetailView decides each source row's pair once", () => {
  it("no cell in either list is formatted on its own", () => {
    expect(loneCellShapes(read(EVENT_DETAIL))).toEqual([]);
  });

  it("all three call sites ask for the joint decision", () => {
    // The draw site plus BOTH `EventSourceLabelColumn.columns(values:)` arrays.
    // A count rather than a boolean: `toContain` would stay green if the two
    // sizing arrays regressed and only the draw site survived, which is exactly
    // the #4208/#5271 half of this defect.
    expect(jointDecisions(read(EVENT_DETAIL))).toBe(3);
  });

  it("the shared helper exists where both lists can reach it", () => {
    expect(swiftCode(read(FORMATTING))).toContain("func duelProbabilityStrings(");
  });

  it("the helper defers to the contract arm rather than rounding again", () => {
    // #3892's class: a call site that re-implements the rule instead of calling
    // it. The pairing decision belongs to `renderedDuelPercents`, which is gated
    // on `isComplementPair` — that gate is why a served, non-complement
    // bookmaker pair is left exactly as it renders today.
    const code = swiftCode(read(FORMATTING));
    expect(code).toContain("renderedDuelPercents(away: away, home: home)");
    expect(code).not.toMatch(/duelProbabilityStrings[\s\S]{0,400}\* 100/);
  });
});

// ---------------------------------------------------------------------------
// 2. THE ARITHMETIC, re-run here so the guard is not purely textual.
//
// The web arm of the same contract is imported and swept over the grid the
// venues actually quote on. Native's `renderedDuelPercents` is the Swift arm of
// this identical rule (`contracts/rendered_percent.json`), so a sum that holds
// here is the sum the phone prints.
// ---------------------------------------------------------------------------

describe("#7984 — a complement pair on the half-percent grid sums to 100", () => {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { renderedDuelPercents } = require("@/lib/renderedPercent");

  /** Only rows that print two numerals have a sum a reader can object to. */
  const printsNumeral = (p: number) => p * 100 >= 1 && p * 100 <= 99;

  it("every quoted value, and the old rule really did disagree on some", () => {
    let checked = 0;
    let independentWouldHaveFailed = 0;

    for (let step = 1; step < 200; step += 1) {
      const home = step * 0.005;
      const away = 1 - home;
      if (!printsNumeral(home) || !printsNumeral(away)) continue;
      checked += 1;

      const [a, h] = renderedDuelPercents(away, home);
      expect(a + h).toBe(100);

      const independently =
        Math.round((away * 1000) / 10) + Math.round((home * 1000) / 10);
      if (independently !== 100) independentWouldHaveFailed += 1;
    }

    expect(checked).toBeGreaterThan(150);
    // If independent rounding never disagreed, this file is guarding nothing.
    expect(independentWouldHaveFailed).toBeGreaterThan(0);
  });

  it("the photographed specimen, end to end", () => {
    const home = 0.585;
    expect(renderedDuelPercents(1 - home, home)).toEqual([41, 59]);
  });
});
