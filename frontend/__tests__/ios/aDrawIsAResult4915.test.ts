/**
 * #4915 — the app's settled surfaces read a DRAW as "both teams lost", asserted
 * by reading the Swift.
 *
 * Photographed on production 2026-09-10 (master `8ec73a3f`, iPhone 17): AS Roma
 * 1 – 1 Fenerbahce (`15296761`) drew a hero whose verdict slot said the bare
 * word `Final` in `.secondary` grey and whose two scores were BOTH `.secondary`
 * — while Bodø/Glimt 0 – 5 Bayern, same competition, same night, same build,
 * said **`Munich Win`** in bold team blue with the winner's `5` in `.primary`.
 * The grey that means *this team lost* was applied to both sides of a level
 * result, and `EventCardView` did the same to both team names and both scores.
 *
 * The cause was one idiom, repeated:
 *
 *     let homeWon = (event.homeScore ?? 0) > (event.awayScore ?? 0)
 *     let awayWon = (event.awayScore ?? 0) > (event.homeScore ?? 0)
 *
 * Two booleans cannot express three outcomes. Every caller then read `!won` as
 * "lost". `Utilities/EventOutcome.swift` replaces the pair with one value that
 * can say `draw`, and prefers the verdict the server already grades and serves
 * as `hero_settled_result` (which iOS decoded nowhere — the web has typed it
 * since `frontend/lib/types.ts`).
 *
 * WHY THIS FILE EXISTS AND `EventOutcomeTests.swift` DOES NOT SUFFICE.
 * The Swift suite proves the enum. It cannot prove the VIEWS call it: the
 * verdict slot and both dim treatments are expressions inside SwiftUI bodies,
 * invisible to XCTest — the same blind spot #4002 lived in. Reverting any one
 * of the call sites below to its pre-fix expression leaves every Swift test
 * green. These assertions are what kill those mutants, and they run in CI,
 * which compiles no Swift at all.
 *
 * SCOPE. `IOS_ROOT` is the phone/iPad/Mac app. The widget and the watch app are
 * outside it; measured at the time of writing, NEITHER derives a winner at all
 * (`grep -rnE '(home|away)Score[^,)]*[<>][^,)]*(away|home)Score'` over the whole
 * `ios/` tree returns only `EventOutcome.swift`'s own docstring), so there is no
 * third copy to migrate and no exception to record.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Utilities/EventOutcome.swift");

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
 * The re-derivation tell: two scores compared against each other, in any
 * direction, with or without the `?? 0` that makes a missing score look like a
 * goalless draw. Written to catch the SHAPE rather than the exact pre-fix line,
 * because the bug is "this file decided the verdict itself", not "this file
 * used a coalescing operator". Its positive control below runs it against the
 * literal source that shipped the defect.
 *
 * Three details are each load-bearing and each was measured, not guessed:
 *  - `)` is INSIDE the gap. The first draft excluded it to avoid running across
 *    argument boundaries, and that single exclusion made the tell miss the
 *    parenthesised `(a ?? 0) > (b ?? 0)` idiom that IS the defect — the control
 *    below caught it.
 *  - `,` is not, so the tell cannot run from one parameter to the next.
 *  - `(?<!-)` keeps a return arrow out of it: `func f(homeScore:) -> T` followed
 *    by `awayScore` on the same line is a signature, not a verdict.
 */
const RE_DERIVES_THE_VERDICT =
  /(home|away)Score[^,\n]{0,24}(?<!-)[<>][^,\n]{0,24}(away|home)Score/;

// A path typo would otherwise read as a clean pass — the unrunnable-check
// failure mode this whole file exists to stop.
const iosPresent = existsSync(CANONICAL);
const d = iosPresent ? describe : describe.skip;

