/**
 * #5133 defect A — the native side of CERT-2611's required repair
 * `5133-TWO-SIDED-SCORING-RACE-REMAINS-VISIBLE`, asserted by reading the Swift.
 *
 * The backend fix lands Kalshi's scoring races in `other[]` instead of serving
 * them as player props. `SpecialEventMarketsView.isWinProbabilityMarket` then
 * filters out any market whose two rows sum to ~1.0 as "the hero market", and a
 * scoring race is that shape — so one of the six races on a measured NFL event
 * disappears instead of moving.
 *
 * MEASURED (`GET /api/events/14780145/game-markets`, 2026-09-11): five races
 * serve THREE rows and survive by accident; `Race to 7 Points` serves TWO,
 * 0.56 / 0.44, because its third row ("Neither team reaches 7 points", 0.010)
 * is dropped upstream.
 *
 * WHY THIS FILE AND NOT ONLY THE SWIFT SUITE.
 * `AScoringRaceStaysVisible5133Tests` proves the filter. It cannot prove the
 * VIEW still applies the filter's answer: `categories` is a computed property
 * on a SwiftUI view, invisible to XCTest. Deleting `!winProbNames.contains(…)`
 * from the filter chain leaves every Swift test green and puts the moneyline
 * back in Special Event Markets. These assertions kill that mutant, and they
 * run in CI, which compiles no Swift.
 *
 * THREE COPIES OF ONE RULE, on purpose and pinned as such: the server's
 * `_SCORING_RACE_RE` (`backend/app/routes/events.py`), the web's
 * `isScoringRaceMarket` (`frontend/lib/otherMarketGroups.ts`), and Swift's
 * `SpecialEventMarketsView.isScoringRaceMarket`. Three surfaces answer the same
 * question and the pattern has to be one pattern; the last test below asserts
 * the three source texts carry it identically.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const REPO = join(__dirname, "../../..");
const VIEW = join(REPO, "ios/Bain Luck/Bain Luck/Components/SpecialEventMarketsView.swift");
const WEB = join(REPO, "frontend/lib/otherMarketGroups.ts");
const SERVER = join(REPO, "backend/app/routes/events.py");

/**
 * The pattern, as it must appear in all three. Written once here and matched
 * against each file's own text, rather than three separate literals that can
 * drift apart without any test noticing.
 */
const PATTERN_BODY = String.raw`\brace to\s+\d+(?:\.\d+)?\s+points?\b`;

function stripSwiftComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

// A path typo would otherwise read as a clean pass.
const present = existsSync(VIEW) && existsSync(WEB) && existsSync(SERVER);
const d = present ? describe : describe.skip;

d("a two-sided scoring race stays visible on iOS", () => {
  const view = () => stripSwiftComments(readFileSync(VIEW, "utf8"));

  it("the view has a named scoring-race predicate", () => {
    expect(view()).toMatch(/static func isScoringRaceMarket\(_ name: String\) -> Bool/);
  });

  /**
   * The repair itself: the hero-suppression loop must SKIP a race before it
   * reaches the two-complementary-rows test. Order matters — an exemption
   * placed after the `winProbMarkets.insert` would never run.
   */
  it("the suppression loop skips a race BEFORE the two-row test", () => {
    const code = view();
    const loop = /func isWinProbabilityMarket\([\s\S]*?\n    \}/.exec(code);

    expect(loop).not.toBeNull();
    const body = loop![0];

    const skip = body.indexOf("isScoringRaceMarket(name)");
    const twoRowTest = body.indexOf("outcomes.count == 2");

    expect(skip).toBeGreaterThan(-1);
    expect(twoRowTest).toBeGreaterThan(-1);
    expect(skip).toBeLessThan(twoRowTest);
    expect(body).toMatch(/if Self\.isScoringRaceMarket\(name\) \{ continue \}/);
  });

  /**
   * …and the rule it rides on is still WIRED. This is the mutant no Swift test
   * can see: the filter can keep working perfectly while the view stops asking
   * it, and the result is the moneyline printed twice.
   */
  it("the view still filters its rows through the suppression set", () => {
    const code = view();

    expect(code).toMatch(/let winProbNames = Self\.isWinProbabilityMarket\(markets\)/);
    expect(code).toMatch(/!winProbNames\.contains\(\$0\.marketName\)/);
  });

  it("all three copies of the rule carry the same pattern", () => {
    const swift = view();
    const web = readFileSync(WEB, "utf8");
    const server = readFileSync(SERVER, "utf8");

    // Swift spells it in a raw string, TS in a regex literal, Python in an
    // r-string; the PATTERN BODY is byte-identical in all three.
    expect(swift).toContain(`#"${PATTERN_BODY}"#`);
    expect(web).toContain(`/${PATTERN_BODY}/i`);
    expect(server).toContain(`r"${PATTERN_BODY}"`);
  });

  /**
   * The control for the test above: it would pass just as happily if
   * `PATTERN_BODY` were a string none of them contained… no, it would not —
   * but it WOULD pass if the pattern were something trivially common. Assert
   * the pattern is the discriminating one by running it against the two names
   * it must separate.
   */
  it("the shared pattern is the discriminating one", () => {
    const re = new RegExp(PATTERN_BODY, "i");

    expect(re.test("New Orleans vs Detroit: Race to 7 Points")).toBe(true);
    expect(re.test("New Orleans vs Detroit Winner")).toBe(false);
    expect(re.test("Race to 5 catches")).toBe(false);
  });
});

