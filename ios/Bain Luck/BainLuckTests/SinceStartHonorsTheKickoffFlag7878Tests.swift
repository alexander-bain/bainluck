import XCTest
@testable import Bain_Luck

/// #7878 D (codex 2026-09-23) — "Since Start" honours `commence_time_is_kickoff`.
///
/// `false` means the stored start is Kalshi's expected EXPIRATION, not a
/// kick-off: Kalshi publishes no start field, so a tennis row clocked from it
/// holds the far end of the match. The web stopped cutting there in #8215; the
/// phone decoded no such key and cut anyway — on `/events/15317314`
/// (Basilashvili v Cina, played in the 07:00Z hour against a stored 09:10Z)
/// that leaves only the points after the winner was decided.
///
/// The controls are half the suite: `true` and an absent key (an older
/// payload) still cut exactly as before, and "All" never cuts.
final class SinceStartHonorsTheKickoffFlag7878Tests: XCTestCase {

    /// 2026-09-23T09:10:00Z — the stored start of the specimen.
    private static let storedStart = Date(timeIntervalSince1970: 1_790_154_600)

    private func decode(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// The specimen's shape: the match swings 0.39 → 0.995 between 07:00Z and
    /// 08:30Z, then four settled readings sit after the stored start.
    private func specimenPoints() -> [ChartDataPoint] {
        let inMatch: [TimeInterval] = stride(from: -7_800, through: -2_400, by: 300).map { $0 }
        let afterStoredStart: [TimeInterval] = [60, 240, 420, 540]
        return (inMatch + afterStoredStart).map {
            ChartDataPoint(date: Self.storedStart.addingTimeInterval($0), probability: 0.6, source: "kalshi")
        }
    }

    private func payload(flag: String?) -> String {
        let key = flag.map { "\"commence_time_is_kickoff\": \($0)," } ?? ""
        return """
        {
          "event_id": 15317314, "home_team": "Basilashvili", "away_team": "Cina", "status": "completed",
          "commence_time": "2026-09-23T09:10:00Z", \(key)
          "history": [],
          "win_prob_history": {"kalshi": [
            {"timestamp": "2026-09-23T07:05:00Z", "home_probability": 0.39},
            {"timestamp": "2026-09-23T08:20:00Z", "home_probability": 0.9},
            {"timestamp": "2026-09-23T08:30:00Z", "home_probability": 0.995},
            {"timestamp": "2026-09-23T09:15:00Z", "home_probability": 0.995}
          ]}
        }
        """
    }

    // MARK: - Decode

    func testTheServedFlagDecodesInBothValuesAndAbsentIsNil() throws {
        XCTAssertEqual(try decode(payload(flag: "false")).commenceTimeIsKickoff, false)
        XCTAssertEqual(try decode(payload(flag: "true")).commenceTimeIsKickoff, true)
        XCTAssertNil(try decode(payload(flag: nil)).commenceTimeIsKickoff)
    }

    // MARK: - The cut

    func testOnlyAnExplicitFalseRemovesTheCut() {
        XCTAssertNil(OddsChartView.sinceStartCut(commenceTime: Self.storedStart, commenceTimeIsKickoff: false))
        XCTAssertEqual(OddsChartView.sinceStartCut(commenceTime: Self.storedStart, commenceTimeIsKickoff: true),
                       Self.storedStart)
        XCTAssertEqual(OddsChartView.sinceStartCut(commenceTime: Self.storedStart, commenceTimeIsKickoff: nil),
                       Self.storedStart)
    }

    /// THE DEFECT. Before: Since Start cut at 09:10Z and kept the four settled
    /// readings. After: the whole match is drawn.
    func testAnExpirationClockedMatchKeepsItsWholeJourneyUnderSinceStart() {
        let points = specimenPoints()
        let cut = OddsChartView.sinceStartCut(commenceTime: Self.storedStart, commenceTimeIsKickoff: false)

        let drawn = OddsChartView.sinceStartWindow(points, range: .sinceStart, kickoff: cut)

        XCTAssertEqual(drawn.count, points.count)
        XCTAssertEqual(drawn.first?.date, points.first?.date)
    }

    /// The same, end to end from a decoded payload through the chart's own
    /// point builder — so a decode that drops the key cannot pass.
    func testADecodedFalsePayloadIsNotCutAtItsStoredStart() throws {
        let history = try decode(payload(flag: "false"))
        let points = OddsChartView.chartPoints(from: history).filter { $0.source == "kalshi" }
            .sorted { $0.date < $1.date }
        let cut = OddsChartView.sinceStartCut(commenceTime: Self.storedStart,
                                              commenceTimeIsKickoff: history.commenceTimeIsKickoff)

        let drawn = OddsChartView.sinceStartWindow(points, range: .sinceStart, kickoff: cut)

        XCTAssertEqual(drawn.count, 4)
        XCTAssertEqual(drawn.first?.date, "2026-09-23T07:05:00Z".asDate)
    }

    /// With no cut there is nothing for "Since Start" to mean, so the phone does
    /// not offer it (and `.task` does not default to it).
    func testNoCutMeansNoSinceStartChoice() {
        XCTAssertFalse(OddsChartView.offersSinceStart(isGameStarted: true, kickoff: nil))
    }

    // MARK: - Controls

    /// CONTROL: a real kick-off still cuts. Same points, flag `true`.
    func testAKickoffClockedGameIsStillCut() {
        let points = specimenPoints()
        let cut = OddsChartView.sinceStartCut(commenceTime: Self.storedStart, commenceTimeIsKickoff: true)

        let drawn = OddsChartView.sinceStartWindow(points, range: .sinceStart, kickoff: cut)

        XCTAssertEqual(drawn.count, 4)
        XCTAssertTrue(drawn.allSatisfy { $0.date >= Self.storedStart })
        XCTAssertTrue(OddsChartView.offersSinceStart(isGameStarted: true, kickoff: cut))
    }

    /// CONTROL: an older payload with no key cuts exactly as before.
    func testAnOlderPayloadWithoutTheKeyIsStillCut() throws {
        let history = try decode(payload(flag: nil))
        let points = OddsChartView.chartPoints(from: history).filter { $0.source == "kalshi" }
        let cut = OddsChartView.sinceStartCut(commenceTime: Self.storedStart,
                                              commenceTimeIsKickoff: history.commenceTimeIsKickoff)

        let drawn = OddsChartView.sinceStartWindow(points, range: .sinceStart, kickoff: cut)

        XCTAssertEqual(drawn.count, 1)
        XCTAssertTrue(OddsChartView.offersSinceStart(isGameStarted: true, kickoff: cut))
    }

    /// CONTROL: "All" never cuts, and an unstarted game offers no choice.
    func testAllNeverCutsAndAnUnstartedGameOffersNoChoice() {
        let points = specimenPoints()

        XCTAssertEqual(OddsChartView.sinceStartWindow(points, range: .all, kickoff: Self.storedStart).count,
                       points.count)
        XCTAssertFalse(OddsChartView.offersSinceStart(isGameStarted: false, kickoff: Self.storedStart))
    }

    /// CONTROL: the smart start still skips a >30 min hole after a real kick-off.
    func testTheSmartStartIsUnchanged() {
        let late = [2_400.0, 2_700, 3_000].map {
            ChartDataPoint(date: Self.storedStart.addingTimeInterval($0), probability: 0.5, source: "kalshi")
        }
        let early = ChartDataPoint(date: Self.storedStart.addingTimeInterval(-600), probability: 0.5, source: "kalshi")

        let drawn = OddsChartView.sinceStartWindow([early] + late, range: .sinceStart, kickoff: Self.storedStart)

        XCTAssertEqual(drawn.map(\.date), late.map(\.date))
    }
}