d("a draw is a result on iOS", () => {
  const canonical = () => readFileSync(CANONICAL, "utf8");
  const detail = () => readFileSync(join(IOS_ROOT, "Views/EventDetailView.swift"), "utf8");
  const card = () => readFileSync(join(IOS_ROOT, "Components/EventCardView.swift"), "utf8");
  const models = () => readFileSync(join(IOS_ROOT, "Models/EventModels.swift"), "utf8");

  it("the canonical outcome exists and can say all three things", () => {
    const code = canonical();

    expect(code).toMatch(/case draw/);
    expect(code).toMatch(/case undecided/);
    expect(code).toMatch(
      /static func resolve\(\s*status: String\?,\s*homeScore: Int\?,\s*awayScore: Int\?,\s*servedResult: String\? = nil\s*\) -> EventOutcome/
    );
    expect(code).toMatch(/func won\(isAway: Bool\) -> Bool/);
    expect(code).toMatch(/func isLoser\(isAway: Bool\) -> Bool/);
    expect(code).toMatch(/var drawLabel: String\?/);
  });

  /**
   * The `?? 0` trap in reverse. Without this guard the honest-looking rule
   * "equal scores ⇒ draw" newly prints **Draw** on every settled row we hold no
   * score for, because `nil ?? 0 == nil ?? 0`. The `guard` is load-bearing and
   * is pinned as text, not just as behaviour.
   */
  it("a missing score can never become a goalless draw", () => {
    expect(stripComments(canonical())).toMatch(
      /guard let homeScore, let awayScore else \{ return \.undecided \}/
    );
  });

  it("the served verdict reaches the model and is what the hero asks with", () => {
    expect(models()).toMatch(/let heroSettledResult: String\?/);
    // …and the hero passes it, rather than decoding it and ignoring it, which
    // is the shape the web was in on the day this was filed.
    expect(stripComments(detail())).toMatch(
      /EventOutcome\.resolve\([\s\S]{0,240}servedResult: event\.heroSettledResult/
    );
  });

  it("the hero prints the draw's own word instead of the bare status", () => {
    const code = stripComments(detail());

    // The verdict slot asks the outcome, and the draw arm comes FIRST — before
    // the `{Team} Win` arm, which cannot name a side on a level result.
    expect(code).toMatch(/if let drawLabel = outcome\.drawLabel \{/);
    expect(code).toMatch(/Text\(drawLabel\)/);

    // "Final" survives, but only for the state that has no verdict to print.
    expect(code).toMatch(/outcome == \.undecided[\s\S]{0,120}Text\("Final"\)/);
  });

  it("the hero's grey is the LOSER's, not everyone-who-did-not-win's", () => {
    const code = stripComments(detail());

    expect(code).toMatch(
      /func winnerColor\(isAway: Bool, event: EventDetail\) -> Color \{[\s\S]{0,400}isLoser\(isAway: isAway\)/
    );
    // The mutant this kills: `won(isAway:)` reads almost the same and is wrong
    // on exactly the case the issue is about.
    expect(code).not.toMatch(
      /func winnerColor\(isAway: Bool, event: EventDetail\) -> Color \{[\s\S]{0,400}\.won\(isAway:/
    );
  });

  it("the card exempts the draw from BOTH of its dim treatments", () => {
    const code = stripComments(card());

    expect(code).toMatch(/EventOutcome\.resolve\(/);
    // the team NAME
    expect(code).toMatch(/isFinished && outcome != \.draw \? \.secondary : \.primary/);
    // the SCORE — a suspended row keeps its dim, so the draw is the one arm
    // that moves; asserting the whole expression is what pins that.
    expect(code).toMatch(
      /isLive \? \.primary : \(won \|\| outcome == \.draw \? \.primary : \.secondary\)/
    );
  });

  it("no Swift file in the app decides a winner for itself — discovered, not listed", () => {
    const offenders: string[] = [];

    for (const path of swiftFiles(IOS_ROOT)) {
      if (path === CANONICAL) continue;
      const code = stripComments(readFileSync(path, "utf8"));

      for (const [index, line] of code.split("\n").entries()) {
        if (RE_DERIVES_THE_VERDICT.test(line)) {
          offenders.push(`${path.slice(IOS_ROOT.length + 1)}:${index + 1} — ${line.trim()}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  /**
   * The scan above passes on an empty codebase and on a typo'd regex alike, so
   * it is run against the lines that actually shipped the defect
   * (`EventCardView.swift:37-38` and `EventDetailView.swift:670` at master
   * `8ec73a3f`). A control validates the PREDICATE here, not merely the call.
   *
   * WHAT THE SCAN CANNOT SEE, stated rather than papered over: the hero's
   * `winnerColor` copied the two scores into locals first
   * (`let away = event.awayScore ?? 0`) and compared BARE names on a later line
   * — `return away > home ? .primary : .secondary` — which carries no `Score`
   * token and matches nothing here. A line-wise scan cannot follow that, and
   * widening the tell to any `a > b` would match arithmetic across the app. The
   * hero's site is pinned by name instead, two tests above; the scan's job is
   * to stop a THIRD copy appearing in a file nobody is watching.
   */
  it("the scan fires on the code that shipped the bug", () => {
    const preFix = [
      `    private var awayWon: Bool { isFinished && (event.awayScore ?? 0) > (event.homeScore ?? 0) }`,
      `    private var homeWon: Bool { isFinished && (event.homeScore ?? 0) > (event.awayScore ?? 0) }`,
      `        let homeWon = (event.homeScore ?? 0) > (event.awayScore ?? 0)`,
      `        if event.homeScore > event.awayScore { return .home }`,
    ];

    for (const line of preFix) {
      expect(RE_DERIVES_THE_VERDICT.test(line)).toBe(true);
    }
  });

  /**
   * …and does NOT fire on a score merely being PRINTED, which is what most of
   * the `?? 0` hits in the tree are. Checked rather than assumed: a tell that
   * matches every score render would have to be suppressed with an allowlist,
   * and an allowlist hands the claim to the first case nobody listed.
   */
  it("the scan does not fire on a score being rendered or formatted", () => {
    const legitimate = [
      `                        Text("\\(event.awayScore ?? 0)")`,
      `                    let score = "\\(away) \\(best.awayScore ?? 0) - \\(home) \\(best.homeScore ?? 0)"`,
      `        homeScore: lastEspn?.homeScore ?? event.homeScore,`,
      `        let away = event.awayScore ?? 0`,
    ];

    for (const line of legitimate) {
      expect(RE_DERIVES_THE_VERDICT.test(line)).toBe(false);
    }
  });
});
