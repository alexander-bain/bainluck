import XCTest
@testable import Bain_Luck

/// Same wire state must retain the same result on search and Market Details.
final class SearchResultParity11616Tests: XCTestCase {
    private func market(_ rows: String, status: String = "open", source: String = "kalshi") throws -> SearchFuturesMarket {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchFuturesMarket.self, from: Data("""
        {"id":11616,"name":"Award winner","status":"\(status)","source":"\(source)","top_outcomes":[\(rows)],"outcome_count":2}
        """.utf8))
    }

    func testAnUnpricedAuthoritativeWinnerRemainsTheFamilyAnswer() throws {
        let m = try market(#"{"id":1,"name":"Victor","probability":null,"is_winner":true,"resolution_source":"api_settlement"}"#)
        let leader = try XCTUnwrap(SearchGrouping.leaderOutcome(m))
        XCTAssertEqual(leader.id, 1)
        XCTAssertNil(leader.probability)
        XCTAssertEqual(leader.verdict(in: m), .won)
    }

    func testAResolvedPolymarketUnknownNeverBecomesLost() throws {
        let m = try market(#"{"id":1,"name":"Over","probability":0.5,"is_winner":false,"resolution_source":"clob_authoritative","settlement_display":{"verdict":"unknown","basis":"nonterminal_stored_price"}}"#, status: "resolved", source: "polymarket")
        let leader = try XCTUnwrap(SearchGrouping.leaderOutcome(m))
        XCTAssertNil(leader.verdict(in: m))
    }

    func testAbsentContractKeepsDetailsConservativePolymarketFallback() throws {
        let m = try market(#"{"id":1,"name":"Over","probability":0.5,"is_winner":false,"resolution_source":"clob_authoritative"}"#, status: "resolved", source: "polymarket")
        XCTAssertNil(try XCTUnwrap(m.topOutcomes?.first).verdict(in: m))
    }

    func testZeroAndNearCertaintyRemainPredictions() throws {
        for probability in [0.0, 0.999] {
            let m = try market("""
            {"id":1,"name":"Victor","probability":\(probability),"is_winner":false,"resolution_source":null}
            """)
            let leader = try XCTUnwrap(SearchGrouping.leaderOutcome(m))
            XCTAssertEqual(leader.probability, probability)
            XCTAssertNil(leader.verdict(in: m))
        }
    }

    func testNoPriceAndNoSupportedResultDoesNotBecomeAnAnswer() throws {
        for source in ["null", #""ungradeable_result""#, #""unknown_source""#] {
            let m = try market("""
            {"id":1,"name":"Victor","probability":null,"is_winner":true,"resolution_source":\(source)}
            """)
            XCTAssertNil(SearchGrouping.leaderOutcome(m))
        }
    }

    func testSearchAndDetailUseTheSameDecodedEvidence() throws {
        let rows = [
            #"{"id":1,"name":"Victor","probability":null,"is_winner":true,"resolution_source":"api_settlement"}"#,
            #"{"id":1,"name":"Victor","probability":null,"is_winner":false,"resolution_source":"api_settlement"}"#,
            #"{"id":1,"name":"Victor","probability":0.5,"is_winner":false,"resolution_source":"clob_authoritative","settlement_display":{"verdict":"unknown","basis":"nonterminal_stored_price"}}"#,
            #"{"id":1,"name":"Victor","probability":1,"is_winner":true,"resolution_source":"clob_authoritative"}"#,
            #"{"id":1,"name":"Victor","probability":0,"is_winner":false,"resolution_source":"clob_authoritative"}"#,
            #"{"id":1,"name":"Victor","probability":0.5,"is_winner":false,"resolution_source":"clob_authoritative"}"#,
            #"{"id":1,"name":"Victor","probability":0.999,"is_winner":false,"resolution_source":null}"#,
            #"{"id":1,"name":"Victor","probability":null,"is_winner":true,"resolution_source":"ungradeable_result"}"#,
        ]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        for source in ["kalshi", "polymarket"] {
            for status in ["open", "resolved"] {
                for row in rows {
                    let m = try market(row, status: status, source: source)
                    let search = try XCTUnwrap(m.topOutcomes?.first)
                    let detail = try decoder.decode(FuturesOutcome.self, from: Data(row.utf8))
                    XCTAssertEqual(search.rowValue(in: m), FuturesDetailRowValue.of(detail, marketStatus: status, marketSource: source), "\(source) / \(status) / \(row)")
                }
            }
        }
    }

    func testAnUnpricedResolvedLossAndAnUnknownStillHaveAnswers() throws {
        let loss = try market(#"{"id":1,"name":"Victor","probability":null,"is_winner":false,"resolution_source":"api_settlement"}"#, status: "resolved")
        XCTAssertEqual(try XCTUnwrap(SearchGrouping.leaderOutcome(loss)).rowValue(in: loss), .verdict(.lost))
        let unknown = try market(#"{"id":1,"name":"Victor","probability":null,"is_winner":false,"resolution_source":"clob_authoritative","settlement_display":{"verdict":"unknown","basis":"missing_stored_price"}}"#, status: "resolved", source: "polymarket")
        XCTAssertEqual(try XCTUnwrap(SearchGrouping.leaderOutcome(unknown)).rowValue(in: unknown), .resultUnknown(lastRecorded: nil))
    }

    func testAnOpenBoardFalseCannotBecomeLost() throws {
        let m = try market(#"{"id":1,"name":"Victor","probability":null,"is_winner":false,"resolution_source":"api_settlement"}"#)
        XCTAssertEqual(try XCTUnwrap(m.topOutcomes?.first).rowValue(in: m), .none)
        XCTAssertNil(SearchGrouping.leaderOutcome(m))
    }

    func testNewOrMalformedContractCannotInventAResultOrEraseSiblings() throws {
        for display in [#"{"verdict":"new_word"}"#, #"{"verdict":7}"#, #"{}"#, #""won""#, "null"] {
            let m = try market("""
            {"id":1,"name":"Victor","probability":0.5,"is_winner":true,"resolution_source":"clob_authoritative","settlement_display":\(display)},
            {"id":2,"name":"Shai","probability":1,"is_winner":true,"resolution_source":"clob_authoritative"}
            """, status: "resolved", source: "polymarket")
            XCTAssertEqual(m.topOutcomes?.count, 2)
            XCTAssertEqual(try XCTUnwrap(m.topOutcomes?.first).rowValue(in: m), .resultUnknown(lastRecorded: 0.5), display)
            XCTAssertEqual(m.topOutcomes?[1].rowValue(in: m), .verdict(.won))
        }
    }

    func testWireOrderAndDestinationSurviveResultSelection() throws {
        let m = try market(#"{"id":1,"name":"Victor","probability":null,"is_winner":true,"resolution_source":"api_settlement"},{"id":2,"name":"Shai","probability":0.6,"is_winner":false,"resolution_source":null}"#)
        XCTAssertEqual(m.id, 11616)
        XCTAssertEqual(m.topOutcomes?.map(\.id), [1, 2])
        XCTAssertEqual(SearchGrouping.leaderOutcome(m)?.id, 1)
        XCTAssertEqual(m.topOutcomes?.map(\.id), [1, 2])
        XCTAssertEqual(m.topOutcomes?[1].rowValue(in: m), .price(0.6))
    }
}
