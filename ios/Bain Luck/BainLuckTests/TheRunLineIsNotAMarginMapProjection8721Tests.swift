import XCTest
@testable import Bain_Luck

/// #8721 — the iPhone twin of web PR #8725. The full-game Run margin map's
/// `PROJECTION` tile read `-(homeSpread)`, and for baseball `homeSpread` is the
/// sportsbooks' run line, ±1.5 whatever the matchup (#8617's
/// ``SportVocab/sportsbookSpreadIsAMargin`` = false). So a 48–52 Cubs @ Red Sox
/// game read `Cubs by 1.5+` as its projection.
///
/// The legs below are the three specimens ux banked from production
/// `/api/events/{id}/game-markets` on 2026-09-25
/// (`frontend/__tests__/fixtures/ux8721_game_markets_*.20260925.json`), fed
/// through the same `SpreadRungs.map` the card builds its rungs with.
final class TheRunLineIsNotAMarginMapProjection8721Tests: XCTestCase {

    private static func rungs(_ legs: [(String, String, Double?, Double)], home: String, away: String) -> [SpreadRungs.Rung] {
        SpreadRungs.map(
            from: legs.map { SpreadRungs.Leg(marketName: $0.0, outcomeName: $0.1, threshold: $0.2, probability: $0.3) },
            home: home, away: away, sportUnit: SportVocab.forSport("baseball_mlb").unit
        ).rungs
    }

    private static func projection(sport: String, homeSpread: Double?, rungs: [SpreadRungs.Rung], isLive: Bool) -> Double? {
        MarketMapView.fullMarginProjection(
            homeSpread: homeSpread, rungs: rungs,
            sportsbookSpreadIsAMargin: SportVocab.forSport(sport).sportsbookSpreadIsAMargin,
            isLive: isLive
        )
    }

    /// 15318410 — Los Angeles Dodgers @ San Francisco Giants, scheduled.
    private static let dodgersAtGiants = rungs([
        ("Spread: San Francisco Giants (-2.5)", "Los Angeles Dodgers", nil, 0.925),
        ("Spread: San Francisco Giants (-2.5)", "San Francisco Giants", nil, 0.075),
        ("Spread: San Francisco Giants (-1.5)", "Los Angeles Dodgers", nil, 0.865),
        ("Spread: San Francisco Giants (-1.5)", "San Francisco Giants", nil, 0.135),
        ("Spread: Los Angeles Dodgers (-2.5)", "San Francisco Giants", nil, 0.505),
        ("Spread: Los Angeles Dodgers (-2.5)", "Los Angeles Dodgers", nil, 0.5),
        ("Spread: Los Angeles Dodgers (-1.5)", "Los Angeles Dodgers", nil, 0.615),
        ("Spread: Los Angeles Dodgers (-1.5)", "San Francisco Giants", nil, 0.385),
        ("Los Angeles Dodgers vs San Francisco: Spread", "Los Angeles Dodgers wins by over 1.5 runs", 1.5, 0.62),
        ("Los Angeles Dodgers vs San Francisco: Spread", "San Francisco wins by over 1.5 runs", 1.5, 0.14),
        ("Los Angeles Dodgers vs San Francisco: Spread", "Los Angeles Dodgers wins by over 2.5 runs", 2.5, 0.5),
        ("Los Angeles Dodgers vs San Francisco: Spread", "San Francisco wins by over 2.5 runs", 2.5, 0.08),
        ("Los Angeles Dodgers vs San Francisco: Spread", "Los Angeles Dodgers wins by over 3.5 runs", 3.5, 0.38),
        ("Los Angeles Dodgers vs San Francisco: Spread", "San Francisco wins by over 3.5 runs", 3.5, 0.05),
    ], home: "San Francisco Giants", away: "Los Angeles Dodgers")

