/**
 * #3966 — the app never says "bookmaker", and the Calibration source name wraps.
 *
 * TWO RULINGS, ONE FILE, because they landed in one sentence from Alex. Shown the
 * Calibration → Source Comparison table on a phone with `Per-Bookmaker (Odds…`
 * cut off, he answered the layout question (**D92 = B**, let the name wrap) and
 * then reacted to the row itself: *"we wouldn't EVER want to reference
 * 'bookmakers'"*. Standing notice 33 is that reaction as a rule — "books",
 * "bookmaker", "bookmakers" never appear in anything the app draws, and **D91**
 * makes "sportsbooks" the approved word.
 *
 * ═══ WHY A SOURCE SCAN AND NOT AN XCTEST ═══
 *
 * CI COMPILES NO SWIFT. Everything the Swift suite asserts about this ship — the
 * renamed label, the tensed chart note — is real and runs on a laptop, and none
 * of it stands between a regression and production. This file does, which is why
 * the wiring assertions are here rather than there.
 *
 * The Swift tests also structurally cannot make the wrap claim. `sourceRow` is a
 * `private func` on a view; XCTest can reach the model's strings but not the
 * modifier chain the strings are drawn through, and `.lineLimit(1)` restored on
 * line 510 leaves every Swift test in the repo green. That one-character mutant
 * is the whole regression and the assertions below are what kill it.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * That two lines are ENOUGH. That is a claim about drawn text and nothing here
 * can read a glyph. #3954 tried to make it arithmetically and was wrong by ~21pt
 * in the safe-looking direction (the fit note on
 * `testTheTableRendersAtEveryPhoneWidthAndReflowsWithIt` records it), so the
 * "reads in full" claim is carried by the 375pt and 402pt screenshots on #3966's
 * PR and is re-owed by whoever adds a longer name. What is asserted here is
 * narrower and checkable: the view asks for a second line, and no string the app
 * draws carries a banned word.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

import { BANNED, KEY_SHAPED } from "../helpers/bannedSupplierWords";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CALIBRATION_VIEW = join(IOS_ROOT, "Views/CalibrationView.swift");
const GEOMETRY = join(IOS_ROOT, "Utilities/CalibrationSourceTableGeometry.swift");

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
 * `\(…)` removed, innermost first, so an IDENTIFIER inside a string stops
 * reading as prose.
 *
 * This is not tidying — it is the difference between a scan and a nuisance.
 * `FuturesDetailView` draws
 * `"Probabilities from \(bookmakers.count) sportsbook\(bookmakers.count != 1 ? "s" : "")"`,
 * whose SENTENCE is already correct ("sportsbook") and whose interpolations name
 * a Swift property. A scan that flagged that line would be reporting a variable
 * name to a reader, and the first person to hit it would suppress the scan.
 *
 * Looped rather than single-pass because interpolations nest, and it strips the
 * quotes inside them too — which is the second reason to do this BEFORE literals
 * are extracted, since `? "s" : ""` would otherwise close the literal early and
 * leave the tail parsing as code.
 */
function stripInterpolations(source: string): string {
  let out = source;
  for (;;) {
    const next = out.replace(/\\\([^()]*\)/g, "");
    if (next === out) return out;
    out = next;
  }
}

/**
 * Every string literal in a Swift file, multi-line ones included.
 *
 * `"""` blocks are lifted out FIRST and their delimiters removed, because the
 * single-line pattern would read the opening `"""` as an empty literal followed
 * by an unterminated one and desynchronise for the rest of the file. Four app
 * files use them (`DiscoverView`, `DiscoverTournamentCard`, `LiquidityMarkView`,
 * `NotificationManager`) and one of those four is prose a reader sees.
 */
function stringLiterals(source: string): string[] {
  const stripped = stripInterpolations(stripComments(source));
  const literals: string[] = [];
  const withoutBlocks = stripped.replace(/"""([\s\S]*?)"""/g, (_, body: string) => {
    literals.push(body);
    return '""';
  });
  for (const match of withoutBlocks.matchAll(/"((?:[^"\\\n]|\\.)*)"/g)) {
    literals.push(match[1]);
  }
  return literals;
}

// The word ban itself — the two regexes and the key-shape exemption, with the
// reasoning for each — moved to `../helpers/bannedSupplierWords` by #4096, and
// the move is the point. This scan was correct and enforced notice 33 over
// `ios/` alone, so the web went on saying "20+ bookmakers" in rendered prose and
// carrying `Per-Bookmaker (Odds API)` in two label maps. `theWebNeverSaysBookmaker`
// is the sibling that closes that, and it imports the SAME predicate so the two
// clients cannot drift into different definitions of the ban.

// A path typo would otherwise read as a clean pass — the unrunnable-check
// failure mode a source scan is most prone to.
const iosPresent = existsSync(CALIBRATION_VIEW) && existsSync(GEOMETRY);
const d = iosPresent ? describe : describe.skip;

