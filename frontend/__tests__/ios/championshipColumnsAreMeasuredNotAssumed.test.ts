/**
 * #4328 — the Championship Path badge column is measured at the reader's text
 * size, and the guard that proves it sweeps that size.
 *
 * `Text(formatProb(prob))` is `.font(.caption)`, a text style, so it grows with
 * the reader's Dynamic Type setting. The trend badge beside it is
 * `.font(.system(size: 9))`, a point size, so it does not. A single `static let`
 * cannot describe a column with one half that scales and one that does not, and
 * the one that shipped was right at `.large` and short at every size above it —
 * from `.xLarge`, one notch up from the default, by 3 pt, out to 65 pt at
 * `.accessibility5`. `lineLimit(1)` then did exactly what it promised and printed
 * `1…` where the probability belonged.
 *
 * ═══ WHY A SOURCE SCAN, WHEN THE REAL GUARD IS IN SWIFT ═══
 *
 * The real guard is `ChampionshipRowLayoutTests`, which hosts the actual views
 * and measures them at all twelve sizes. CI COMPILES NO SWIFT (#4302), so that
 * suite is a fact about one laptop at one moment. This file is what stands
 * between master and a future edit that quietly puts the constant back or
 * deletes the sweep — the two ways #4328 comes back.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * That the column is correct. A scan cannot measure a glyph. It claims only that
 * the view asks the measured rule rather than a constant, and that the Swift
 * suite still sweeps the size dimension.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS = join(__dirname, "../../../ios/Bain Luck");
const VIEW = join(IOS, "Bain Luck/Components/ChampionshipPathView.swift");
const RULE = join(IOS, "Bain Luck/Utilities/ChampionshipRowLayout.swift");
const TESTS = join(IOS, "BainLuckTests/ChampionshipRowLayoutTests.swift");

/**
 * Comments only. String bodies are KEPT: nothing here bans a rendered string, and
 * stripping them is how a scan comes to pass on the expression it banned
 * (native/082's `\(...)` interpolation finding).
 */
function code(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

const present = [VIEW, RULE, TESTS].every(existsSync);
const d = present ? describe : describe.skip;

d("#4328 — the badge column is measured, not assumed", () => {
  it("the scan is looking at the real files", () => {
    // A path typo reads as a clean pass, which is the failure mode a source scan
    // is most prone to. First assertion, on purpose.
    for (const path of [VIEW, RULE, TESTS]) {
      expect([path, existsSync(path)]).toEqual([path, true]);
    }
    expect(code(readFileSync(VIEW, "utf8"))).toContain("struct ChampionshipStageBadges");
    expect(code(readFileSync(RULE, "utf8"))).toContain("enum ChampionshipRowLayout");
  });

  it("the view asks for the MEASURED columns, not the constant", () => {
    const view = code(readFileSync(VIEW, "utf8"));

    // The call the fix put in.
    expect(view).toContain("ChampionshipRowLayout.columns(");
    expect(view).toContain("measured: measuredColumns");

    // And the call it replaced. `badgeWidth(for:)` survives in the rule type as
    // the floor, but a VIEW that reads it directly is back to a column that
    // cannot know what text size it is drawing at.
    expect(view).not.toContain("ChampionshipRowLayout.badgeWidth(for:");
    expect(view).not.toContain("ChampionshipRowLayout.labelWidth");
  });

  it("something actually reports what the rows want", () => {
    // #4134's lesson: a rule that consumes a measurement nobody produces is a
    // rule reading its own default forever. Both ends, named.
    const view = code(readFileSync(VIEW, "utf8"));
    expect(view).toContain("ChampionshipColumnsKey");
    expect(view).toContain("onPreferenceChange(ChampionshipColumnsKey.self)");
    expect(view.match(/NaturalWidthProbe\(column:/g)?.length).toBe(2); // label + badges

    // And it reports the width it read. A probe wired to everything and
    // reporting a constant leaves the rule on its floor forever, and every
    // assertion above it still passes — mutation found this one.
    expect(view).toContain("value[keyPath: column] = width");
  });

  it("the constants are a FLOOR — the default-size render may not move", () => {
    const rule = code(readFileSync(RULE, "utf8"));
    // `merged` takes the element-wise max, so a measurement can only raise the
    // constant. Written the other way round, this fix would shave points off
    // every bar for a reader who changed nothing.
    expect(rule).toMatch(/fallbackColumns\(for: stages\)\.merged\(with: measured\)/);
  });

  it("the third shape exists and gives the bar the WHOLE card", () => {
    const rule = code(readFileSync(RULE, "utf8"));
    // Two separate ways this collapses back into #4328, both found by mutation:
    // a `shape` that can never return the third case, and a third case that
    // still subtracts the column it exists to escape.
    expect(rule).toContain("return .badgesAboveBar");
    expect(rule).toMatch(/case \.badgesAboveBar:\s*\n\s*return contentWidth\s*\n/);
  });

  it("the badge reflows instead of truncating when it cannot fit", () => {
    const view = code(readFileSync(VIEW, "utf8"));
    // At `.accessibility5` the one-line badge wants 141.33 pt and a phone card
    // has 137.3. No column is wide enough, so the arrangement has to give.
    expect(view).toContain("ViewThatFits(in: .horizontal)");
    expect(view).toContain("HStackLayout(alignment: .center, spacing: 4)");
    expect(view).toContain("VStackLayout(alignment: .trailing, spacing: 2)");
  });

  it("the Swift suite still sweeps the text size", () => {
    const tests = code(readFileSync(TESTS, "utf8"));
    // Every size, not a sample: the defect starts at `.xLarge` and a sweep that
    // jumped from `.large` to `.accessibility5` would have missed where it began.
    for (const size of [
      ".xSmall", ".small", ".medium", ".large", ".xLarge", ".xxLarge", ".xxxLarge",
      ".accessibility1", ".accessibility2", ".accessibility3", ".accessibility4",
      ".accessibility5",
    ]) {
      expect([size, tests.includes(size)]).toEqual([size, true]);
    }
    // And it renders the real card at a non-default size — the only assertion in
    // that file that can tell "the rule is right" from "the view uses the rule".
    expect(tests).toContain("render(card, width: 402, at: size)");
  });
});
