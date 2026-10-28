import XCTest
@testable import Bain_Luck

/// #10090 — the Sports tab's 30 s live refresh pauses while a page is pushed
/// over the list, and catches up once when the list is visible again.
///
/// `FeedView`'s `onDisappear` fires for a tab switch but not for a push inside
/// its own `NavigationStack`, so the timer kept fetching and publishing 50 rows
/// on the main actor behind a live event page (~26 ms of main-thread time per
/// refresh, measured on a simulator with a recorded 50-item feed). Freshness
/// while the list is visible must not change.
@MainActor
final class ACoveredSportsListPausesItsLiveRefresh10090Tests: XCTestCase {

    private nonisolated final class Client: SportsFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var _mainCalls = 0
        let main: FeedResponse
        let empty: FeedResponse
        let grouped: GroupedFeedResponse
        init(main: FeedResponse, empty: FeedResponse, grouped: GroupedFeedResponse) {
            self.main = main; self.empty = empty; self.grouped = grouped
        }
        var mainCalls: Int { lock.withLock { _mainCalls } }
        nonisolated func fetchSportsFeed() async throws -> FeedResponse {
            lock.withLock { _mainCalls += 1 }
            return main
        }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse { empty }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { grouped }
    }

    private nonisolated final class Clock: @unchecked Sendable {
        private let lock = NSLock()
        private var _now = Date(timeIntervalSince1970: 1_793_000_000)
        var now: Date { lock.withLock { _now } }
        func advance(_ s: TimeInterval) { lock.withLock { _now = _now.addingTimeInterval(s) } }
    }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(type, from: Data(json.utf8))
    }

    private func page(status: String) throws -> (FeedViewModel, Client, Clock) {
        let item = #"{"type":"event","score":90,"data":{"id":1,"home_team":"H","away_team":"A","status":"\#(status)"}}"#
        let client = Client(
            main: try decode(FeedResponse.self, #"{"items":[\#(item)],"total":1,"limit":50,"offset":0,"has_more":false}"#),
            empty: try decode(FeedResponse.self, #"{"items":[],"total":0,"limit":50,"offset":0,"has_more":false}"#),
            grouped: try decode(GroupedFeedResponse.self, #"{"feed":[],"total":0,"limit":20,"offset":0}"#))
        let clock = Clock()
        let vm = FeedViewModel(client: client, telemetry: nil, clock: { clock.now }, autoRefreshEnabled: true)
        return (vm, client, clock)
    }

    func testAPushedPageStopsTheTimerAndALoadThatLandsUnderItDoesNotRearmIt() async throws {
        let (vm, client, _) = try page(status: "live")
        defer { vm.viewDidStop() }
        await vm.load()
        XCTAssertTrue(vm.refreshArmed, "premise: a live list arms the refresh")

        vm.feedCovered()
        XCTAssertFalse(vm.refreshArmed, "a page on top stops the timer")

        await vm.load()  // e.g. a load already in flight when the page was pushed
        XCTAssertFalse(vm.refreshArmed, "a load that lands under the page does not re-arm it")
        XCTAssertEqual(client.mainCalls, 2)
    }

    func testReturningBeforeARefreshIsDueRearmsWithoutFetching() async throws {
        let (vm, client, clock) = try page(status: "live")
        defer { vm.viewDidStop() }
        await vm.load()
        vm.feedCovered()
        clock.advance(FeedViewModel.autoRefreshInterval - 1)

        await vm.feedUncovered()
        XCTAssertEqual(client.mainCalls, 1, "nothing came due, so nothing is fetched")
        XCTAssertTrue(vm.refreshArmed, "the visible list refreshes on its usual cadence again")
    }

    func testReturningAfterARefreshCameDueRefreshesOnceAndRearms() async throws {
        let (vm, client, clock) = try page(status: "live")
        defer { vm.viewDidStop() }
        await vm.load()
        vm.feedCovered()
        clock.advance(5 * FeedViewModel.autoRefreshInterval)

        await vm.feedUncovered()
        XCTAssertEqual(client.mainCalls, 2, "one catch-up refresh, not one per missed tick")
        XCTAssertTrue(vm.refreshArmed)

        await vm.feedUncovered()
        XCTAssertEqual(client.mainCalls, 2, "an uncovered list does not refresh again on a repeat")
    }

    /// Control: with no live game there was never a timer, so returning to the
    /// list adds no fetch the old code did not make.
    func testWithNoLiveGameReturningFetchesNothing() async throws {
        let (vm, client, clock) = try page(status: "scheduled")
        defer { vm.viewDidStop() }
        await vm.load()
        XCTAssertFalse(vm.refreshArmed)
        vm.feedCovered()
        clock.advance(5 * FeedViewModel.autoRefreshInterval)

        await vm.feedUncovered()
        XCTAssertEqual(client.mainCalls, 1)
        XCTAssertFalse(vm.refreshArmed)
    }
}
