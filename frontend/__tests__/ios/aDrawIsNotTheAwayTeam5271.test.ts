/**
 * #5271 — the iOS event page printed `1 − P(home)` under the away crest, and
 * on a three-outcome market that figure is *away win **or** draw*, asserted by
 * reading the Swift.
 *
 * Photographed on production 2026-09-11, event `15304603` (Al-Faisaly KSA FC v
 * Al-Ittihad, live 0–2). `win_probability_sources` held one entry —
 * `{"kalshi": {"value": 0.01}}` — so both of these came from the same price:
 *
 * | where | Al-Ittihad | Tie | Al-Faisaly |
 * |---|---|---|---|
 * | hero, top of page | **99%** | — | 1% |
 * | Other Markets card, same page | **93%** | 5% | 1% |
 *
 * The reader scrolls two cards and the favourite loses six points. Alex found
 * the same 99% a third time in the goal-margin map's header. Mid-game at 0–2
 * the draw is nearly dead so the error is ~6pp; pre-match a league draw prices
 * around 20–30%, and every scheduled soccer fixture the app renders is hit.
 *
 * There is nowhere to read a real away price from — the event payload's away
 * field IS the complement, `win_prob_snapshots.draw_probability` is NULL on all
 * 3,084,750 rows, and the three-way groups on `game-markets` are not fit to
 * print (#5328) — so `Utilities/DrawPricedWinner.swift` withholds the slot
 * instead of filling it. The full measurement is in that file's docstring.
 *
 * WHY THIS FILE EXISTS AND `DrawPricedWinnerTests.swift` DOES NOT SUFFICE.
 * The Swift suite proves the rule. It cannot prove the VIEWS obey it: all six
 * call sites are expressions inside SwiftUI bodies, invisible to XCTest.
 * Reverting any one of them to `1 - homeProb` leaves every Swift test green.
 * These assertions kill those mutants, and they run in CI, which compiles no
 * Swift at all (#4302).
 *
 * SCOPE, and it is deliberately the EVENT PAGE. The feed and search cards draw
 * the same complement from the same served field and are #5335, not this ship:
 * they are a different surface with its own card-family rules (notice 35), and
 * `IOS_CARD_SURFACES` below is asserted to still hold the old idiom so that
 * this file records the boundary rather than leaving it to be rediscovered.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Utilities/DrawPricedWinner.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/**
 * The tell, in two halves, because the six pre-fix sites did not all name the
 * number they were subtracting from:
 *
 *  - a complement built off something CALLED home (`1 - homeProb`,
 *    `1 - $0.homeProbability`), and
 *  - a complement assigned to something called AWAY, whatever the subtrahend is
 *    named. `OddsChartView` wrote `awayProb: 1.0 - nearest.probability`, which
 *    the first half misses entirely — caught by the positive control below,
 *    which is the reason that control lists all four literals rather than one.
 *
 * Both match the SHAPE, not a spelling, because the bug is "this view decided
 * the away number itself".
 */
