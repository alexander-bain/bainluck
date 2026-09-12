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
 * The Swift suite proves the rule. It cannot prove the VIEWS obey it: all seven
 * call sites are expressions inside SwiftUI bodies, invisible to XCTest.
 * Reverting any one of them to `1 - homeProb` leaves every Swift test green.
 * These assertions kill those mutants, and they run in CI, which compiles no
 * Swift at all (#4302).
 *
 * SCOPE, and it is deliberately the EVENT PAGE. The feed and search cards draw
 * the same complement from the same served field and are #5363, not this ship:
 * they are a different surface with its own card-family rules (notice 35). The
 * last assertion below pins `EventCardView` as still being on the old reading,
 * so this file RECORDS that boundary instead of leaving it to be rediscovered —
 * whoever fixes #5363 deletes that test, which is the point.
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

  /**
   * THE INDIVIDUAL SPORTSBOOKS TABLE, one card below the sources rows and the
   * site the first LOOK caught: `BetMGM 53% 47%` sat under an away column the
   * rows above had already emptied.
   *
   * Its away price is SERVED, not derived, so the complement sweep below can
   * never see it — the tell is that the pair sums to 100 on a match that can be
   * drawn. Withheld at display time only, so #4406's "a row is a name AND a
   * number" filter keeps taking both prices.
   */
  it("the book table withholds its away column too, without losing rows", () => {
    const code = stripComments(detail());

    expect(code).toMatch(
      /let printable = \{ \(row: NamedBookmakerRow\) in\s*DrawPricedWinner\.printablePair\(/
    );
    expect(code).toMatch(
      /\[formatProbabilityOrDash\(printable\(row\)\?\.away\),\s*formatProbability\(row\.probabilities\.home\)\]/
    );
    // #4406's filter is untouched: the row still needs BOTH prices to exist.
    expect(code).toMatch(
      /guard let key = bm\.bookmaker,[\s\S]{0,300}let probabilities = bookmakerProbabilities\(bm\)/
    );
    expect(code).toMatch(/let probabilities: \(away: Double, home: Double\)/);
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

  // ══════════════════════════════════════════════════════════════════════
  // #5363 — THE CARD FAMILY.
  //
  // The boundary test that used to sit here asserted `EventCardView` was
  // knowingly still on the old reading. It has been deleted because it stopped
  // being true, which was always its exit condition. What replaces it is the
  // same coverage the event page gets: every card site, by name.
  //
  // The rule the sites divide on, stated once so it does not have to be
  // rediscovered from the diff — WHAT REPLACES A WITHHELD AWAY NUMBER:
  //
  //  * the slot survives, as the app's em-dash, where the surface keeps a
  //    two-slot layout whose OTHER slot still attributes the survivor
  //    (`RelatedByTagView`'s "— / 55%", sitting on the same line as its
  //    "<away> @ <home>" title);
  //  * the survivor is NAMED where the pair collapses to a lone number a
  //    reader had been attributing positionally (the Discover strip, the
  //    search row, the menu-bar row, the card footer's "Opened …") — the
  //    hero's rule in #5271, for the hero's reason;
  //  * nothing is drawn where the number was already attached to its own
  //    named row (`EventCardView`'s per-team rows, the widget's team rows,
  //    `TeamDetailView`, the share image's away crest);
  //  * and the BAR keeps its remainder everywhere, minus the away team's
  //    colour, because a partition's other half is a true quantity.
  // ══════════════════════════════════════════════════════════════════════

  const card = (p: string) => () => readFileSync(join(IOS_ROOT, p), "utf8");
  const eventCard = card("Components/EventCardView.swift");
  const discoverCard = card("Components/DiscoverEventCard.swift");
  const relatedCard = card("Components/RelatedByTagView.swift");
  const searchView = card("Views/SearchView.swift");
  const menuBar = card("Views/MenuBarView.swift");
  const teamDetail = card("Views/TeamDetailView.swift");
  const shareCard = card("Utilities/ShareCardRenderer.swift");
  const percents = card("Utilities/RenderedPercent.swift");
  const widgetClient = () =>
    readFileSync(join(IOS_ROOT, "../BainLuckWidget/WidgetAPIClient.swift"), "utf8");
  const widgetView = () =>
    readFileSync(join(IOS_ROOT, "../BainLuckWidget/LiveGamesWidget.swift"), "utf8");
  const widgetModels = () =>
    readFileSync(join(IOS_ROOT, "../BainLuckWidget/WidgetModels.swift"), "utf8");

  /**
   * THE STACKED CARD. Its two numbers live in per-team rows, so the withheld
   * side simply renders nothing — and it asks `sportPricesADraw` rather than
   * `printablePair` ON PURPOSE: the pair rule answers `nil` for a two-way sport
   * holding no away price, which would newly blank the HOME number on a card
   * that has always printed it alone. That regression is the mutant here.
   */
  it("the stacked card withholds only the away side, per row", () => {
    const code = stripComments(eventCard());

    expect(code).toMatch(
      /private var awayIsWithheld: Bool \{\s*DrawPricedWinner\.sportPricesADraw\(event\.sport\)/
    );
    // Both per-side readers gate the AWAY branch and neither touches home.
    expect(code).toMatch(
      /side == \.home\s*\?\s*event\.currentOdds\?\.homeProbability\s*:\s*\(awayIsWithheld \? nil : event\.currentOdds\?\.awayProbability\)/
    );
    expect(code).toMatch(
      /side == \.home\s*\?\s*opening\?\.homeProbability\s*:\s*\(awayIsWithheld \? nil : opening\?\.awayProbability\)/
    );
    // Both bars keep the remainder and drop the colour.
    const neutralised =
      code.match(/awayIsWithheld\s*\r?\n?\s*\?\s*Color\.secondary\.opacity\(0\.25\)/g) ??
      code.match(/awayIsWithheld \? Color\.secondary\.opacity\(0\.25\)/g) ??
      [];
    expect(
      (code.match(/Color\.secondary\.opacity\(0\.25\)/g) ?? []).length
    ).toBe(2);
    expect(neutralised.length).toBeGreaterThan(0);
  });

  /**
   * THE FOOTER, and its emptiness mirror. `hasContent` has to agree with
   * `footerRow` on BOTH arms now: home-alone is content on a draw-priced sport
   * and is not on any other. A `hasContent` that ignored the sport would leave
   * the 8pt dead strip #4094 removed, on soccer only.
   */
  it("the footer's caption and its emptiness gate move together", () => {
    const code = stripComments(eventCard());

    expect(code).toMatch(/sport: String\?\s*\)\s*-> Bool/);
    expect(code).toMatch(
      /return awayOpening != nil \|\| DrawPricedWinner\.sportPricesADraw\(sport\)/
    );
    // The caption itself goes through the rule and names its survivor.
    expect(code).toMatch(
      /if isLive, let opened = DrawPricedWinner\.printablePair\(/
    );
    expect(code).toMatch(
      /Text\("Opened \\\(named\.home\) \\\(formatProbability\(opened\.home\)\)"\)/
    );
  });

  /** THE DISCOVER STRIP — the pair collapses, so the survivor is named. */
  it("the discover strip asks the rule and names the side it keeps", () => {
    const code = stripComments(discoverCard());

    expect(code).toMatch(
      /let printable = DrawPricedWinner\.printablePair\([\s\S]{0,200}sport: event\.sport\)/
    );
    expect(code).toMatch(/if let awayProbability = printable\.away \{/);
    // The withheld arm names the home side beside its number.
    expect(code).toMatch(
      /\} else \{[\s\S]{0,600}Text\(cardSides\.home\)[\s\S]{0,300}Text\(formatProbability\(homeProbability\)\)/
    );
    // The bar is told, explicitly, rather than inferring from a colour.
    expect(code).toMatch(/awayIsWithheld: printable\.away == nil/);
    expect(code).toMatch(
      /awayIsWithheld \? Color\.secondary\.opacity\(0\.25\) : awayColor/
    );
  });

  /**
   * THE SHARE SENTENCE AND THE SHARE IMAGE — the two artefacts that leave the
   * app, where there is no page underneath to check a number against.
   */
  it("neither shared artefact carries the complement", () => {
    const cardCode = stripComments(discoverCard());
    const renderer = stripComments(shareCard());

    // The sentence: a withheld away side makes this half a duel, and half a
    // duel already quotes no number.
    expect(cardCode).toMatch(
      /let awayPercent = DrawPricedWinner\.sportPricesADraw\(event\.sport\) \? nil : duel\[0\]/
    );
    expect(cardCode).toMatch(/awayPercent: awayPercent,/);

    // The image: an OPTIONAL away probability, no default on the entry point.
    expect(renderer).toMatch(/let awayProbability: Double\?/);
    expect(renderer).toMatch(/awayProbability: Double\?,\s*\n\s*sportName: String,/);
    expect(renderer).toMatch(/if let awayProbability \{/);
    // …and the card hands it the rule's answer, not the served field.
    expect(cardCode).toMatch(/awayProbability: printable\.away,/);
  });

  /** THE COMPACT PAIR — the slot survives as the app's absent marker. */
  it("the related-by-tag row dashes the slot rather than collapsing it", () => {
    const code = stripComments(relatedCard());

    expect(code).toMatch(
      /let printable = DrawPricedWinner\.printablePair\([\s\S]{0,200}sport: data\.sport\)/
    );
    expect(code).toMatch(/formatProbabilityOrDash\(printable\.away, renderedPercent: awayPct\)/);
  });

  /**
   * THE SEARCH ROW — the densest copy of the defect, because a lone number has
   * no second number beside it to look wrong against. The helper moves the
   * reading to HOME and the row NAMES it; the two-way arm is byte-identical.
   */
  it("the search row's lone number changes sides and gains a name", () => {
    const helper = stripComments(percents());
    const view = stripComments(searchView());

    expect(helper).toMatch(
      /sport sportKey: String\?\s*\)\s*-> \(probability: Double, percent: Int, isHome: Bool\)\?/
    );
    expect(helper).toMatch(
      /if DrawPricedWinner\.sportPricesADraw\(sportKey\) \{[\s\S]{0,240}isHome: true\)/
    );
    // No default on the sport, or a call site can silently keep the old reading.
    expect(helper).not.toMatch(/sport sportKey: String\? = nil/);

    expect(view).toMatch(/sport: event\.sport/);
    expect(view).toMatch(
      /if firstNamed\.isHome \{[\s\S]{0,400}TeamShortName\.shortPair\([\s\S]{0,140}\)\.home/
    );
  });

  /** THE MENU BAR and THE WIDGET — the two surfaces that derive `1 − home`. */
  it("the menu bar and the widget both gate their derived away number", () => {
    const menu = stripComments(menuBar());
    const client = stripComments(widgetClient());
    const view = stripComments(widgetView());
    const models = stripComments(widgetModels());

    expect(menu).toMatch(/let awayProb: Int\?/);
    expect(menu).toMatch(
      /let printable = DrawPricedWinner\.printablePair\([\s\S]{0,200}sport: event\.sport\s*\)/
    );
    expect(menu).toMatch(/awayProb: printableAwayPct,/);
    expect(menu).toMatch(/Text\("\\\(game\.homeAbbrev\) \\\(game\.homeProb\)"\)/);

    // The widget is a STANDALONE TARGET and shares the rule rather than
    // transcribing it — the membership exception is asserted below.
    expect(client).toMatch(
      /let awayIsWithheld = DrawPricedWinner\.sportPricesADraw\(event\.sport\)/
    );
    expect(client).toMatch(/awayProb: awayIsWithheld \? nil :/);
    expect(models).toMatch(/let awayProb: Int\?/);
    // "Who leads" is unanswerable with one price, so neither side claims it.
    expect(models).toMatch(/var awayIsLeading: Bool \{\s*guard let awayProb else \{ return false \}/);
    expect(models).toMatch(/var homeIsLeading: Bool \{\s*guard let awayProb else \{ return false \}/);
    expect(view).not.toMatch(/game\.awayProb > game\.homeProb/);
    expect(view).not.toMatch(/game\.homeProb > game\.awayProb/);
  });

  /**
   * The widget can only call the rule because the rule is a MEMBER of its
   * target. Xcode 16 file-system-synchronized groups mean membership is the
   * pbxproj exception set and nothing else, so this is the assertion that the
   * `DrawPricedWinner` call above is not a build error waiting to happen —
   * and CI compiles no Swift, so nothing else would catch it.
   */
  it("the widget target actually contains the rule it calls", () => {
    const pbxproj = readFileSync(
      join(IOS_ROOT, "../Bain Luck.xcodeproj/project.pbxproj"),
      "utf8"
    );
    const widgetExceptions = pbxproj.match(
      /Exceptions for "Bain Luck" folder in "BainLuckWidget" target \*\/ = \{[\s\S]*?\};/
    );
    expect(widgetExceptions).not.toBeNull();
    expect(widgetExceptions![0]).toMatch(/Utilities\/DrawPricedWinner\.swift,/);
    expect(widgetExceptions![0]).toMatch(/Utilities\/SportVocab\.swift,/);
  });

  /** THE TEAM PAGE — a site the issue's own grep missed. */
  it("a team's own page stops inventing its away-fixture number", () => {
    const code = stripComments(teamDetail());

    expect(code).toMatch(
      /: DrawPricedWinner\.printablePair\(\s*away: 1 - homeProb, home: homeProb, sport: event\.sport\)\?\.away/
    );
    // The old unconditional complement is gone.
    expect(code).not.toMatch(/let prob = isHome \? homeProb : \(1 - homeProb\)/);
  });

  /**
   * THE SWEEP, over the whole card family this time. Same shape as the
   * event-page sweep above and same reason: an eleventh site added later fails
   * here rather than shipping the bug an eleventh time.
   *
   * Every survivor is pinned as a literal. Each is either a BAR REMAINDER (a
   * partition's other half, which the assertions above require to be drawn in
   * the neutral colour) or a value handed to `duelPercents`/the rule itself —
   * never a number printed under an away crest.
   */
  it("no card-family file prints an away number it derived itself", () => {
    const expected: Record<string, string[]> = {
      "EventCardView.swift": [],
      "SearchView.swift": [],
      "TeamDetailView.swift": [],
      "RenderedPercent.swift": [],
      "LiveGamesWidget.swift": [],
      "DiscoverEventCard.swift": [
        "                        away: printable.away ?? (1 - homeProbability),",
        "                            awayProbability: printable.away ?? (1 - homeProbability),",
      ],
      "RelatedByTagView.swift": [
        "                    away: printable.away ?? (1 - homeProbability),",
      ],
      "MenuBarView.swift": [
        "                let awayProbability = 1.0 - homeProbability",
      ],
      "ShareCardRenderer.swift": [
        "    private var awayBarShare: Double { awayProbability ?? (1 - homeProbability) }",
      ],
      "WidgetAPIClient.swift": [
        "            let awayProbability = 1.0 - homeProbability",
      ],
    };

    for (const [name, source] of [
      ["EventCardView.swift", eventCard()],
      ["DiscoverEventCard.swift", discoverCard()],
      ["RelatedByTagView.swift", relatedCard()],
      ["SearchView.swift", searchView()],
      ["MenuBarView.swift", menuBar()],
      ["TeamDetailView.swift", teamDetail()],
      ["ShareCardRenderer.swift", shareCard()],
      ["RenderedPercent.swift", percents()],
      ["WidgetAPIClient.swift", widgetClient()],
      ["LiveGamesWidget.swift", widgetView()],
    ] as const) {
      const offenders = withoutRuleCalls(stripComments(source))
        .split("\n")
        .filter((line) => DERIVES_A_COMPLEMENT.test(line));
      expect({ name, offenders }).toEqual({ name, offenders: expected[name] });
    }
  });
});
