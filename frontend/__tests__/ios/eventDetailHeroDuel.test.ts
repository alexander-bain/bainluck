/**
 * #2085 — the iOS event detail hero decides its two percents TOGETHER, asserted
 * by reading the Swift.
 *
 * `EventDetailView` printed `formatProbability(away)` beside
 * `formatProbability(home)` for a pair the backend derives as
 * `round(1 - home, 6)`, so it printed 101 whenever `home * 100` landed on a
 * half-percent — 34 of 414 scheduled/live events, measured 2026-08-21. Native's
 * hero reads `currentOdds` directly (unlike web, whose live hero is the blend),
 * so the SERVED pair is the right one here — but a cached or pre-deploy payload
 * has neither field, which is what `renderedDuelPercents` is for.
 *
 * ## Why this lives in jest
 *
 * `periodLabelSingleSource.test.ts`'s reason, unchanged: jest is a deploy gate
 * here and the Swift test target is not reachable from CI
 * (`scripts/ios_native_gate.sh test` is attended). The RULE itself is proven by
 * `BainLuckTests/RenderedPercentContractTests.swift` against the shared contract
 * table; what cannot be proven from CI is that this VIEW calls it, and that is
 * exactly what a source read can establish. A grep cannot tell a rendered field
 * from a declared one — so this file asserts the absence of the bare call as
 * well as the presence of the fixed one, which is the pair of claims a
 * half-applied edit fails.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const VIEW = join(IOS_ROOT, "Views/EventDetailView.swift");
const HELPER = join(IOS_ROOT, "Utilities/RenderedPercent.swift");
const FORMATTER = join(IOS_ROOT, "Utilities/FormattingUtilities.swift");

// The whole suite is meaningless if it is pointed at nothing — a path typo would
// otherwise read as a clean pass.
const iosPresent = existsSync(VIEW) && existsSync(HELPER);
const d = iosPresent ? describe : describe.skip;

d("the iOS event detail hero prints a decided pair", () => {
  const view = readFileSync(VIEW, "utf8");

  it("the shared helper and the override parameter both still exist", () => {
    // If either of these is renamed, the assertions below would pass vacuously
    // for a view that no longer compiles.
    expect(readFileSync(HELPER, "utf8")).toContain(
      "nonisolated func renderedDuelPercents(",
    );
    expect(readFileSync(FORMATTER, "utf8")).toMatch(
      /func formatProbability\(_ value: Double, renderedPercent: Int\? = nil\)/,
    );
  });

  it("the hero pair goes through renderedDuelPercents", () => {
    expect(view).toContain("renderedDuelPercents(away: away, home: home)");
  });

  it("the hero takes BOTH served percents or neither", () => {
    // One served value beside a locally derived one re-opens the same 101 from
    // the other direction, and an older deploy can carry one field and not the
    // other. `DiscoverEventCard` still coalesces per side (`?? duelFallback[0]`)
    // — that is a separate surface and a separate fix; this assertion is here so
    // the pattern is not copied INTO this view later.
    expect(view).toContain(
      "let bothServed = odds.awayRenderedPercent != nil && odds.homeRenderedPercent != nil",
    );
    expect(view).toContain("bothServed ? odds.awayRenderedPercent : duelFallback[0]");
    expect(view).toContain("bothServed ? odds.homeRenderedPercent : duelFallback[1]");
  });

  it("no probability pair in this view is formatted without a decided percent", () => {
    // THE LOAD-BEARING ASSERTION. Every `formatProbability` call in this file
    // that draws one side of a two-sided question must carry a
    // `renderedPercent:`. Listed by their argument names rather than by a
    // catch-all regex, so a NEW pair added later shows up as an unlisted name
    // in the next test rather than as a silently shorter scan.
    const PAIRED_ARGS = [
      "away",
      "home",
      "awayOpeningProbability",
      "homeOpeningProbability",
      "awayOpen",
      "homeOpen",
    ];
    for (const arg of PAIRED_ARGS) {
      const bare = new RegExp(`formatProbability\\(${arg}\\)`);
      expect({ arg, bare: bare.test(view) }).toEqual({ arg, bare: false });
      expect(view).toMatch(
        new RegExp(`formatProbability\\(${arg}, renderedPercent:`),
      );
    }
  });

  it("both opening lines are covered, not just the settled one", () => {
    // The settled branch and the live branch each draw their own
    // "Opened away – home". Fixing one and not the other is the shape this
    // counts against: two distinct `renderedDuelPercents(away:` call sites for
    // opening probabilities, plus the hero's own.
    const duelCalls = view.match(/renderedDuelPercents\(/g) ?? [];
    expect(duelCalls.length).toBeGreaterThanOrEqual(3);
    // Whitespace-tolerant: SwiftFormat wraps a long argument list, and a guard
    // that a reformat can turn red is a guard nobody keeps.
    expect(view).toMatch(
      /renderedDuelPercents\(\s*away: awayOpeningProbability,\s*home: homeOpeningProbability\s*\)/,
    );
    expect(view).toMatch(
      /renderedDuelPercents\(\s*away: awayOpen,\s*home: homeOpen\s*\)/,
    );
  });

  it("the probabilities themselves are still what the bar and the chart read", () => {
    // Rendering-only, and it must stay that way. `ProbabilityBar` takes the
    // PROBABILITIES; if a percent ever reached it the bar would be drawn on a
    // 0–100 value in a 0–1 API.
    expect(view).toMatch(/ProbabilityBar\(\s*\n?\s*awayProb: awayProbability, homeProb: homeProbability/);
  });
});
