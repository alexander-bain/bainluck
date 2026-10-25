import XCTest
@testable import Bain_Luck

/// Runtime guards for the Native hero/share adoption of the existing row rule.
/// These do not establish mounted SwiftUI or device acceptance.
final class FuturesDetailHeroResult11616Tests: XCTestCase {
    private func row(_ id: Int, _ name: String, price: Double? = nil,
                     won: Bool? = nil, source: String? = nil,
                     settlement: String? = nil, percent: Int? = nil) -> [String: Any] {
        var value: [String: Any] = ["id": id, "name": name,
            "probability": price.map { $0 as Any } ?? NSNull(),
            "is_winner": won.map { $0 as Any } ?? NSNull(),
            "resolution_source": source.map { $0 as Any } ?? NSNull()]
        if let settlement { value["settlement_display"] = ["verdict": settlement, "basis": "fixture"] }
        if let percent { value["rendered_percent"] = percent }
        return value
    }

    private func market(_ outcomes: [[String: Any]], status: String = "resolved",
                        source: String = "kalshi", lead: Int? = nil,
                        verified: Bool = false) throws -> FuturesMarketDetail {
        var value: [String: Any] = ["id": 11616, "name": "Awards field", "status": status,
            "source": source, "outcomes": outcomes, "mutually_exclusive": false]
        if let lead { value["lead_outcome_id"] = lead }
        if verified { value["representation"] = "verified_title" }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FuturesMarketDetail.self, from: JSONSerialization.data(withJSONObject: value))
    }

    private func value(_ market: FuturesMarketDetail) throws -> FuturesDetailRowValue {
        let leader = try XCTUnwrap(futuresDetailHeroOutcome(market))
        return FuturesDetailRowValue.of(leader, marketStatus: market.status, marketSource: market.source)
    }

    func testUnpricedWinnerLeadsAheadOfPricedLoserAndSharesItsResult() throws {
        let m = try market([row(1, "Shai", price: 0.8, won: false, source: "api_settlement"),
                            row(2, "Victor", won: true, source: "api_settlement")])
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2)
        XCTAssertEqual(try value(m), .verdict(.won))
        XCTAssertEqual(futuresDetailShareMessage(m), "Victor: Won — Awards field on Bain Luck")
    }

    func testOpenAuthoritativeWinnerNeedsNoPrice() throws {
        let m = try market([row(1, "Victor", won: true, source: "api_settlement")], status: "open")
        XCTAssertEqual(try value(m), .verdict(.won))
        XCTAssertFalse(try value(m).printsMovement)
        XCTAssertFalse(futuresDetailShareMessage(m).contains("%"))
    }

    func testNearCertainSettledWinnerIsAResultNotAPrediction() throws {
        let m = try market([row(1, "Victor", price: 0.999, won: true, source: "game_score")])
        XCTAssertEqual(try value(m), .verdict(.won))
        XCTAssertEqual(futuresDetailShareMessage(m), "Victor: Won — Awards field on Bain Luck")
    }

    func testUnpricedLossIsAResultAndIsSharedAsLost() throws {
        let m = try market([row(1, "Victor", won: false, source: "api_settlement")])
        XCTAssertEqual(try value(m), .verdict(.lost))
        XCTAssertEqual(futuresDetailShareMessage(m), "Victor: Lost — Awards field on Bain Luck")
    }

    func testIndependentWinnersRetainServedOrderWithoutRepricing() throws {
        let m = try market([row(1, "Victor", won: true, source: "api_settlement"),
                            row(2, "Shai", price: 0.9, won: true, source: "api_settlement")])
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
        XCTAssertEqual(m.outcomes[1].probability, 0.9)
        XCTAssertEqual(m.outcomes.count, 2)
    }

    func testExplicitOpenMatchWinnerLeadWinsOverAnUnrelatedGradedProp() throws {
        let m = try market([row(1, "Match winner", price: 0.355),
                            row(2, "Prop", price: 0.99, won: true, source: "api_settlement")], status: "open", lead: 1)
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
        XCTAssertEqual(try value(m), .price(0.355))
    }

    func testExplicitOpenLeadRetainsItsUnpricedSupportedResult() throws {
        let m = try market([row(1, "Match winner", won: true, source: "api_settlement"),
                            row(2, "Prop", price: 0.9)], status: "open", lead: 1)
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
        XCTAssertEqual(try value(m), .verdict(.won))
    }

    func testUnsupportedUnpricedLeadStillFallsBackToPrice() throws {
        let m = try market([row(1, "Match winner"), row(2, "Prop", price: 0.9)], status: "open", lead: 1)
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2)
        XCTAssertEqual(try value(m), .price(0.9))
    }

    func testResolvedMarketIgnoresOldLeadAndFindsSupportedWinner() throws {
        let m = try market([row(1, "Old lead", price: 0.9, won: false, source: "api_settlement"),
                            row(2, "Victor", won: true, source: "api_settlement")], lead: 1)
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2)
    }

    func testUnknownServedAndLegacyResultsAreNeverSharedAsLiveChances() throws {
        for served in [true, false] {
            let m = try market([row(1, "Victor", price: 0.5, won: false, source: "clob_authoritative",
                                    settlement: served ? "unknown" : nil)], source: "polymarket")
            XCTAssertEqual(try value(m), .resultUnknown(lastRecorded: 0.5))
            XCTAssertEqual(futuresDetailShareMessage(m), "Awards field on Bain Luck")
        }
    }

    func testUnpricedExplicitResultUsesStoredContract() throws {
        let m = try market([row(1, "Victor", won: true, source: "clob_authoritative", settlement: "won")], source: "polymarket")
        XCTAssertEqual(try value(m), .verdict(.won))
        XCTAssertEqual(futuresDetailShareMessage(m), "Victor: Won — Awards field on Bain Luck")
    }

    func testRetractionMissingSourceAndOpenDefaultLossAreNotInventedResults() throws {
        for source in [nil, "ungradeable_result", "unknown_source"] {
            let m = try market([row(1, "Victor", won: true, source: source), row(2, "Shai", price: 0.4)], status: "open")
            XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2)
            XCTAssertEqual(try value(m), .price(0.4))
        }
        let uncalled = try market([row(1, "Victor", price: 0.4, won: false, source: "api_settlement")], status: "open")
        XCTAssertEqual(try value(uncalled), .price(0.4))
    }

    func testVerifiedSharesStillOmitQuoteAndResult() throws {
        let m = try market([row(1, "Victor", price: 0.99, won: true, source: "api_settlement")], verified: true)
        XCTAssertEqual(futuresDetailShareMessage(m), "Awards field on Bain Luck")
    }

    func testUnsettledSharesUseTheFullFieldIntegerAndBoundaryLabel() throws {
        let rounded = try market([row(1, "Victor", price: 0.395, percent: 39)], status: "open")
        XCTAssertEqual(futuresDetailShareMessage(rounded), "Victor at 39% — Awards field on Bain Luck")
        let nearCertain = try market([row(1, "Victor", price: 0.999)], status: "open")
        XCTAssertEqual(futuresDetailShareMessage(nearCertain), "Victor at >99% — Awards field on Bain Luck")
    }

    func testEmptyAndMissingMarketsKeepHonestShareFallbacks() throws {
        let empty = try market([])
        XCTAssertNil(futuresDetailHeroOutcome(empty))
        XCTAssertEqual(futuresDetailShareMessage(empty), "Awards field on Bain Luck")
        XCTAssertEqual(futuresDetailShareMessage(nil), "Check this out on Bain Luck")
    }
}
