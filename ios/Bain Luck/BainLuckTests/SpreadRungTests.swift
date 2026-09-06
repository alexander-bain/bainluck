import XCTest
@testable import Bain_Luck

/// native/040 — #3552 / #3533 / #3568, one job.
///
/// **What a reader saw.** On every US Open match page: no margin map. Not an
/// empty one, not a wrong one — absent — while the books' game spread and set
/// handicap sat in the payload the page had already fetched.
/// `artifacts-native-037/RIG-scroll800-15305580.png` and `-scroll1600-` are the
/// whole of Swiatek–Zheng below the hero: chart, "Projected scoring",
/// Additional Markets, end of page.
///
/// **Why.** `MarketMapView.parseSprOutcome` looked for a team's name inside the
/// OUTCOME name. Tennis names every spread outcome `Yes` or `No`.
///
/// **Why it could not be fixed on its own.** The moment the parser reads the
/// market name, three things that were latent become visible at once, and each
/// of them is a falsehood on a card:
///
/// 1. **#3533** — `Set Handicap: Swiatek (-1.5)` (SETS) and `Game Spread:
///    Swiatek (-5.5)` (GAMES) both start parsing onto one rail whose width is
///    `vocab.marginRange` = ±6 **games**.
/// 2. **#3555** — the served legs contradict themselves, and a density built
///    from them is a picture of our bug wearing the books' name.
/// 3. **#3568** — the side test was a substring match that resolved ties to
///    home, so on a game whose teams share a word every rung of both teams
///    landed on the home side.
///
/// Every fixture below is a VERBATIM production payload, captured 2026-09-06
/// from `GET /api/events/{id}/game-markets`, with the event's own `home_team` /
/// `away_team`. The numbers are not illustrative.
final class SpreadRungTests: XCTestCase {

    private let tennisUnit = SportVocab.forSport("tennis_wta_us_open").unit   // "games"
    private let footballUnit = SportVocab.forSport("americanfootball_nfl").unit // "points"

    // MARK: - Fixtures (production, 2026-09-06)

    /// Event 15305580, `tennis_wta_us_open`, `scheduled`.
    /// home `Iga Swiatek`, away `Qinwen Zheng`.
    private let swiatekZheng = [
        SpreadRungs.Leg(marketName: "Set Handicap: Swiatek (-1.5) vs Zheng (+1.5)", outcomeName: "Yes", probability: 0.585),
        SpreadRungs.Leg(marketName: "Set Handicap: Swiatek (-1.5) vs Zheng (+1.5)", outcomeName: "No", probability: 0.415),
        SpreadRungs.Leg(marketName: "Game Spread: Swiatek (-5.5) vs Zheng (+5.5)", outcomeName: "No", probability: 0.415),
        SpreadRungs.Leg(marketName: "Game Spread: Swiatek (-5.5) vs Zheng (+5.5)", outcomeName: "Yes", probability: 0.415),
    ]

    /// Event 15304906, `tennis_wta_us_open`, `scheduled`.
    /// home `Marta Kostyuk`, away `Linda Noskova`. The mirror image of
    /// Swiatek–Zheng: here the GAME spread is the coherent market and the set
    /// handicap is the broken one.
    private let kostyukNoskova = [
        SpreadRungs.Leg(marketName: "Game Spread: Kostyuk (-1.5) vs Noskova (+1.5)", outcomeName: "Yes", probability: 0.515),
        SpreadRungs.Leg(marketName: "Game Spread: Kostyuk (-1.5) vs Noskova (+1.5)", outcomeName: "No", probability: 0.485),
        SpreadRungs.Leg(marketName: "Set Handicap: Kostyuk (-1.5) vs Noskova (+1.5)", outcomeName: "No", probability: 0.485),
        SpreadRungs.Leg(marketName: "Set Handicap: Kostyuk (-1.5) vs Noskova (+1.5)", outcomeName: "Yes", probability: 0.345),
    ]

    /// Event 15305728. home `Iva Jović`, away `Coco Gauff` — and the venue
    /// writes the market name without the diacritic.
    private let gauffJovic = [
        SpreadRungs.Leg(marketName: "Set Handicap: Gauff (-1.5) vs Jovic (+1.5)", outcomeName: "No", probability: 0.545),
        SpreadRungs.Leg(marketName: "Set Handicap: Gauff (-1.5) vs Jovic (+1.5)", outcomeName: "Yes", probability: 0.455),
        SpreadRungs.Leg(marketName: "Game Spread: Gauff (-3.5) vs Jovic (+3.5)", outcomeName: "Yes", probability: 0.455),
        SpreadRungs.Leg(marketName: "Game Spread: Gauff (-3.5) vs Jovic (+3.5)", outcomeName: "No", probability: 0.455),
    ]

