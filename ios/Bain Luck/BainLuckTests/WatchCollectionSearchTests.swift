import Foundation
import XCTest
@testable import Bain_Luck

/// Local presentation values, not producer captures or runtime acceptance.
final class WatchCollectionSearchTests: XCTestCase {
    private func nflGame(_ id: Int, home: String, away: String) -> WatchNFLGame {
        .init(id: id, home: home, away: away, status: "live", scheduledStart: nil,
              startIsTbd: nil, startedWithoutResult: nil, authorityNotStarted: nil,
              homeScore: 0, awayScore: nil, scoreSource: "received-source",
              scoreObservedAt: "2026-10-11T00:00:00Z", heroProbability: 0,
              heroProbabilitySource: "received-source")
    }

    private var nfl: WatchNFLMembership {
        .init(published: true, revision: 7,
              games: [nflGame(8, home: "Buffalo Bills", away: "New York Jets"),
                      nflGame(2, home: "New York Giants", away: "Buffalo Bills"),
                      nflGame(6, home: "Miami Dolphins", away: "Cincinnati Bengals")],
              hasOtherEntries: true,
              questions: [.init(id: 8, name: "Will Buffalo win the division?"),
                          .init(id: 3, name: "Will the résumé leader qualify?"),
                          .init(id: 9, name: "Will New York win?")])
    }

    private var mlb: WatchMLBMembership {
        .init(availability: .published, revision: 9,
              games: [.init(id: 12, home: "New York Yankees", away: "Los Angeles Dodgers",
                            stateText: "Start unavailable", scheduledStart: nil, startContext: nil),
                      .init(id: 4, home: "San Diego Padres", away: "New York Mets",
                            stateText: "Scheduled", scheduledStart: Date(timeIntervalSince1970: 42),
                            startContext: "Received start"),
                      .init(id: 7, home: "Seattle Mariners", away: "Boston Red Sox",
                            stateText: "Result unavailable", scheduledStart: nil, startContext: nil)],
              children: [.init(id: 99, name: "Received round label")], hasOtherEntries: true,
              questions: [.init(id: 12, name: "Will New York win the title?"),
                          .init(id: 5, name: "Will the résumé leader advance?"),
                          .init(id: 2, name: "Will Los Angeles win?")])
    }

    func testNFLWhitespaceRestoresAllOriginalRecords() {
        let membership = nfl
        for query in ["", " ", "\n\t "] {
            XCTAssertEqual(membership.games(matching: query), membership.games)
            XCTAssertEqual(membership.questions(matching: query), membership.questions)
        }
    }

    func testNFLMatchesEitherFullTeamNameAndPreservesOrderAndReadings() {
        let membership = nfl
        XCTAssertEqual(membership.games(matching: "  BUFFALO bills\n"), Array(membership.games.prefix(2)))
        XCTAssertEqual(membership.games(matching: "new york"), Array(membership.games.prefix(2)))
        let result = membership.games(matching: "jets")
        XCTAssertEqual(result, [membership.games[0]])
        XCTAssertEqual(result.first?.homeScore, 0)
        XCTAssertNil(result.first?.awayScore)
        XCTAssertEqual(result.first?.heroProbability, 0)
    }

    func testNFLQuestionSearchRetainsTypedIdentityAndFullTitle() {
        let membership = nfl
        XCTAssertEqual(membership.questions(matching: "RESUME"), [membership.questions[1]])
        XCTAssertEqual(membership.games(matching: "Buffalo").first?.id, 8)
        XCTAssertEqual(membership.questions(matching: "Buffalo"), [membership.questions[0]])
        XCTAssertTrue(membership.games(matching: "division").isEmpty)
    }

    func testNFLNoMatchDoesNotChangeMembershipOrOmissionDisclosure() {
        let membership = nfl
        XCTAssertTrue(membership.games(matching: "unmatched phrase").isEmpty)
        XCTAssertTrue(membership.questions(matching: "unmatched phrase").isEmpty)
        XCTAssertEqual(membership.games.count, 3)
        XCTAssertEqual(membership.questions.count, 3)
        XCTAssertTrue(membership.published)
        XCTAssertTrue(membership.hasOtherEntries)
        XCTAssertEqual(membership.revision, 7)
    }

    func testMLBWhitespaceRestoresAllOriginalRecords() {
        let membership = mlb
        for query in ["", " ", "\n\t "] {
            XCTAssertEqual(membership.games(matching: query), membership.games)
            XCTAssertEqual(membership.questions(matching: query), membership.questions)
        }
    }

    func testMLBMatchesEitherFullTeamNameAndPreservesOrderAndStartContext() {
        let membership = mlb
        XCTAssertEqual(membership.games(matching: "  NEW YORK\n"), Array(membership.games.prefix(2)))
        XCTAssertEqual(membership.games(matching: "dodgers"), [membership.games[0]])
        XCTAssertEqual(membership.games(matching: "padres"), [membership.games[1]])
        XCTAssertNil(membership.games(matching: "yankees").first?.scheduledStart)
    }

    func testMLBQuestionSearchRetainsTypedIdentityAndFullTitle() {
        let membership = mlb
        XCTAssertEqual(membership.questions(matching: "RESUME"), [membership.questions[1]])
        XCTAssertEqual(membership.games(matching: "New York").first?.id, 12)
        XCTAssertEqual(membership.questions(matching: "new york"), [membership.questions[0]])
        XCTAssertTrue(membership.games(matching: "title").isEmpty)
    }

    func testMLBNoMatchDoesNotChangeChildLabelsOrAvailability() {
        let membership = mlb
        XCTAssertTrue(membership.games(matching: "Received round label").isEmpty)
        XCTAssertTrue(membership.questions(matching: "Received round label").isEmpty)
        XCTAssertEqual(membership.children, [.init(id: 99, name: "Received round label")])
        XCTAssertEqual(membership.games.count, 3)
        XCTAssertEqual(membership.questions.count, 3)
        XCTAssertEqual(membership.availability, .published)
        XCTAssertTrue(membership.hasOtherEntries)
        XCTAssertEqual(membership.revision, 9)
    }
}
