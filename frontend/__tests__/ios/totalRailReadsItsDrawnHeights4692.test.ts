/**
 * #4692 — the app's totals map asks whether the rail it is about to DRAW has a
 * shape, not whether the lines behind it were distinct.
 *
 * The two map families on one event page asked different questions about the
 * same thing. The margin cards read `marginRailHasDistribution(density:)` — the
 * heights they are about to paint. The totals cards read
 * `totalRailHasDistribution(thresholds:)` — whether any two served lines
 * differed. Photographed on iPhone 17 against production, 2026-09-10, event
 * 15308052 (Reds 1 – Dodgers 14, `completed`,
 * `artifacts-native-093/before-4692-mlb-15308052-s1000.png`):
 *
 *     Run margin map    Final margin              distinct blocks   ← right
 *     1st half margin   Half margin               two blocks        ← right, word withheld
 *     Runs map          Final runs distribution   uniform, empty    ← overclaims
 *     1st half total    Half runs distribution    uniform, empty    ← overclaims
 *
 * Eleven lines, 2.5 → 12.5, every one served at `over_probability = 0.99` (the
 * Dodgers won by thirteen). Distinct thresholds, so the old rule said "yes";
 * every `dp` is zero, so the builder returns fourteen zeros and the rail draws
 * nothing. Census the same day, a random 60 of the 500 events completed in the
 * previous five days, taken through `extractTotalThresholds`' own filter (only
 * outcomes NAMED "over" parse, so a feed row is not a drawn line): 34 draw two
 * or more lines, 9 lose the word, 25 keep it — the keepers straddle their final
 * and their prices step there.
 *
 * The WEB has always asked the drawn heights (`densityDrawsShape(density, …)`
 * on both families), so this is the app catching up to its own twin, and the
 * parity is asserted below rather than assumed.
 *
 * Lives in jest because jest is a deploy gate here and the Swift test target is
 * not reachable from CI (standing notice 10), the same reason
 * `mapTitleSingleSource` and `teamShortNameSingleSource` do. The Swift-side
 * behaviour is `TotalRailReadsItsDrawnHeights4692Tests`.
 */

import { existsSync, readFileSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const MAP_VIEW = join(IOS_ROOT, "Components/MarketMapView.swift");
const MAP_RAIL = join(IOS_ROOT, "Utilities/MarketMapRail.swift");
const WEB_SECTION = join(__dirname, "../../components/MarketMapSection.tsx");

/** Swift line comments and doc comments, removed — this ship's own prose names
 *  the call it guards, and a scanner that reads prose measures the write-up. */
function stripSwiftComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
}

/** Every argument list passed to `name(` in `source`, comments already gone. */
function argumentsPassedTo(source: string, name: string): string[] {
  return source
    .split(`${name}(`)
    .slice(1)
    .map((rest) => rest.slice(0, rest.indexOf(")")).trim());
}

describe("#4692 — the totals rail's subtitle reads the heights it draws", () => {
  it("finds the files it is guarding", () => {
    expect(existsSync(MAP_VIEW)).toBe(true);
    expect(existsSync(MAP_RAIL)).toBe(true);
    expect(existsSync(WEB_SECTION)).toBe(true);
  });

  /**
   * THE SHIP. Both totals cards — full game and half — hand the rule the same
   * `density` they hand `mapCard`, so the sentence and the shading cannot
   * disagree about the same array.
   */
  it("passes both totals cards' drawn heights to the rule", () => {
    const view = stripSwiftComments(readFileSync(MAP_VIEW, "utf8"));
    const calls = argumentsPassedTo(view, "MarketMapRail.totalRailHasDistribution");
    expect(calls).toEqual(["density: density", "density: density"]);
  });

  /**
   * The class, not the case: no totals card may re-derive the flag from the
   * LINES. `allThresh` is the array the old rule was given, and it still exists
   * on both cards because `totalBounds` legitimately needs it — which is
   * exactly how the old call would come back unnoticed.
   */
  it("lets no totals card compute its flag from a threshold array", () => {
    const view = stripSwiftComments(readFileSync(MAP_VIEW, "utf8"));
    const offenders = argumentsPassedTo(view, "MarketMapRail.totalRailHasDistribution").filter(
      (argument) => /thresh/i.test(argument),
    );
    expect(offenders).toEqual([]);
    expect(view).not.toMatch(/totalRailHasDistribution\(\s*thresholds\s*:/);
  });

  /**
   * The rule and the arithmetic it reads live in one file. While the builder
   * was a `private func` on the view, the rule could not see its output and
   * restated its exits from the outside — it agreed with the builder on the two
   * cases it was written from and disagreed on a third, which IS #4692.
   */
  it("keeps the builder beside the rule that reads its output", () => {
    const rail = stripSwiftComments(readFileSync(MAP_RAIL, "utf8"));
    const view = stripSwiftComments(readFileSync(MAP_VIEW, "utf8"));
    expect(rail).toMatch(/static func densityFromThresholds\(/);
    expect(view).not.toMatch(/func buildDensityFromThresholds\(/);
    expect(view).toContain("MarketMapRail.densityFromThresholds(");
  });

  /**
   * The rule itself is one expression shared with the margin twin, so the two
   * families cannot drift. A fix that copied `densityVaries`' body into the
   * totals rule would pass every assertion above and start #3554's failure
   * again on the next edit.
   */
  it("asks the margin twin's question rather than a copy of it", () => {
    const rail = stripSwiftComments(readFileSync(MAP_RAIL, "utf8"));
    for (const rule of ["totalRailHasDistribution", "marginRailHasDistribution"]) {
      const body = rail.slice(rail.indexOf(`static func ${rule}(`));
      const firstStatement = body.slice(body.indexOf("{") + 1, body.indexOf("}")).trim();
      expect(firstStatement).toBe("densityVaries(density)");
    }
  });

  /**
   * CONTROL, so none of the above is vacuous: the WEB card asks the drawn
   * heights on BOTH families and always has. If this ever stops being true the
   * app is no longer catching up to its twin and this whole guard needs
   * rewriting rather than quietly passing.
   */
  it("CONTROL: the web twin asks the same question of both families", () => {
    const web = readFileSync(WEB_SECTION, "utf8");
    const calls = argumentsPassedTo(web, "densityDrawsShape");
    expect(calls.length).toBeGreaterThanOrEqual(2);
    expect(calls.some((argument) => /MARGIN_ACCENT/.test(argument))).toBe(true);
    expect(calls.some((argument) => /TOTAL_ACCENT/.test(argument))).toBe(true);
    for (const argument of calls) {
      expect(argument).toMatch(/^\w*[Dd]ensity\s*,/);
    }
  });
});
