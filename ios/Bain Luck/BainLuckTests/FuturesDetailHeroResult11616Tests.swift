import XCTest
@testable import Bain_Luck

/// Runtime guards for the Native hero/share adoption of the existing row rule.
/// These do not establish mounted SwiftUI or device acceptance.
final class FuturesDetailHeroResult11616Tests: XCTestCase {
    private func row(_ id: Int, _ name: String, price: Double? = nil,
                     won: Bool? = nil, source: String? = nil,
                     settlement: String? = nil, percent: Int? = nil,
                     updated: String? = nil) -> [String: Any] {
        var value: [String: Any] = ["id": id, "name": name,
            "probability": price.map { $0 as Any } ?? NSNull(),
            "is_winner": won.map { $0 as Any } ?? NSNull(),
            "resolution_source": source.map { $0 as Any } ?? NSNull()]
        if let settlement { value["settlement_display"] = ["verdict": settlement, "basis": "fixture"] }
        if let percent { value["rendered_percent"] = percent }
        if let updated { value["last_updated"] = updated }
        return value
    }

    private func market(_ outcomes: [[String: Any]], status: String = "resolved",
                        source: String = "kalshi", lead: Int? = nil,
                        verified: Bool = false, exclusive: Bool? = false,
                        shape: String? = nil, name: String = "Awards field") throws -> FuturesMarketDetail {
        var value: [String: Any] = ["id": 11616, "name": name, "status": status,
            "source": source, "outcomes": outcomes]
        if let shape { value["market_type"] = shape }
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

    /// lane1b N5: an open lead with a supported Won and NO price still leads.
    /// Root chose L3(c) (web admits this lead), not R2's rollback to
    /// `lead.probability != nil` — so this must keep passing.
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

    /// R1: a settled one-row board whose result is unknown names nobody; the
    /// hero says "Result unknown" for the board and the row keeps its last price.
    func testUnknownServedAndLegacyResultsAreNeverSharedAsLiveChances() throws {
        for served in [true, false] {
            let m = try market([row(1, "Victor", price: 0.5, won: false, source: "clob_authoritative",
                                    settlement: served ? "unknown" : nil)], source: "polymarket")
            XCTAssertNil(futuresDetailHeroOutcome(m), "\(served)")
            XCTAssertEqual(futuresDetailHeroValue(m, hero: nil), .resultUnknown(lastRecorded: nil))
            XCTAssertEqual(FuturesDetailRowValue.of(m.outcomes[0], marketStatus: m.status, marketSource: m.source),
                           .resultUnknown(lastRecorded: 0.5))
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
    /// as search's result tier does. Web at 0d239c9d's base did NOT: it led with
    /// its price `leader` (Shai 97%) over its own table's Victor Won. Root's
    /// disposition gives web's alignment to Lane1 (lane1b L3(a)); this pins iOS.
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

    // MARK: - N2 / R1: a settled board names its supported winner or nobody (web heroNamesNobody)

    /// Interim review N2: the Vuelta shape — every row lost at 0.0.
    func testResolvedMultiRowAllLostBoardNamesNobodyInHeroOrShare() throws {
        let m = try market([row(1, "Rider A", price: 0.0, won: false, source: "api_settlement"),
                            row(2, "Rider B", price: 0.0, won: false, source: "api_settlement"),
                            row(3, "Rider C", won: false, source: "api_settlement")])
        XCTAssertNil(futuresDetailHeroOutcome(m))
        XCTAssertEqual(futuresDetailShareMessage(m), "Awards field on Bain Luck")
        XCTAssertFalse(futuresDetailShareMessage(m).contains("Lost"))
    }

    /// R1(a), lane1b §2.3(a): mixed Lost/unknown names nobody, and — certainty
    /// only "some" — the hero has no board-level "Result unknown" either (web).
    /// 0d239c9d named the unknown row here.
    func testResolvedMixedLostAndUnknownBoardNamesNobody() throws {
        let m = try market([row(2, "Unknown", price: 0.0, won: false, source: "clob_authoritative",
                                settlement: "unknown"),
                            row(1, "Lost", price: 0.0, won: false, source: "clob_authoritative")], source: "polymarket")
        XCTAssertNil(futuresDetailHeroOutcome(m))
        XCTAssertEqual(SettledResultDisplay698.board(m), .some)
        XCTAssertEqual(futuresDetailHeroValue(m, hero: nil), .none)
        XCTAssertEqual(futuresDetailShareMessage(m), "Awards field on Bain Luck")
    }

    /// R1(a), lane1b §2.3(b): a settled board whose rows are ungraded but priced
    /// (Kalshi `is_winner` null) is not a forecast. Before R1 the hero printed a
    /// 52pt "60%" and a name under RESOLVED and shared "Yes at 60%"; web prints
    /// nothing. Multi-row and single-row alike.
    func testResolvedUngradedPricedBoardIsNeverANamedForecast() throws {
        for rows in [[row(1, "Yes", price: 0.6), row(2, "No", price: 0.4)], [row(1, "Yes", price: 0.6)]] {
            let m = try market(rows)
            XCTAssertNil(futuresDetailHeroOutcome(m), "\(rows.count) rows")
            XCTAssertNil(SettledResultDisplay698.board(m))
            XCTAssertEqual(futuresDetailHeroValue(m, hero: nil), .none)
            XCTAssertEqual(futuresDetailShareMessage(m), "Awards field on Bain Luck")
            XCTAssertFalse(futuresDetailShareMessage(m).contains("%"))
            // The rows below still print what they printed: the hero names nobody,
            // it does not reprice the table.
            XCTAssertEqual(FuturesDetailRowValue.of(m.outcomes[0], marketStatus: m.status, marketSource: m.source),
                           .price(0.6))
        }
    }

    /// The opposite direction: the same ungraded board with ONE supported winner
    /// served last and priced lowest still names that winner, not the price leader.
    func testResolvedBoardWithOneSupportedWinnerStillNamesIt() throws {
        let m = try market([row(1, "Yes", price: 0.6), row(2, "No", price: 0.4),
                            row(3, "Push", price: 0.01, won: true, source: "game_score")])
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 3)
        XCTAssertEqual(futuresDetailHeroValue(m, hero: futuresDetailHeroOutcome(m)), .verdict(.won))
        XCTAssertEqual(futuresDetailShareMessage(m), "Push: Won — Awards field on Bain Luck")
    }

    /// A settled one-row board with no grade and no price names nobody.
    func testResolvedSingleUnpricedUngradedRowNamesNobody() throws {
        let m = try market([row(1, "Yes")])
        XCTAssertNil(futuresDetailHeroOutcome(m))
        XCTAssertEqual(futuresDetailHeroValue(m, hero: nil), .none)
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

    // MARK: - B2 / #7906: an open peer board with several supported winners crowns none

    private static let bmw = "BMW PGA Championship - Make the Cut"

    /// lane1b `zzLane1bProbePeerOpen6430` (DELTA-REVIEW-6430a461 §3), both arms:
    /// open, `participation`, `mutually_exclusive: false`, no lead; Aberg and
    /// McIlroy Won on `api_settlement` at 1.0 (arm 1) or null (arm 2); Fleetwood
    /// and Rahm graded false at 0.0. Before B2 both arms heroed "Won · Ludvig
    /// Aberg" and shared "Ludvig Aberg: Won — …" (00791f95 / 6430a461 iOS tree).
    private func peerOpenBoard(winnersPriced: Bool, updated: (String?, String?) = (nil, nil)) throws -> FuturesMarketDetail {
        let price: Double? = winnersPriced ? 1.0 : nil
        return try market([row(1, "Ludvig Aberg", price: price, won: true, source: "api_settlement"),
                           row(2, "Tommy Fleetwood", price: 0.0, won: false, source: "api_settlement",
                               updated: updated.0),
                           row(3, "Rory McIlroy", price: price, won: true, source: "api_settlement"),
                           row(4, "Jon Rahm", price: 0.0, won: false, source: "api_settlement",
                               updated: updated.1)],
                          status: "open", exclusive: false, shape: "participation", name: Self.bmw)
    }

    func testAnOpenPeerBoardWithSeveralSupportedWinnersNamesNoneInHeroOrShare() throws {
        for priced in [true, false] {
            let m = try peerOpenBoard(winnersPriced: priced)
            XCTAssertNil(futuresDetailHeroOutcome(m), "priced=\(priced)")
            // No crown and no winner's last price promoted to a forecast.
            XCTAssertEqual(futuresDetailHeroValue(m, hero: nil), .none, "priced=\(priced)")
            let share = futuresDetailShareMessage(m)
            XCTAssertEqual(share, "\(Self.bmw) on Bain Luck", "priced=\(priced)")
            XCTAssertFalse(share.contains("Won"), "priced=\(priced)")
            XCTAssertFalse(share.contains("%"), "priced=\(priced)")
            // Every successful participant keeps its own Won row.
            let values = m.outcomes.map { FuturesDetailRowValue.of($0, marketStatus: m.status, marketSource: m.source) }
            XCTAssertEqual(values, [.verdict(.won), .price(0.0), .verdict(.won), .price(0.0)], "priced=\(priced)")
        }
    }

    /// The saved card consumes the page's hero, so it names no winner either and
    /// stays an open card; both winners keep their Won and lead the rows.
    func testTheSavedCardOfAnOpenPeerBoardNamesNoWinnerAndKeepsBothWonRows() throws {
        for priced in [true, false] {
            let card = FeedFuturesData(savedPinDetail: try peerOpenBoard(winnersPriced: priced))
            XCTAssertNil(card.winner, "priced=\(priced)")
            XCTAssertEqual(card.topOutcomes?.prefix(2).map(\.id), [1, 3], "priced=\(priced)")
            XCTAssertEqual(card.topOutcomes?.prefix(2).map(\.detailValue), [.verdict(.won), .verdict(.won)])
        }
    }

    /// The shape survives the reconciliation rebuild (a preserved older quote
    /// re-composes the body through the memberwise init), so a refresh cannot
    /// bring the crown back.
    func testThePeerShapeSurvivesAReconciledRefresh() throws {
        let held = try peerOpenBoard(winnersPriced: true,
                                     updated: ("2026-09-22T06:45:00Z", "2026-09-22T06:45:00Z"))
        let incoming = try peerOpenBoard(winnersPriced: true,
                                         updated: ("2026-09-22T06:40:00Z", "2026-09-22T06:45:00Z"))
        let adopted = FuturesPriceReconciliation.adopting(incoming, over: held)
        XCTAssertEqual(adopted.marketType, "participation")
        XCTAssertNil(futuresDetailHeroOutcome(adopted))
    }

    /// Opposite: a participation board with exactly ONE supported winner keeps its
    /// crown, as web `gradedWinner` allows.
    func testAnOpenPeerBoardWithOneSupportedWinnerKeepsItsCrown() throws {
        let m = try market([row(1, "Ludvig Aberg", won: true, source: "api_settlement"),
                            row(2, "Tommy Fleetwood", price: 0.0, won: false, source: "api_settlement")],
                           status: "open", exclusive: false, shape: "participation", name: Self.bmw)
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
        XCTAssertEqual(try value(m), .verdict(.won))
        XCTAssertEqual(futuresDetailShareMessage(m), "Ludvig Aberg: Won — \(Self.bmw) on Bain Luck")
    }

    /// Opposite: an unsupported raw flag cannot manufacture the second winner.
    func testAnUnsupportedRawFlagDoesNotCountTowardSeveralWinners() throws {
        let m = try market([row(1, "Flagged", won: true),
                            row(2, "Ludvig Aberg", won: true, source: "api_settlement"),
                            row(3, "Retracted", won: true, source: "ungradeable_result")],
                           status: "open", exclusive: false, shape: "participation")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2)
        XCTAssertEqual(try value(m), .verdict(.won))
    }

    /// Opposite: a genuine live, priced, ungraded row still leads the peer board.
    func testAGenuineLiveRowStillLeadsAnOpenPeerBoardWithSeveralWinners() throws {
        let m = try market([row(1, "Ludvig Aberg", price: 1.0, won: true, source: "api_settlement"),
                            row(2, "Still playing", price: 0.42),
                            row(3, "Rory McIlroy", price: 1.0, won: true, source: "api_settlement")],
                           status: "open", exclusive: false, shape: "participation")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 2)
        XCTAssertEqual(try value(m), .price(0.42))
    }

    /// The contradiction door: an affirmative exclusivity claim contradicted by
    /// two supported winners names neither (#6590 / #4923). One winner on the
    /// same claim is `testOpenExclusiveOrUnstatedBoardStillLeadsWithItsSupportedWinner`.
    func testAnOpenExclusiveBoardWithTwoSupportedWinnersNamesNeither() throws {
        let m = try market([row(1, "SK Beveren", won: true, source: "api_settlement"),
                            row(2, "Draw", won: true, source: "api_settlement"),
                            row(3, "Away", price: 0.2)], status: "open", exclusive: true)
        XCTAssertNil(futuresDetailHeroOutcome(m))
        XCTAssertEqual(futuresDetailShareMessage(m), "Awards field on Bain Luck")
    }

    /// Opposite: with no affirming shape and no `true` claim (a ladder, a grouped
    /// independent board), plural winners are the design and served order holds
    /// — the same input as `testAnOpenBoardKeepsServedOrderAmongItsSupportedWinners`
    /// (8280), and the shape door is keyed positively, never "anything but quantity".
    func testWithoutAPeerShapeOrAnExclusivityClaimSeveralOpenWinnersKeepServedOrder() throws {
        for shape in [nil, "quantity", "duel", "field"] as [String?] {
            let m = try market([row(1, "77° or above", won: true, source: "api_settlement"),
                                row(2, "78° or above", won: true, source: "api_settlement")],
                               status: "open", exclusive: false, shape: shape)
            XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1, "\(String(describing: shape))")
        }
    }
}
