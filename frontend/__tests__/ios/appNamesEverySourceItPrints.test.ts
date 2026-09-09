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
});
