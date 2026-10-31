import XCTest
@testable import Bain_Luck

/// #10090 — the installed-iPhone kit's periodic clock exchange
/// (`EventDetailViewModel.clockExchangeArgument`). Measurement's clock form
/// needs a successful phone↔database exchange at least every 15 s across a
/// hold; a page's own reads come 30 s apart and are often cached builds.
///
/// BOTH DIRECTIONS: launched with the argument, an open page asks the client
/// for an exchange every `clockExchangePeriod` and stops when the reader
/// leaves; without it, the page never asks, however long it stays open.
@MainActor
final class TheKitsClockExchangeRunsOnlyWhenAsked10090Tests: XCTestCase {

    /// A settled game: no stream and no poll, so the exchange is the only
    /// loop that sleeps.
    private nonisolated final class Client: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private let detail: EventDetail
        private var exchanges: [Int] = []
        init(_ detail: EventDetail) { self.detail = detail }
        var asked: [Int] { lock.withLock { exchanges } }
        func clockExchange(eventId: Int) async throws { lock.withLock { exchanges.append(eventId) } }
        func fetchEvent(id: Int) async throws -> EventDetail { detail }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    /// Parks each sleep (cancellably) until the test releases one wake, and
    /// records the interval each was asked for.
    private nonisolated final class Sleeper: @unchecked Sendable {
        private let lock = NSLock()
        private var wakes = 0
        private var sleeping = 0
        private var intervals: [TimeInterval] = []
        var parked: Int { lock.withLock { sleeping } }
        var asked: [TimeInterval] { lock.withLock { intervals } }
        func release() { lock.withLock { wakes += 1 } }
        func sleep(_ seconds: TimeInterval) async {
            lock.withLock { sleeping += 1; intervals.append(seconds) }
            defer { lock.withLock { sleeping -= 1 } }
            while !Task.isCancelled {
                let go: Bool = lock.withLock {
                    guard wakes > 0, !Task.isCancelled else { return false }
                    wakes -= 1
                    return true
                }
                if go { return }
                try? await Task.sleep(nanoseconds: 200_000)
            }
        }
    }

    private func settled() throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4243,"home_team":"Denver Broncos","away_team":"Los Angeles Rams","status":"completed",
         "home_score":23,"away_score":20,
         "current_odds":{"home_probability":1.0,"away_probability":0.0}}
        """.utf8))
    }

    private func page(asked: Bool) throws -> (EventDetailViewModel, Client, Sleeper) {
        let client = Client(try settled())
        let sleeper = Sleeper()
        let vm = EventDetailViewModel(
            eventId: 4243,
            client: client,
            makeStreamHandle: { _ in XCTFail("a settled page opens no stream"); throw Client.Declined() },
            now: { 1_790_562_050 },
            sleep: { seconds in await sleeper.sleep(seconds) },
            clockExchangePeriodic: asked
        )
        return (vm, client, sleeper)
    }

    private func waitUntil(
        _ description: String, timeout: TimeInterval = 3, _ condition: @MainActor () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            await Task.yield()
            try? await Task.sleep(nanoseconds: 200_000)
        }
        XCTFail("timed out waiting for: \(description)")
    }

    /// Long enough for a loop that is not parked to have run, were one running.
    private func settle() async {
        for _ in 0..<50 {
            await Task.yield()
            try? await Task.sleep(nanoseconds: 200_000)
        }
    }

    func testTheKitsPeriodIsShortEnoughThatTwoMissesStayUnderFifteenSeconds() {
        // One miss doubles a gap, two triple it; each read adds its round trip.
        XCTAssertLessThanOrEqual(EventDetailViewModel.clockExchangePeriod * 3 + 3 * 1, 15)
        XCTAssertEqual(EventDetailViewModel.clockExchangeArgument, "-BLClockExchangePeriodic")
    }

    /// THE SHIP. Asked, an open page exchanges every period; leaving stops it.
    func testAnAskedPageExchangesEveryPeriodUntilTheReaderLeaves() async throws {
        let (vm, client, sleeper) = try page(asked: true)
        await vm.load()
        await waitUntil("the exchange loop to park") { sleeper.parked == 1 }
        XCTAssertEqual(client.asked, [], "the first exchange waits one period")

        for n in 1...3 {
            sleeper.release()
            await waitUntil("exchange \(n)") { client.asked.count == n && sleeper.parked == 1 }
        }
        XCTAssertEqual(client.asked, [4243, 4243, 4243])
        XCTAssertEqual(sleeper.asked, Array(repeating: EventDetailViewModel.clockExchangePeriod, count: 4))

        // A second load on the same visit starts no second loop.
        await vm.load()
        await settle()
        XCTAssertEqual(sleeper.parked, 1, "one loop per visit")

        vm.stopRefresh()
        await waitUntil("the loop to stop") { sleeper.parked == 0 }
        sleeper.release()
        sleeper.release()
        await settle()
        XCTAssertEqual(client.asked.count, 3, "a left page exchanges nothing more")

        // Coming back starts it again.
        await vm.load()
        await waitUntil("the loop to resume") { sleeper.parked == 1 }
    }

    /// Without the argument the page never asks, however long it stays open.
    func testAPageNotAskedNeverExchanges() async throws {
        let (vm, client, sleeper) = try page(asked: false)
        await vm.load()
        await settle()
        XCTAssertEqual(sleeper.parked, 0, "no loop is sleeping")
        for _ in 0..<3 { sleeper.release() }
        await settle()
        XCTAssertEqual(client.asked, [])
        vm.stopRefresh()
    }

    /// Launched as the store build is, the argument is absent: the default
    /// reads the launch arguments and the page never exchanges.
    func testTheDefaultReadsTheLaunchArguments() async throws {
        XCTAssertFalse(ProcessInfo.processInfo.arguments.contains(EventDetailViewModel.clockExchangeArgument))
        let client = Client(try settled())
        let sleeper = Sleeper()
        let vm = EventDetailViewModel(eventId: 4243, client: client,
                                      sleep: { seconds in await sleeper.sleep(seconds) })
        await vm.load()
        await settle()
        XCTAssertEqual(sleeper.parked, 0)
        XCTAssertEqual(client.asked, [])
        vm.stopRefresh()
    }
}
