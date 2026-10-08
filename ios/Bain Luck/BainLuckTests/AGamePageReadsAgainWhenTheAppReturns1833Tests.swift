import SwiftUI
import XCTest
@testable import Bain_Luck

/// #1833 (build-34 recurrence) — a game page brought back from the background
/// reads the game again at once.
///
/// Alex, Oct 2, 9:24 AM PT: Steelers at Browns (14780550) had been left open
/// overnight. The hero still said Q4 0:10, live, 'Received 8:43:04 PM' — 116 s
/// before the server stamped the final at 8:45 PM — and the live chart axis ran
/// from Thursday evening to Friday morning. The server had served `completed`
/// all night. Returning to the app only toggled market visibility, so the page
/// waited on a poll loop that iOS had suspended with the app.
///
/// BOTH DIRECTIONS (gotcha #43): a return from the background reads once and
/// takes the final; a pulled-down Control Center (`.inactive`), a page the
/// reader already left, and a second `.active` with no background between do
/// not read at all.
@MainActor
final class AGamePageReadsAgainWhenTheAppReturns1833Tests: XCTestCase {

    // MARK: - Fakes

    private final class FakeHandle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
        func close() { isClosed = true }
    }

    /// Serves `script` in order, then repeats its last entry, counting detail
    /// reads. Every other endpoint declines.
    private nonisolated final class ScriptedClient: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private var script: [EventDetail]
        private var last: EventDetail?
        private var details = 0
        private var cachedDetails = 0
        init(_ script: [EventDetail]) { self.script = script }
        var detailCount: Int { lock.withLock { details } }
        var cachedDetailCount: Int { lock.withLock { cachedDetails } }
        func fetchEvent(id: Int) async throws -> EventDetail {
            // A cached read could replay the pre-background price. Initial
            // opens and returns must select the fresh endpoint instead.
            lock.withLock { cachedDetails += 1 }
            throw Declined()
        }
        func fetchFreshEvent(id: Int) async throws -> EventDetail {
            let next: EventDetail? = lock.withLock {
                details += 1
                if !script.isEmpty { last = script.removeFirst() }
                return last
            }
            guard let next else { throw Declined() }
            return next
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    // MARK: - Fixtures

    /// Steelers at Browns. Live: Q4 0:10, 24–27. Completed: Final, 24–27.
    private func game(status: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let clock = status == "live" ? "0:10" : "0:00"
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":14780550,"home_team":"Cleveland Browns","away_team":"Pittsburgh Steelers",
         "status":"\(status)","home_score":27,"away_score":24,
         "espn":{"game_clock":"\(clock)","period":"4"},
         "current_odds":{"home_probability":0.97,"away_probability":0.03,
           "home_rendered_percent":97,"away_rendered_percent":3},
         "win_probability_sources":{"kalshi":{"value":0.97,"updated_at":"2026-10-02T03:43:04Z"}}}
        """.utf8))
    }

    /// A page that loaded the live game. Its poll never wakes during a test, so
    /// every read after the first is one the scene change asked for.
    private func heldLivePage(
        then later: EventDetail
    ) async throws -> (EventDetailViewModel, ScriptedClient) {
        let client = ScriptedClient([try game(status: "live"), later])
        let vm = EventDetailViewModel(
            eventId: 14780550,
            client: client,
            makeStreamHandle: { _ in FakeHandle() },
            now: { 1_790_221_384 },
            sleep: { _ in
                while !Task.isCancelled { try? await Task.sleep(nanoseconds: 1_000_000) }
            }
        )
        await vm.load()
        XCTAssertEqual(vm.event?.status, "live")
        XCTAssertEqual(client.detailCount, 1)
        XCTAssertEqual(client.cachedDetailCount, 0, "an open must request current probabilities")
        return (vm, client)
    }

    // MARK: - The ship

    /// THE SHIP. Background, then active: one read, and the page takes the final.
    func testAPageBackFromTheBackgroundTakesTheFinal() async throws {
        let (vm, client) = try await heldLivePage(then: try game(status: "completed"))
        defer { vm.stopRefresh() }

        XCTAssertNil(vm.scenePhaseChanged(to: .inactive, pageVisible: true))
        XCTAssertNil(vm.scenePhaseChanged(to: .background, pageVisible: true))
        XCTAssertNil(vm.scenePhaseChanged(to: .inactive, pageVisible: true))
        let read = vm.scenePhaseChanged(to: .active, pageVisible: true)
        XCTAssertNotNil(read, "returning from the background asked for nothing")
        await read?.value

        XCTAssertEqual(client.detailCount, 2)
        XCTAssertEqual(client.cachedDetailCount, 0, "a return must not replay its cached price")
        XCTAssertEqual(vm.event?.status, "completed", "the reopened page still reads live")
        XCTAssertFalse(vm.isAutoRefreshing, "a settled page kept polling")
    }

    /// One return, one read: the next `.active` with no background before it
    /// is not a return.
    func testOneReturnReadsOnce() async throws {
        let (vm, client) = try await heldLivePage(then: try game(status: "live"))
        defer { vm.stopRefresh() }

        vm.scenePhaseChanged(to: .background, pageVisible: true)
        await vm.scenePhaseChanged(to: .active, pageVisible: true)?.value
        XCTAssertEqual(client.detailCount, 2)

        vm.scenePhaseChanged(to: .inactive, pageVisible: true)
        XCTAssertNil(vm.scenePhaseChanged(to: .active, pageVisible: true))
        XCTAssertEqual(client.detailCount, 2)
    }

    // MARK: - What is not a return

    /// Control Center or a notification pulled down: the app kept running.
    func testAnInactiveSceneIsNotAReturn() async throws {
        let (vm, client) = try await heldLivePage(then: try game(status: "completed"))
        defer { vm.stopRefresh() }

        vm.scenePhaseChanged(to: .inactive, pageVisible: true)
        XCTAssertNil(vm.scenePhaseChanged(to: .active, pageVisible: true))
        XCTAssertEqual(client.detailCount, 1)
        XCTAssertEqual(vm.event?.status, "live")
    }

    /// A page the reader navigated away from is not read: `load()` re-plans the
    /// poll and would restart it for a page nobody can see. The owed read
    /// waits until the page is on screen for a return.
    func testAPageOffScreenIsNotReadUntilItIsOnScreen() async throws {
        let (vm, client) = try await heldLivePage(then: try game(status: "completed"))
        vm.stopRefresh()

        vm.scenePhaseChanged(to: .background, pageVisible: false)
        XCTAssertNil(vm.scenePhaseChanged(to: .active, pageVisible: false))
        XCTAssertEqual(client.detailCount, 1)
        XCTAssertFalse(vm.isAutoRefreshing, "an off-screen page started polling")

        vm.scenePhaseChanged(to: .background, pageVisible: true)
        await vm.scenePhaseChanged(to: .active, pageVisible: true)?.value
        XCTAssertEqual(client.detailCount, 2)
        XCTAssertEqual(vm.event?.status, "completed")
        vm.stopRefresh()
    }
}
