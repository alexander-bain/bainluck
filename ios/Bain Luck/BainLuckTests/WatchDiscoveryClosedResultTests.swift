import Foundation
import XCTest
@testable import Bain_Luck

final class WatchDiscoveryClosedResultTests: XCTestCase {
    private func reading(status: String, extra: String = "") throws -> WatchDiscoveryReading {
        let json = """
        {"items":[{"type":"futures","data":{"id":81,"name":"Question",
        "status":"\(status)","top_outcomes":[{"name":"Yes","probability":0.64,
        "price_observed_at":"2026-10-05T12:00:00Z"}]\(extra)}}]}
        """
        return try XCTUnwrap(WatchDiscoveryDecoder.decode(Data(json.utf8)).first)
    }

    func testClosedWithoutResolutionDoesNotClaimSettlementOrReusePrice() throws {
        for extra in ["", ",\"resolved\":false", ",\"winner\":\" \"", ",\"resolution_date\":\"2020-01-01T00:00:00Z\""] {
            let value = try reading(status: "closed", extra: extra)
            XCTAssertEqual(value.resultUnconfirmed, true)
            XCTAssertEqual(value.resultLabel, "Result unconfirmed")
            XCTAssertNil(value.probability)
            XCTAssertNil(value.observedAt)
            let card = WatchDiscoveryCardPresentation(reading: value, now: Date(timeIntervalSince1970: 1_800_000_000))
            XCTAssertEqual(card.result, "Result unconfirmed")
            XCTAssertNil(card.probability)
            XCTAssertEqual(card.observation, "Observation time unavailable")
        }
    }

    func testExplicitResolutionAndWinnerRetainExistingResultPolicy() throws {
        let resolved = try reading(status: "closed", extra: ",\"resolved\":true")
        XCTAssertNil(resolved.resultUnconfirmed)
        XCTAssertEqual(resolved.resultLabel, "Settled · Result unavailable")
        let winner = try reading(status: "closed", extra: ",\"winner\":\" Yes \"")
        XCTAssertNil(winner.resultUnconfirmed)
        XCTAssertEqual(winner.resultLabel, "Result: Yes")
        XCTAssertEqual(WatchDiscoveryCardPresentation(reading: winner, now: Date(timeIntervalSince1970: 1_800_000_000)).result, "Result: Yes")
    }

    func testOpenAndResolvedResponsesKeepExistingMeaning() throws {
        let open = try reading(status: "open")
        XCTAssertNil(open.resultUnconfirmed)
        XCTAssertFalse(open.isSettled)
        XCTAssertEqual(open.probability, 0.64)
        XCTAssertNotNil(open.observedAt)
        XCTAssertNil(open.resultLabel)
        let resolved = try reading(status: "resolved")
        XCTAssertNil(resolved.resultUnconfirmed)
        XCTAssertEqual(resolved.resultLabel, "Settled · Result unavailable")
        XCTAssertNil(resolved.probability)
    }

    func testUnconfirmedClosureSurvivesSavedRoundTrip() throws {
        let value = try reading(status: "closed")
        let restored = try JSONDecoder().decode(WatchDiscoveryReading.self,
                                                from: JSONEncoder().encode(value))
        XCTAssertEqual(restored, value)
        XCTAssertEqual(WatchDiscoveryCardPresentation(reading: restored, now: Date(timeIntervalSince1970: 1_800_000_000)).result, "Result unconfirmed")
        XCTAssertNil(restored.probability)
        XCTAssertNil(restored.observedAt)
    }

    func testLegacySavedReadingWithoutNewFieldStillDecodes() throws {
        let json = """
        {"id":81,"question":"Question","isSettled":true}
        """
        let restored = try JSONDecoder().decode(WatchDiscoveryReading.self, from: Data(json.utf8))
        XCTAssertNil(restored.resultUnconfirmed)
        XCTAssertEqual(restored.resultLabel, "Settled · Result unavailable")
        XCTAssertNil(restored.probability)
    }
}
