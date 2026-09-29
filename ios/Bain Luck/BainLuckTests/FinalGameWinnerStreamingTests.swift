import XCTest
@testable import Bain_Luck

@MainActor
final class FinalGameWinnerStreamingTests: XCTestCase {
    private let t0 = "2030-01-01T00:00:00.000001Z"
    private let t1 = "2030-01-01T00:00:00.000002Z"
    private let t2 = "2030-01-01T00:00:00.000003Z"

    private func body(_ home: Double = 0.99, quote: Bool = true, market: Int = 11,
                      revision: String? = "2030-01-01T00:00:00.000001Z",
                      siblingRevision: String = "2030-01-01T00:00:00.000001Z",
                      status: String = "completed", score: Int = 24,
                      closed: [Int] = [], eventId: Int = 42,
                      bindQuote: Bool = true) throws -> GameMarketsResponse {
        let first = market == 11 ? 1 : 3
        let price: [String: Any] = ["event_id": eventId, "market_id": market,
            "market_name": "Bears vs Eagles", "source": "kalshi", "status": "open",
            "observed_at": NSNull(), "outcomes": [
                ["outcome_id": first, "side": "home", "name": "Bears", "probability": home,
                 "observed_at": NSNull()],
                ["outcome_id": first + 1, "side": "away", "name": "Eagles", "probability": 1 - home,
                 "observed_at": NSNull()],
            ]]
        let bindings = ["1": 11, "2": 11, "3": 12, "4": 12, "9": 99]
        let dict: [String: Any] = ["event_id": eventId, "status": status,
            "home_score": score, "away_score": 17, "open_winner_quote": quote ? price as Any : NSNull(),
            "closed_winner_market_ids": closed, "stream_market_ids": [11, 12, 99],
            "outcome_market_ids": bindQuote ? bindings : ["1": 99, "2": 99],
            "outcome_revision_at": ["1": revision as Any? ?? NSNull(), "2": revision as Any? ?? NSNull(),
                                    "3": t0, "4": t0, "9": siblingRevision],
            "outcome_observed_at": ["1": NSNull(), "2": NSNull()]]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func adopt(_ next: GameMarketsResponse, _ held: GameMarketsResponse?,
                       _ fence: inout GameMarketsPriceReconciliation.Fence) -> GameMarketsResponse {
        GameMarketsPriceReconciliation.adopting(next, over: held, fence: &fence)
    }

    func testFinalQuoteUpdatesWhileResultAndUnknownAgeStayFixed() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(), nil, &fence)
        let next = adopt(try body(0.98, revision: t1), held, &fence)
        XCTAssertEqual(next.openWinnerQuote?.outcomes.first?.probability, 0.98)
        XCTAssertEqual(next.status, "completed")
        XCTAssertEqual(next.homeScore, 24)
        XCTAssertEqual(next.awayScore, 17)
        XCTAssertNil(next.openWinnerQuote?.observedAt)
        XCTAssertTrue(next.openWinnerQuote?.outcomes.allSatisfy { $0.observedAt == nil } == true)
    }

    func testQuoteCannotChangeFinalScoreOrTurnTheGameLive() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(), nil, &fence)
        XCTAssertEqual(adopt(try body(0.5, revision: t1, score: 0), held, &fence), held)
        XCTAssertEqual(adopt(try body(0.5, revision: t1, status: "live"), held, &fence), held)
    }

    func testQuoteClockCannotRegressOrBorrowAnUnrelatedSiblingRevision() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(revision: t1), nil, &fence)
        XCTAssertEqual(adopt(try body(0.8, revision: t0), held, &fence), held)
        XCTAssertEqual(adopt(try body(0.8, revision: t1, siblingRevision: t2), held, &fence), held)
    }

    func testWithdrawalNeedsOwnNewRevisionToReturn() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(), nil, &fence)
        let absent = adopt(try body(quote: false, revision: nil), held, &fence)
        XCTAssertNil(absent.openWinnerQuote)
        let stale = adopt(try body(siblingRevision: t1), absent, &fence)
        XCTAssertNil(stale.openWinnerQuote)
        let restored = adopt(try body(0.98, revision: t1, siblingRevision: t1), stale, &fence)
        XCTAssertEqual(restored.openWinnerQuote?.outcomes.first?.probability, 0.98)
    }

    func testTerminalQuoteClearsEvenIfScoreAndClockRegressThenNeverReopens() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(revision: t1), nil, &fence)
        let closed = adopt(try body(quote: false, revision: t0, score: 0, closed: [11]), held, &fence)
        XCTAssertNil(closed.openWinnerQuote)
        XCTAssertEqual(closed.homeScore, 24)
        XCTAssertEqual(closed.status, "completed")
        XCTAssertEqual(closed.closedWinnerMarketIds, [11])
        let reopened = adopt(try body(0.7, revision: t2), closed, &fence)
        XCTAssertNil(reopened.openWinnerQuote)
        XCTAssertEqual(reopened.closedWinnerMarketIds, [11])
    }

    func testForeignEventCannotCloseThisPagesQuote() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(), nil, &fence)
        XCTAssertEqual(adopt(try body(closed: [11], eventId: 99), held, &fence), held)
        XCTAssertTrue(fence.winnerQuotes.closedMarketIds.isEmpty)
    }

    func testUnboundOutcomeCannotAppearAsMappedWinnerQuote() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        XCTAssertNil(adopt(try body(bindQuote: false), nil, &fence).openWinnerQuote)
    }

    func testQuoteCanFirstAppearWhenSportFinishesWithoutInventingANewQuoteObservation() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let live = adopt(try body(quote: false, status: "live"), nil, &fence)
        let final = adopt(try body(), live, &fence)
        XCTAssertNotNil(final.openWinnerQuote)
        XCTAssertEqual(final.status, "completed")
        XCTAssertNil(final.openWinnerQuote?.observedAt)
    }

    func testWholeBookSelectionDoesNotBecomeAPriceWithdrawalFence() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(), nil, &fence)
        let selected = adopt(try body(0.8, market: 12), held, &fence)
        XCTAssertEqual(selected.openWinnerQuote?.marketId, 12)
        let original = adopt(try body(), selected, &fence)
        XCTAssertEqual(original.openWinnerQuote?.marketId, 11)
        XCTAssertTrue(fence.withdrawn.isEmpty)
    }

    func testClosingSelectedBookCanRevealAnotherAlreadyKnownOpenBook() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(), nil, &fence)
        let replacement = adopt(try body(0.8, market: 12, closed: [11]), held, &fence)
        XCTAssertEqual(replacement.openWinnerQuote?.marketId, 12)
        XCTAssertEqual(replacement.closedWinnerMarketIds, [11])
        XCTAssertEqual(replacement.homeScore, 24)
    }
}
