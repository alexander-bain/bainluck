import XCTest
@testable import Bain_Luck

/// #8739 (iPhone half; web was PR #8746). A page priced only on Polymarket drew
/// no margin map: Polymarket writes the spread line in the MARKET name
/// (`Spread: Texas (-7.5)`), serves `threshold` null and leaves only a team in
/// each leg, and `SpreadRungs` read the number from the outcome alone.
///
/// Every fixture is a VERBATIM production row from
/// `GET /api/events/{id}/game-markets`, captured 2026-09-25/26 PDT.
final class PolymarketSpreadLineInMarketName8739Tests: XCTestCase {

    private let footballUnit = SportVocab.forSport("americanfootball_ncaaf").unit

    private func leg(_ market: String, _ outcome: String, _ p: Double) -> SpreadRungs.Leg {
        SpreadRungs.Leg(marketName: market, outcomeName: outcome, probability: p)
    }

    /// Event 14870011, `americanfootball_ncaaf`, scheduled. home `Tennessee
    /// Volunteers`, away `Texas Longhorns`. All 52 Polymarket legs.
    private var texasTennessee: [SpreadRungs.Leg] { [
        leg("Spread: Tennessee (-0.5)", "Tennessee", 0.355),
        leg("Spread: Tennessee (-0.5)", "Texas", 0.645),
        leg("Spread: Tennessee (-1.5)", "Tennessee", 0.325),
        leg("Spread: Tennessee (-1.5)", "Texas", 0.675),
        leg("Spread: Tennessee (-10.5)", "Tennessee", 0.125),
        leg("Spread: Tennessee (-10.5)", "Texas", 0.875),
        leg("Spread: Tennessee (-13.5)", "Tennessee", 0.105),
        leg("Spread: Tennessee (-13.5)", "Texas", 0.895),
        leg("Spread: Tennessee (-16.5)", "Tennessee", 0.055),
        leg("Spread: Tennessee (-16.5)", "Texas", 0.945),
        leg("Spread: Tennessee (-2.5)", "Tennessee", 0.315),
        leg("Spread: Tennessee (-2.5)", "Texas", 0.685),
        leg("Spread: Tennessee (-3.5)", "Tennessee", 0.265),
        leg("Spread: Tennessee (-3.5)", "Texas", 0.735),
        leg("Spread: Tennessee (-4.5)", "Tennessee", 0.24),
        leg("Spread: Tennessee (-4.5)", "Texas", 0.76),
        leg("Spread: Tennessee (-6.5)", "Tennessee", 0.215),
        leg("Spread: Tennessee (-6.5)", "Texas", 0.785),
        leg("Spread: Tennessee (-9.5)", "Tennessee", 0.145),
        leg("Spread: Tennessee (-9.5)", "Texas", 0.855),
        leg("Spread: Texas (-0.5)", "Tennessee", 0.355),
        leg("Spread: Texas (-0.5)", "Texas", 0.645),
        leg("Spread: Texas (-1.5)", "Tennessee", 0.38),
        leg("Spread: Texas (-1.5)", "Texas", 0.62),
        leg("Spread: Texas (-10.5)", "Tennessee", 0.685),
        leg("Spread: Texas (-10.5)", "Texas", 0.315),
        leg("Spread: Texas (-11.5)", "Tennessee", 0.7),
        leg("Spread: Texas (-11.5)", "Texas", 0.3),
        leg("Spread: Texas (-14.5)", "Tennessee", 0.755),
        leg("Spread: Texas (-14.5)", "Texas", 0.245),
        leg("Spread: Texas (-17.5)", "Tennessee", 0.81),
        leg("Spread: Texas (-17.5)", "Texas", 0.19),
        leg("Spread: Texas (-2.5)", "Tennessee", 0.385),
        leg("Spread: Texas (-2.5)", "Texas", 0.615),
        leg("Spread: Texas (-20.5)", "Tennessee", 0.835),
        leg("Spread: Texas (-20.5)", "Texas", 0.165),
        leg("Spread: Texas (-21.5)", "Tennessee", 0.855),
        leg("Spread: Texas (-21.5)", "Texas", 0.145),
        leg("Spread: Texas (-3.5)", "Tennessee", 0.445),
        leg("Spread: Texas (-3.5)", "Texas", 0.555),
        leg("Spread: Texas (-4.5)", "Tennessee", 0.485),
        leg("Spread: Texas (-4.5)", "Texas", 0.515),
        leg("Spread: Texas (-5.5)", "Tennessee", 0.515),
        leg("Spread: Texas (-5.5)", "Texas", 0.485),
        leg("Spread: Texas (-6.5)", "Tennessee", 0.545),
        leg("Spread: Texas (-6.5)", "Texas", 0.455),
        leg("Spread: Texas (-7.5)", "Tennessee", 0.615),
        leg("Spread: Texas (-7.5)", "Texas", 0.385),
        leg("Spread: Texas (-8.5)", "Tennessee", 0.615),
        leg("Spread: Texas (-8.5)", "Texas", 0.385),
        leg("Spread: Texas (-9.5)", "Tennessee", 0.635),
        leg("Spread: Texas (-9.5)", "Texas", 0.365),
    ] }
    private let tnHome = "Tennessee Volunteers"
    private let txAway = "Texas Longhorns"

