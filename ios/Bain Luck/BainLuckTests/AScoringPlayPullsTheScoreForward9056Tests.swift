import XCTest
@testable import Bain_Luck

/// #9056 — a big pushed move pulls the score forward.
///
/// Rage shake #157 (GT @ STAN): the phone painted 10–7 about 55 s after the
/// server row read 13–7. The push stream carries a price and no score, so while
/// it delivers the page re-asked for the score only every 120 s — and a scoring
/// play is exactly what moves the price. The hero jumped; the score stayed on
/// the play before.
///
/// BOTH DIRECTIONS (gotcha #43): a big move goes fast, a small one stays on the
/// slow lane, and the fast lane ENDS — a page that stayed at 30 s after one
/// touchdown would satisfy the first half while throwing #2687's saving away.
@MainActor
final class AScoringPlayPullsTheScoreForward9056Tests: XCTestCase {

    // MARK: - The pure decision

    private let anchor = Date(timeIntervalSince1970: 1_757_000_000)

    func testCatchingUpTakesAPushedPageToTheLiveCadence() {
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "live", streamDelivering: true,
                commenceTime: anchor.addingTimeInterval(-600), now: anchor, catchingUp: true
            ),
            .poll(every: EventRefreshPlan.livePollInterval)
        )
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "live", streamDelivering: true,
                commenceTime: anchor.addingTimeInterval(-600), now: anchor, catchingUp: false
            ),
            .poll(every: EventRefreshPlan.livePushPollInterval)
        )
    }

    /// Catching up only ever speeds the pushed lane; it never wakes a settled
    /// page or changes a pre-game one.
    func testCatchingUpChangesNothingElse() {
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "completed", streamDelivering: true,
                commenceTime: anchor.addingTimeInterval(-7200), now: anchor, catchingUp: true
            ),
            .idle
        )
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "scheduled", streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(7200), now: anchor, catchingUp: true
            ),
            .poll(every: EventRefreshPlan.distantPollInterval)
        )
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "live", streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(-600), now: anchor, catchingUp: true
            ),
            .poll(every: EventRefreshPlan.livePollInterval)
        )
    }

    // MARK: - Fakes

    private final class FakeHandle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        @MainActor func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    /// Serves `script` in order, then repeats its last entry.
    private nonisolated final class ScriptedClient: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private var script: [EventDetail]
        private var last: EventDetail?
        private var fetches = 0
        init(_ script: [EventDetail]) { self.script = script }
        var fetchCount: Int { lock.withLock { fetches } }
        func fetchEvent(id: Int) async throws -> EventDetail {
            let next: EventDetail? = lock.withLock {
                fetches += 1
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

    /// The poll's sleep. Parks every loop (cancellably, so a re-plan retires
    /// it) unless the test has released one wake — then exactly one sleeper
    /// returns and the loop runs a single `load()`.
    private nonisolated final class Sleeper: @unchecked Sendable {
        private let lock = NSLock()
        private var wakes = 0
        func release() { lock.withLock { wakes += 1 } }
        func sleep(_ seconds: TimeInterval) async {
            while !Task.isCancelled {
                // A cancelled loop never takes the wake: it would return, see
                // its own cancellation and exit without loading, and the live
                // loop would park on a wake that is already spent.
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

    /// The wall clock the view model reads, moved by the test and never by time.
    private final class Clock: @unchecked Sendable {
        var t: TimeInterval
        init(_ t: TimeInterval) { self.t = t }
    }

    // MARK: - Fixtures

    private func live(p: Double, home: Int, away: Int) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {
          "id": 4242, "home_team": "Stanford Cardinal", "away_team": "Georgia Tech Yellow Jackets",
          "status": "live", "home_score": \(home), "away_score": \(away),
          "current_odds": {"home_probability": \(p), "away_probability": \(1 - p)}
        }
        """.utf8))
    }

    private var stampSecond = 0
    /// Every frame carries a strictly later stamp, so none is refused as older.
    private func push(_ handle: FakeHandle, _ p: Double) {
        stampSecond += 1
        let stamp = String(format: "2026-09-27T03:26:%02dZ", stampSecond)
        handle.fire("probability", """
        {"event_id": 4242, "p": \(p), "source": "kalshi", "source_value": \(p), \
        "updated_at": "\(stamp)", "status": "live"}
        """)
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

    private func page(
        _ script: [EventDetail]
    ) async -> (EventDetailViewModel, FakeHandle, ScriptedClient, Sleeper, Clock) {
        let handle = FakeHandle()
        let client = ScriptedClient(script)
        let sleeper = Sleeper()
        let clock = Clock(anchor.timeIntervalSince1970)
        let vm = EventDetailViewModel(
            eventId: 4242,
            client: client,
            makeStreamHandle: { _ in handle },
            now: { clock.t },
            sleep: { seconds in await sleeper.sleep(seconds) }
        )
        await vm.load()
        handle.fire("open")
        return (vm, handle, client, sleeper, clock)
    }

    // MARK: - The wired page

    /// THE SHIP. Stanford scores; the price jumps by push; the page goes to the
    /// live cadence and its next poll brings the score the server already had.
    func testABigPushedMoveFetchesTheNewScore() async throws {
        let (vm, handle, client, sleeper, _) = await page([
            try live(p: 0.40, home: 7, away: 10),
            try live(p: 0.52, home: 13, away: 10)
        ])
        defer { vm.stopRefresh() }
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 120))

        push(handle, 0.52)
        XCTAssertEqual(
            vm.currentRefreshPlan, .poll(every: 30),
            "a twelve-point pushed move left the score on the two-minute lane"
        )
        XCTAssertEqual(vm.event?.homeScore, 7, "nothing has been fetched yet")

        sleeper.release()
        await waitUntil("the poll to bring the new score") { vm.event?.homeScore == 13 }
        XCTAssertEqual(client.fetchCount, 2)
    }

    /// The sibling: a quiet market's drift stays on the slow lane.
    func testASmallPushedMoveKeepsTheSlowLane() async throws {
        let (vm, handle, _, _, _) = await page([try live(p: 0.40, home: 7, away: 10)])
        defer { vm.stopRefresh() }
        push(handle, 0.42)
        push(handle, 0.38)
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 120))
    }

    /// Measured from the last LOAD: a play priced in over several small frames
    /// is still one big move.
    func testSmallFramesThatAddUpToABigMoveCount() async throws {
        let (vm, handle, _, _, _) = await page([try live(p: 0.40, home: 7, away: 10)])
        defer { vm.stopRefresh() }
        push(handle, 0.42)
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 120))
        push(handle, 0.45)
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 30))
    }

    /// The window ENDS. Inside it every load keeps the live cadence (the first
    /// poll can be served a cached score); past it the page goes back to 120.
    func testTheCatchUpWindowCloses() async throws {
        let (vm, handle, client, sleeper, clock) = await page([
            try live(p: 0.40, home: 7, away: 10),
            try live(p: 0.52, home: 7, away: 10),
            try live(p: 0.52, home: 13, away: 10)
        ])
        defer { vm.stopRefresh() }
        push(handle, 0.52)
        let openedAt = vm.lastLoadedAt

        clock.t += 30
        sleeper.release()
        await waitUntil("the first catch-up poll to complete") {
            client.fetchCount == 2 && vm.lastLoadedAt != openedAt
        }
        XCTAssertEqual(vm.event?.homeScore, 7, "a cached payload: the score has not arrived yet")
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 30), "the window closed on a cached score")

        clock.t += EventRefreshPlan.scoreCatchUpWindow
        sleeper.release()
        await waitUntil("the score, and the slow lane back") {
            vm.event?.homeScore == 13 && vm.currentRefreshPlan == .poll(every: 120)
        }
    }

    /// A load resets the baseline. After it, a small move from the NEW price
    /// does not re-open the window, however far the price is from the old one.
    func testALoadResetsTheBaseline() async throws {
        let (vm, handle, _, _, clock) = await page([
            try live(p: 0.40, home: 7, away: 10),
            try live(p: 0.52, home: 13, away: 10)
        ])
        defer { vm.stopRefresh() }
        push(handle, 0.52)
        clock.t += EventRefreshPlan.scoreCatchUpWindow + 1
        await vm.load()
        XCTAssertEqual(vm.event?.homeScore, 13)
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 120))

        push(handle, 0.54)
        XCTAssertEqual(
            vm.currentRefreshPlan, .poll(every: 120),
            "the move was measured from a stale baseline"
        )
    }
}