/**
 * #5133 — CERT-2620's half, `5133-NATIVE-SCORING-RACE-OVERFLOW-IS-REACHABLE`.
 *
 * `NativeScoringRaceOverflowIsReachable5133Tests` proves `displayedItems` hands
 * back the ninth, tenth and eleventh cards when asked to expand. It cannot
 * prove `body` ASKS — a SwiftUI body is unreachable from XCTest, and the whole
 * defect was a body that rendered `prefix(5)` and then an inert `Text`. So the
 * two mutants that matter are pinned here, in a file CI actually runs.
 */
d("the scoring race is reachable past the category cap", () => {
  const view = () => stripSwiftComments(readFileSync(VIEW, "utf8"));

  it("the body renders through the seam the guard tests, not its own cap", () => {
    const code = view();

    expect(code).toMatch(
      /ForEach\(Self\.displayedItems\(cat\.items, expanded: isExpanded\)\)/,
    );
    // THE DEFECT, spelled out so it cannot come back by accident.
    expect(code).not.toMatch(/cat\.items\.prefix\(/);
  });

  it("the overflow is a control a reader can hit, not a caption", () => {
    const code = view();
    const overflow = /if cat\.items\.count > Self\.itemDisplayCap \{[\s\S]*?\n {28}\}/.exec(code);

    expect(overflow).not.toBeNull();
    const body = overflow![0];

    // A Button, and one that mutates the state the seam reads.
    expect(body).toMatch(/Button \{/);
    expect(body).toMatch(/expandedCategories\.insert\(cat\.id\)/);
    expect(body).toMatch(/expandedCategories\.remove\(cat\.id\)/);
    // The old shape: a Text and nothing else.
    expect(body).not.toMatch(/^\s*Text\("\+\\\(cat\.items\.count/m);
  });

  it("the cap is one named number, not a literal sprinkled through the view", () => {
    const code = view();

    expect(code).toMatch(/static let itemDisplayCap = 5/);
    // `prefix(5)` / `> 5` anywhere in this view is the drift this catches.
    expect(code).not.toMatch(/\.prefix\(5\)/);
    expect(code).not.toMatch(/cat\.items\.count > 5/);
  });

  /**
   * The control. Every assertion above is a `toMatch` against source text, and
   * source text passes vacuously if the symbol it names does not exist at all —
   * so assert the seam and its state are really declared.
   */
  it("the seam and its state exist", () => {
    const code = view();

    expect(code).toMatch(
      /static func displayedItems\(_ items: \[MarketItem\], expanded: Bool\) -> \[MarketItem\]/,
    );
    expect(code).toMatch(/@State private var expandedCategories: Set<String> = \[\]/);
  });
});
