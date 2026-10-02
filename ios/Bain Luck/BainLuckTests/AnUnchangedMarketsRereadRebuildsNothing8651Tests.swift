import Combine
import XCTest
@testable import Bain_Luck

/// #8651 (build 34) — **an unchanged markets reread does not rebuild the page.**
///
/// The markets can be reread as often as every 2 s. Every write to a `@Published`
/// property rebuilds the whole event page, identical value or not, so a quiet
/// stretch of a long-open page froze on every reread for nothing. The page
/// model now writes only a body that differs; any difference still lands.
@MainActor
final class AnUnchangedMarketsRereadRebuildsNothing8651Tests: XCTestCase {

    private func markets(home: Double) throws -> GameMarketsResponse {
        let dict: [String: Any] = [
            "event_id": 14780550, "status": "live", "home_score": 10, "away_score": 7,
            "open_winner_quote": [
                "event_id": 14780550, "market_id": 11, "market_name": "Steelers at Browns",
                "source": "kalshi", "status": "open", "observed_at": NSNull(),
                "outcomes": [
                    ["outcome_id": 1, "side": "home", "name": "Browns", "probability": home,
                     "observed_at": NSNull()],
                    ["outcome_id": 2, "side": "away", "name": "Steelers", "probability": 1 - home,
                     "observed_at": NSNull()],
                ]],
            "stream_market_ids": [11], "outcome_market_ids": ["1": 11, "2": 11],
        ]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private struct NoClient: EventDetailProviding {
        struct Declined: Error {}
        func fetchEvent(id: Int) async throws -> EventDetail { throw Declined() }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchFreshGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    func testAnIdenticalRereadPublishesNothingAndAChangedOneLands() throws {
        let vm = EventDetailViewModel(eventId: 14780550, client: NoClient())
        var writes = 0
        let watch = vm.objectWillChange.sink { writes += 1 }
        defer { watch.cancel() }

        vm.receiveGameMarkets(try markets(home: 0.40))
        XCTAssertEqual(writes, 1, "the first body lands")
        XCTAssertEqual(vm.gameMarkets?.openWinnerQuote?.outcomes.first?.probability, 0.40)

        vm.receiveGameMarkets(try markets(home: 0.40))
        XCTAssertEqual(writes, 1, "an identical reread must not rebuild the page")

        vm.receiveGameMarkets(try markets(home: 0.41))
        XCTAssertEqual(writes, 2, "a changed price must still rebuild it")
        XCTAssertEqual(vm.gameMarkets?.openWinnerQuote?.outcomes.first?.probability, 0.41)
    }
}