const DERIVES_A_COMPLEMENT =
  /(1(\.0)?\s*-\s*[\w.$]*[hH]ome[\w.]*)|([aA]way\w*\s*[:=]\s*\(?\s*1(\.0)?\s*-\s*)/;

/**
 * Blank out every `DrawPricedWinner.…(…)` call before sweeping, counting
 * parens so a nested call cannot end the span early.
 *
 * The complement has to be WRITTEN somewhere — the rule's whole job is to be
 * handed the number a two-way surface would have printed and to decide whether
 * it may be printed. `away: 1 - entry.homeProbability` inside a `printablePair`
 * call is the fix, not the defect, and a sweep that cannot tell those apart
 * would have to be deleted the first time someone read it.
 */
function withoutRuleCalls(source: string): string {
  let out = "";
  let i = 0;
  for (;;) {
    const at = source.indexOf("DrawPricedWinner.", i);
    if (at === -1) return out + source.slice(i);
    const open = source.indexOf("(", at);
    if (open === -1) return out + source.slice(i);
    let depth = 0;
    let j = open;
    for (; j < source.length; j++) {
      if (source[j] === "(") depth++;
      else if (source[j] === ")" && --depth === 0) break;
    }
    // Keep the newlines so the surviving lines still read as themselves.
    out += source.slice(i, at) + source.slice(at, j).replace(/[^\n]/g, "");
    i = j;
  }
}

// A path typo would otherwise read as a clean pass — the unrunnable-check
// failure mode this whole file exists to stop.
const iosPresent = existsSync(CANONICAL);
const d = iosPresent ? describe : describe.skip;

d("a draw is not the away team on iOS", () => {
  const canonical = () => readFileSync(CANONICAL, "utf8");
  const detail = () =>
    readFileSync(join(IOS_ROOT, "Views/EventDetailView.swift"), "utf8");
  const map = () =>
    readFileSync(join(IOS_ROOT, "Components/MarketMapView.swift"), "utf8");
  const chart = () =>
    readFileSync(join(IOS_ROOT, "Components/OddsChartView.swift"), "utf8");
  const playCard = () =>
    readFileSync(join(IOS_ROOT, "Components/GamePlayCardView.swift"), "utf8");
  const vocab = () =>
    readFileSync(join(IOS_ROOT, "Utilities/SportVocab.swift"), "utf8");

  /** The tell has to actually fire on the code that shipped the bug. */
  it("the complement tell matches the four pre-fix lines", () => {
    for (const line of [
      "awayProb: 1.0 - homeProb,",
      "probabilities: (away: 1 - homeProbability, home: homeProbability),",
      "[formatProbability(1 - $0.homeProbability), formatProbability($0.homeProbability)]",
      "awayProb: 1.0 - nearest.probability,",
    ]) {
      expect(line).toMatch(DERIVES_A_COMPLEMENT);
    }
    // …and does not fire on the fixed shape, which names the rule.
    expect("home: homeProbability, sport: event.sport").not.toMatch(
      DERIVES_A_COMPLEMENT
    );
  });

  it("the canonical rule exists and answers the three questions", () => {
    const code = canonical();

    expect(code).toMatch(/enum DrawPricedWinner/);
    expect(code).toMatch(
      /static func sportPricesADraw\(_ sportKey: String\?\) -> Bool/
    );
    expect(code).toMatch(
      /static func printablePair\([\s\S]{0,200}\) -> \(away: Double\?, home: Double\)\?/
    );
    expect(code).toMatch(
      /static func headlineSide\([\s\S]{0,200}\) -> \(isHome: Bool, probability: Double\)\?/
    );
    expect(code).toMatch(
      /static func trendSubject\([\s\S]{0,160}\) -> \(isHome: Bool, signedPoints: Int\)/
    );
  });

  /**
   * The gate is DECLARED per sport, never sniffed out of a key at the call
   * site. A second copy of "is this soccer" is a second thing to get wrong,
   * and the soccer key list already exists once in `SportVocab`.
   */
  it("exactly one sport declares a draw-priced winner market", () => {
    const code = vocab();
    expect(code).toMatch(/let winnerMarketPricesADraw: Bool/);

    const yeses = code.match(/winnerMarketPricesADraw: true/g) ?? [];
    expect(yeses).toHaveLength(1);

    // …and it is the soccer row that says it. The `true` has to sit inside the
    // entry whose key list starts with "soccer", not in a neighbour.
    expect(code).toMatch(
      /\["soccer",[\s\S]{0,600}?winnerMarketPricesADraw: true\)\)/
    );

    // Every other declared row, and the undeclared default, say no.
    const nos = code.match(/winnerMarketPricesADraw: false/g) ?? [];
    expect(nos).toHaveLength(6);

    // The rule reads the fact rather than re-deriving it from the key.
    expect(stripComments(canonical())).toMatch(
      /SportVocab\.forSport\(sportKey\)\.winnerMarketPricesADraw/
    );
  });

  /**
   * THE HERO. The duel's guard goes through the rule, and the withheld arm
   * names its subject — a lone number centred between two crests belongs to
   * neither, so dropping the name would re-open the misattribution from the
   * other direction.
   */
  it("the hero asks the rule and names the side it keeps", () => {
    const code = stripComments(detail());

    expect(code).toMatch(
      /else if let odds = event\.currentOdds,[\s\S]{0,200}DrawPricedWinner\.printablePair\([\s\S]{0,200}sport: event\.sport\)/
    );
    // The withheld arm: a named short pair, then the one number.
    expect(code).toMatch(
      /if let away = pair\.away \{[\s\S]{0,2400}\} else \{[\s\S]{0,900}TeamShortName\.shortPair\([\s\S]{0,120}\)[\s\S]{0,400}Text\(named\.home\)/
    );
  });

  /** Both "Opened …" captions, settled and live, go through the same rule. */
  it("both opening-line captions withhold the same slot", () => {
    const code = stripComments(detail());
    const opened =
      code.match(
        /DrawPricedWinner\.printablePair\(\s*away: event\.openingOdds\?\.awayProbability,\s*home: event\.openingOdds\?\.homeProbability,\s*sport: event\.sport\)/g
      ) ?? [];
    expect(opened).toHaveLength(2);

    // Neither caption reads the opening pair straight off the model any more.
    expect(code).not.toMatch(
      /let awayOpeningProbability = event\.openingOdds\?\.awayProbability/
    );
    expect(code).not.toMatch(/let awayOpen = opening\.awayProbability/);
  });

  /**
   * THE TREND CAPTION. #1830 named the RISER and always printed a gain, which
   * is only sound while `away == 1 − home`. A draw breaks that identity, so
   * who to name is the rule's call and the sign survives.
   */
  it("the since-open caption asks the rule who moved", () => {
    const code = stripComments(detail());

    expect(code).toMatch(
      /DrawPricedWinner\.trendSubject\(\s*homeDelta: home - openingHome, sport: event\.sport\s*\)/
    );
    // The old unconditional "+" is gone: the caption can print a minus.
    expect(code).not.toMatch(/Text\("\\\(subject\) \+\\\(points\)% since open"\)/);
    expect(code).toMatch(/trend\.signedPoints < 0/);
  });

  /** THE SOURCES CARD — the per-source rows, and the column they are sized in. */
  it("each source row withholds its away number and its width", () => {
    const code = stripComments(detail());

    // The row's away side is optional all the way through.
    expect(code).toMatch(/probabilities: \(away: Double\?, home: Double\)/);
    expect(code).toMatch(/Text\(formatProbabilityOrDash\(probabilities\.away\)\)/);

    // The measured strings are the printed strings (a column sized against
    // "1%" and printing "—" is the mutant here).
    expect(code).toMatch(
      /values: entries\.flatMap \{[\s\S]{0,200}formatProbabilityOrDash\(printable\(\$0\)\?\.away\)/
    );

    // The bar's remainder loses the away team's COLOUR with its number.
    expect(code).toMatch(
      /awayColor: probabilities\.away == nil[\s\S]{0,120}: colors\.away/
    );
  });

  /** THE MAP HEADER — Alex's third sighting of the same 99%. */
  it("the map headline asks the rule which side it may name", () => {
    const code = stripComments(map());

    expect(code).toMatch(
      /DrawPricedWinner\.headlineSide\(\s*away: awayWinProb, home: homeWinProb, sport: sportKey\s*\)/
    );
    // The old name-the-favourite line is gone.
    expect(code).not.toMatch(/let favored = homeProbability > 0\.5/);
  });

  /** THE PLAY POINT — both of its construction sites. */
  it("the play point carries an optional away price from both writers", () => {
    expect(stripComments(playCard())).toMatch(/let awayProb: Double\?/);
    // …and the card draws the away half only when there is one.
    expect(stripComments(playCard())).toMatch(
      /if let away = point\.awayProb \{/
    );

    for (const source of [detail(), chart()]) {
      expect(stripComments(source)).toMatch(
        /awayProb: DrawPricedWinner\.printablePair\([\s\S]{0,200}\)\?\.away/
      );
    }
  });

  /**
   * NO SITE ON THE EVENT PAGE STILL BUILDS ITS OWN COMPLEMENT — every one of
   * them now hands the number to the rule instead. The sweep, and the reason
   * the tell above had to match a SHAPE: a seventh site added later fails here
   * rather than shipping the bug a seventh time.
   *
   * Exactly one complement survives outside a rule call and it is pinned as a
   * literal rather than waved through by a pattern, so a second one cannot
   * hide behind the exception. It is the source card's BAR, whose two segments
   * are a partition: "this source does not have the home team winning" is a
   * true quantity, and the neighbouring assertion above requires that segment
   * to lose the away team's colour along with its number.
   */
  it("no event-page file derives an away number from a home one", () => {
    const expected: Record<string, string[]> = {
      "EventDetailView.swift": [
        "            awayProb: probabilities.away ?? (1 - probabilities.home),",
      ],
      "MarketMapView.swift": [],
      "OddsChartView.swift": [],
      "GamePlayCardView.swift": [],
    };

    for (const [name, source] of [
      ["EventDetailView.swift", detail()],
      ["MarketMapView.swift", map()],
      ["OddsChartView.swift", chart()],
      ["GamePlayCardView.swift", playCard()],
    ] as const) {
      const offenders = withoutRuleCalls(stripComments(source))
        .split("\n")
        .filter((line) => DERIVES_A_COMPLEMENT.test(line));
      expect({ name, offenders }).toEqual({ name, offenders: expected[name] });
    }
  });

  /**
   * THE BOUNDARY, recorded rather than left to be rediscovered. The card
   * family draws the same complement off the same served field and is #5335 —
   * a separate ship under notice 35's one-card-family rule. If someone fixes
   * those, this assertion fails and they delete it, which is the point: it
   * cannot silently stop describing the app.
   */
  it("the card surfaces are knowingly still on the old reading (#5335)", () => {
    const cards = readFileSync(
      join(IOS_ROOT, "Components/EventCardView.swift"),
      "utf8"
    );
    expect(cards).toMatch(/awayProbability/);
    expect(stripComments(cards)).not.toMatch(/DrawPricedWinner/);
  });
});
