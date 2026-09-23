import XCTest
@testable import Bain_Luck

/// #8215, phone half — a served `commence_time_is_kickoff == false` is not a
/// start, so neither the page's shared chart domain nor "Since Start" cuts at it.
///
/// For a Kalshi-clocked dated fixture (tennis and the rest) the stored hour is
/// Kalshi's `occurrence_datetime`, byte-identical to its expected RESOLUTION
/// time. The web declines both cuts on the flag (`ef81eafb9b`); the phone
/// decoded no such key and cut at it twice — `EventDetailView.sharedChartDomain`
/// (applied under All as well) and `OddsChartView.filterPoints`.
///
/// Live specimen, Kicker v Dellien `15317706` (Kalshi-only, 2026-09-23
/// 22:03Z): stored 20:20Z, 294 of 486 readings before it. Absent (older
/// payload) and `true` are the controls: they must cut exactly as before.
final class SinceStartDoesNotCutAtAnExpectedEnd8215Tests: XCTestCase {

    private static let stored = "2026-09-23T20:20:00Z".asDate!

    private func decode(flag: String?) throws -> EventHistoryResponse {
        let flagLine = flag.map { "\"commence_time_is_kickoff\": \($0)," } ?? ""
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {
          "event_id": 15317706, "home_team": "Kicker", "away_team": "Dellien", "status": "live",
          \(flagLine)
          "history": [],
          "win_prob_history": {"kalshi": [
            {"timestamp": "2026-09-23T06:55:19Z", "home_probability": 0.21},
            {"timestamp": "2026-09-23T21:30:00Z", "home_probability": 0.33},
            {"timestamp": "2026-09-23T22:03:24Z", "home_probability": 0.12}
          ]}
        }
        """.utf8))
    }

    func testTheFlagDecodes() throws {
        XCTAssertEqual(try decode(flag: "false").commenceTimeIsKickoff, false)
        XCTAssertEqual(try decode(flag: "true").commenceTimeIsKickoff, true)
        XCTAssertNil(try decode(flag: nil).commenceTimeIsKickoff)
    }

    // MARK: - Since Start

    func testSinceStartDeclinesTheCutOnFalse() {
        XCTAssertNil(OddsChartView.sinceStartCut(commence: Self.stored, commenceTimeIsKickoff: false))
    }

    func testSinceStartCutsAsBeforeOnTrueAndAbsent() {
        XCTAssertEqual(OddsChartView.sinceStartCut(commence: Self.stored, commenceTimeIsKickoff: true), Self.stored)
        XCTAssertEqual(OddsChartView.sinceStartCut(commence: Self.stored, commenceTimeIsKickoff: nil), Self.stored)
        XCTAssertNil(OddsChartView.sinceStartCut(commence: nil, commenceTimeIsKickoff: true))
    }

    // MARK: - The page's shared domain

    /// On false the domain opens at the first captured reading — the whole
    /// extent, the web's remedy — not at the stored hour.
    func testTheSharedDomainOpensAtTheFirstReadingOnFalse() throws {
        let start = EventDetailView.sharedDomainStart(scheduledStart: Self.stored, history: try decode(flag: "false"))
        XCTAssertEqual(start, "2026-09-23T06:55:19Z".asDate)
    }

    func testTheSharedDomainKeepsTheScheduleOnTrueAndAbsent() throws {
        XCTAssertEqual(EventDetailView.sharedDomainStart(scheduledStart: Self.stored, history: try decode(flag: "true")),
                       Self.stored)
        XCTAssertEqual(EventDetailView.sharedDomainStart(scheduledStart: Self.stored, history: try decode(flag: nil)),
                       Self.stored)
        XCTAssertEqual(EventDetailView.sharedDomainStart(scheduledStart: Self.stored, history: nil), Self.stored)
    }

    /// #1833's warm-up clamp is untouched on a trusted start: an ESPN row 20 h
    /// early still cannot open the axis more than two hours before the schedule.
    func testTheTwoHourClampStillHoldsOnATrustedStart() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let history = try decoder.decode(EventHistoryResponse.self, from: Data("""
        {
          "event_id": 1, "home_team": "Red Sox", "away_team": "Blue Jays", "status": "live",
          "commence_time_is_kickoff": true, "history": [],
          "espn_history": [{"timestamp": "2026-09-23T00:20:00Z", "home_probability": 0.5, "period": "Top 3"}]
        }
        """.utf8))

        XCTAssertEqual(EventDetailView.sharedDomainStart(scheduledStart: Self.stored, history: history),
                       Self.stored.addingTimeInterval(-2 * 60 * 60))
    }
}
