import XCTest
@testable import Bain_Luck

/// #10964 — a settled market's Market Details rows printed a leftover quote or
/// nothing, never Won/Lost.
///
/// Production `/api/futures/54069274` "Boston vs Detroit: Team Total" (Kalshi,
/// resolved; Boston 10, Detroit 3), read 2026-10-13 11:04Z: nine legs served
/// `is_winner: true` and five `false`, all `resolution_source: "game_score"`.
/// The app drew the winners as `✓ >99%`, Detroit over 3.5/7.5 as `1%`, and
/// Detroit over 4.5/5.5/6.5 (price null) as a bare name.
final class MarketDetailsGradedRowsSayWonOrLost10964Tests: XCTestCase {

    // MARK: - Harness

    /// The served payload, every leg in payload order with the keys the row
    /// reads. `status` and `source` are parameters only for the controls.
    private func bostonDetroit(status: String = "resolved") throws -> FuturesMarketDetail {
        func leg(_ id: Int, _ name: String, _ p: String, _ won: Bool) -> String {
            """
            {"id": \(id), "name": "\(name) runs scored", "probability": \(p),
             "is_winner": \(won), "resolution_source": "game_score"}
            """
        }
        let legs = [
            leg(202058556, "Detroit over 1.5", "0.995", true),
            leg(202058557, "Detroit over 2.5", "0.995", true),
            leg(202058558, "Boston over 1.5", "0.995", true),
            leg(202058559, "Boston over 2.5", "0.995", true),
            leg(202058560, "Boston over 3.5", "0.995", true),
            leg(202058561, "Boston over 4.5", "0.995", true),
            leg(202058562, "Boston over 5.5", "0.995", true),
            leg(202058563, "Boston over 6.5", "0.995", true),
            leg(202058564, "Boston over 7.5", "0.995", true),
            leg(202058565, "Detroit over 5.5", "null", false),
            leg(202058566, "Detroit over 6.5", "null", false),
            leg(202058567, "Detroit over 4.5", "null", false),
            leg(202058568, "Detroit over 3.5", "0.01", false),
            leg(202058569, "Detroit over 7.5", "0.01", false),
        ].joined(separator: ",\n")
        let json = """
        {
          "id": 54069274,
          "name": "Boston vs Detroit: Team Total",
          "status": "\(status)",
          "source": "kalshi",
          "mutually_exclusive": false,
          "lead_outcome_id": null,
          "outcomes": [\(legs)]
        }
        """
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FuturesMarketDetail.self, from: Data(json.utf8))
    }

    private func outcome(
        isWinner: String = "null",
        source: String = "null",
        probability: String = "0.4"
    ) throws -> FuturesOutcome {
        let json = """
        {"id": 1, "name": "Leg", "probability": \(probability),
         "is_winner": \(isWinner), "resolution_source": \(source)}
        """
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FuturesOutcome.self, from: Data(json.utf8))
    }

    private func values(_ market: FuturesMarketDetail) -> [String: FuturesDetailRowValue] {
        Dictionary(uniqueKeysWithValues: market.outcomes.map {
            ($0.name, FuturesDetailRowValue.of($0, marketStatus: market.status))
        })
    }

    // MARK: - The specimen

    func test_resolutionSourceReachesTheModel() throws {
        let market = try bostonDetroit()
        XCTAssertEqual(market.outcomes.count, 14)
        XCTAssertTrue(market.outcomes.allSatisfy { $0.resolutionSource == "game_score" },
                      "`resolution_source` must decode under convertFromSnakeCase")
    }

    func test_everyWinnerSaysWonNotItsLastQuote() throws {
        let v = values(try bostonDetroit())
        for name in ["Detroit over 1.5", "Detroit over 2.5", "Boston over 1.5", "Boston over 2.5",
                     "Boston over 3.5", "Boston over 4.5", "Boston over 5.5", "Boston over 6.5",
                     "Boston over 7.5"] {
            XCTAssertEqual(v["\(name) runs scored"], .verdict(.won), name)
        }
    }

    func test_everyLoserSaysLost_pricedAndUnpricedAlike() throws {
        let v = values(try bostonDetroit())
        // 3.5 / 7.5 printed `1%`; 4.5 / 5.5 / 6.5 printed nothing.
        for name in ["Detroit over 3.5", "Detroit over 7.5",
                     "Detroit over 4.5", "Detroit over 5.5", "Detroit over 6.5"] {
            XCTAssertEqual(v["\(name) runs scored"], .verdict(.lost), name)
        }
    }

    func test_aGradedRowPrintsNoMovement() throws {
        let v = values(try bostonDetroit())
        XCTAssertTrue(v.values.allSatisfy { !$0.printsMovement })
        XCTAssertEqual(FuturesDetailRowValue.verdict(.won).label, "Won")
        XCTAssertEqual(FuturesDetailRowValue.verdict(.lost).label, "Lost")
    }

    // MARK: - Controls: the rule withholds where it cannot prove a grade

    /// The same board while still open: a defaulted `false` is not a loss, and a
    /// non-authoritative `true` is not a settlement (#6082). Every row prints
    /// what it printed before this change — its price, or nothing.
    func test_stillLive_sameBoardPrintsPrices() throws {
        let market = try bostonDetroit(status: "open")
        for o in market.outcomes {
            let value = FuturesDetailRowValue.of(o, marketStatus: market.status)
            if let p = o.probability {
                XCTAssertEqual(value, .price(p), o.name)
            } else {
                XCTAssertEqual(value, FuturesDetailRowValue.none, o.name)
            }
            XCTAssertTrue(value.printsMovement, o.name)
        }
    }

    func test_openMarket_authoritativeWinnerStillSaysWon() throws {
        let o = try outcome(isWinner: "true", source: "\"api_settlement\"", probability: "0.98")
        XCTAssertEqual(FuturesDetailRowValue.of(o, marketStatus: "open"), .verdict(.won))
        let loser = try outcome(isWinner: "false", source: "\"api_settlement\"", probability: "0.02")
        XCTAssertEqual(FuturesDetailRowValue.of(loser, marketStatus: "open"), .price(0.02))
    }

    func test_unknownGrade_withholds() throws {
        // Resolved market, `is_winner: null`: no result is invented.
        let priced = try outcome(isWinner: "null", source: "\"game_score\"", probability: "0.3")
        XCTAssertEqual(FuturesDetailRowValue.of(priced, marketStatus: "resolved"), .price(0.3))
        let unpriced = try outcome(isWinner: "null", source: "\"game_score\"", probability: "null")
        XCTAssertEqual(FuturesDetailRowValue.of(unpriced, marketStatus: "resolved"), FuturesDetailRowValue.none)
    }

    func test_voidOrRetracted_withholdsInBothDirections() throws {
        for won in ["true", "false"] {
            let o = try outcome(isWinner: won, source: "\"ungradeable_result\"", probability: "0.5")
            XCTAssertEqual(FuturesDetailRowValue.of(o, marketStatus: "resolved"), .price(0.5), won)
        }
    }

    func test_noGrader_withholds() throws {
        // A served/absent null `resolution_source`: `is_winner` alone is not a grade.
        let o = try outcome(isWinner: "false", source: "null", probability: "0.01")
        XCTAssertEqual(FuturesDetailRowValue.of(o, marketStatus: "resolved"), .price(0.01))
        let absent = try JSONDecoder().decode(
            FuturesOutcome.self,
            from: Data(#"{"id": 2, "name": "Leg", "probability": 0.01, "isWinner": false}"#.utf8)
        )
        XCTAssertEqual(FuturesDetailRowValue.of(absent, marketStatus: "resolved"), .price(0.01))
    }

    // MARK: - The row reads this decision (static: no SwiftUI render here)

    func test_theMarketDetailsRowReadsTheDecision() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Views/FuturesDetailView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        let start = try XCTUnwrap(source.range(of: "private func outcomeRow("))
        let end = try XCTUnwrap(source.range(of: "// MARK: - Golf Tournament Dates",
                                             range: start.upperBound..<source.endIndex))
        let row = String(source[start.upperBound..<end.lowerBound])
        XCTAssertTrue(row.contains("FuturesDetailRowValue.of(outcome, marketStatus: marketStatus, marketSource: marketSource)"))
        XCTAssertTrue(row.contains("case .verdict(let verdict):"))
        XCTAssertTrue(row.contains("if case .price = value {"), "the bar is drawn only for a price")
        XCTAssertTrue(row.contains("if value.printsMovement {"))
        XCTAssertFalse(row.contains("if let prob = outcome.probability {"),
                       "the value slot must switch on the decision, not on the raw price")
        XCTAssertFalse(row.contains("outcome.isWinner == true"),
                       "`is_winner` alone is not a grade")
        XCTAssertTrue(source.contains("marketStatus: market.status"))
    }

    // MARK: - The last rows clear the iPhone's floating tab bar

    /// Review of PR #10999: at the deepest scroll on iPhone, #13 Detroit over
    /// 5.5 sat under the floating tab bar. The page now ends with room for it.
    func test_iPhoneLeavesRoomBelowTheLastRow_iPadDoesNot() {
        let compact = FuturesDetailView.bottomClearance(horizontalSizeClass: .compact)
        XCTAssertGreaterThanOrEqual(compact, 120, "the tab bar is ~76pt over the safe area; a row is ~60pt")
        XCTAssertEqual(FuturesDetailView.bottomClearance(horizontalSizeClass: nil), compact,
                       "an unknown size class is treated as the phone")
        XCTAssertEqual(FuturesDetailView.bottomClearance(horizontalSizeClass: .regular), 0,
                       "iPad's tab bar is at the top")
    }

    func test_thePageAppliesTheClearance() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/FuturesDetailView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        let start = try XCTUnwrap(source.range(of: "outcomesSection(market)\n"))
        let tail = source[start.upperBound...].prefix(400)
        XCTAssertTrue(tail.contains(".padding(.bottom, Self.bottomClearance(horizontalSizeClass: horizontalSizeClass))"),
                      "the clearance must follow the outcomes section inside the scroll content")
    }
}

private extension FuturesDetailRowValue {
    var label: String? {
        if case .verdict(let v) = self { return v.label }
        return nil
    }
}
