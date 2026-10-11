import Foundation
import XCTest
@testable import Bain_Luck

final class WatchOutcomeSearchTests: XCTestCase {
    private func detail(status: String = "open") throws -> WatchQuestionDetail {
        let payload: [String: Any] = [
            "id": 42, "name": "Full published question?", "status": status,
            "outcomes": [
                ["id": 11, "name": "Chloé Zhao", "probability": 0.0],
                ["id": 12, "name": "Full Northern Team Name", "probability": 0.63],
                ["id": 13, "name": "Another Northern Team", "probability": NSNull()],
                ["id": 14, "name": "A separate candidate", "probability": 1.0]
            ]
        ]
        return try WatchQuestionDetailDecoder.decode(
            JSONSerialization.data(withJSONObject: payload), expectedID: 42)
    }

    func testEmptyAndWhitespaceSearchRestoreAllReceivedOutcomes() throws {
        let value = try detail()
        XCTAssertEqual(value.outcomes(matching: ""), value.outcomes)
        XCTAssertEqual(value.outcomes(matching: " \t\n"), value.outcomes)
    }

    func testNameSearchIgnoresCaseAccentsAndSurroundingWhitespace() throws {
        let value = try detail()
        let matches = value.outcomes(matching: "  CHLOE \n")
        XCTAssertEqual(matches.map(\.id), [11])
        XCTAssertEqual(matches.first?.name, "Chloé Zhao")
        XCTAssertEqual(matches.first?.probability, 0.0)
    }

    func testPartialNameKeepsReceivedOrderAndExactReadings() throws {
        let value = try detail()
        let matches = value.outcomes(matching: "northern")
        XCTAssertEqual(matches.map(\.id), [12, 13])
        XCTAssertEqual(matches, [value.outcomes[1], value.outcomes[2]])
        XCTAssertNil(matches[1].probability)
    }

    func testNoMatchDoesNotEraseTheUnderlyingQuestionOrOutcomes() throws {
        let value = try detail()
        XCTAssertTrue(value.outcomes(matching: "not in this field").isEmpty)
        XCTAssertEqual(value.id, 42)
        XCTAssertEqual(value.question, "Full published question?")
        XCTAssertEqual(value.outcomes(matching: "").map(\.id), [11, 12, 13, 14])
    }

    func testSearchUsesNamesNotDisplayedProbabilitiesOrResultCopy() throws {
        let value = try detail()
        XCTAssertTrue(value.outcomes(matching: "63%").isEmpty)
        XCTAssertTrue(value.outcomes(matching: "Chance").isEmpty)
        let closed = try detail(status: "closed")
        let matches = closed.outcomes(matching: "northern")
        XCTAssertEqual(matches, [closed.outcomes[1], closed.outcomes[2]])
        XCTAssertTrue(matches.allSatisfy(\.resultUnavailable))
        XCTAssertTrue(matches.allSatisfy { $0.probability == nil })
    }

    func testSearchCannotReintroduceRefusedDuplicateIdentities() throws {
        let payload = Data(#"{"id":42,"name":"Question?","status":"open","outcomes":[{"id":11,"name":"Northern duplicate","probability":0.4},{"id":11,"name":"Northern duplicate","probability":0.4},{"id":12,"name":"Northern valid","probability":0.6}]}"#.utf8)
        let value = try WatchQuestionDetailDecoder.decode(payload, expectedID: 42)
        XCTAssertTrue(value.hasOmittedOutcomes)
        XCTAssertEqual(value.outcomes(matching: "northern").map(\.id), [12])
        XCTAssertEqual(value.outcomes(matching: "").map(\.id), [12])
    }
}