    /// The same event's Kalshi ladder, first rows verbatim.
    private var texasTennesseeKalshi: [SpreadRungs.Leg] { [
        SpreadRungs.Leg(marketName: "Texas vs Tennessee: Spread", outcomeName: "Texas wins by over 1.5 points", threshold: 1.5, probability: 0.625),
        SpreadRungs.Leg(marketName: "Texas vs Tennessee: Spread", outcomeName: "Tennessee wins by over 1.5 points", threshold: 1.5, probability: 0.33),
        SpreadRungs.Leg(marketName: "Texas vs Tennessee: Spread", outcomeName: "Texas wins by over 2.5 points", threshold: 2.5, probability: 0.605),
    ] }

    private func rungs(_ legs: [SpreadRungs.Leg], home: String, away: String) -> [SpreadRungs.Rung] {
        SpreadRungs.map(from: legs, home: home, away: away, sportUnit: footballUnit).rungs
    }

    private func side(_ r: [SpreadRungs.Rung], home: Bool) -> [[Double]] {
        r.filter { $0.isHome == home }
            .sorted { abs($0.margin) < abs($1.margin) }
            .map { [$0.margin, $0.probability] }
    }

    // MARK: - The page draws, one rung per market

    func testAPolymarketOnlyPageDrawsOneRungPerMarketOnTheCoverTeamsSide() {
        let map = SpreadRungs.map(from: texasTennessee, home: tnHome, away: txAway, sportUnit: footballUnit)
        XCTAssertEqual(map.unit, footballUnit)
        XCTAssertEqual(map.rungs.count, 26, "52 legs are 26 markets; each asks one question")
        XCTAssertEqual(side(map.rungs, home: false), [
            [-0.5, 0.645], [-1.5, 0.62], [-2.5, 0.615], [-3.5, 0.555], [-4.5, 0.515], [-5.5, 0.485],
            [-6.5, 0.455], [-7.5, 0.385], [-8.5, 0.385], [-9.5, 0.365], [-10.5, 0.315], [-11.5, 0.3],
            [-14.5, 0.245], [-17.5, 0.19], [-20.5, 0.165], [-21.5, 0.145],
        ], "Texas's rungs are the Texas legs of `Spread: Texas (-N)` at their own price")
        XCTAssertEqual(side(map.rungs, home: true), [
            [0.5, 0.355], [1.5, 0.325], [2.5, 0.315], [3.5, 0.265], [4.5, 0.24], [6.5, 0.215],
            [9.5, 0.145], [10.5, 0.125], [13.5, 0.105], [16.5, 0.055],
        ])
    }

    /// `Tennessee` in `Spread: Texas (-7.5)` is "Texas does not cover", not
    /// "Tennessee by 7.5+". Served WITH a threshold, the named-outcome reader
    /// would have drawn exactly that.
    func testTheLosingLegIsNeverDrawnAsTheOtherTeamsRung() {
        let r = rungs([
            SpreadRungs.Leg(marketName: "Spread: Texas (-7.5)", outcomeName: "Tennessee", threshold: 7.5, probability: 0.615),
            SpreadRungs.Leg(marketName: "Spread: Texas (-7.5)", outcomeName: "Texas", threshold: 7.5, probability: 0.385),
        ], home: tnHome, away: txAway)
        XCTAssertEqual(r, [SpreadRungs.Rung(margin: -7.5, probability: 0.385, isHome: false, quotedUnit: nil)])
    }

    // MARK: - The other leg, only when the cover leg is absent

    /// Event 15310972, soccer, settled: Polymarket serves ONE leg per market.
    /// home `Racing Louisville FC`, away `San Diego Wave FC`.
    func testALoneOtherLegIsReadAsTheCoverRungAtItsComplement() {
        let r = rungs([
            leg("Spread: Racing Louisville FC (-3.5)", "San Diego Wave FC", 0.9995),
            leg("Spread: San Diego Wave FC (-1.5)", "San Diego Wave FC", 0.9995),
            leg("Spread: San Diego Wave FC (-2.5)", "Racing Louisville FC", 0.999),
        ], home: "Racing Louisville FC", away: "San Diego Wave FC")
        XCTAssertEqual(side(r, home: false).map { $0[0] }, [-1.5, -2.5])
        XCTAssertEqual(side(r, home: false)[1][1], 0.001, accuracy: 1e-9)
        XCTAssertEqual(side(r, home: true).map { $0[0] }, [3.5])
        XCTAssertEqual(side(r, home: true)[0][1], 0.0005, accuracy: 1e-9)
    }

