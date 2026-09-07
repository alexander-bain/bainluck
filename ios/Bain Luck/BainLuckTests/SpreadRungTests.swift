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
    ///
    /// #3743 amended the count from 2 to 1 — see
    /// ``testATwoWayHandicapDrawsTheCoverAndNotItsComplement``.
    func testUSOpenMatchDrawsAMarginMapFromTheMarketTitle() {
        let map = SpreadRungs.map(from: swiatekZheng, home: "Iga Swiatek", away: "Qinwen Zheng", sportUnit: tennisUnit)

        XCTAssertEqual(map.unit, "sets")
        XCTAssertEqual(map.rungs.count, 1, "one rung for the one readable market: the cover")

        // `Yes` is Swiatek covering -1.5 sets. Swiatek is HOME, so the rung is
        // +1.5 at the `Yes` price.
        XCTAssertEqual(map.rungs.first?.margin, 1.5)
        XCTAssertEqual(map.rungs.first?.probability, 0.585)
        XCTAssertEqual(map.rungs.first?.isHome, true)
    }

    /// The venue spells `Jovic`; the event spells `Jović`. Without accent
    /// folding the underdog's name matches nothing, `fromHandicap` bails, and
    /// this page is back to drawing no map — the exact bug, one diacritic away.
    ///
    /// 🔴 STILL LOAD-BEARING AFTER #3743, and worth saying why: Jović is the
    /// UNDERDOG here and no longer gets a rung at all. The test still bites
    /// because `fromHandicap` resolves the underdog's side as a GUARD — proof
    /// that the title names this event's two competitors — and bails when it
    /// cannot. Fold the diacritic away and this page draws nothing again.
    func testAParticipantNamedWithoutItsDiacriticStillFindsItsSide() {
        let map = SpreadRungs.map(from: gauffJovic, home: "Iva Jović", away: "Coco Gauff", sportUnit: tennisUnit)

        XCTAssertEqual(map.rungs.count, 1)
        XCTAssertEqual(map.rungs.first?.isHome, false, "Gauff is away and is the favourite")
        XCTAssertEqual(map.rungs.first?.margin, -1.5, "away by 1.5 — the sign is the SIDE, not the handicap")
        XCTAssertEqual(map.rungs.first?.probability, 0.455, "the `Yes` price, Gauff covering -1.5")
    }

    /// 🔴 THE UNDERDOG GUARD, on its own. Jović no longer gets a rung, so a
    /// mutant that deletes the underdog resolution keeps every assertion above
    /// green — and lets a title naming somebody who is not playing draw a rung
    /// on the favourite anyway.
    func testAHandicapTitleNamingANonParticipantDrawsNothing() {
        let wrongMatch = [
            SpreadRungs.Leg(marketName: "Set Handicap: Gauff (-1.5) vs Sabalenka (+1.5)", outcomeName: "Yes", probability: 0.455),
            SpreadRungs.Leg(marketName: "Set Handicap: Gauff (-1.5) vs Sabalenka (+1.5)", outcomeName: "No", probability: 0.545),
        ]
        let map = SpreadRungs.map(from: wrongMatch, home: "Iva Jović", away: "Coco Gauff", sportUnit: tennisUnit)
        XCTAssertTrue(map.rungs.isEmpty,
                      "Gauff resolves, but Sabalenka is not the other side of this match — so this title is not about this event")
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
        // One rung per admitted pair since #3743, so the counts read 1/0.
        XCTAssertEqual(sum(0.5, 0.6), 1, "1.100, the live US Open match at capture — vig, not a fault")
        XCTAssertEqual(sum(0.465, 0.5), 0, "0.965, the same match's set handicap — a 3.5% arbitrage")
        XCTAssertEqual(sum(0.5, 0.49), 1, "0.990, inside the floor")
        XCTAssertEqual(sum(0.5, 0.47), 0, "0.970, outside it")
        XCTAssertEqual(sum(0.5, 0.64), 1, "1.140, inside the ceiling")
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
        XCTAssertEqual(map.rungs.count, 1)
        XCTAssertEqual(map.rungs.first { $0.isHome }?.probability, 0.515, "Kostyuk covers -1.5 games")
        XCTAssertNil(map.rungs.first { !$0.isHome }, "Noskova's 0.485 is 1 - Kostyuk's, not a second rung")
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
        XCTAssertEqual(map.rungs.count, 1)
        XCTAssertTrue(map.rungs.allSatisfy { $0.quotedUnit == "games" })
    }

    // MARK: - #3743: one fact is drawn once

    /// 🟢 THE SHIP. A two-way handicap market draws the COVER and not its
    /// complement.
    ///
    /// Before this, `Set Handicap: Swiatek (-1.5) vs Zheng (+1.5)` produced two
    /// rungs and the card printed them as two rows of one ladder:
    ///
    /// ```
    /// Zheng   +1.5   42%
    /// Swiatek +1.5   59%
    /// ```
    ///
    /// **101%.** Not a rounding artifact — the tell. Parallel rungs on a margin
    /// ladder ("A by more than 1.5", "A by more than 2.5") are nested and sum to
    /// no more than 1 only by accident; these two summed to exactly 1 because
    /// they are COMPLEMENTS. `Zheng +1.5 42%` was `P(No)` = Zheng wins or loses
    /// 1-2, which is not "Zheng by more than 1.5" and is not what any other row
    /// of that ladder means.
    func testATwoWayHandicapDrawsTheCoverAndNotItsComplement() {
        let map = SpreadRungs.map(from: swiatekZheng, home: "Iga Swiatek", away: "Qinwen Zheng", sportUnit: tennisUnit)

        XCTAssertEqual(map.rungs.count, 1)
        let rung = try! XCTUnwrap(map.rungs.first)
        XCTAssertEqual(rung.probability, 0.585, "the `Yes` price — the favourite covering its own line")
        XCTAssertNotEqual(rung.probability, 0.415, "`No` is 1 - `Yes`, not a second reading")

        // The property the old shape broke, stated as a property: no margin map
        // may carry two rungs whose probabilities are each other's complement.
        for a in map.rungs {
            for b in map.rungs where a != b {
                XCTAssertGreaterThan(abs((a.probability + b.probability) - 1.0), 0.02,
                                     "two rungs summing to 1 are one fact drawn twice")
            }
        }
    }

    /// 🔴 THE ONE THAT KILLS "just keep whichever leg is over 50%". Event
    /// 15305797, production: home `Naomi Osaka`, away `Elena Rybakina`, and the
    /// venue writes `Rybakina (-1.5) vs Osaka (+1.5)` with `Yes` at 0.335.
    ///
    /// The surviving rung is therefore the LOWER price, and it is on the AWAY
    /// side with a negative margin. A fix that kept the bigger number would
    /// print `Osaka +1.5 67%` — the underdog's not-swept probability, drawn as
    /// though Osaka were favoured to win by two sets.
    func testTheCoverIsKeptEvenWhenItIsTheLongerPriceAndOnTheAwaySide() {
        let rybakinaOsaka = [
            SpreadRungs.Leg(marketName: "Set Handicap: Rybakina (-1.5) vs Osaka (+1.5)", outcomeName: "No", probability: 0.665),
            SpreadRungs.Leg(marketName: "Set Handicap: Rybakina (-1.5) vs Osaka (+1.5)", outcomeName: "Yes", probability: 0.335),
        ]
        let map = SpreadRungs.map(from: rybakinaOsaka, home: "Naomi Osaka", away: "Elena Rybakina", sportUnit: tennisUnit)

        XCTAssertEqual(map.rungs.count, 1)
        XCTAssertEqual(map.rungs.first?.probability, 0.335, "the cover, not the bigger number")
        XCTAssertEqual(map.rungs.first?.isHome, false, "Rybakina is away")
        XCTAssertEqual(map.rungs.first?.margin, -1.5)
    }

    /// The other two production shapes drawing a two-row ladder on 2026-09-06,
    /// so the census is on the record and not just in a comment: a `-2.5` set
    /// line whose event ALSO serves two incoherent markets that must stay
    /// refused, and a live `-0.5` GAME line (event 15304973) which is the
    /// smallest line the venue quotes.
    func testTheRemainingProductionShapesEachDrawExactlyOneRung() {
        // 15305796 — home Karen Khachanov, away Learner Tien. Only the -2.5 set
        // handicap is coherent (1.000); the -1.5 set handicap and the -2.5 game
        // spread both repeat 0.225 and sum to 0.450.
        let tienKhachanov = [
            SpreadRungs.Leg(marketName: "Set Handicap: Tien (-2.5) vs Khachanov (+2.5)", outcomeName: "No", probability: 0.775),
            SpreadRungs.Leg(marketName: "Set Handicap: Tien (-2.5) vs Khachanov (+2.5)", outcomeName: "Yes", probability: 0.225),
            SpreadRungs.Leg(marketName: "Game Spread: Tien (-2.5) vs Khachanov (+2.5)", outcomeName: "Yes", probability: 0.225),
            SpreadRungs.Leg(marketName: "Game Spread: Tien (-2.5) vs Khachanov (+2.5)", outcomeName: "No", probability: 0.225),
            SpreadRungs.Leg(marketName: "Set Handicap: Tien (-1.5) vs Khachanov (+1.5)", outcomeName: "No", probability: 0.225),
            SpreadRungs.Leg(marketName: "Set Handicap: Tien (-1.5) vs Khachanov (+1.5)", outcomeName: "Yes", probability: 0.225),
        ]
        let a = SpreadRungs.map(from: tienKhachanov, home: "Karen Khachanov", away: "Learner Tien", sportUnit: tennisUnit)
        XCTAssertEqual(a.unit, "sets")
        XCTAssertEqual(a.rungs.count, 1, "one coherent market on the event, one rung")
        XCTAssertEqual(a.rungs.first?.margin, -2.5, "Tien is away")
        XCTAssertEqual(a.rungs.first?.probability, 0.225)

        // 15304973, LIVE — home Anna Kalinskaya, away Emma Navarro. The GAME
        // spread is coherent (1.000) and is in tennis's own unit; the set
        // handicap sums to 0.715 and is refused.
        let kalinskayaNavarro = [
            SpreadRungs.Leg(marketName: "Game Spread: Kalinskaya (-0.5) vs Navarro (+0.5)", outcomeName: "Yes", probability: 0.505),
            SpreadRungs.Leg(marketName: "Game Spread: Kalinskaya (-0.5) vs Navarro (+0.5)", outcomeName: "No", probability: 0.495),
            SpreadRungs.Leg(marketName: "Set Handicap: Kalinskaya (-1.5) vs Navarro (+1.5)", outcomeName: "No", probability: 0.495),
            SpreadRungs.Leg(marketName: "Set Handicap: Kalinskaya (-1.5) vs Navarro (+1.5)", outcomeName: "Yes", probability: 0.22),
        ]
        let b = SpreadRungs.map(from: kalinskayaNavarro, home: "Anna Kalinskaya", away: "Emma Navarro", sportUnit: tennisUnit)
        XCTAssertEqual(b.unit, "games")
        XCTAssertEqual(b.rungs.count, 1)
        XCTAssertEqual(b.rungs.first?.margin, 0.5, "Kalinskaya is home; a half-game line is still a line")
        XCTAssertEqual(b.rungs.first?.probability, 0.505)
    }

    /// The PROJECTION marker does not move on any of them, which is the reason
    /// this change is narrow enough to make.
    ///
    /// `MarketMapView.closestToEvenMargin` picks the rung nearest a coin flip
    /// and `min(by:)` keeps the FIRST minimal element. Because a two-way pair
    /// sums to ~1, `|yes - 0.5|` and `|no - 0.5|` were equal-or-nearly on every
    /// one of these, so the tie always resolved to the favourite — which is the
    /// only rung left. Same margin, before and after.
    func testTheProjectionMarkerLandsOnTheSameMarginAsBefore() {
        func nearestEven(_ rungs: [SpreadRungs.Rung]) -> Double? {
            rungs.min(by: { abs($0.probability - 0.5) < abs($1.probability - 0.5) })?.margin
        }
        // What the two-rung shape produced, reconstructed by hand: favourite
        // first, underdog second, exactly as `fromHandicap` used to order them.
        let old = [
            SpreadRungs.Rung(margin: 1.5, probability: 0.585, isHome: true, quotedUnit: "sets"),
            SpreadRungs.Rung(margin: -1.5, probability: 0.415, isHome: false, quotedUnit: "sets"),
        ]
        let new = SpreadRungs.map(from: swiatekZheng, home: "Iga Swiatek", away: "Qinwen Zheng", sportUnit: tennisUnit).rungs
        XCTAssertEqual(nearestEven(old), 1.5)
        XCTAssertEqual(nearestEven(new), nearestEven(old), "the marker sat on the favourite before and still does")
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

    /// 🔴 THE PIN #3743 ASKED FOR, and the reason it is a separate test from
    /// the one above: the two constructors put DIFFERENT SEMANTICS behind one
    /// `Rung` type, and that is the root of #3743. `fromNamedOutcome`'s rungs
    /// all genuinely mean "this side wins by more than X" and are parallel;
    /// `fromHandicap`'s two used to be complementary. Narrowing the handicap
    /// path to one rung is only safe if the named path is provably untouched,
    /// so this pins the WHOLE named ladder as one value rather than
    /// field-by-field — a mutant that changes any margin, price, side or unit
    /// fails here even if it slips past the assertions above.
    ///
    /// This is as close to byte-identical as the seam allows: these four rungs
    /// are the complete input to the labels `MarketMapView` prints, and the
    /// labels themselves are unreachable without rasterising a SwiftUI view,
    /// which is the reason `SpreadRungs` was extracted in the first place.
    func testTheWholeNamedNFLLadderIsPinnedAsOneValue() {
        let map = SpreadRungs.map(from: patriotsSeahawks, home: "Seattle Seahawks", away: "New England Patriots", sportUnit: footballUnit)

        XCTAssertEqual(
            map.rungs.sorted(by: { $0.margin < $1.margin }),
            [
                SpreadRungs.Rung(margin: -4.5, probability: 0.145, isHome: false, quotedUnit: nil),
                SpreadRungs.Rung(margin: -1.5, probability: 0.145, isHome: false, quotedUnit: nil),
                SpreadRungs.Rung(margin: 1.5, probability: 0.145, isHome: true, quotedUnit: nil),
                SpreadRungs.Rung(margin: 4.5, probability: 0.145, isHome: true, quotedUnit: nil),
            ],
            "a named ladder keeps BOTH sides — #3743 narrowed the handicap path only"
        )
        XCTAssertEqual(map.unit, "points")

        // …and the two independent reasons it never reaches `fromHandicap`, so
        // a change to either one cannot silently route NFL down the new path.
        XCTAssertNil(SpreadRungs.Handicap.read(marketName: "New England vs Seattle: Spread"),
                     "no signed pair in the title")
        XCTAssertEqual(
            SpreadRungs.map(from: Array(patriotsSeahawks.prefix(2)),
                            home: "Seattle Seahawks", away: "New England Patriots", sportUnit: footballUnit).rungs.count,
            2,
            "two named legs are not a `Yes`/`No` two-way market and are not pair-collapsed")
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
