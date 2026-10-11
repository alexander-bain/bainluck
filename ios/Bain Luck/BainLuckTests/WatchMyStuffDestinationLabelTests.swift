import Foundation
import XCTest
@testable import Bain_Luck

final class WatchMyStuffDestinationLabelTests: XCTestCase {
    private func page(upcoming: [[String: Any]] = [], recent: [[String: Any]] = [],
                      questions: [[String: Any]] = []) throws -> WatchMyStuffTeamPage {
        let data = try JSONSerialization.data(withJSONObject: [
            "team": ["id": 72, "name": "Saved team"],
            "upcoming_events": upcoming, "recent_events": recent, "futures": questions
        ])
        var state = WatchMyStuffTeamState()
        state.receive(data, expectedTeamID: 72)
        XCTAssertNil(state.error)
        return try XCTUnwrap(state.page)
    }

    func testBlankGameSidesAreUnavailableWhileHealthySiblingKeepsExactRoute() throws {
        let value = try page(upcoming: [
            ["id": 101, "home_team": " \n", "away_team": "Away"],
            ["id": 102, "home_team": "Home", "away_team": "\t"],
            ["id": 103, "home_team": "Full Home Name", "away_team": "Full Away Name"]
        ])
        XCTAssertEqual(value.games.map(\.id), [103])
        XCTAssertEqual(value.games.first?.homeTeam, "Full Home Name")
        XCTAssertEqual(value.games.first?.awayTeam, "Full Away Name")
        XCTAssertTrue(value.hasUnavailableGames)
        XCTAssertFalse(value.hasUnavailableQuestions)
    }

    func testBlankQuestionIsNotAnEmptyButtonAndHealthyQuestionRemains() throws {
        let value = try page(questions: [
            ["market_id": 301, "market_name": ""],
            ["market_id": 302, "market_name": " \t\n"],
            ["market_id": 303, "market_name": "Full published question?"]
        ])
        XCTAssertEqual(value.questions.map(\.marketId), [303])
        XCTAssertEqual(value.questions.first?.marketName, "Full published question?")
        XCTAssertTrue(value.hasUnavailableQuestions)
        XCTAssertFalse(value.hasUnavailableGames)
    }

    func testUnreadableFirstRowDoesNotConsumeIdentityAndValidDuplicatesStayDeduplicated() throws {
        let value = try page(upcoming: [
            ["id": 101, "home_team": "", "away_team": "Away"],
            ["id": 202, "home_team": "Home two", "away_team": "Away two"]
        ], recent: [
            ["id": 101, "home_team": "Home one", "away_team": "Away one"],
            ["id": 202, "home_team": "Home two", "away_team": "Away two"]
        ], questions: [
            ["market_id": 301, "market_name": " "],
            ["market_id": 301, "market_name": "Recovered question?"],
            ["market_id": 301, "market_name": "Recovered question?"]
        ])
        XCTAssertEqual(value.games.map(\.id), [202, 101])
        XCTAssertEqual(value.questions.map(\.marketId), [301])
        XCTAssertEqual(value.questions.first?.marketName, "Recovered question?")
        XCTAssertTrue(value.hasUnavailableGames)
        XCTAssertTrue(value.hasUnavailableQuestions)
    }

    func testEmptyResponseIsDistinctFromUnavailableRowsAndZeroIDsRemainRefused() throws {
        let empty = try page()
        XCTAssertTrue(empty.games.isEmpty)
        XCTAssertTrue(empty.questions.isEmpty)
        XCTAssertFalse(empty.hasUnavailableGames)
        XCTAssertFalse(empty.hasUnavailableQuestions)
        let invalid = try page(upcoming: [
            ["id": 0, "home_team": "Home", "away_team": "Away"]
        ], questions: [["market_id": 0, "market_name": "Question?"]])
        XCTAssertTrue(invalid.games.isEmpty)
        XCTAssertTrue(invalid.questions.isEmpty)
        XCTAssertTrue(invalid.hasUnavailableGames)
        XCTAssertTrue(invalid.hasUnavailableQuestions)
    }
}