    /// 15318545 — Chicago Cubs @ Boston Red Sox, live at 0–0.
    private static let cubsAtRedSox = rungs([
        ("Spread: Boston Red Sox (-2.5)", "Chicago Cubs", nil, 0.79),
        ("Spread: Boston Red Sox (-2.5)", "Boston Red Sox", nil, 0.21),
        ("Spread: Boston Red Sox (-1.5)", "Chicago Cubs", nil, 0.685),
        ("Spread: Boston Red Sox (-1.5)", "Boston Red Sox", nil, 0.315),
        ("Spread: Chicago Cubs (-1.5)", "Boston Red Sox", nil, 0.68),
        ("Spread: Chicago Cubs (-1.5)", "Chicago Cubs", nil, 0.32),
        ("Spread: Chicago Cubs (-2.5)", "Boston Red Sox", nil, 0.775),
        ("Spread: Chicago Cubs (-2.5)", "Chicago Cubs", nil, 0.225),
        ("Chicago Cubs vs Boston: Game 2 Spread", "Chicago Cubs wins by over 1.5 runs", 1.5, 0.35),
        ("Chicago Cubs vs Boston: Game 2 Spread", "Boston wins by over 1.5 runs", 1.5, 0.34),
        ("Chicago Cubs vs Boston: Game 2 Spread", "Chicago Cubs wins by over 2.5 runs", 2.5, 0.24),
        ("Chicago Cubs vs Boston: Game 2 Spread", "Boston wins by over 2.5 runs", 2.5, 0.2),
        ("Chicago Cubs vs Boston: Game 2 Spread", "Chicago Cubs wins by over 3.5 runs", 3.5, 0.2),
        ("Chicago Cubs vs Boston: Game 2 Spread", "Boston wins by over 3.5 runs", 3.5, 0.09),
    ], home: "Boston Red Sox", away: "Chicago Cubs")

    /// 15318549 — the same pair's Game 1, completed 4–3: every leg settled to 0.
    private static let cubsAtRedSoxFinal = rungs([
        ("Chicago C vs Boston: Game 1 Spread", "Chicago C wins by over 1.5 runs", 1.5, 0.0),
        ("Chicago C vs Boston: Game 1 Spread", "Boston wins by over 1.5 runs", 1.5, 0.0),
        ("Chicago C vs Boston: Game 1 Spread", "Chicago C wins by over 2.5 runs", 2.5, 0.0),
        ("Chicago C vs Boston: Game 1 Spread", "Boston wins by over 2.5 runs", 2.5, 0.0),
    ], home: "Boston Red Sox", away: "Chicago Cubs")

    func testTheSpecimensParse() {
        XCTAssertFalse(Self.dodgersAtGiants.isEmpty)
        XCTAssertFalse(Self.cubsAtRedSox.isEmpty)
    }

    func testTheLiveRunLineIsNotAProjection() {
        // The run line the card used to negate: Cubs +1.1 on the home side.
        XCTAssertNil(Self.projection(sport: "baseball_mlb", homeSpread: 1.1, rungs: Self.cubsAtRedSox, isLive: true),
                     "the live Run margin map prints the run line as its projection (#8721)")
        XCTAssertNil(Self.projection(sport: "baseball_mlb", homeSpread: nil, rungs: Self.cubsAtRedSox, isLive: true),
                     "a live baseball ladder's coin-flip rung is not a projection either")
    }

    func testAnUnplayedCloseGameNamesNoLongShotRung() {
        // Nearest a coin flip is "Cubs by 1.5+" at 35% — the run line again.
        XCTAssertNil(Self.projection(sport: "baseball_mlb", homeSpread: 1.5, rungs: Self.cubsAtRedSox, isLive: false))
        XCTAssertNil(Self.projection(sport: "baseball_npb", homeSpread: 1.5, rungs: Self.cubsAtRedSox, isLive: false))
    }

    func testAnUnplayedGameWithAnEvenMoneyRungReadsIt() {
        // Web reads this specimen `LAD by 2.5+` after #8725; the run line (SF +1.5)
        // would have read `LAD by 1.5+`.
        XCTAssertEqual(Self.projection(sport: "baseball_mlb", homeSpread: 1.5, rungs: Self.dodgersAtGiants, isLive: false), -2.5)
    }

    func testASettledLadderNamesNothing() {
        XCTAssertNil(Self.projection(sport: "baseball_mlb", homeSpread: 1.5, rungs: Self.cubsAtRedSoxFinal, isLive: false))
    }

    func testControlAMarginSportReadsExactlyAsBefore() {
        for sport in ["americanfootball_nfl", "basketball_nba", "icehockey_nhl"] {
            XCTAssertEqual(Self.projection(sport: sport, homeSpread: 1.5, rungs: Self.cubsAtRedSox, isLive: true), -1.5, sport)
            XCTAssertEqual(Self.projection(sport: sport, homeSpread: 1.5, rungs: Self.cubsAtRedSox, isLive: false), -1.5, sport)
            XCTAssertEqual(
                Self.projection(sport: sport, homeSpread: nil, rungs: Self.cubsAtRedSox, isLive: true),
                MarketMapView.closestToEvenMargin(Self.cubsAtRedSox), sport)
        }
    }
}
