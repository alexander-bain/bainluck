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
    // #3430 moved the glyph-taking into `glyphs(ofLabel:)` so the pair rule
    // could badge a label it had just widened. The property is unchanged and
    // still asserted: `abbreviation` starts from `short`, never from its own
    // split of the raw name.
    expect(canonical).toMatch(/static func abbreviation\(_ name: String\) -> String \{\s*glyphs\(ofLabel: short\(name\)\)/);
    expect(canonical).toMatch(/label\.split\(separator: " "\)/);
    expect(canonical).toMatch(/\.uppercased\(\)/);
  });

  it("the badge skips a LEADING designator, but never down to nothing", () => {
    // `short` returns the FULL name for a designator-ending club, so taking its
    // first three characters put the designator straight back on the badge when
    // it sits at the front — "FC Schalke 04" drew `FC `, "AD Ceuta FC" drew
    // `AD `. Measured: 11 badges worse than the rule #3374 replaced.
    expect(canonical).toMatch(/firstIndex\(where: \{ !isDesignator\(\$0\) \}\)/);
    // The over-correction guard: dropping leading designators unconditionally
    // turns "Athletic Club" into `CLU`. `firstIndex` returning nil must leave
    // the parts alone, so the skip is inside `if let`.
    expect(canonical).toMatch(/if let firstReal = parts\.firstIndex/);
  });

  it("the badge's three glyphs carry no space or punctuation", () => {
    // A badge has room for three characters and a space is not one of them.
    expect(canonical).toMatch(/filter \{ \$0\.isLetter \|\| \$0\.isNumber \}/);
  });

  it("the women's marker is seen in both spellings production uses", () => {
    // `teams` writes it as "Argentina W" and as "Harvard Crimson (W)". Trimming
    // only `.` and `,` saw the first and missed the second.
    expect(canonical).toMatch(/charactersIn: "\(\)\.,"/);
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

  /**
   * #3430 — the pair rule, and the scan that keeps it from being bypassed.
   *
   * Every assertion above judges ONE name in isolation, which is why the whole
   * suite was green over the settled Clemson–LSU page: "Tigers" is exactly what
   * a reader calls Clemson, and `short` returning it is correct. It is only
   * wrong because LSU are the Tigers too — a fact no single-name test can see.
   */
  describe("#3430 — the two competitors of one matchup", () => {
    it("the pair rule exists and grows the label rather than truncating it", () => {
      expect(canonical).toMatch(/static func shortPair\(/);
      expect(canonical).toMatch(/static func abbreviationPair\(/);
      // The mechanism: widen leftward until the two differ.
      expect(canonical).toMatch(/private static func grown\(away: String, home: String\)/);
      expect(canonical).toMatch(/private static func lastWords\(/);
    });

    it("a served abbreviation loses to the names when it collides with the other side", () => {
      // `teams.abbreviation` is wrong for hundreds of rows (#3353), so trusting
      // a served pair unconditionally re-prints "TIG" twice on the provider's
      // word. If this guard inverts, the fix is dead wherever team_data is set.
      expect(canonical).toMatch(/guard a == h else \{ return \(a, h\) \}/);
    });

    it("the badge is taken from the WIDENED label, not re-shortened", () => {
      // `abbreviation` runs `short` first, so badging the widened "White Sox"
      // through it collapses straight back onto SOX. The split-out helper is
      // what makes the widening reach the badge at all.
      expect(canonical).toMatch(/private static func glyphs\(ofLabel label: String\)/);
      expect(canonical).toMatch(/glyphs\(ofLabel: widened\.away\)/);
    });

    it("growth does not stop on a bare designator", () => {
      expect(canonical).toMatch(/private static func namesSomething\(/);
    });

    /** A call that shortens one SIDE of a matchup rather than a lone name. */
    const SIDE_CALL = /TeamShortName\.(short|abbreviation)\(\s*([^)]*)\)/g;

    it("no view shortens both sides of a matchup on its own — discovered, not listed", () => {
      const offenders: string[] = [];

      for (const path of swiftFiles(IOS_ROOT)) {
        if (path === CANONICAL) continue;
        const code = stripComments(readFileSync(path, "utf8"));
        // A file that asks for a pair has already made the decision.
        if (/TeamShortName\.(shortPair|abbreviationPair)\(/.test(code)) continue;

        const sides = new Set<string>();
        for (const [, , arg] of code.matchAll(SIDE_CALL)) {
          if (/away/i.test(arg)) sides.add("away");
          if (/home/i.test(arg)) sides.add("home");
        }
        if (sides.has("away") && sides.has("home")) {
          offenders.push(
            `${path.slice(IOS_ROOT.length + 1)} — shortens away AND home without TeamShortName.shortPair/abbreviationPair`
          );
        }
      }

      expect(offenders).toEqual([]);
    });

    it("the pair scan fires on the REAL pre-fix source", () => {
      // Copied verbatim from EventDetailView.swift at origin/master 38324fb2 —
      // the two lines that printed "Tigers 10 - Tigers 51". A scan is only
      // proven by the code it was built to catch, and this one would happily
      // pass over a synthetic that merely matches its own regex.
      const prefix = `
        let away = event.awayTeamData?.abbreviation ?? TeamShortName.short(event.awayTeam)
        let home = event.homeTeamData?.abbreviation ?? TeamShortName.short(event.homeTeam)
      `;
      const sides = new Set<string>();
      for (const [, , arg] of stripComments(prefix).matchAll(SIDE_CALL)) {
        if (/away/i.test(arg)) sides.add("away");
        if (/home/i.test(arg)) sides.add("home");
      }
      expect([...sides].sort()).toEqual(["away", "home"]);
    });

    it("the pair scan does NOT fire on a surface that shows one competitor", () => {
      // The inverse hazard: a scan that flags every file makes the suite a
      // nuisance and gets suppressed. A futures row names one entrant and has
      // no second side to collide with.
      const oneSided = `Text(TeamShortName.short(teamName))`;
      const sides = new Set<string>();
      for (const [, , arg] of stripComments(oneSided).matchAll(SIDE_CALL)) {
        if (/away/i.test(arg)) sides.add("away");
        if (/home/i.test(arg)) sides.add("home");
      }
      expect(sides.size).toBe(0);
    });

    /**
     * The pair rule run over the production pairs that motivated it.
     * Transcribed, like the rule above it, so an edit to one must touch the
     * other — and stated as LITERAL expectations, never re-derived.
     */
    it("the pair rule agrees with the Swift on the real colliding matchups", () => {
      const DESIGNATORS = new Set([
        "fc", "sc", "cf", "ac", "ad", "united", "city", "town", "county", "club",
        "athletic", "w", "jr", "sr", "b", "ii", "iii", "u20", "u21", "u23",
      ]);
      const isDesignator = (t: string) => {
        const s = t.replace(/^[().,]+|[().,]+$/g, "").toLowerCase();
        return DESIGNATORS.has(s) || /^\d{1,4}$/.test(s);
      };
      const words = (s: string) => s.split(" ").filter(Boolean);
      const short = (name: string) => {
        const p = words(name);
        if (p.length <= 1) return name;
        return isDesignator(p[p.length - 1]) ? p.join(" ") : p[p.length - 1];
      };
      const lastWords = (name: string, k: number) => {
        const w = words(name);
        return w.length === 0 ? name : w.slice(Math.max(0, w.length - Math.max(1, k))).join(" ");
      };
      const namesSomething = (name: string, k: number) => {
        const whole = words(name).length;
        const first = words(lastWords(name, k))[0];
        return first === undefined || !isDesignator(first) || k >= whole;
      };
      const shortPair = (away: string, home: string): [string, string] => {
        const a = short(away), h = short(home);
        if (a !== h) return [a, h];
        let k = Math.max(1, words(a).length, words(h).length);
        const limit = Math.max(words(away).length, words(home).length);
        while (k <= limit) {
          const ga = lastWords(away, k), gh = lastWords(home, k);
          if (ga !== gh && namesSomething(away, k) && namesSomething(home, k)) return [ga, gh];
          k += 1;
        }
        return [away, home];
      };

      // The photographed page, and the derby that reads worst.
      expect(shortPair("Clemson Tigers", "LSU Tigers")).toEqual(["Clemson Tigers", "LSU Tigers"]);
      expect(shortPair("Chicago White Sox", "Boston Red Sox")).toEqual(["White Sox", "Red Sox"]);
      expect(shortPair("Dinamo Moscow", "Spartak Moscow")).toEqual(["Dinamo Moscow", "Spartak Moscow"]);
      expect(shortPair("Cercle Brugge", "Club Brugge")).toEqual(["Cercle Brugge", "Club Brugge"]);
      // Growth that must not stop on the designator it passes through.
      expect(shortPair("AA Internacional Limeira SP", "Guarani FC SP"))
        .toEqual(["Internacional Limeira SP", "Guarani FC SP"]);
      // The other direction: a pair that already reads correctly is untouched.
      expect(shortPair("Baltimore Orioles", "Boston Red Sox")).toEqual(["Orioles", "Sox"]);
      expect(shortPair("Charlotte FC", "Houston Dynamo")).toEqual(["Charlotte FC", "Dynamo"]);
      // Identical names: terminate, do not invent a difference.
      expect(shortPair("Detroit Tigers", "Detroit Tigers")).toEqual(["Detroit Tigers", "Detroit Tigers"]);
    });
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
      // `(Pair)?` because #3430 moved the both-competitor surfaces onto the
      // pair entry points, which are the same shared rule seeing both names.
      expect(readFileSync(join(IOS_ROOT, file), "utf8")).toMatch(/TeamShortName\.(short|abbreviation)(Pair)?\b/);
    }
  });

  /**
   * Transcribed from the Swift so an edit to one must touch the other. This is
   * the rule itself, run over the production names that motivated it.
   */
  it("the rule agrees with the Swift on real production team names", () => {
    // A subset of the Swift set — every token an assertion below depends on.
    // A case whose tokens are NOT here would take a different path than the
    // Swift and could agree by luck, so keep the two in step when adding one.
    const DESIGNATORS = new Set([
      "fc", "sc", "cf", "ac", "ad", "united", "city", "town", "county", "club",
      "athletic", "w", "jr", "sr", "b", "ii", "iii", "u20", "u21", "u23",
    ]);
    const isDesignator = (t: string) => {
      const s = t.replace(/^[().,]+|[().,]+$/g, "").toLowerCase();
      return DESIGNATORS.has(s) || (/^\d{1,4}$/.test(s));
    };
    const short = (name: string) => {
      const parts = name.split(" ").filter(Boolean);
      if (parts.length <= 1) return name;
      return isDesignator(parts[parts.length - 1]) ? parts.join(" ") : parts[parts.length - 1];
    };
    const abbreviation = (name: string) => {
      let parts = short(name).split(" ").filter(Boolean);
      const firstReal = parts.findIndex((p) => !isDesignator(p));
      if (firstReal !== -1) parts = parts.slice(firstReal);
      return (parts.join(" ").match(/[\p{L}\p{N}]/gu) ?? []).slice(0, 3).join("").toUpperCase();
    };

    expect(short("Charlotte FC")).toBe("Charlotte FC");
    expect(short("Houston Dynamo")).toBe("Dynamo");
    expect(short("San Diego FC")).toBe("San Diego FC");
    expect(short("Baltimore Orioles")).toBe("Orioles");
    expect(short("Argentina W")).toBe("Argentina W");
    expect(short("1. FC Heidenheim 1846")).toBe("1. FC Heidenheim 1846");
    expect(short("AIK")).toBe("AIK");
    // The parenthesised spelling of the same women's marker.
    expect(short("Harvard Crimson (W)")).toBe("Harvard Crimson (W)");

    // The badge: never the designator, at either end, and always three glyphs.
    expect(abbreviation("Charlotte FC")).toBe("CHA");
    expect(abbreviation("FC Schalke 04")).toBe("SCH");
    expect(abbreviation("AD Ceuta FC")).toBe("CEU");
    expect(abbreviation("1. FC Heidenheim 1846")).toBe("HEI");
    expect(abbreviation("St. Louis City SC")).toBe("STL");
    expect(abbreviation("D.C. United")).toBe("DCU");
    expect(abbreviation("Baltimore Orioles")).toBe("ORI");
    // Every token is a designator — skipping them all would read `CLU`.
    expect(abbreviation("Athletic Club")).toBe("ATH");
  });
});
