/**
 * #4135 — the app names a source or draws none; it never title-cases a raw key.
 *
 * `bainluck://futures/60393473` ("Amgen Irish Open - Winner", `source: "datagolf"`,
 * `bookmakers: ["datagolf_model"]`) drew three lines that argued with each other:
 *
 *     Source  ● Datagolf
 *     Probabilities from 1 sportsbook
 *     [ Datagolf Model ]
 *
 * DataGolf is a statistical model. The card called it a sportsbook two lines above
 * a chip that said "Model", and spelled the brand from `"datagolf".capitalized`.
 *
 * ═══ WHY A SOURCE SCAN AND NOT (ONLY) AN XCTEST ═══
 *
 * CI COMPILES NO SWIFT. `SourceLabelsTests` proves the resolver and runs on a
 * laptop; nothing in it stands between a regression and production, and none of it
 * can see whether a VIEW reaches the resolver at all. That gap is not theoretical
 * here — it is the whole bug class. Every one of the eight sites below already had
 * a correct-looking `switch` with the three big sources spelled right, and each one
 * ended in a `default:` arm that handed the screen to whatever key came next. A
 * ninth copy would look just as correct and would be just as wrong.
 *
 * So this file asserts the WIRING: the raw-key fallback is gone as a discovered
 * property of the tree, and each site reaches the one resolver.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * That the DataGolf card reads well. It cannot read a glyph. The "Source ● DataGolf
 * / Probabilities from the DataGolf model" frame is carried by the screenshot on
 * #4135's PR, and is re-owed by whoever changes that card.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const RESOLVER = join(IOS_ROOT, "Utilities/SourceLabels.swift");

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
 * Every string literal in a Swift file, with `\(…)` removed innermost-first so an
 * IDENTIFIER inside a string stops reading as prose.
 *
 * The stripping is not tidiness. `SourceLabels.sportsbookChips(...)` is a method
 * NAME containing the noun, and the first version of the mutant check below banned
 * the bare substring and failed on it — reporting an identifier to a reader, which
 * is how a scan earns a suppression. What a reader sees is the literal.
 */
function stringLiterals(source: string): string[] {
  let stripped = stripComments(source);
  for (;;) {
    const next = stripped.replace(/\\\([^()]*\)/g, "");
    if (next === stripped) break;
    stripped = next;
  }
  return [...stripped.matchAll(/"((?:[^"\\\n]|\\.)*)"/g)].map((m) => m[1]);
}

/**
 * A source key being title-cased onto the screen. Both spellings the tree used —
 * `source.capitalized` and `source?.capitalized`.
 */
const RAW_KEY_FALLBACK = /\bsource\??\.capitalized\b/;

/**
 * The one place a `source` key is still title-cased, and why it is not this ship's.
 *
 * `OddsChartView.fallbackDisplayName` resolves a DIFFERENT vocabulary — the
 * `win_probability_sources` keys (`espn`, `stat_model`, `bainluck_model`, `mlb`),
 * mirroring web's `FALLBACK_SOURCE_CONFIG` so the two clients label one chart the
 * same way. None of the four market sources reaches it, so `SourceLabels` cannot
 * name its keys and pointing it at the resolver would silently drop every chart
 * series. Notice 33's addendum also says in terms: do not redesign the chart.
 *
 * Pinned by FILE and by the CODE, never by a line number — a comment added above
 * it would red the guard for no reason.
 */
const KNOWN_SURVIVOR = {
  file: "Components/OddsChartView.swift",
  code: "default: return source.capitalized",
};

// A path typo would otherwise read as a clean pass — the unrunnable-check failure
// mode a source scan is most prone to.
const iosPresent = existsSync(RESOLVER) && existsSync(IOS_ROOT);
const d = iosPresent ? describe : describe.skip;