    /// Event 14780138, `americanfootball_nfl`. home `Seattle Seahawks`, away
    /// `New England Patriots`. THE CONTROL — the shape that has always worked
    /// and must not move.
    private let patriotsSeahawks = [
        SpreadRungs.Leg(marketName: "New England vs Seattle: Spread", outcomeName: "Seattle wins by over 1.5 points", threshold: 1.5, probability: 0.145),
        SpreadRungs.Leg(marketName: "New England vs Seattle: Spread", outcomeName: "New England wins by over 1.5 points", threshold: 1.5, probability: 0.145),
        SpreadRungs.Leg(marketName: "New England vs Seattle: Spread", outcomeName: "Seattle wins by over 4.5 points", threshold: 4.5, probability: 0.145),
        SpreadRungs.Leg(marketName: "New England vs Seattle: Spread", outcomeName: "New England wins by over 4.5 points", threshold: 4.5, probability: 0.145),
    ]

    // MARK: - #3552: the map appears at all

    /// 🟢 THE SHIP. Swiatek–Zheng drew nothing; it now draws the one market on
    /// the event that is internally consistent, with both players named out of
    /// the market title and the line the venue quoted.
    func testUSOpenMatchDrawsAMarginMapFromTheMarketTitle() {
        let map = SpreadRungs.map(from: swiatekZheng, home: "Iga Swiatek", away: "Qinwen Zheng", sportUnit: tennisUnit)

        XCTAssertEqual(map.unit, "sets")
        XCTAssertEqual(map.rungs.count, 2, "one rung per side of the one readable market")

        let home = map.rungs.first { $0.isHome }
        let away = map.rungs.first { !$0.isHome }
        // `Yes` is Swiatek covering -1.5 sets. Swiatek is HOME, so the rung is
        // +1.5 at the `Yes` price; `No` is Zheng at the other end of the same
        // line, at the `No` price.
        XCTAssertEqual(home?.margin, 1.5)
        XCTAssertEqual(home?.probability, 0.585)
        XCTAssertEqual(away?.margin, -1.5)
        XCTAssertEqual(away?.probability, 0.415)
    }

    /// The venue spells `Jovic`; the event spells `Jović`. Without accent
    /// folding the underdog's name matches nothing, `fromHandicap` bails, and
    /// this page is back to drawing no map — the exact bug, one diacritic away.
    func testAParticipantNamedWithoutItsDiacriticStillFindsItsSide() {
        let map = SpreadRungs.map(from: gauffJovic, home: "Iva Jović", away: "Coco Gauff", sportUnit: tennisUnit)

        XCTAssertEqual(map.rungs.count, 2)
        XCTAssertEqual(map.rungs.first { $0.isHome }?.margin, 1.5, "Jović is home and takes the +1.5")
        XCTAssertEqual(map.rungs.first { $0.isHome }?.probability, 0.545)
        XCTAssertEqual(map.rungs.first { !$0.isHome }?.margin, -1.5, "Gauff is away and covers the -1.5")
        XCTAssertEqual(map.rungs.first { !$0.isHome }?.probability, 0.455)
    }

    /// A title is only read in the ONE shape the venue serves. Everything else
    /// draws nothing rather than guessing — a rung on the wrong player is worse
    /// than no rung.
    func testAHandicapTitleIsReadStrictlyOrNotAtAll() {
        XCTAssertEqual(
            SpreadRungs.Handicap.read(marketName: "Game Spread: Swiatek (-5.5) vs Zheng (+5.5)"),
            SpreadRungs.Handicap(favourite: "Swiatek", underdog: "Zheng", line: 5.5)
        )
        XCTAssertNil(SpreadRungs.Handicap.read(marketName: "Game Spread: Swiatek (-5.5) vs Zheng (+4.5)"),
                     "unequal lines are not one two-way market")
        XCTAssertNil(SpreadRungs.Handicap.read(marketName: "Game Spread: Swiatek (+5.5) vs Zheng (-5.5)"),
                     "the favourite is the side `Yes` asks about, and it is written first")
        XCTAssertNil(SpreadRungs.Handicap.read(marketName: "Winner: Swiatek (1.30) vs Zheng (3.40)"),
                     "two prices are not a handicap")
        XCTAssertNil(SpreadRungs.Handicap.read(marketName: "New England vs Seattle: Spread"),
                     "a named ladder states no line in its title")
    }

