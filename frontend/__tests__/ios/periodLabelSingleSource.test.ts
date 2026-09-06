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

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Utilities/PeriodLabel.swift");
const CONSUMERS = [
  join(IOS_ROOT, "Components/OddsChartView.swift"),
  join(IOS_ROOT, "Components/ScoreDifferentialChartView.swift"),
];

/**
 * #3273 — the list above is why this ratchet failed.
 *
 * It named its consumers, so it only ever watched the two files that were
 * already broken in #1832. Two MORE copies grew where it was not looking:
 * `Views/EventDetailView.swift` (Game Segments) read ESPN's clock PREFIX as the
 * period number and headed a four-quarter football game
 * `Q14 · Q8 · Q5 · Q1 … Q4`; `Components/GamePlayCardView.swift` returned the
 * raw string and printed the clock twice. An allowlist cannot catch the file
 * nobody thought to add — so the check below DISCOVERS instead.
 *
 * Comments are stripped before scanning: the fixed files legitimately discuss
 * quarters and overtime at length in their doc comments, and a substring match
 * over raw source would call that a reimplementation.
 */
function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/**
 * Tells that a file is BUILDING a period label rather than asking for one:
 * interpolating a period prefix, or matching a period noun in code.
 */
const REIMPLEMENTATION_TELLS: Array<[string, RegExp]> = [
  ["interpolates a quarter label", /"Q\\\(/],
  ["interpolates a period label", /"P\\\(/],
  ["interpolates an overtime label", /"OT\\\(/],
  ["interpolates a half label", /\)H"/],
  ["matches the word 'quarter'", /quarter/i],
  ["matches the word 'halftime'", /halftime/i],
  ["matches the word 'overtime'", /overtime/i],
  ["matches baseball half-innings", /top\|bottom/],
];

/**
 * Files allowed to mention this vocabulary in code for a reason that is not
 * period labelling. Each needs a stated reason, so adding one is a decision.
 */
const NOT_PERIOD_PARSERS = new Map([
  [
    join(IOS_ROOT, "Components/SpecialEventMarketsView.swift"),
    "classifies MARKET NAMES ('halftime result', 'overtime') into prop groups — never labels a period",
  ],
]);

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

  it("no OTHER Swift file reimplements period labelling — discovered, not listed", () => {
    const offenders: string[] = [];

    for (const path of swiftFiles(IOS_ROOT)) {
      if (path === CANONICAL) continue;
      if (NOT_PERIOD_PARSERS.has(path)) continue;

      const code = stripComments(readFileSync(path, "utf8"));
      const hits = REIMPLEMENTATION_TELLS.filter(([, re]) => re.test(code)).map(([why]) => why);
      if (hits.length > 0) {
        offenders.push(`${path.slice(IOS_ROOT.length + 1)} — ${hits.join("; ")}`);
      }
    }

    expect(offenders).toEqual([]);
  });

  it("the discovery check can actually fail", () => {
    // A scan that cannot fail is the failure mode this whole file exists to
    // stop. Feed it the exact defect from #3273 and require it to fire.
    const drifted = stripComments(`
      private static func formatPeriodLabel(_ raw: String) -> String {
        if raw.lowercased().contains("quarter"), let n = firstNumber(in: raw) { return "Q\\(n)" }
        return raw
      }
    `);
    const hits = REIMPLEMENTATION_TELLS.filter(([, re]) => re.test(drifted));
    expect(hits.length).toBeGreaterThan(0);
  });

  it("the two files fixed by #3273 delegate to the shared parser", () => {
    // Named explicitly so a revert is loud rather than merely un-discovered.
    for (const [file, call] of [
      ["Views/EventDetailView.swift", "PeriodLabel.columnLabel("],
      ["Components/GamePlayCardView.swift", "PeriodLabel.normalize("],
    ]) {
      expect(readFileSync(join(IOS_ROOT, file), "utf8")).toContain(call);
    }
  });

  it("the scoreboard column vocabulary is defined once, beside normalize", () => {
    // #3273: the column label differs from the chart chip in exactly two ways
    // (innings as digits, non-periods dropped). It lives on PeriodLabel so it
    // cannot drift back into a view.
    expect(canonical).toMatch(/static func columnLabel\(/);
    expect(canonical).toMatch(/normalize\(raw\)/);
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
