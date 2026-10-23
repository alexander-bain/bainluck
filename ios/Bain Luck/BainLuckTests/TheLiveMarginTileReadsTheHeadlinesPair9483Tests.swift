import XCTest
@testable import Bain_Luck

/// #9483 / #11296 — the live full-game margin card tells the headline's story.
///
/// Retained specimen 15195971 (Nuggets @ Thunder, live Q3 7:13, 58–55), captured
/// 2026-10-23T03:13:58Z (`artifacts/authority-403-15195971-live-capture-20261023T0315Z`):
/// the headline printed `104–106 Projected final` from the admitted in-play pair
/// 106.0 / 103.6, while the margin card's PROJECTION tile read `OKC by 4.5+` —
/// `current_odds` carries `spread: -2.4` and no `home_spread`, so the tile fell
/// back to the Kalshi rung nearest a coin flip (`OKC by over 4.5`, 0.49). And
/// the card's header printed the blended winner `OKC 56%` over venue rungs
/// reading `OKC by 1.5+ 62%`.
///
/// The `liveProjection` object and the rungs below are the specimen's served
/// values, trimmed to the fields read; the row around them is reduced to what
/// the admission reads.
@MainActor
final class TheLiveMarginTileReadsTheHeadlinesPair9483Tests: XCTestCase {

    private static let pageNow = ISO8601DateFormatter().date(from: "2026-10-23T03:14:01Z")!

