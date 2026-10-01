import XCTest
@testable import Bain_Luck

/// #9963: Search names the first likely date, not the first date in the payload.
@MainActor final class SearchDateLadderAnswer9963Tests: XCTestCase {
    // Verbatim Search market 30635376, 2026-10-01 00:00Z, trimmed to decoded keys.
    private let productionJSON = """
    {"id":30635376,"name":"Anthropic IPO by __?","category":"economics","status":"open","source":"polymarket","resolution_date":"2027-07-01T00:00:00+00:00","top_outcomes":[{"id":230903801,"name":"October 15, 2026","probability":0.0065,"rank":7},{"id":142581282,"name":"October 31, 2026","probability":0.039,"rank":6},{"id":230903799,"name":"November 15, 2026","probability":0.265,"rank":5},{"id":230903798,"name":"November 30, 2026","probability":0.605,"rank":4},{"id":230903797,"name":"December 15, 2026","probability":0.755,"rank":3}],"outcome_count":10}
    """

    private func outcome(_ name: String, _ probability: Double?, rank: Int? = nil) -> SearchFuturesOutcome {
        SearchFuturesOutcome(id: rank ?? 1, name: name, probability: probability,
                             americanOdds: nil, rank: rank, movement: nil)
    }

    private func market(_ outcomes: [SearchFuturesOutcome]?, status: String = "open") -> SearchFuturesMarket {
        SearchFuturesMarket(id: 1, name: "When?", sport: nil, sportName: nil, category: nil,
                            llmSportCategory: nil, status: status, source: nil, resolutionDate: nil,
                            topOutcomes: outcomes, outcomeCount: outcomes?.count, updatedAt: nil)
    }

