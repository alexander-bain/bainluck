/**
 * #3374 — one team-short-name implementation on iOS, asserted by reading the Swift.
 *
 * The live Discover card labelled Charlotte FC **"FC"** (photographed
 * 2026-09-05, `artifacts-native-031/discover.png`). The rule that produced it,
 * `name.split(separator: " ").last`, was hand-rolled in 39 places across 15 files on the iPhone
 * target — so every surface that shows a team in less room than its full name
 * carried the same defect, and fixing the card alone would have fixed one of 39.
 *
 * Measured over all 5,559 distinct `teams.name` rows: 1,901 (34.2%) collapsed
 * onto a label shared with another team, `FC` alone absorbing 102 of them.
 *
 * This is #3273's ratchet built the way #3273 taught: it DISCOVERS
 * re-implementations instead of naming consumers, because an allowlist cannot
 * catch the file nobody thought to add. Comments are stripped first — the fixed
 * files legitimately quote the old expression in their doc comments, and a raw
 * substring scan would call that a reimplementation.
 *
 * It lives in jest because jest is a deploy gate here and the Swift test target
 * is not reachable from CI.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Utilities/TeamShortName.swift");

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

/** Tells that a line is BUILDING a short name rather than asking for one. */
const REIMPLEMENTATION_TELLS: Array<[string, RegExp]> = [
  ["takes the last space-separated word", /\.split\(separator: " "\)\s*\.last/],
  ["takes the last word via components()", /\.components\(separatedBy: " "\)\s*\.last/],
];

/**
 * Lines allowed to take a last word for a reason that is not a team label.
 * Keyed by file, matched as a substring, each with a stated reason — so adding
 * one is a decision rather than a silent widening.
 */
const NOT_TEAM_LABELS = new Map<string, Array<[string, string]>>([
  [
    join(IOS_ROOT, "Components/RelatedFuturesView.swift"),
    [
      [
        "let lastName = playerName.split",
        "matches a PLAYER surname across box-score spellings ('J. Tatum' vs 'Jayson Tatum') — never rendered as a label",
      ],
      [
        "let boxLastName = name.split",
        "the other half of that same player-surname comparison",
      ],
    ],
  ],
]);

// A path typo would otherwise read as a clean pass — the unrunnable-check
// failure mode this whole file exists to stop.
const iosPresent = existsSync(CANONICAL);
const d = iosPresent ? describe : describe.skip;