    // MARK: - #3555: a self-contradicting pair is refused

    /// 🔴 THE REASON THIS FIX IS NOT JUST A PARSER. Both legs of Swiatek's GAME
    /// spread are 0.415 — the pair sums to 0.830, which is an arbitrage no book
    /// has ever offered. Drawn, it would be two equal bars captioned as the
    /// books' opinion. The parser reads the market fine; the map refuses it.
    func testATwoWayPairThatSumsBelowOneDrawsNothing() {
        let broken = Array(swiatekZheng[2...])   // the Game Spread legs alone
        XCTAssertEqual(broken.count, 2)

        let map = SpreadRungs.map(from: broken, home: "Iga Swiatek", away: "Qinwen Zheng", sportUnit: tennisUnit)
        XCTAssertTrue(map.rungs.isEmpty, "0.415 + 0.415 = 0.830 is not a priced market")
        XCTAssertEqual(map.unit, "games", "no rungs still leaves the sport's own unit for a projection marker")
    }

    /// Both ends of the window, and the two production readings that sit
    /// nearest them: the live Sabalenka–Townsend game spread at 1.100 (a book's
    /// overround, admitted) and Sabalenka's set handicap at 0.965 (refused).
    func testTheCoherenceWindowIsPinnedAtBothEnds() {
        func sum(_ yes: Double, _ no: Double) -> Int {
            SpreadRungs.map(
                from: [
                    SpreadRungs.Leg(marketName: "Game Spread: Sabalenka (-5.5) vs Townsend (+5.5)", outcomeName: "Yes", probability: yes),
                    SpreadRungs.Leg(marketName: "Game Spread: Sabalenka (-5.5) vs Townsend (+5.5)", outcomeName: "No", probability: no),
                ],
                home: "Aryna Sabalenka", away: "Taylor Townsend", sportUnit: tennisUnit
            ).rungs.count
        }
        XCTAssertEqual(sum(0.5, 0.6), 2, "1.100, the live US Open match at capture — vig, not a fault")
        XCTAssertEqual(sum(0.465, 0.5), 0, "0.965, the same match's set handicap — a 3.5% arbitrage")
        XCTAssertEqual(sum(0.5, 0.49), 2, "0.990, inside the floor")
        XCTAssertEqual(sum(0.5, 0.47), 0, "0.970, outside it")
        XCTAssertEqual(sum(0.5, 0.64), 2, "1.140, inside the ceiling")
        XCTAssertEqual(sum(0.5, 0.66), 0, "1.160, outside it")

        // The floor and ceiling are the numbers, not whatever the constants
        // happen to say — a test that reads them back cannot fail when they move.
        XCTAssertEqual(SpreadRungs.twoWaySumFloor, 0.98)
        XCTAssertEqual(SpreadRungs.twoWaySumCeiling, 1.15)
    }

    // MARK: - #3533: sets never land on the games rail

    /// The whole of #3533 in one assertion. Swiatek's event serves a ±1.5 SET
    /// handicap and a ±5.5 GAME spread in one array; before this, both parsed
    /// and both were drawn on tennis's ±6 **games** rail, the set handicap
    /// sitting exactly where a 1.5-game spread would.
    func testASetHandicapIsNeverDrawnOnTheGamesRail() {
        let map = SpreadRungs.map(from: swiatekZheng, home: "Iga Swiatek", away: "Qinwen Zheng", sportUnit: tennisUnit)
        XCTAssertEqual(map.unit, "sets")
        XCTAssertTrue(map.rungs.allSatisfy { $0.quotedUnit == "sets" })
        XCTAssertTrue(map.rungs.allSatisfy { abs($0.margin) == 1.5 },
                      "the 5.5 GAME line is not on this map at any width")

        // …and the rail it is drawn on is not tennis's games span.
        let tennis = SportVocab.forSport("tennis_wta_us_open")
        XCTAssertEqual(tennis.marginRange, 6)
        XCTAssertNil(tennis.marginRange(quotedBy: "sets"))
        XCTAssertEqual(tennis.marginRange(quotedBy: "games"), 6)
    }