    func testWhereTheCoverLegIsServedItsOwnPriceIsTheRung() {
        // Both legs served and not quite complementary: the cover leg wins.
        let r = rungs([
            leg("Spread: Texas (-2.5)", "Texas", 0.5),
            leg("Spread: Texas (-2.5)", "Tennessee", 0.505),
        ], home: tnHome, away: txAway)
        XCTAssertEqual(r.map(\.probability), [0.5])
    }

    // MARK: - Refusals

    func testALegNamingNeitherTeamOrANumberOrTwoLegsOnOneSideDrawsNothing() {
        XCTAssertEqual(rungs([leg("Spread: Texas (-7.5)", "Draw", 0.2)], home: tnHome, away: txAway), [])
        XCTAssertEqual(rungs([leg("Spread: Texas (-7.5)", "Texas -7.5", 0.4)], home: tnHome, away: txAway).count, 0)
        XCTAssertEqual(rungs([
            leg("Spread: Texas (-7.5)", "Texas", 0.4), leg("Spread: Texas (-7.5)", "Texas Longhorns", 0.5),
        ], home: tnHome, away: txAway), [])
        XCTAssertEqual(rungs([leg("Spread: Texas (-7.5)", "Texas", 0.4)], home: tnHome, away: txAway).count, 1,
                       "control: the same market with one clean leg reads")
    }

    func testOnlyAFullGameMinusLineTitleIsRead() {
        XCTAssertNil(SpreadRungs.TitledSpread.read(marketName: "1st 5 Innings Spread: San Francisco (-1.5)"),
                     "First 5 stays out of the full-game map until #8785")
        XCTAssertNil(SpreadRungs.TitledSpread.read(marketName: "Spread: Texas (+7.5)"))
        XCTAssertNil(SpreadRungs.TitledSpread.read(marketName: "Texas vs Tennessee: Spread"))
        XCTAssertEqual(SpreadRungs.TitledSpread.read(marketName: "Spread: Racing Louisville FC (-3.5)"),
                       SpreadRungs.TitledSpread(coverTeam: "Racing Louisville FC", line: 3.5))
    }

    // MARK: - Never merged; monotone per side

    /// Another venue's ladder parses, so the map is exactly what it was — no
    /// line printed twice, no thin far end beside it (#8773).
    func testWhereAnotherVenuesLadderParsesPolymarketAddsNothing() {
        let kalshiOnly = SpreadRungs.map(from: texasTennesseeKalshi, home: tnHome, away: txAway, sportUnit: footballUnit)
        let both = SpreadRungs.map(from: texasTennesseeKalshi + texasTennessee, home: tnHome, away: txAway, sportUnit: footballUnit)
        XCTAssertEqual(kalshiOnly.rungs.count, 3)
        XCTAssertEqual(both, kalshiOnly)
    }

    /// Event 14781134 (Chargers @ Bills), the #8773 far end, verbatim.
    func testARungPricedAboveATighterOneOnItsSideIsWithheld() {
        let chargers = [
            leg("Spread: Chargers (-1.5)", "Bills", 0.775), leg("Spread: Chargers (-1.5)", "Chargers", 0.225),
            leg("Spread: Chargers (-2.5)", "Bills", 0.795), leg("Spread: Chargers (-2.5)", "Chargers", 0.205),
            leg("Spread: Chargers (-10.5)", "Bills", 0.937), leg("Spread: Chargers (-10.5)", "Chargers", 0.063),
            leg("Spread: Chargers (-13.5)", "Bills", 0.962), leg("Spread: Chargers (-13.5)", "Chargers", 0.038),
            leg("Spread: Chargers (-14.5)", "Bills", 0.9695), leg("Spread: Chargers (-14.5)", "Chargers", 0.0305),
            leg("Spread: Chargers (-16.5)", "Bills", 0.9485), leg("Spread: Chargers (-16.5)", "Chargers", 0.0515),
            leg("Spread: Chargers (-17.5)", "Bills", 0.961), leg("Spread: Chargers (-17.5)", "Chargers", 0.039),
            leg("Spread: Chargers (-19.5)", "Bills", 0.937), leg("Spread: Chargers (-19.5)", "Chargers", 0.063),
            leg("Spread: Chargers (-20.5)", "Bills", 0.9285), leg("Spread: Chargers (-20.5)", "Chargers", 0.0715),
            leg("Spread: Chargers (-21.5)", "Bills", 0.9075), leg("Spread: Chargers (-21.5)", "Chargers", 0.0925),
        ]
        let r = rungs(chargers, home: "Buffalo Bills", away: "Los Angeles Chargers")
        XCTAssertEqual(side(r, home: false), [
            [-1.5, 0.225], [-2.5, 0.205], [-10.5, 0.063], [-13.5, 0.038], [-14.5, 0.0305],
        ], "LAC by 16.5+ .. 21.5+ each price above LAC by 14.5+ and are withheld")
        XCTAssertTrue(side(r, home: true).isEmpty)
    }
}
