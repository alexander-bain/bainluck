import Foundation
import XCTest
@testable import Bain_Luck

final class WatchMyStuffTeamRecoveryTests: XCTestCase {
    private func response(teamID: Int = 72) throws -> Data {
        try JSONSerialization.data(withJSONObject: [
            "team": ["id": teamID, "name": "Saved team"],
            "upcoming_events": [["id": 101, "home_team": "Home", "away_team": "Away"]],
            "recent_events": [["id": 101, "home_team": "Home", "away_team": "Away"],
                             ["id": 202, "home_team": "Other home", "away_team": "Other away"]],
            "futures": [["market_id": 303, "market_name": "Full saved question?"]]
        ])
    }

    func testExactTeamKeepsProviderOrderDeduplicationAndQuestionIdentity() throws {
        var state = WatchMyStuffTeamState()
        state.receive(try response(), expectedTeamID: 72)
        let page = try XCTUnwrap(state.page)
        XCTAssertEqual(page.team.id, 72)
        XCTAssertEqual(page.games.map(\.id), [101, 202])
        XCTAssertEqual(page.questions.map(\.marketId), [303])
        XCTAssertEqual(page.questions.first?.marketName, "Full saved question?")
        XCTAssertNil(state.error)
    }

    func testWrongTeamResponseRevokesPriorDestinationsEvenWithSameName() throws {
        var state = WatchMyStuffTeamState()
        state.receive(try response(), expectedTeamID: 72)
        state.receive(try response(teamID: 73), expectedTeamID: 72)
        XCTAssertNil(state.page)
        XCTAssertNotNil(state.error)
        state.receive(try response(), expectedTeamID: 0)
        XCTAssertNil(state.page)
    }

    func testRefreshClearsOldDestinationsThenFailureAndRetryRecover() throws {
        var state = WatchMyStuffTeamState()
        state.receive(try response(), expectedTeamID: 72)
        state.beginRefresh()
        XCTAssertNil(state.page, "Loading cannot expose stale game or market buttons")
        XCTAssertNil(state.error)
        state.fail("This team is no longer listed.")
        XCTAssertNil(state.page)
        XCTAssertEqual(state.error, "This team is no longer listed.")
        state.beginRefresh()
        state.receive(try response(), expectedTeamID: 72)
        XCTAssertNotNil(state.page)
        XCTAssertNil(state.error)
        state.fail("Offline")
        XCTAssertNil(state.page)
        XCTAssertEqual(state.error, "Offline")
    }

    func testMalformedResponseCannotKeepOldDestinations() throws {
        var state = WatchMyStuffTeamState()
        state.receive(try response(), expectedTeamID: 72)
        state.receive(Data("{}".utf8), expectedTeamID: 72)
        XCTAssertNil(state.page)
        XCTAssertNotNil(state.error)
    }
}