    /// 🔴 THE OTHER DIRECTION, and the one a "just drop the set handicaps" fix
    /// would fail. On Kostyuk–Noskova the GAME spread is the coherent market
    /// and the set handicap is the broken one, so the map is a GAMES map — the
    /// sport's own unit, its own ±6 rail, the behaviour every other sport has.
    func testWhereTheSportsOwnUnitIsQuotedItIsTheMapAndTheOthersAreDropped() {
        let map = SpreadRungs.map(from: kostyukNoskova, home: "Marta Kostyuk", away: "Linda Noskova", sportUnit: tennisUnit)

        XCTAssertEqual(map.unit, "games")
        XCTAssertEqual(map.rungs.count, 2)
        XCTAssertEqual(map.rungs.first { $0.isHome }?.probability, 0.515, "Kostyuk covers -1.5 games")
        XCTAssertEqual(map.rungs.first { !$0.isHome }?.probability, 0.485)
        XCTAssertEqual(SportVocab.forSport("tennis_wta_us_open").marginRange(quotedBy: map.unit), 6)
    }

    /// Both units coherent on one event: the sport's own wins outright, rather
    /// than the two being mixed or the map being withheld.
    func testWhenBothUnitsArePricedTheSportsUnitTakesTheMap() {
        let both = [
            SpreadRungs.Leg(marketName: "Game Spread: Kostyuk (-1.5) vs Noskova (+1.5)", outcomeName: "Yes", probability: 0.515),
            SpreadRungs.Leg(marketName: "Game Spread: Kostyuk (-1.5) vs Noskova (+1.5)", outcomeName: "No", probability: 0.485),
            SpreadRungs.Leg(marketName: "Set Handicap: Kostyuk (-1.5) vs Noskova (+1.5)", outcomeName: "Yes", probability: 0.62),
            SpreadRungs.Leg(marketName: "Set Handicap: Kostyuk (-1.5) vs Noskova (+1.5)", outcomeName: "No", probability: 0.38),
        ]
        let map = SpreadRungs.map(from: both, home: "Marta Kostyuk", away: "Linda Noskova", sportUnit: tennisUnit)
        XCTAssertEqual(map.unit, "games")
        XCTAssertEqual(map.rungs.count, 2)
        XCTAssertTrue(map.rungs.allSatisfy { $0.quotedUnit == "games" })
    }

    // MARK: - #3568: which side a rung is on

    /// `"san"` is inside `"kansas"`. With away = San Francisco and home =
    /// Kansas City, every Chiefs rung matched the away side too, and
    /// `isHome ? t : -t` resolved the tie to home in silence.
    func testASubstringOfOneTeamNameIsNotTheOtherTeam() {
        XCTAssertEqual(
            SpreadRungs.side(of: "Kansas City wins by over 3.5 points", home: "Kansas City Chiefs", away: "San Francisco 49ers"),
            .home
        )
        XCTAssertEqual(
            SpreadRungs.side(of: "San Francisco wins by over 3.5 points", home: "Kansas City Chiefs", away: "San Francisco 49ers"),
            .away
        )
    }

    /// A word both teams carry cannot identify either, so it is discarded from
    /// both — which is what makes `Clemson Tigers @ LSU Tigers` readable at all.
    func testASharedWordIsDiscardedSoTheDistinguishingOneStillWorks() {
        let home = "LSU Tigers", away = "Clemson Tigers"
        XCTAssertEqual(SpreadRungs.side(of: "LSU Tigers wins by over 3.5 points", home: home, away: away), .home)
        XCTAssertEqual(SpreadRungs.side(of: "Clemson Tigers wins by over 3.5 points", home: home, away: away), .away)
        XCTAssertNil(SpreadRungs.side(of: "Tigers wins by over 3.5 points", home: home, away: away),
                     "`Tigers` alone names neither, and saying so is the honest answer")
    }

    /// Event 14793422, measured: `Washington State Cougars @ Washington
    /// Huskies`. An outcome that says only "Washington" is genuinely ambiguous
    /// and is skipped — not drawn on the home side, which is what it used to be.
    func testAnAmbiguousOutcomeIsSkippedRatherThanResolvedToHome() {
        let home = "Washington Huskies", away = "Washington State Cougars"
        XCTAssertNil(SpreadRungs.side(of: "Washington wins by over 3.5 points", home: home, away: away))
        XCTAssertEqual(SpreadRungs.side(of: "Washington State wins by over 3.5 points", home: home, away: away), .away)
        XCTAssertEqual(SpreadRungs.side(of: "Washington Huskies wins by over 3.5 points", home: home, away: away), .home)
    }

