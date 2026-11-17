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
const HEADLINE = join(IOS_ROOT, "Utilities/EventSportHeadlines12472.swift");
const HELPER = join(IOS_ROOT, "Utilities/RenderedPercent.swift");
const FORMATTER = join(IOS_ROOT, "Utilities/FormattingUtilities.swift");

// The whole suite is meaningless if it is pointed at nothing — a path typo would
// otherwise read as a clean pass.
const iosPresent = existsSync(VIEW) && existsSync(HEADLINE) && existsSync(HELPER);
const d = iosPresent ? describe : describe.skip;

d("the iOS event detail hero prints a decided pair", () => {
  const view = readFileSync(VIEW, "utf8");
  const headline = readFileSync(HEADLINE, "utf8");

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
    expect(view).toContain("complementDisplayPercents(away: away, home: home)");
    expect(headline).toContain("complementDisplayPercents(away: away, home: home)");
  });

  it("the hero takes BOTH served percents or neither", () => {
    // One served value beside a locally derived one re-opens the same 101 from
    // the other direction, and an older deploy can carry one field and not the
    // other.
    //
    // Direction 199 RE-ANCHORED: the unified event-page headline resolves all
    // pre-game pairs in `EventSportHeadlines12472.nflPregameChanceTexts` and
    // `EventDetailView.heroPairPercents`, both enforcing both-or-neither.
    for (const src of [view, headline]) {
      expect(src).toContain(
        "let bothServed = shown.awayRenderedPercent != nil && shown.homeRenderedPercent != nil",
      );
      expect(src).toContain("bothServed ? shown.awayRenderedPercent : duelFallback[0]");
      expect(src).toContain("bothServed ? shown.homeRenderedPercent : duelFallback[1]");
    }
  });

  it("no probability pair in this view is formatted without a decided percent", () => {
    // Direction 199 RE-ANCHORED: the unified headline formats pairs in
    // `EventSportHeadlines12472.swift` while `EventDetailView.swift` retains
    // `openedText` and `nflPairedHeadline`. Neither file may format a paired
    // `away` probability without a `renderedPercent:` or `EventHeadlineTenths10090.pair`.
    const PAIRED_ARGS = ["away", "home", "awayOpen", "opened\\.home"];
    const TENTHS_PAIRED = new Set(["away", "home"]);
    const BARE_IS_EARNED = new Set(["home", "opened\\.home"]);

    for (const arg of PAIRED_ARGS) {
      if (!BARE_IS_EARNED.has(arg)) {
        const bare = new RegExp(`formatProbability\\(${arg}\\)`);
        expect({ arg, bare: bare.test(view) }).toEqual({ arg, bare: false });
        expect({ arg, bare: bare.test(headline) }).toEqual({ arg, bare: false });
      }
      if (TENTHS_PAIRED.has(arg)) continue;
      expect(view).toMatch(
        new RegExp(`formatProbability\\(${arg}, renderedPercent:`),
      );
    }
    expect(headline).toContain("let tenths = EventHeadlineTenths10090.pair(home: home, away: away)");
    expect(headline).toContain("let tenths = EventHeadlineTenths10090.pair(home: pair.home, away: away)");
    expect(headline).toMatch(/formatProbability\(away, renderedPercent: awayPct\)/);
    expect(headline).toMatch(/formatProbability\(home, renderedPercent: homePct\)/);
    expect(view).toContain("let printed = EventHeadlineTenths10090.pair(home: pair.home, away: away)");
    expect(view).not.toMatch(/formatProbability\(away, renderedPercent:/);
  });

  it("the withheld single numbers are rounded alone, and only in that arm", () => {
    // Direction 199 RE-ANCHORED: on a draw-priced sport where `pair.away == nil`,
    // `EventSportHeadlines12472.swift` formats `pair.home` alone (leaving the away
    // cell `""`), never computing `1 - home`.
    // #12822: before kickoff always uses whole-percent `formatProbability(...)`;
    // only the live `during` arm formats lone home chances in tenths.
    expect(
      headline.match(/EventHeadlineTenths10090\.pair\(home: pair\.home, away: nil\)\.home/g) ?? [],
    ).toHaveLength(1);
    expect(headline).toMatch(/formatProbability\(pair\.home, renderedPercent: shown\.homeRenderedPercent\)/);
    expect(headline).toMatch(/formatProbability\(pair\.home, renderedPercent: homePct\)/);

    const openedSolo =
      view.match(
        /(?:Text\(|return )"Opened \\\(named\.home\) \\\(formatProbability\(opened\.home\)\)"/g,
      ) ?? [];
    expect(openedSolo).toHaveLength(1);

    expect(view.match(/formatProbability\(home\)/g) ?? []).toHaveLength(0);
    expect(headline.match(/formatProbability\(home\)/g) ?? []).toHaveLength(0);
    expect(view.match(/formatProbability\(opened\.home\)/g) ?? []).toHaveLength(1);

    for (const withheld of ["opened\\.away", "pair\\.away"]) {
      expect(view).not.toMatch(new RegExp(`formatProbability\\(${withheld}`));
      expect(headline).not.toMatch(new RegExp(`formatProbability\\(${withheld}`));
    }
  });

  it("both pregame and opening lines decide their pairs through the shared helpers", () => {
    const resolver = readFileSync(
      join(IOS_ROOT, "Utilities/PrematchReading.swift"), "utf8");
    expect(resolver).toMatch(/percents: duelPercents\(/);
    expect(resolver).toMatch(/percents: renderedDuelPercents\(away: away, home: home\)/);

    // Unified headline pregame column (`nbaPregameTexts`) + live pregame summary (`buildLivePregameSummary`).
    expect(headline).toMatch(/formatProbability\(pregame\.awayProbability, renderedPercent: awayPct\)/);
    expect(headline).toMatch(/formatProbability\(pregame\.homeProbability, renderedPercent: homePct\)/);
    expect(headline).toMatch(/let favChanceText = formatProbability\(favProb, renderedPercent: favRendered\)/);

    // Game Info `openedText` in `EventDetailView.swift`.
    const openingDuels =
      view.match(
        /renderedDuelPercents\(\s*away: awayOpen,\s*home: opened\.home\s*\)/g,
      ) ?? [];
    expect(openingDuels).toHaveLength(1);
    const guards =
      view.match(/guard let awayOpen = opened\.away else \{/g) ?? [];
    expect(guards).toHaveLength(1);
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
