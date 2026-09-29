import XCTest
@testable import Bain_Luck

@MainActor
final class FinalGameWinnerQuoteTests: XCTestCase {
    private func quote(status: String = "open", marketId: Int = 11,
                       probability: Double = 0.99) -> FinalGameWinnerQuote {
        FinalGameWinnerQuote(eventId: 42, marketId: marketId, marketName: "Bears vs Eagles",
            source: "kalshi", status: status, observedAt: nil, outcomes: [
                FinalGameWinnerQuoteOutcome(outcomeId: 1, side: .home, name: "Bears",
                                           probability: probability, observedAt: nil),
                FinalGameWinnerQuoteOutcome(outcomeId: 2, side: .away, name: "Eagles",
                                           probability: 0.01, observedAt: nil),
            ])
    }

    func testOnlyFinishedGameCanConstructSeparateTradingSection() {
        for status in ["completed", "closed"] {
            XCTAssertNotNil(FinalGameWinnerQuoteView(quote: quote(), eventId: 42,
                                                    eventStatus: status, closedMarketIds: []))
        }
        for status: String? in ["live", "scheduled", "suspended", "postponed", nil] {
            XCTAssertNil(FinalGameWinnerQuoteView(quote: quote(), eventId: 42,
                                                 eventStatus: status, closedMarketIds: []))
        }
    }

    func testIdentityAndTerminalStatusCannotBorrowFinalResultForAnotherQuote() {
        XCTAssertNil(FinalGameWinnerQuoteView(quote: quote(), eventId: 99,
                                             eventStatus: "completed", closedMarketIds: []))
        for status in ["closed", "resolved", "settled", "suspended"] {
            XCTAssertFalse(quote(status: status).isPresentable(eventId: 42,
                           eventStatus: "completed", closedMarketIds: []))
        }
    }

    func testTerminalFenceSurvivesMissingQuoteAndCannotReopen() {
        var fence = FinalGameWinnerQuoteFence()
        XCTAssertNotNil(fence.visible(quote(), eventId: 42, eventStatus: "completed"))
        fence.recordClosed([11])
        XCTAssertNil(fence.visible(nil, eventId: 42, eventStatus: "completed"))
        fence.recordClosed([])
        XCTAssertNil(fence.visible(quote(), eventId: 42, eventStatus: "completed"))
        XCTAssertNotNil(fence.visible(quote(marketId: 12), eventId: 42, eventStatus: "completed"))
    }

    func testMissingQuoteAloneDoesNotClaimSettlement() {
        let fence = FinalGameWinnerQuoteFence()
        XCTAssertNil(fence.visible(nil, eventId: 42, eventStatus: "completed"))
        XCTAssertNotNil(fence.visible(quote(), eventId: 42, eventStatus: "completed"))
        XCTAssertTrue(fence.closedMarketIds.isEmpty)
    }

    func testInvalidPriceCannotConstructTradingSection() {
        for value in [Double.nan, Double.infinity, -0.1, 1.1] {
            XCTAssertFalse(quote(probability: value).isPresentable(eventId: 42,
                           eventStatus: "completed", closedMarketIds: []))
        }
        XCTAssertTrue(quote(probability: 1).isPresentable(eventId: 42,
                      eventStatus: "completed", closedMarketIds: []))
    }

    func testWireDecodingBindsRealOutcomesWithoutInventingObservation() throws {
        let json = """
        {"event_id":42,"market_id":11,"market_name":"Bears vs Eagles","source":"kalshi",
         "status":"open","observed_at":null,"outcomes":[
          {"outcome_id":1,"side":"home","name":"Bears","probability":0.99,"observed_at":null},
          {"outcome_id":2,"side":"away","name":"Eagles","probability":0.01,"observed_at":null}]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let decoded = try decoder.decode(FinalGameWinnerQuote.self, from: Data(json.utf8))
        XCTAssertEqual(decoded.contributorOutcomeIds, ["1", "2"])
        XCTAssertNil(decoded.observedAt)
        XCTAssertTrue(decoded.outcomes.allSatisfy { $0.observedAt == nil })
        XCTAssertTrue(decoded.isPresentable(eventId: 42, eventStatus: "completed", closedMarketIds: []))
    }

    func testQuoteEndpointsNeverClaimTheFinalResultsCertainty() {
        XCTAssertEqual(quote(probability: 1).printableProbabilities[1], ">99%")
        XCTAssertEqual(quote(probability: 0).printableProbabilities[1], "<1%")
    }

    func testComplementPairRoundingDoesNotPrint101Percent() {
        let pair = FinalGameWinnerQuote(eventId: 42, marketId: 11, marketName: "Bears vs Eagles",
            source: "kalshi", status: "open", observedAt: nil, outcomes: [
                FinalGameWinnerQuoteOutcome(outcomeId: 1, side: .home, name: "Bears",
                                           probability: 0.925, observedAt: nil),
                FinalGameWinnerQuoteOutcome(outcomeId: 2, side: .away, name: "Eagles",
                                           probability: 0.075, observedAt: nil),
            ])
        XCTAssertEqual(pair.printableProbabilities[1], "93%")
        XCTAssertEqual(pair.printableProbabilities[2], "7%")
    }
}