d("#4135 — the app names a source or draws none", () => {
  /**
   * Slice a declaration's body, and PROVE the slice — a scoping regex that
   * silently matches nothing turns every assertion below it into a vacuous
   * pass. (#4134 shipped a guard that tested a helper nothing called; this is
   * the same failure wearing different clothes.)
   */
  function slice(relPath: string, declaration: string): string {
    const source = stripComments(readFileSync(join(IOS_ROOT, relPath), "utf8"));
    const start = source.indexOf(declaration);
    expect([relPath, declaration, start > -1]).toEqual([relPath, declaration, true]);
    const body = source.slice(start, start + 900);
    expect(body.length).toBeGreaterThan(declaration.length);
    return body;
  }

  describe("the raw-key fallback is gone, as a discovered property", () => {
    it("no view title-cases a market source onto the screen", () => {
      const offenders = swiftFiles(IOS_ROOT)
        .flatMap((path) => {
          const rel = path.slice(IOS_ROOT.length + 1);
          return stripComments(readFileSync(path, "utf8"))
            .split("\n")
            .filter((line) => RAW_KEY_FALLBACK.test(line))
            .map((line) => `${rel} — ${line.trim()}`);
        })
        .sort();

      // An EXACT set, not "at most one". A tenth copy is red, and so is removing
      // the survivor without saying so here — either way the list is a decision
      // somebody made on purpose, with the reason written down beside it.
      expect(offenders).toEqual([`${KNOWN_SURVIVOR.file} — ${KNOWN_SURVIVOR.code}`]);
    });

    it("the scan is looking at real files and would have fired before the fix", () => {
      // Guards that scan a tree fail vacuously when the walk breaks or the path
      // rots, and a green vacuous scan is worse than no scan. So: the walk found
      // the app, and the pattern kills the code this ship deleted — copied
      // verbatim from origin/master d8a63c57, not written to match.
      const files = swiftFiles(IOS_ROOT);
      expect(files.length).toBeGreaterThan(100);
      expect(files.some((f) => f.endsWith("Views/FuturesDetailView.swift"))).toBe(true);

      const prefix = [
        `        default: return source.capitalized`,
        `        default: return (DS.textMuted, source.capitalized, DS.trackBg)`,
        `    default: return source?.capitalized ?? ""`,
        `                    Text(source.capitalized)`,
        `                Text(sourceLabels[market.source] ?? market.source.capitalized)`,
      ];
      for (const line of prefix) {
        expect([line, RAW_KEY_FALLBACK.test(line)]).toEqual([line, true]);
      }
    });
  });

  describe("every surface that draws a source reaches the one resolver", () => {
    // Every site the tree had, discovered by grepping for the old switch. Each
    // must now ASK the resolver rather than carry its own copy of the answer.
    const sites: Array<[string, string]> = [
      ["Views/FuturesDetailView.swift", "private func sourceLabel("],
      ["Views/SearchView.swift", "private func searchSourceBadge("],
      ["Components/RelatedFuturesView.swift", "private func sourceLabel("],
      ["Components/FuturesBrowseComponents.swift", "private var label:"],
      ["Components/DesignSystem.swift", "private var config:"],
    ];

    it.each(sites)("%s %s asks SourceLabels", (relPath, declaration) => {
      expect(slice(relPath, declaration)).toContain("SourceLabels.label(for:");
    });

    it.each([
      ["Views/LeagueGridView.swift"],
      ["Views/MyStuffView.swift"],
      ["Components/FuturesCardView.swift"],
    ])("%s draws its source badge through the resolver", (relPath) => {
      const source = stripComments(readFileSync(join(IOS_ROOT, relPath), "utf8"));
      expect(source).toContain("SourceLabels.label(for:");
    });

    it("the dead label dictionary is gone and the live colour map is not", () => {
      // `MyStuffView`'s `sourceLabels` had zero readers; its `sourceColors` has
      // two. Deleting the wrong one is a silent visual regression.
      const myStuff = readFileSync(join(IOS_ROOT, "Views/MyStuffView.swift"), "utf8");
      expect(myStuff).not.toContain("private let sourceLabels");
      expect(myStuff).toContain("private let sourceColors");
    });
  });

  describe("#4284 — the event page's book table draws brands, not keys", () => {
    /**
     * The same defect as #4135, on the fifth surface: `bookmakerContent` drew
     * `bm.bookmaker ?? "Unknown"`, so every event page in the app printed
     * `betonlineag`, `lowvig` and `betus` while `SourceLabels` two files away
     * already knew them as BetOnline, LowVig and BetUS.
     *
     * A raw CONTRIBUTOR key does not match `RAW_KEY_FALLBACK` above — that
     * pattern is about `source.capitalized`, and this site never title-cased
     * anything, it just printed the key. So the class needs its own pattern, or
     * the scan that exists to catch "a key reached the screen" reads green while
     * one does.
     */
    const RAW_BOOKMAKER_FALLBACK = /\.bookmaker\s*\?\?\s*"/;

    it("no view falls back to a raw bookmaker key", () => {
      const offenders = swiftFiles(IOS_ROOT)
        .flatMap((path) => {
          const rel = path.slice(IOS_ROOT.length + 1);
          return stripComments(readFileSync(path, "utf8"))
            .split("\n")
            .filter((line) => RAW_BOOKMAKER_FALLBACK.test(line))
            .map((line) => `${rel} — ${line.trim()}`);
        })
        .sort();

      expect(offenders).toEqual([]);
    });

    it("that scan would have fired before the fix", () => {
      // Both pre-fix lines, copied verbatim from origin/master 8d0abc64 — the
      // row and the width model each carried their own copy.
      for (const line of [
        `                    label: bm.bookmaker ?? "Unknown",`,
        `            labels: bookmakers.map { $0.bookmaker ?? "Unknown" },`,
      ]) {
        expect([line, RAW_BOOKMAKER_FALLBACK.test(line)]).toEqual([line, true]);
      }
      // …and it is not firing on a comment that merely quotes them: this file's
      // own Swift doc comments name the deleted code, which is exactly how a
      // `not.toContain` scan reds on the explanation of its own fix.
      const detail = readFileSync(join(IOS_ROOT, "Views/EventDetailView.swift"), "utf8");
      expect(RAW_BOOKMAKER_FALLBACK.test(detail)).toBe(true);
      expect(RAW_BOOKMAKER_FALLBACK.test(stripComments(detail))).toBe(false);
    });

    it("the rows are built by asking the resolver", () => {
      expect(slice("Views/EventDetailView.swift", "static func namedBookmakerRows(")).toContain(
        "SourceLabels.sportsbookName(for:"
      );
    });

    it("the width model measures the brand the row draws, not the key", () => {
      // #4208/#4233's invariant: the column is sized on the strings the list
      // prints. Measuring keys is wrong in BOTH directions — `betonlineag` is
      // wider than "BetOnline", `betmgm` narrower than "BetMGM" — and no
      // screenshot shows a column that is merely the wrong width.
      const body = slice("Views/EventDetailView.swift", "private func bookmakerContent(");
      expect(body).toContain("rows.map(\\.label)");
      expect(body).not.toContain("$0.bookmaker");

      // And the row DRAWS the brand. Measuring `\.label` while drawing `\.id`
      // would size the column correctly and still print the key — a mutant no
      // Swift test can see, because which field the view passes is view code.
      expect(body).toContain("label: row.label");
      expect(body).not.toContain("label: row.id");
    });

    it("the disclosure asks for named rows before promising a table", () => {
      // An unnameable key draws no row, so `bookmakerOdds` being non-empty no
      // longer implies a table — asking the payload here opens the disclosure
      // onto an "Individual sportsbooks" heading with nothing under it.
      expect(slice("Views/EventDetailView.swift", "private func sourcesToggle(")).toContain(
        "namedBookmakerRows("
      );
    });
  });

  describe("the noun follows what the sources ARE", () => {
    const detail = () =>
      stripComments(readFileSync(join(IOS_ROOT, "Views/FuturesDetailView.swift"), "utf8"));

    it("THE MUTANT: the card cannot hardcode the sportsbook noun again", () => {
      // The entire #4135 defect, in one interpolated string. It counted whatever
      // `market.bookmakers` held and called every element a sportsbook, which for
      // the DataGolf market meant calling a statistical model a bookmaker's line.
      // No string this view DRAWS may carry the noun; only the resolver decides it.
      const drawn = stringLiterals(detail());
      expect(drawn.filter((l) => /sportsbook|Probabilities from/i.test(l))).toEqual([]);
    });

    it("that mutant check is not vacuous", () => {
      // It would pass just as green against a file with no literals at all, so:
      // the extractor found this view's real prose, and the pre-fix line — copied
      // verbatim from origin/master d8a63c57 — is caught.
      expect(stringLiterals(detail()).length).toBeGreaterThan(20);
      const prefix = `Text("Probabilities from \\(bookmakers.count) sportsbook\\(bookmakers.count != 1 ? "s" : "")")`;
      expect(
        stringLiterals(prefix).some((l) => /sportsbook|Probabilities from/i.test(l))
      ).toBe(true);
    });

    it("it asks the resolver for the sentence and for the chips", () => {
      expect(detail()).toContain("SourceLabels.attribution(for:");
      expect(detail()).toContain("SourceLabels.sportsbookChips(for:");
    });

    it("the resolver only ever calls a sportsbook a sportsbook", () => {
      // The noun is now reachable from exactly one place, so this is the whole
      // exposure. `isSportsbook` gates it, and the model map is what the DataGolf
      // key resolves through instead.
      const resolver = readFileSync(RESOLVER, "utf8");
      expect(resolver).toContain('"datagolf_model": "the DataGolf model"');
      expect(resolver).toContain('"datagolf": "DataGolf"');
      expect(stripComments(resolver)).toMatch(/keys\.filter\(isSportsbook\)\.count/);
    });
  });

  describe("#4351 — the ban covers every spelling, not the one the tree happened to use", () => {
    /**
     * ═══ THIS SUITE WAS GREEN WITH `ODDS_API` ON THE FIRST DISCOVER CARD ═══
     *
     * `RAW_KEY_FALLBACK` above bans `source.capitalized` and nothing else, so NINE
     * sites across seven files — spelling the same defect `.uppercased()`,
     * `?? "literal"`, or just printing the key — were never candidates. The scan
     * asserted the tree was clean, and the app's default screen read `ODDS_API`, a
     * database value with an underscore in it, on the MLB World Series card.
     * Measured on `GET /api/feed?limit=60`, 2026-09-09: 48 of 60 cards drew one of
     * these marks, two of them `ODDS_API`.
     *
     * The wiring half missed them for a second, independent reason: its `sites`
     * list was DISCOVERED by grepping for the old `switch source`, so a surface
     * that never had a switch could never appear in it. An allowlist built from
     * yesterday's defect does not contain tomorrow's surface.
     *
     * This is #4337's shape with a different blind spot — there a strip that ate
     * string interpolation, here an enumerated spelling. The lesson both times:
     * a negative scan is only as wide as the ONE pattern somebody thought of, so
     * it is pinned here beside a POSITIVE assertion that each site reaches the
     * resolver, which does not depend on guessing the next spelling.
     */

    /** A source key shouted onto the screen: `sources.map { $0.uppercased() }`. */
    const RAW_KEY_UPPERCASED = /\bsources?\b[^\n]*\.uppercased\(\)/;

    /** A source key with a fabricated stand-in: `market.source ?? "kalshi"`. */
    const INVENTED_SOURCE = /\bsource\s*\?\?\s*"/;

    /**
     * ═══ THE ALIAS SCAN, AND WHY IT IS THE ONLY ONE THAT MATTERS ═══
     *
     * The first version of this ship shipped `RAW_KEY_UPPERCASED` above and pinned
     * the four sites it knew. Then the post-fix LOOK photographed a Discover card
     * still reading `KALSHI` — `DistributionCardView`, and two more like it, each
     * spelling the defect
     *
     *     if let src = data.source { Text(src.uppercased()) }
     *
     * The drawn line says `src`. It contains no `source`, no `capitalized`, no key,
     * nothing any of the three line patterns in this file can match — and the
     * binding that gives it meaning is on the line ABOVE. Every negative scan here
     * was blind to the commonest spelling of the very defect it exists to ban, and
     * a screenshot is what found it, not the suite.
     *
     * So the scan resolves the alias instead of guessing the next spelling: bind
     * every local that comes from a `source`/`sources` expression, then ban
     * re-casing or drawing THAT NAME. A binding that already went through
     * `SourceLabels` is not an alias for a key — it is a name — so it is skipped,
     * which is also why the fixed sites read `Text(src)` and stay green.
     */
    function aliasOffenders(): string[] {
      return swiftFiles(IOS_ROOT)
        .flatMap((path) => {
          const rel = path.slice(IOS_ROOT.length + 1);
          const body = stripComments(readFileSync(path, "utf8"));

          // The binding must be the source FIELD ITSELF, not any expression that
          // mentions one. `let label = sourceLabel(source)` is a name already, and
          // binding it would make every later `Text(label)` in that file an
          // offender — aliases here are file-scoped, so a loose left-hand side
          // poisons the whole file. Verified against RelatedFuturesView, which
          // holds both spellings.
          const aliases = new Set<string>();
          for (const m of body.matchAll(/\blet\s+(\w+)\s*=\s*([^\n{,]+)/g)) {
            if (!/^(?:[A-Za-z_][\w.]*\.)?sources?(?:\.first)?$/.test(m[2].trim())) continue;
            aliases.add(m[1]);
          }
          if (aliases.size === 0) return [];

          const names = [...aliases].map((a) => a.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
          const drawnRaw = new RegExp(`\\b(?:${names})\\b\\s*\\.(?:uppercased\\(\\)|capitalized)|Text\\(\\s*(?:${names})\\s*\\)`);

          return body
            .split("\n")
            .filter((line) => drawnRaw.test(line))
            .map((line) => `${rel} — ${line.trim()}`);
        })
        .sort();
    }

    /**
     * The two survivors, each a decision with its reason, in the KNOWN_SURVIVOR
     * idiom above — an EXACT set, so deleting one without saying so is red.
     *
     * `DiscoverLabelingView` is the internal labeling surface. Its whole row is
     * machine vocabulary on purpose (`stratum`, `archetype`, `qualityClass`,
     * `score`), read by whoever is grading the feed, and no reader reaches it.
     * Notice 34 is about a READER's screen; naming these keys would make the tool
     * worse at its only job.
     *
     * `MyStuffView`'s `"unknown"` is not drawn at all: `srcName` is a grouping key
     * for the dedup below it and a lookup into `sourceColors`. The badge that view
     * actually PRINTS already asks the resolver. A scan that flagged it would be
     * teaching the next person to route a dictionary key through a label map.
     */
    const INVENTED_SOURCE_SURVIVORS = [
      'Views/DiscoverLabelingView.swift — pill(item.source ?? "unknown")',
      'Views/MyStuffView.swift — let srcName = item.source ?? "unknown"',
    ];

    function offenders(pattern: RegExp): string[] {
      return swiftFiles(IOS_ROOT)
        .flatMap((path) => {
          const rel = path.slice(IOS_ROOT.length + 1);
          return stripComments(readFileSync(path, "utf8"))
            .split("\n")
            .filter((line) => pattern.test(line))
            .map((line) => `${rel} — ${line.trim()}`);
        })
        .sort();
    }

    it("no view uppercases a source key onto the screen", () => {
      expect(offenders(RAW_KEY_UPPERCASED)).toEqual([]);
    });

    it("no view draws or re-cases a LOCAL bound from a source key", () => {
      expect(aliasOffenders()).toEqual([]);
    });

    it("the alias scan resolves real bindings and catches the line that beat the line scans", () => {
      // The scan is only as good as its binding step, and a binding step that
      // matched nothing would make the assertion above vacuous — the exact way
      // this file was already green while `ODDS_API` was on the screen.
      const distribution = stripComments(
        readFileSync(join(IOS_ROOT, "Components/DistributionCardView.swift"), "utf8")
      );
      expect(distribution).toContain("SourceLabels.label(for: data.source)");

      // Verbatim from origin/master 10cbbcfd. Neither line pattern in this file
      // matches the drawn line; the alias scan does, and only because it read the
      // binding above it.
      const preFix = [
        `                if let src = data.source {`,
        `                    Text(src.uppercased())`,
      ].join("\n");
      expect(RAW_KEY_UPPERCASED.test(preFix.split("\n")[1])).toBe(false);
      expect(INVENTED_SOURCE.test(preFix.split("\n")[1])).toBe(false);
      expect(/\bsource\??\.capitalized\b/.test(preFix.split("\n")[1])).toBe(false);

      const aliases = [...preFix.matchAll(/\blet\s+(\w+)\s*=\s*([^\n]*\bsources?\b[^\n]*)/g)]
        .filter((m) => !m[2].includes("SourceLabels"))
        .map((m) => m[1]);
      expect(aliases).toEqual(["src"]);
      expect(/\bsrc\b\s*\.uppercased\(\)/.test(preFix)).toBe(true);
    });

    it("no view invents a source name where the payload gave none", () => {
      expect(offenders(INVENTED_SOURCE)).toEqual(INVENTED_SOURCE_SURVIVORS);
    });

    it("both new patterns would have fired before this fix, and do not fire on its explanation", () => {
      // Verbatim from origin/master 10cbbcfd. A negative scan that matches
      // nothing is green for the same reason a correct tree is green, so the
      // only proof it can offer is the deleted code.
      const deleted: Array<[RegExp, string]> = [
        [RAW_KEY_UPPERCASED, `                        Text(sources.map { $0.uppercased() }.joined(separator: " + "))`],
        [RAW_KEY_UPPERCASED, `                    Text((data.source ?? "market").uppercased())`],
        [INVENTED_SOURCE, `                    Text((data.source ?? "market").uppercased())`],
        [INVENTED_SOURCE, `                        Text(market.source ?? "kalshi")`],
      ];
      for (const [pattern, line] of deleted) {
        expect([line, pattern.test(line)]).toEqual([line, true]);
      }

      // …and the fix's own prose quotes two of those lines, which is exactly how
      // a tree scan reds on the comment explaining it (#4135 hit this; the strip
      // is what stands between us and a suppression nobody can argue with).
      const discover = readFileSync(join(IOS_ROOT, "Views/DiscoverView.swift"), "utf8");
      expect(INVENTED_SOURCE.test(discover)).toBe(true);
      expect(INVENTED_SOURCE.test(stripComments(discover))).toBe(false);
    });

    /**
     * The alias scan is the net; these are the belt. Each site is ALSO pinned
     * positively — its declaration reaches the resolver and does not re-case what
     * comes back — because a negative scan can only ever say "the spellings I
     * know are absent", and this file has now been wrong about that twice.
     */
    function declarationBody(relPath: string, declaration: string): string {
      const source = stripComments(readFileSync(join(IOS_ROOT, relPath), "utf8"));
      const start = source.indexOf(declaration);
      expect([relPath, declaration, start > -1]).toEqual([relPath, declaration, true]);
      const after = source.indexOf("\nprivate struct ", start + declaration.length);
      const body = source.slice(start, after > -1 ? after : source.length);
      // A slice that collapsed to the declaration would pass every assertion below.
      expect(body.length).toBeGreaterThan(declaration.length + 200);
      return body;
    }

    it.each([
      ["Components/DiscoverFuturesCard.swift", "private var sourceMark: String? {"],
      ["Views/DiscoverView.swift", "private struct NativeIPOComparisonRow: View {"],
      ["Views/DiscoverView.swift", "private struct NativeThresholdComparisonRow: View {"],
    ])("%s %s names its source through the resolver and does not re-case it", (relPath, declaration) => {
      const body = declarationBody(relPath, declaration);
      expect(body).toContain("SourceLabels.label(for:");
      expect(body).not.toContain(".uppercased()");
      expect(body).not.toContain(".capitalized");
    });

    it("every one of the seven files reaches the resolver at all", () => {
      // The coarse net under the slices: a rewrite that renames the declarations
      // above would skip every `it.each` case via a red slice, but this one still
      // has to hold. All seven files #4351 touched are here, including the four
      // the first cut of this ship missed and a LOOK found.
      for (const rel of [
        "Components/DiscoverFuturesCard.swift",
        "Views/DiscoverView.swift",
        "Components/RelatedFuturesView.swift",
        "Components/DistributionCardView.swift",
        "Components/HeatMapCardView.swift",
        "Components/PlayerPropsCardView.swift",
        "Views/TeamDetailView.swift",
      ]) {
        const source = stripComments(readFileSync(join(IOS_ROOT, rel), "utf8"));
        expect([rel, source.includes("SourceLabels.label(for:")]).toEqual([rel, true]);
      }
    });

    it("the resolver still refuses to name a key it does not know", () => {
      // The whole fix rests on `label(for:)` returning nil rather than the key —
      // every call site above draws nothing on nil. A `?? source` added to the
      // resolver would repair all five screens' silence into five raw keys again,
      // and no assertion above would move.
      const resolver = stripComments(readFileSync(RESOLVER, "utf8"));
      expect(resolver).toMatch(/return marketSourceNames\[source\]\s*$/m);
      expect(resolver).not.toMatch(/marketSourceNames\[source\]\s*\?\?/);
    });
  });
});