d("iOS team short names have exactly one implementation", () => {
  const canonical = readFileSync(CANONICAL, "utf8");

  it("the canonical implementation exists and is the only definition", () => {
    expect(canonical).toContain("enum TeamShortName");
    expect(canonical).toMatch(/static func short\(/);
    expect(canonical).toMatch(/static func abbreviation\(/);
  });

  it("a designator is never the whole label — the name it qualifies is shown", () => {
    // The branch that fixes the photographed defect. If this inverts, "FC" is
    // back and every other test here still passes on the mascot cases.
    expect(canonical).toMatch(/if isDesignator\(last\) \{ return parts\.joined\(separator: " "\) \}/);
  });

  it("the designator set covers the labels measured to collide in production", () => {
    // Each of these was the ENTIRE label for many teams before #3374.
    for (const token of ["fc", "sc", "cf", "united", "city", "town", "w", "jr", "b", "ii"]) {
      expect(canonical).toMatch(new RegExp(`"${token}"`));
    }
  });

  it("a founding year counts as a designator", () => {
    // "1. FC Heidenheim 1846" rendered as `1846`.
    expect(canonical).toMatch(/allSatisfy\(\\?\.isNumber\)/);
  });

  it("the crest placeholder derives from the shared rule, not its own split", () => {
    expect(canonical).toMatch(/String\(short\(name\)\.prefix\(3\)\)\.uppercased\(\)/);
  });

  it("no OTHER Swift file builds a short name — discovered, not listed", () => {
    const offenders: string[] = [];

    for (const path of swiftFiles(IOS_ROOT)) {
      if (path === CANONICAL) continue;
      const allowed = NOT_TEAM_LABELS.get(path) ?? [];

      const code = stripComments(readFileSync(path, "utf8"));
      for (const line of code.split("\n")) {
        if (allowed.some(([needle]) => line.includes(needle))) continue;
        const hits = REIMPLEMENTATION_TELLS.filter(([, re]) => re.test(line)).map(([why]) => why);
        if (hits.length > 0) {
          offenders.push(`${path.slice(IOS_ROOT.length + 1)} — ${hits.join("; ")} — ${line.trim()}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it("the discovery check fires on the REAL pre-fix source, both forms", () => {
    // Not a synthetic that merely proves the regex can match: these two lines
    // are copied verbatim from DiscoverEventCard.swift at origin/master
    // b09d63f4, and are exactly what drew `FC` on the card. A guard is only
    // proven by the code it was built to catch.
    const prefix = [
      `Text(String(name.split(separator: " ").last ?? "").prefix(3).uppercased())`,
      `Text(name.split(separator: " ").last.map(String.init) ?? name)`,
    ];
    for (const line of prefix) {
      const hits = REIMPLEMENTATION_TELLS.filter(([, re]) => re.test(stripComments(line)));
      expect(hits.length).toBeGreaterThan(0);
    }
  });

  it("stripping comments does not blind the scan to real code", () => {
    // The inverse hazard: strip too eagerly and every offender vanishes.
    const withTrailingComment = `let x = team.split(separator: " ").last // shorten`;
    expect(
      REIMPLEMENTATION_TELLS.some(([, re]) => re.test(stripComments(withTrailingComment)))
    ).toBe(true);
  });

  it("the surfaces fixed by #3374 delegate to the shared rule", () => {
    // Named explicitly so a revert is loud rather than merely un-discovered.
    for (const file of [
      "Components/DiscoverEventCard.swift",
      "Views/EventDetailView.swift",
      "Components/GamePlayCardView.swift",
      "Utilities/ShareCardRenderer.swift",
      "Components/OddsChartView.swift",
      // Found by this scan, not by the author: both took a golfer's last word,
      // so a leaderboard headed "Davis Love III" read `III`.
      "Components/DiscoverTournamentCard.swift",
      "Components/TournamentCompactRow.swift",
    ]) {
      // `\b` not `\(` — OddsChartView passes the function itself to `.map`.
      expect(readFileSync(join(IOS_ROOT, file), "utf8")).toMatch(/TeamShortName\.(short|abbreviation)\b/);
    }
  });

  /**
   * Transcribed from the Swift so an edit to one must touch the other. This is
   * the rule itself, run over the production names that motivated it.
   */
  it("the rule agrees with the Swift on real production team names", () => {
    const DESIGNATORS = new Set([
      "fc", "sc", "cf", "ac", "united", "city", "town", "county", "club",
      "w", "jr", "sr", "b", "ii", "iii", "u20", "u21", "u23",
    ]);
    const isDesignator = (t: string) => {
      const s = t.replace(/^[.,]+|[.,]+$/g, "").toLowerCase();
      return DESIGNATORS.has(s) || (/^\d{1,4}$/.test(s));
    };
    const short = (name: string) => {
      const parts = name.split(" ").filter(Boolean);
      if (parts.length <= 1) return name;
      return isDesignator(parts[parts.length - 1]) ? parts.join(" ") : parts[parts.length - 1];
    };

    expect(short("Charlotte FC")).toBe("Charlotte FC");
    expect(short("Houston Dynamo")).toBe("Dynamo");
    expect(short("San Diego FC")).toBe("San Diego FC");
    expect(short("Baltimore Orioles")).toBe("Orioles");
    expect(short("Argentina W")).toBe("Argentina W");
    expect(short("1. FC Heidenheim 1846")).toBe("1. FC Heidenheim 1846");
    expect(short("AIK")).toBe("AIK");
  });
});