d("the app never says \"bookmaker\", and the source name wraps", () => {
  describe("standing notice 33 — no banned supplier word in anything the app draws", () => {
    it("no string literal in the iOS app carries one — discovered, not listed", () => {
      const offenders: string[] = [];

      for (const path of swiftFiles(IOS_ROOT)) {
        for (const literal of stringLiterals(readFileSync(path, "utf8"))) {
          if (KEY_SHAPED.test(literal)) continue;
          const hit = BANNED.find(([, re]) => re.test(literal));
          if (hit) {
            offenders.push(`${path.slice(IOS_ROOT.length + 1)} — ${hit[0]} — "${literal.trim()}"`);
          }
        }
      }

      expect(offenders).toEqual([]);
    });

    it("fires on the REAL pre-fix strings, verbatim from origin/master 980beeef", () => {
      // Not synthetics that merely prove a regex can match. Every line is copied
      // from the source this ship changed — a guard is only proven by the code it
      // was built to catch. Both were live on production when Alex read the row.
      const prefix = [
        `        "odds_api_bookmaker": "Per-Bookmaker (Odds API)",`,
        `                + "\\(scoreboardUnit). The line below was the books' projected "`,
        `            + "\\(scoreboardUnit). The line below is the books' projected "`,
      ];
      for (const line of prefix) {
        const literals = stringLiterals(line).filter((l) => !KEY_SHAPED.test(l));
        expect([line, literals.some((l) => BANNED.some(([, re]) => re.test(l)))]).toEqual([
          line,
          true,
        ]);
      }
    });

    it("does NOT fire on the approved word, on a wire key, or on an interpolated identifier", () => {
      // The inverse hazard. Each of these is live in the app today and each would
      // make the scan a nuisance if it fired — which is how scans get suppressed.
      const legitimate = [
        // D91's approved word. No boundary inside "sportsbooks", so `\bbooks?\b` misses it.
        `                    Text("Probabilities from \\(bookmakers.count) sportsbook\\(bookmakers.count != 1 ? "s" : "")")`,
        // The wire key stays; only its NAME moved.
        `        "odds_api_bookmaker": "Per-sportsbook (Odds API)",`,
        // A decoding key and a property, neither of them drawn.
        `        case lastUpdated, nextUpdateExpected, resolutionDate, bookmakerCount`,
        // The repaired sentence.
        `            + "\\(scoreboardUnit). The line below is the sportsbooks' projected "`,
      ];
      for (const line of legitimate) {
        const flagged = stringLiterals(line)
          .filter((l) => !KEY_SHAPED.test(l))
          .filter((l) => BANNED.some(([, re]) => re.test(l)));
        expect([line, flagged]).toEqual([line, []]);
      }
    });

    it("a comment may still carry the word, and a multi-line literal may not", () => {
      // Comments and identifiers are exempt BY CONSTRUCTION (notice 33 is about
      // what a reader sees), and the `"""` path is the one most likely to rot
      // silently — it is a different extractor from the single-line pattern.
      const comment = `    /// the books' GAME spread, drawn on the same axis.`;
      expect(stringLiterals(comment)).toEqual([]);

      const block = ['let body = """', "Odds from 20+ bookmakers.", '"""'].join("\n");
      const flagged = stringLiterals(block).filter((l) =>
        BANNED.some(([, re]) => re.test(l))
      );
      expect(flagged.length).toBe(1);
    });
  });

  describe("#3966 (D92 = B) — the Calibration source name is allowed a second line", () => {
    const view = () => readFileSync(CALIBRATION_VIEW, "utf8");
    const geometry = () => readFileSync(GEOMETRY, "utf8");

    /**
     * `sourceRow`'s body alone, and the scoping is a correction rather than
     * tidiness.
     *
     * The first version of this guard asserted `.lineLimit(1)` was absent from
     * the FILE and failed immediately — on `categorySummaryCard` and
     * `categoryMetricRow`, which draw a `CalCategoryRow` ("Baseball",
     * "Politics") in a different table and are correctly one line. A whole-file
     * assertion here does not read as strict, it reads as wrong, and the only
     * way to make it pass would have been to change a table nobody asked about.
     */
    function sourceRowBody(): string {
      const source = stripComments(view());
      const start = source.indexOf("private func sourceRow(");
      expect(start).toBeGreaterThan(-1);
      const next = source.indexOf("\n    private ", start + 1);
      expect(next).toBeGreaterThan(start);
      return source.slice(start, next);
    }

    it("the row asks for the shared line limit and lets the text grow vertically", () => {
      // Both halves matter. `.lineLimit(2)` alone still truncates when a parent
      // proposes a single line's height, so the wrap is only real with
      // `.fixedSize(horizontal: false, vertical: true)` beside it.
      expect(sourceRowBody()).toMatch(
        /Text\(row\.name\)\n\s*\.lineLimit\(CalibrationSourceTableGeometry\.sourceNameLineLimit\)\n\s*\.fixedSize\(horizontal: false, vertical: true\)/
      );
    });

    it("THE MUTANT: the source row does not go back to one line", () => {
      // `.lineLimit(1)` on this `row.name` is the entire regression, it is one
      // character, and it leaves every Swift test green.
      expect(sourceRowBody()).not.toMatch(/Text\(row\.name\)[\s\S]{0,120}?\.lineLimit\(1\)/);
    });

    it("the mutant check is looking at the right function", () => {
      // The scoping above can fail two ways, and a silent empty slice would make
      // the assertion vacuous. So: the slice is the SOURCE table (it carries the
      // measured numeric columns), and it does NOT contain the category table's
      // legitimate one-line names.
      const body = sourceRowBody();
      expect(body).toMatch(/widths: CalibrationSourceTableGeometry\.NumericWidths/);
      expect(body).not.toContain("categoryMetricRow");
      // And the mutant is detectable: the same assertion on the pre-fix text fails.
      const prefix = body.replace(
        /\.lineLimit\(CalibrationSourceTableGeometry\.sourceNameLineLimit\)\n\s*\.fixedSize\(horizontal: false, vertical: true\)/,
        ".lineLimit(1)"
      );
      expect(prefix).toMatch(/Text\(row\.name\)[\s\S]{0,120}?\.lineLimit\(1\)/);
    });

    it("the limit is declared once, as two, where the ruling is recorded", () => {
      // Read from the constant rather than the call site: a test that hard-codes
      // the number keeps passing after the view stops asking for it.
      expect(geometry()).toMatch(/static let sourceNameLineLimit: Int = 2/);
    });
  });
});