    /// 🔴 THE CLAUSE THE OTHER TESTS DO NOT REACH. Discarding shared words
    /// already makes `"Washington"` resolve to neither side, so a mutant that
    /// removes `guard isHome != isAway` — restoring the silent resolve-to-home
    /// this fix exists to delete — survives every test above. It takes an
    /// outcome that names BOTH sides' distinguishing words to reach it, which
    /// is exactly what a venue writing the matchup into the outcome name gives
    /// you (`"New England vs Seattle: Spread"` is that string in the market
    /// name today, and nothing stops it appearing in the other field).
    ///
    /// Found by mutation, not by reading: this file was written believing the
    /// ambiguity test above covered it.
    func testAnOutcomeNamingBothSidesIsAmbiguousAndIsSkipped() {
        XCTAssertNil(
            SpreadRungs.side(of: "Clemson Tigers vs LSU Tigers", home: "LSU Tigers", away: "Clemson Tigers"),
            "both distinguishing words are present; there is no honest side to pick")
        XCTAssertNil(
            SpreadRungs.side(of: "New England vs Seattle", home: "Seattle Seahawks", away: "New England Patriots"))
        XCTAssertNil(
            SpreadRungs.side(of: "Washington State beats Washington Huskies",
                             home: "Washington Huskies", away: "Washington State Cougars"))
    }

    /// The other five collisions measured in the visible league windows on
    /// 2026-09-06 — `state`, `city`, `new`, `arizona` — all of which used to
    /// put both teams' rungs on the home side.
    func testTheMeasuredCollisionsAllResolveOrAbstain() {
        XCTAssertEqual(SpreadRungs.side(of: "New York City FC wins by over 1.5 goals",
                                        home: "New York City FC", away: "New England Revolution"), .home)
        XCTAssertEqual(SpreadRungs.side(of: "Manchester City wins by over 1.5 goals",
                                        home: "Manchester City", away: "Coventry City"), .home)
        XCTAssertEqual(SpreadRungs.side(of: "Northern Arizona wins by over 3.5 points",
                                        home: "Arizona Wildcats", away: "Northern Arizona Lumberjacks"), .away)
        XCTAssertEqual(SpreadRungs.side(of: "Sacramento State wins by over 3.5 points",
                                        home: "Sacramento State", away: "Mississippi Valley State"), .home)
    }

    // MARK: - The control: nothing about a named ladder moves

    /// 🔴 THE REGRESSION THAT WOULD BE WORSE THAN THE BUG. NFL is 100% named
    /// markets (16 of 16 measured) and its margin maps work. Every rung, every
    /// sign, every price, and the sport's own rail.
    func testANamedNFLLadderParsesExactlyAsItAlwaysHas() {
        let map = SpreadRungs.map(from: patriotsSeahawks, home: "Seattle Seahawks", away: "New England Patriots", sportUnit: footballUnit)

        XCTAssertEqual(map.unit, "points")
        XCTAssertEqual(map.rungs.count, 4, "a named ladder is not a two-way market and is not pair-checked")
        XCTAssertTrue(map.rungs.allSatisfy { $0.quotedUnit == nil },
                      "`New England vs Seattle: Spread` declares no unit and inherits the sport's")
        XCTAssertEqual(map.rungs.filter(\.isHome).map(\.margin).sorted(), [1.5, 4.5])
        XCTAssertEqual(map.rungs.filter { !$0.isHome }.map(\.margin).sorted(), [-4.5, -1.5])
        XCTAssertTrue(map.rungs.allSatisfy { $0.probability == 0.145 })

        XCTAssertEqual(SportVocab.forSport("americanfootball_nfl").marginRange(quotedBy: map.unit), 18)
    }

    /// A named ladder whose every rung repeats one price is #3555's shape on a
    /// sport that has always drawn — this is what NFL serves today. It is NOT
    /// refused here: a flat ladder is implausible, but unlike a two-way pair
    /// summing to 0.83 it is not self-contradicting, and suppressing every NFL
    /// margin map on a suspicion is not a fix. Pinned so the boundary of what
    /// this change does and does not refuse is on the record.
    func testAFlatNamedLadderIsDrawnBecauseItIsNotProvablyImpossible() {
        let map = SpreadRungs.map(from: patriotsSeahawks, home: "Seattle Seahawks", away: "New England Patriots", sportUnit: footballUnit)
        XCTAssertEqual(map.rungs.count, 4)
    }

    /// With nothing readable at all the map is empty — but it still reports the
    /// SPORT's unit, because a card can carry a projection marker with no rung
    /// on it and that marker is quoted in the sport's unit. Reporting "" here
    /// suppressed the margin map on every NFL event whose ladder failed to
    /// parse but whose spread was known.
    func testAnEmptyMapStillCarriesTheSportsUnit() {
        let map = SpreadRungs.map(from: [], home: "Seattle Seahawks", away: "New England Patriots", sportUnit: footballUnit)
        XCTAssertTrue(map.rungs.isEmpty)
        XCTAssertEqual(map.unit, "points")
    }
}
