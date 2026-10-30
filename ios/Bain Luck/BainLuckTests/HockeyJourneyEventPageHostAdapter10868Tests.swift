import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the hockey journey host glue rebuilds the page from the values it
/// is passed, so a changed box count or ESPN clock reaches the screen on the
/// very next pass, with every other input held fixed (same player count,
/// score and probability clocks, history and `now`).
///
/// Bodies are part three's reduced verbatim subsets of the retained Minnesota
/// Wild 4–1 Boston Bruins final (`HockeyJourneyContributionAdapter10868Tests`,
/// provenance and hashes there). CONSTRUCTED here, and only here: the reader's
/// calendar and `now`; an empty `/history` envelope (the page's honest empty
/// history); one box value (Quinn Hughes's assists 1 → 2); and, for the clock
/// case, `status` set to `live` with an ESPN period and clock (no live NHL body
/// is retained), then that clock alone moved.
@MainActor
final class HockeyJourneyEventPageHostAdapter10868Tests: XCTestCase {
    private typealias Host = HockeyJourneyEventPageHost10868
    private typealias Fixtures = HockeyJourneyContributionAdapter10868Tests

    private static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()
    private static let locale = Locale(identifier: "en_US")
    private static let readAt = "2026-10-04T06:10:00Z"

    private nonisolated struct BoxBody: Decodable {
        nonisolated struct Box: Decodable { let players: [String: [String: Double]]? }
        let boxScoreData: Box?
    }

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func detail(_ object: [String: Any]) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: try JSONSerialization.data(withJSONObject: object))
    }

    private func detailObject() throws -> [String: Any] {
        try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(Fixtures.wildBruinsDetail.utf8)) as? [String: Any])
    }

    private func emptyHistory() throws -> EventHistoryResponse {
        try decoder().decode(EventHistoryResponse.self, from: Data(#"""
        {"event_id":15169793,"home_team":"Minnesota Wild","away_team":"Boston Bruins","status":"completed","history":[]}
        """#.utf8))
    }

    private func build(_ event: EventDetail, box: [String: [String: Double]]?,
                       history: EventHistoryResponse?, reading: Host.Reading = .init()) throws -> Host.Built? {
        let markets = try decoder().decode(GameMarketsResponse.self, from: Data(Fixtures.wildBruinsMarkets.utf8))
        return Host.build(event: event, history: history, markets: markets, boxScore: box,
                          probabilityObservedAt: event.heroProbabilityObservedAt?.asDate,
                          now: try XCTUnwrap(Self.readAt.asDate), reading: reading,
                          calendar: Self.pacific, locale: Self.locale)
    }

    func testAChangedBoxCountReachesTheAssistsStoryAtTheSamePlayerCountAndClocks() throws {
        let event = try detail(try detailObject())
        let box = try XCTUnwrap(try decoder().decode(BoxBody.self, from: Data(Fixtures.wildBruinsDetail.utf8))
            .boxScoreData?.players)
        var moved = box
        XCTAssertEqual(moved["Quinn Hughes"]?["assists"], 1)
        moved["Quinn Hughes"]?["assists"] = 2
        XCTAssertEqual(moved.count, box.count)

        let reading = Host.Reading(assistsPlayer: "player:quinn hughes")
        let before = try XCTUnwrap(try build(event, box: box, history: try emptyHistory(), reading: reading))
        let after = try XCTUnwrap(try build(event, box: moved, history: try emptyHistory(), reading: reading))
        XCTAssertNotNil(before.input.assists)
        XCTAssertNotEqual(before.input.assists, after.input.assists)
        XCTAssertEqual(before.input.headline, after.input.headline)
    }

    func testAMovedESPNClockReachesTheHeadlineWithTheScoreAndProbabilityClocksUnchanged() throws {
        var object = try detailObject()
        object["status"] = "live"
        var espn = try XCTUnwrap(object["espn"] as? [String: Any])
        espn["period"] = "2nd"
        espn["game_clock"] = "12:34"
        object["espn"] = espn
        let first = try detail(object)
        espn["game_clock"] = "11:02"
        object["espn"] = espn
        let second = try detail(object)
        XCTAssertEqual(first.scoreObservedAt, second.scoreObservedAt)
        XCTAssertEqual(first.heroProbabilityObservedAt, second.heroProbabilityObservedAt)

        let a = try XCTUnwrap(try build(first, box: nil, history: try emptyHistory()))
        let b = try XCTUnwrap(try build(second, box: nil, history: try emptyHistory()))
        XCTAssertEqual(a.input.phase, .live)
        XCTAssertNotEqual(a.input.headline, b.input.headline)
    }

    func testNoHistoryYetBuildsNoPageSoTheSlotKeepsThePagesLoadingMark() throws {
        XCTAssertNil(try build(try detail(try detailObject()), box: nil, history: nil))
    }

    func testOnlyNHLEventsTakeTheScreen() throws {
        XCTAssertTrue(Host.applies(try detail(try detailObject())))
        var object = try detailObject()
        object["sport"] = "basketball_nba"
        XCTAssertFalse(Host.applies(try detail(object)))
    }
}