    func testTheProductionSearchAnswerNamesNovember30At605Percent() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let result = try decoder.decode(SearchFuturesMarket.self, from: Data(productionJSON.utf8))
        XCTAssertEqual(result.dateLadderAnswer?.id, 230903798)
        XCTAssertEqual(result.dateLadderAnswer?.name, "November 30, 2026")
        XCTAssertEqual(result.dateLadderAnswer?.probability, 0.605)
        XCTAssertEqual(result.topOutcomes?.first?.probability, 0.0065)
    }

    func testCalendarOrderWinsOverWireOrderAndProbabilityRank() {
        let result = market([
            outcome("January 31, 2027", 0.95, rank: 1),
            outcome("December 31, 2026", 0.8, rank: 2),
            outcome("November 30, 2026", 0.605, rank: 4),
            outcome("October 31, 2026", 0.03, rank: 6),
        ])
        XCTAssertEqual(result.dateLadderAnswer?.name, "November 30, 2026")
    }

    func testExactlyEvenUsesTheSameBoundaryAsDiscover() {
        XCTAssertEqual(market([
            outcome("October 31, 2026", 0.49),
            outcome("November 30, 2026", 0.5),
            outcome("December 31, 2026", 0.8),
        ]).dateLadderAnswer?.name, "November 30, 2026")
    }

    func testNonDateRankedAnswersKeepTheirExistingLeader() {
        let result = market([outcome("600B+", 0.94), outcome("500B+", 0.98)])
        XCTAssertNil(result.dateLadderAnswer)
        XCTAssertEqual(SearchGrouping.leaderOutcome(result)?.name, "600B+")
    }

    func testMixedLabelsDoNotInventADateLadder() {
        XCTAssertNil(market([
            outcome("October 31, 2026", 0.02), outcome("No IPO", 0.8),
        ]).dateLadderAnswer)
    }

    func testNoCrossoverKeepsTheExistingRowFallback() {
        let result = market([
            outcome("October 31, 2026", 0.02), outcome("November 30, 2026", 0.3),
        ])
        XCTAssertNil(result.dateLadderAnswer)
        XCTAssertEqual(SearchGrouping.leaderOutcome(result)?.name, "October 31, 2026")
    }

    func testMissingQuotesAreNotEvidenceOfACrossover() {
        XCTAssertEqual(market([
            outcome("October 31, 2026", nil), outcome("November 30, 2026", 0.6),
        ]).dateLadderAnswer?.name, "November 30, 2026")
        XCTAssertNil(market(nil).dateLadderAnswer)
        XCTAssertNil(market([outcome("November 30, 2026", 0.6)]).dateLadderAnswer)
    }

    func testBeforeAndByLabelsReuseTheSameCalendarRule() {
        XCTAssertEqual(market([
            outcome("Before Jan 1, 2027", 0.8), outcome("By Dec 1, 2026", 0.6),
        ]).dateLadderAnswer?.name, "By Dec 1, 2026")
    }

    func testMalformedDatesDoNotTurnAFieldIntoALadder() {
        for invalid in ["February 30, 2026", "Octopus 31, 2026", "November 30, 2026 or never"] {
            XCTAssertNil(market([
                outcome(invalid, 0.9), outcome("December 31, 2026", 0.8),
            ]).dateLadderAnswer, invalid)
        }
    }

    func testInvalidProbabilitiesDoNotEarnTheAnswer() {
        for probability in [Double.infinity, Double.nan, 1.1] {
            XCTAssertEqual(market([
                outcome("October 31, 2026", probability), outcome("November 30, 2026", 0.6),
            ]).dateLadderAnswer?.name, "November 30, 2026")
        }
    }

    func testResolvedAnswersKeepTheirExistingVerdictPath() {
        var winner = outcome("October 31, 2026", 0.99)
        winner.isWinner = true
        winner.resolutionSource = "api_settlement"
        let result = market([winner, outcome("November 30, 2026", 0.99)], status: "resolved")
        XCTAssertNil(result.dateLadderAnswer)
        XCTAssertEqual(SearchGrouping.leaderOutcome(result)?.verdict(in: result), .won)
    }

    func testSelectedAuthoritativelyCalledRungStillReadsWon() {
        var winner = outcome("November 30, 2026", 0.99)
        winner.isWinner = true
        winner.resolutionSource = "api_settlement"
        let result = market([outcome("October 31, 2026", 0.01), winner])
        XCTAssertEqual(result.dateLadderAnswer?.verdict(in: result), .won)
    }

    func testDateSortingCannotReplaceACalledLeaderOnAnOpenMarket() {
        var winner = outcome("November 30, 2026", 0.99)
        winner.isWinner = true
        winner.resolutionSource = "api_settlement"
        let result = market([winner, outcome("October 31, 2026", 0.6)])
        XCTAssertNil(result.dateLadderAnswer)
        XCTAssertEqual(SearchGrouping.leaderOutcome(result)?.name, "November 30, 2026")
        XCTAssertEqual(SearchGrouping.leaderOutcome(result)?.verdict(in: result), .won)
        XCTAssertEqual(result.topOutcomes?.first?.verdict(in: result), .won)
    }

    func testAFlatRowsCalledLeaderDoesNotNeedAQuoteToKeepItsGrade() {
        var winner = outcome("November 30, 2026", nil)
        winner.isWinner = true
        winner.resolutionSource = "api_settlement"
        let result = market([winner, outcome("October 31, 2026", 0.6)])
        XCTAssertNil(result.dateLadderAnswer)
        XCTAssertEqual(result.topOutcomes?.first?.verdict(in: result), .won)
        XCTAssertEqual(SearchGrouping.leaderOutcome(result)?.name, "October 31, 2026")
    }

    func testBothSearchRowsUseTheDateAnswerBeforeTheirExistingFallback() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/SearchView.swift")
        let source = try String(contentsOf: root, encoding: .utf8)
        XCTAssertTrue(source.contains("market.dateLadderAnswer ?? SearchGrouping.leaderOutcome(market)"))
        XCTAssertTrue(source.contains("market.dateLadderAnswer ?? market.topOutcomes?.first"))
        XCTAssertEqual(source.components(separatedBy: ".verdict(in: market)").count - 1, 2)
    }
}
