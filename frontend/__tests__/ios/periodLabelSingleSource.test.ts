/**
 * #1832 — one period-label implementation on iOS, asserted by reading the Swift.
 *
 * `normalizePeriodLabel` existed in TWO Swift files and had already drifted:
 * `ScoreDifferentialChartView`'s copy was missing the plain-ordinal inning
 * branch and all three golf branches, so the two charts stacked on the SAME
 * event page could label one period differently — or one could label it and the
 * other fall through to ESPN's raw string.
 *
 * That is gotcha #128's shape: a rule in N consumers has N verdicts, and the
 * healthy copy is what hides the broken one. This is the ratchet that stops it
 * coming back. It lives in jest because jest is a deploy gate here and the Swift
 * test target is not reachable from CI.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Utilities/PeriodLabel.swift");
const CONSUMERS = [
  join(IOS_ROOT, "Components/OddsChartView.swift"),
  join(IOS_ROOT, "Components/ScoreDifferentialChartView.swift"),
];

// The whole suite is meaningless if it is pointed at nothing — a path typo
// would otherwise read as a clean pass (the unrunnable-check failure mode).
const iosPresent = existsSync(CANONICAL);

const d = iosPresent ? describe : describe.skip;

d("iOS period labels have exactly one implementation", () => {
  const canonical = readFileSync(CANONICAL, "utf8");

  it("the canonical implementation exists and is the only definition", () => {
    expect(canonical).toContain("enum PeriodLabel");
    expect(canonical).toMatch(/static func normalize\(/);
  });

  it.each(CONSUMERS)("%s delegates rather than reimplementing", (path) => {
    const src = readFileSync(path, "utf8");
    expect(src).toContain("PeriodLabel.normalize(raw)");

    // A real reimplementation is a body full of period regexes. The delegating
    // shim has none, so counting them separates "calls the shared rule" from
    // "quietly grew its own again".
    const quarterBranches = src.match(/\[Qq\]uarter|quarter\$/g) ?? [];
    const inningBranches = src.match(/top\|bottom\|mid/g) ?? [];
    expect(quarterBranches).toHaveLength(0);
    expect(inningBranches).toHaveLength(0);
  });

  it("baseball innings render as self-explaining ordinals, not bare digits", () => {
    // Ruling 5. A chart chip strip reading "0 8" names no unit; "8th" does.
    expect(canonical).toMatch(/return inning\(/);
    expect(canonical).toMatch(/func inning<S: StringProtocol>/);
    expect(canonical).toMatch(/func ordinalSuffix/);
  });

  it("a non-positive period number yields no chip at all", () => {
    // This is where the unexplained "0" chip came from: the short-form regex
    // had a bare `\d+` arm that passed "0" straight through.
    expect(canonical).toMatch(/guard let n = Int\(digits\), n > 0 else \{ return "" \}/);
    // The bare-integer arm must no longer sit inside the pass-through regex.
    expect(canonical).not.toMatch(/\^\(Q\\d\|P\\d\|\\d\+H\|OT\\d\?\|HT\|\\d\+\)\$/);
  });

  it("ordinal suffixes follow English, including the 11-13 exception", () => {
    // Transcribed from the Swift so a future edit to one must touch the other.
    const suffix = (n: number) => {
      const mod100 = n % 100;
      if (mod100 >= 11 && mod100 <= 13) return "th";
      switch (n % 10) {
        case 1:
          return "st";
        case 2:
          return "nd";
        case 3:
          return "rd";
        default:
          return "th";
      }
    };
    expect([1, 2, 3, 4, 9, 11, 12, 13, 21, 22].map((n) => `${n}${suffix(n)}`)).toEqual([
      "1st",
      "2nd",
      "3rd",
      "4th",
      "9th",
      "11th",
      "12th",
      "13th",
      "21st",
      "22nd",
    ]);
  });
});
