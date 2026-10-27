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
                        verified: Bool = false, exclusive: Bool? = false) throws -> FuturesMarketDetail {
        var value: [String: Any] = ["id": 11616, "name": "Awards field", "status": status,
            "source": source, "outcomes": outcomes]
        if let exclusive { value["mutually_exclusive"] = exclusive }
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

    // MARK: - N1: an open independent board leads with its live leader (web + search)

    /// Interim review N1: rung A ungraded at 0.97, rung B graded won at 0.95.
    /// Web `pickHeroOutcome` and search `_demote_graded` both lead with A.
    func testOpenIndependentBoardLeadsWithTheLiveRungNotTheGradedOne() throws {
        let m = try market([row(1, "Above 4.25%", price: 0.97),
                            row(2, "Above 4.00%", price: 0.95, won: true, source: "api_settlement")], status: "open")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
        XCTAssertEqual(try value(m), .price(0.97))
        XCTAssertEqual(futuresDetailShareMessage(m), "Above 4.25% at 97% — Awards field on Bain Luck")
        // The graded rung keeps its own result on its row.
        XCTAssertEqual(FuturesDetailRowValue.of(m.outcomes[1], marketStatus: m.status, marketSource: m.source),
                       .verdict(.won))
    }

    /// Served order does not matter: the graded rung served FIRST still does not lead.
    func testOpenIndependentBoardIgnoresServedOrderOfTheGradedRung() throws {
        let m = try market([row(2, "Above 4.00%", price: 0.95, won: true, source: "api_settlement"),
                            row(1, "Above 4.25%", price: 0.4)], status: "open")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
    }

    /// Web's second clause: a live row at 0% is not a live leader, so the
    /// graded result still answers.
    func testOpenIndependentBoardWhoseLiveRungsAreAllZeroKeepsTheResult() throws {
        let m = try market([row(1, "Above 60", price: 0.0),
                            row(2, "Above 56", price: 0.9995, won: true, source: "api_settlement")], status: "open")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2)
        XCTAssertEqual(try value(m), .verdict(.won))
    }

    /// An exclusive (or unstated) open board is answered by its supported winner,
    /// as web keeps it and as search's result tier does.
    func testOpenExclusiveOrUnstatedBoardStillLeadsWithItsSupportedWinner() throws {
        for exclusive in [true, nil] as [Bool?] {
            let m = try market([row(1, "Shai", price: 0.97),
                                row(2, "Victor", price: 0.95, won: true, source: "api_settlement")],
                               status: "open", exclusive: exclusive)
            XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2, "\(String(describing: exclusive))")
        }
    }

    /// A raw `is_winner` with no supported source is neither the live leader nor a winner.
    func testOpenIndependentBoardSkipsAnUnsupportedWinnerFlagAsWebDoes() throws {
        let m = try market([row(1, "Flagged", price: 0.9, won: true),
                            row(2, "Live", price: 0.3)], status: "open")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2)
        XCTAssertEqual(try value(m), .price(0.3))
    }

    // MARK: - N2: a resolved board of several losers names nobody (web heroNamesNobody)

    /// Interim review N2: the Vuelta shape — every row lost at 0.0.
    func testResolvedMultiRowAllLostBoardNamesNobodyInHeroOrShare() throws {
        let m = try market([row(1, "Rider A", price: 0.0, won: false, source: "api_settlement"),
                            row(2, "Rider B", price: 0.0, won: false, source: "api_settlement"),
                            row(3, "Rider C", won: false, source: "api_settlement")])
        XCTAssertNil(futuresDetailHeroOutcome(m))
        XCTAssertEqual(futuresDetailShareMessage(m), "Awards field on Bain Luck")
        XCTAssertFalse(futuresDetailShareMessage(m).contains("Lost"))
    }

    /// A resolved board with no winner never heroes a LOST row over one whose
    /// result is unknown; the unknown row keeps the explicit "Result unknown".
    /// The loser is served LAST so `max(by:)`'s last-of-ties cannot pass this.
    func testResolvedBoardWithoutWinnerPrefersAnUnknownRowOverALoser() throws {
        let m = try market([row(2, "Unknown", price: 0.0, won: false, source: "clob_authoritative",
                                settlement: "unknown"),
                            row(1, "Lost", price: 0.0, won: false, source: "clob_authoritative")], source: "polymarket")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2)
        XCTAssertEqual(try value(m), .resultUnknown(lastRecorded: 0.0))
        XCTAssertEqual(futuresDetailShareMessage(m), "Awards field on Bain Luck")
    }

    /// The justified single-row case is unchanged: that row IS the question.
    func testResolvedSingleRowLossStillReadsLost() throws {
        let m = try market([row(1, "Yes", price: 0.0, won: false, source: "api_settlement")])
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
        XCTAssertEqual(try value(m), .verdict(.lost))
        XCTAssertEqual(futuresDetailShareMessage(m), "Yes: Lost — Awards field on Bain Luck")
    }

    /// A tie on price leads with the first row in served order, as web's sort.
    func testAPriceTieLeadsWithTheFirstServedRow() throws {
        let m = try market([row(1, "First", price: 0.4), row(2, "Second", price: 0.4)],
                           status: "open", exclusive: true)
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
    }

    // MARK: - N4: a repeated outcome id never traps

    func testARepeatedOutcomeIdKeepsTheFirstServedIntegerWithoutTrapping() throws {
        let m = try market([row(1, "Victor", price: 0.6, percent: 60),
                            row(2, "Shai", price: 0.4, percent: 40),
                            row(1, "Victor", price: 0.61, percent: 61)], status: "open", exclusive: true)
        let percents = futuresDetailRenderedPercents(m.outcomes)
        XCTAssertEqual(percents, [1: 60, 2: 40])
        // The served integers are read, never recomputed for the subset.
        XCTAssertEqual(futuresDetailRenderedPercents(Array(m.outcomes.prefix(1))), [1: 60])
    }

    func testARepeatedOutcomeIdOnALegacyPayloadIsDeterministic() throws {
        let m = try market([row(1, "Victor", price: 0.6), row(2, "Shai", price: 0.4),
                            row(1, "Victor", price: 0.6)], status: "open", exclusive: true)
        let first = futuresDetailRenderedPercents(m.outcomes)
        XCTAssertEqual(Set(first.keys), [1, 2])
        for _ in 0..<5 { XCTAssertEqual(futuresDetailRenderedPercents(m.outcomes), first) }
    }

    func testEmptyAndMissingMarketsKeepHonestShareFallbacks() throws {
        let empty = try market([])
        XCTAssertNil(futuresDetailHeroOutcome(empty))
        XCTAssertEqual(futuresDetailShareMessage(empty), "Awards field on Bain Luck")
        XCTAssertEqual(futuresDetailShareMessage(nil), "Check this out on Bain Luck")
    }
}