    private static let specimenRow = #"""
    {"id": 15195971, "sport": "basketball_nba", "home_team": "Oklahoma City Thunder", "away_team": "Denver Nuggets", "commence_time": "2026-10-23T01:30:00+00:00", "status": "live", "home_score": 55, "away_score": 58, "current_odds": {"home_probability": 0.561514, "away_probability": 0.438486, "spread": -2.4, "over_under": 209.5, "projected_home_score": 106.0, "projected_away_score": 103.6, "bookmaker_count": 15, "live_projection": {"projected_home_score": 106.0, "projected_away_score": 103.6, "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-10-23T01:30:00+00:00", "earliest_confirmed_at": "2026-10-23T03:13:27.610336+00:00", "latest_captured_at": "2026-10-23T03:13:27.713325+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 13, "unit": "points", "period": "full_game"}}, "espn": {"period": "7:13 - 3rd Quarter"}}
    """#

    /// The specimen's served Kalshi full-game rungs around even money.
    private static let specimenRungs: [SpreadRungs.Rung] = SpreadRungs.map(
        from: [
            ("Oklahoma City wins by over 1.5 points", 1.5, 0.615),
            ("Denver wins by over 1.5 points", 1.5, 0.335),
            ("Oklahoma City wins by over 2.5 points", 2.5, 0.565),
            ("Denver wins by over 2.5 points", 2.5, 0.295),
            ("Oklahoma City wins by over 3.5 points", 3.5, 0.525),
            ("Oklahoma City wins by over 4.5 points", 4.5, 0.49),
            ("Denver wins by over 4.5 points", 4.5, 0.225),
            ("Oklahoma City wins by over 5.5 points", 5.5, 0.425),
        ].map {
            SpreadRungs.Leg(marketName: "Denver vs Oklahoma City: Spread",
                            outcomeName: $0.0, threshold: $0.1, probability: $0.2)
        },
        home: "Oklahoma City Thunder", away: "Denver Nuggets",
        sportUnit: SportVocab.forSport("basketball_nba").unit
    ).rungs

    private func row(_ json: String = TheLiveMarginTileReadsTheHeadlinesPair9483Tests.specimenRow,
                     file: StaticString = #filePath, line: UInt = #line) throws -> EventDetail {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        do { return try d.decode(EventDetail.self, from: Data(json.utf8)) } catch {
            XCTFail("row did not decode: \(error)", file: file, line: line); throw error
        }
    }

    /// What the page hands the card: the headline's own decision.
    private func forecast(_ e: EventDetail) -> MarketMapRail.LiveMarginForecast? {
        EventDetailView.liveForecast11296(
            e, ladderHome: nil, ladderAway: nil,
            hasScore: EventDetailView.showsScore(status: e.status, away: e.awayScore, home: e.homeScore),
            now: Self.pageNow
        ).map { MarketMapRail.LiveMarginForecast($0.current) }
    }

    private func liveTile(_ forecast: MarketMapRail.LiveMarginForecast?, homeSpread: Double? = nil,
                          sport: String = "basketball_nba") -> Double? {
        MarketMapView.fullGameMarginProjection(
            isLive: true, liveForecast: forecast?.margin, homeSpread: homeSpread,
            rungs: Self.specimenRungs,
            sportsbookSpreadIsAMargin: SportVocab.forSport(sport).sportsbookSpreadIsAMargin)
    }

    // MARK: - The specimen

    func testTheSpecimenRungsAreWhatTheOldTileRead() {
        XCTAssertFalse(Self.specimenRungs.isEmpty)
        XCTAssertEqual(MarketMapView.closestToEvenMargin(Self.specimenRungs), 4.5,
                       "the rung nearest a coin flip is OKC by 4.5 at 49% — what the tile used to name")
    }

    func testTheHeadlineAdmitsTheSpecimenPair() throws {
        let f = try XCTUnwrap(forecast(try row()), "the headline prints 104–106 on this row")
        XCTAssertEqual(f.margin, 2.4, accuracy: 1e-9, "106.0 − 103.6, home-signed")
        XCTAssertEqual(f.printedMargin, 2, "106 − 104, as the headline prints it")
    }

    func testTheLiveTileSitsOnTheHeadlinesMarginNotTheCoinFlipRung() throws {
        let f = try XCTUnwrap(forecast(try row()))
        let tile = try XCTUnwrap(liveTile(f))
        XCTAssertEqual(tile, 2.4, accuracy: 1e-9)
        XCTAssertNotEqual(tile, 4.5)
        XCTAssertEqual(MarketMapRail.liveForecastMarginLabel(homeAbbr: "OKC", awayAbbr: "DEN",
                                                             printedMargin: f.printedMargin),
                       "OKC by about 2")
    }

    // MARK: - No admitted pair, no tile

    func testARefusedPairDrawsNoTileWhateverElseIsServed() throws {
        // The same row with the object's source changed: served and refused.
        let refused = try row(Self.specimenRow.replacingOccurrences(
            of: #""source": "sportsbooks""#, with: #""source": "kalshi""#))
        XCTAssertNil(forecast(refused))
        XCTAssertNil(liveTile(nil, homeSpread: -2.4),
                     "a raw spread is not the admitted pair")
        XCTAssertNil(liveTile(nil), "the coin-flip rung is a market threshold, not a projected final")
    }

    func testAnAbsentObjectDrawsNoTile() throws {
        let absent = try row(Self.specimenRow.replacingOccurrences(
            of: #", "live_projection": \{[^}]*\}"#, with: "", options: .regularExpression))
        XCTAssertNil(absent.currentOdds?.liveProjection)
        XCTAssertNil(forecast(absent))
    }

    func testANonLiveRowHandsTheCardNothing() throws {
        let finished = try row(Self.specimenRow.replacingOccurrences(
            of: #""status": "live""#, with: #""status": "final""#))
        XCTAssertNil(forecast(finished))
    }

    func testARunLineSportNeverProjectsLive() {
        let f = MarketMapRail.LiveMarginForecast(LiveProjectedFinalAdmission2920.Printed(
            label: "Projected final", home: 5, away: 4,
            admitted: .init(home: 4.6, away: 4.2, provenance: .init(
                bookmakerCount: 2, scheduledStart: Self.pageNow, earliestConfirmedAt: Self.pageNow,
                latestCapturedAt: Self.pageNow, unit: .points, period: .fullGame))))
        XCTAssertNil(liveTile(f, sport: "baseball_mlb"))
    }

    // MARK: - Before the game nothing moves

    func testThePregameTileReadsExactlyAsBefore() {
        for spread: Double? in [-2.5, nil] {
            XCTAssertEqual(
                MarketMapView.fullGameMarginProjection(
                    isLive: false, liveForecast: 9.9, homeSpread: spread, rungs: Self.specimenRungs,
                    sportsbookSpreadIsAMargin: true),
                MarketMapView.marginProjection(
                    homeSpread: spread, rungs: Self.specimenRungs,
                    sportsbookSpreadIsAMargin: true, isLive: false))
        }
    }

    // MARK: - The label

    func testTheLabelNamesTheSideFromThePrintedPair() {
        XCTAssertEqual(MarketMapRail.liveForecastMarginLabel(homeAbbr: "OKC", awayAbbr: "DEN", printedMargin: -3),
                       "DEN by about 3")
        XCTAssertEqual(MarketMapRail.liveForecastMarginLabel(homeAbbr: "OKC", awayAbbr: "DEN", printedMargin: 0),
                       MarketMapRail.tiedMarginLabel)
    }

    // MARK: - Wiring

    private func source(_ path: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
    }

    /// The page hands the card the headline's decision, and nothing else.
    func testThePageHandsTheCardTheHeadlinesPair() throws {
        let page = try source("Bain Luck/Views/EventDetailView.swift")
            .replacingOccurrences(of: " ", with: "").replacingOccurrences(of: "\n", with: "")
        XCTAssertTrue(page.contains("liveForecast:revealForecast11296.map{MarketMapRail.LiveMarginForecast($0.current)}"))
        XCTAssertFalse(page.contains("homeWinProb:event.currentOdds"),
                       "the card no longer takes the blended winner")
    }

    /// The full-game card reads its tile through the live rule, and prints no header.
    func testTheCardReadsTheLiveRuleAndPrintsNoHeader() throws {
        let card = try source("Bain Luck/Components/MarketMapView.swift")
        XCTAssertTrue(card.contains("let projValue = Self.fullGameMarginProjection("))
        XCTAssertFalse(card.contains("marginHeadline"))
        XCTAssertFalse(card.contains("DrawPricedWinner"),
                       "no blended winner badge on any margin card")
    }
}
