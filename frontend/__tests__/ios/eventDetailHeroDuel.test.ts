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
    //
    // #5271 RE-ANCHORED. The opening captions now ask `DrawPricedWinner`
    // whether they may print a pair at all, so both branches bind the same two
    // names: `awayOpen` (from `opened.away`, inside the guard) and
    // `opened.home`. That collapses the old four opening names to two and makes
    // the settled and live captions indistinguishable here — which is the
    // point of the separate both-branches test below. The claim is unchanged:
    // every side of a two-sided question carries a decided percent.
    const PAIRED_ARGS = ["away", "home", "awayOpen", "opened\\.home"];

    // `home` and `opened.home` also each have exactly ONE legitimate bare use —
    // the withheld arm, where there is no second side to sum with. Those are
    // counted and located by the next test; here they are simply not counted as
    // violations, and every other paired name stays banned outright.
    const BARE_IS_EARNED = new Set(["home", "opened\\.home"]);

    for (const arg of PAIRED_ARGS) {
      if (!BARE_IS_EARNED.has(arg)) {
        const bare = new RegExp(`formatProbability\\(${arg}\\)`);
        expect({ arg, bare: bare.test(view) }).toEqual({ arg, bare: false });
      }
      expect(view).toMatch(
        new RegExp(`formatProbability\\(${arg}, renderedPercent:`),
      );
    }
  });

  /**
   * #5271 — THE ONE EXEMPTION, and it is stated rather than carved out of the
   * list above, because "which numbers may be rounded alone" is the question
   * the assertion above exists to answer.
   *
   * On a draw-priced sport the hero withholds the away slot, so what it prints
   * is not one side of a two-sided question — there is no complement for it to
   * sum to 101 with. It must NOT go through `duelPercents`: that contract's
   * answer for one side can be `100 − other`, a number about the very
   * complement this branch refuses to print.
   *
   * Asserted by NAME rather than by sweeping every bare `formatProbability` in
   * the file — this view has legitimate lone numbers that were never pairs (a
   * divergence magnitude, a line move's before and after), and a sweep would
   * make this guard a list of unrelated call sites that anyone would delete.
   */
  it("the withheld single numbers are rounded alone, and only in that arm", () => {
    // The hero's lone named number, directly under the name that attributes
    // it — the two are one unit, and the name is what makes the bare rounding
    // legitimate.
    expect(view).toMatch(
      /Text\(named\.home\)[\s\S]{0,400}Text\(formatProbability\(home\)\)/,
    );
    // Both "Opened {Home} 47%" captions, settled and live.
    const openedSolo =
      view.match(
        /Text\("Opened \\\(named\.home\) \\\(formatProbability\(opened\.home\)\)"\)/g,
      ) ?? [];
    expect(openedSolo).toHaveLength(2);

    // EXACTLY those three bare uses and no fourth — this is the half the test
    // above hands over, so a bare `home` appearing anywhere else (in the duel
    // arm, say, where it would re-open the 101) fails here.
    expect(view.match(/formatProbability\(home\)/g) ?? []).toHaveLength(1);
    expect(view.match(/formatProbability\(opened\.home\)/g) ?? []).toHaveLength(2);

    // AND THE DIRECTION THAT MATTERS: no withheld side is ever printed. If a
    // later edit reaches for the complement again it has to name it, and these
    // are the names it would have to use.
    for (const withheld of ["opened\\.away", "pair\\.away"]) {
      expect(view).not.toMatch(new RegExp(`formatProbability\\(${withheld}`));
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
    //
    // #5271 RE-ANCHORED to the names the two captions bind now. Both still
    // decide their pair through the shared helper; what changed is that each
    // first asks `DrawPricedWinner` whether it may draw a pair at all, so the
    // duel call sits inside an `if let awayOpen = opened.away`.
    const openingDuels =
      view.match(
        /renderedDuelPercents\(\s*away: awayOpen,\s*home: opened\.home\s*\)/g,
      ) ?? [];
    expect(openingDuels).toHaveLength(2);

    // …and each of the two is guarded by its own withholding check, so a
    // caption that lost its guard and printed the complement again fails here.
    const guards = view.match(/if let awayOpen = opened\.away \{/g) ?? [];
    expect(guards).toHaveLength(2);
  });

  it("the probabilities themselves are still what the bar and the chart read", () => {
    // Rendering-only, and it must stay that way. `ProbabilityBar` takes the
    // PROBABILITIES; if a percent ever reached it the bar would be drawn on a
    // 0–100 value in a 0–1 API.
    //
    // #4233 — RE-ANCHORED, and worth saying why. This asserted the literal text
    // `awayProb: awayProbability, homeProb: homeProbability`, which was the
    // SOURCES ROW's call, not the hero's — the only `ProbabilityBar` in this
    // file is the sources list's, and the hero draws its duel elsewhere. So this
    // guard has been passing on a render path its own describe block does not
    // name. Consolidating the two source rows into one builder (#4233) renamed
    // those locals and surfaced it.
    //
    // The claim is still worth keeping and is kept, now stated as the property
    // rather than as one call's spelling: whatever this file hands the bar is a
    // 0–1 probability, never a percent.
    //
    // #5271 — the away segment is now `probabilities.away ?? (1 - …home)`,
    // because a withheld away side still has a BAR: its two segments are a
    // partition and the remainder is a true quantity ("this source does not
    // have the home team winning"). Still a 0–1 probability, which is the
    // property this guard holds.
    const barCall = view.slice(view.indexOf("ProbabilityBar("));
    expect(barCall).toMatch(
      /awayProb: probabilities\.away \?\? \(1 - probabilities\.home\),\s*homeProb: probabilities\.home/,
    );
    expect(barCall.slice(0, 300)).not.toMatch(/awayProb:[^,]*[Pp]ercent/);
    // …and the remainder loses the away team's COLOUR when it loses its number,
    // so the bar never claims for a team what the row declines to print.
    expect(barCall.slice(0, 400)).toMatch(
      /awayColor: probabilities\.away == nil/,
    );
  });
});
