import XCTest
@testable import Bain_Luck

/// D106 — an open event page keeps itself up to date, without being reopened.
///
/// `EventDetailViewModel.configureAutoRefresh` asked `event?.status == "live"`
/// and installed a poll only on yes. Three readers were frozen by that, and each
/// has cases here named after it:
///
///   1. A SCHEDULED PAGE COULD NEVER WAKE UP. Only the poll calls `load()`, so a
///      page that installed no poll never re-asked for its own status. Opened
///      twenty minutes before kick-off it still said "scheduled" an hour into
///      the game. No poll ⇒ no status ⇒ no poll.
///   2. A SUSPENDED MATCH WAS FROZEN FOR GOOD — `suspended` is non-terminal and
///      returns to `live`, but it is not the string `"live"`.
///   3. A HEALTHY PUSH STREAM FROZE THE SCORE. The poll stood down entirely
///      while the stream delivered, and `LiveStreamFrame` carries no score.
///
/// BOTH DIRECTIONS, PER GOTCHA #43. Every "it now polls" case has a sibling
/// proving a FINISHED page still polls never, and that the pushed page keeps a
/// slower cadence rather than the full one — a view model that polled
/// unconditionally at 30s would satisfy the unfreezing half on its own while
/// throwing away #2687's saving and re-billing the quota.
///
/// NOTHING HERE TOUCHES A SOCKET, A SERVER OR THE WALL CLOCK. The fetches go
/// through the `EventDetailProviding` seam, the stream through a fake handle,
/// and the poll's own sleep is a gate the test owns, so a 300-second cadence is
/// exercised in microseconds and no case branches on the real clock
/// (gotcha #44).
@MainActor
final class EventRefreshLifecycleTests: XCTestCase {

    // MARK: - Anchors

    /// Fixed. Offsets are applied to THIS, never to `Date()`, so no case can
    /// change its meaning depending on when the suite runs.
    private let anchor = Date(timeIntervalSince1970: 1_757_000_000)

    private func iso(_ offset: TimeInterval) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: anchor.addingTimeInterval(offset))
    }

    // MARK: - The pure decision

    func testFinishedPageNeverPolls() {
        for status in ["completed", "closed"] {
            XCTAssertEqual(
                EventRefreshPlan.decide(
                    status: status, streamDelivering: false,
                    commenceTime: anchor.addingTimeInterval(-7200), now: anchor
                ),
                .idle,
                "\(status) is settled — nothing on the page can change again"
            )
        }
    }

    func testLivePageWithoutStreamKeepsTheFullCadence() {
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "live", streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(-600), now: anchor
            ),
            .poll(every: 30)
        )
    }

    /// Defect 3. The old code returned "no poll at all" here.
    func testLivePageWithDeliveringStreamStillPollsForTheScore() {
        let plan = EventRefreshPlan.decide(
            status: "live", streamDelivering: true,
            commenceTime: anchor.addingTimeInterval(-600), now: anchor
        )
        XCTAssertEqual(plan, .poll(every: 120))
        XCTAssertNotEqual(plan, .idle, "the stream carries no score; something must refetch it")
    }

    /// …and the saving #2687 bought is still bought: the pushed cadence is
    /// strictly slower than the unpushed one.
    func testPushedCadenceIsCheaperThanUnpushed() {
        XCTAssertGreaterThan(
            EventRefreshPlan.livePushPollInterval,
            EventRefreshPlan.livePollInterval
        )
    }

    /// Defect 1, the window a reader actually sits in.
    func testScheduledPageNearKickoffPolls() {
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "scheduled", streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(600), now: anchor
            ),
            .poll(every: 60)
        )
    }

    /// Kick-off has passed and the status has NOT flipped yet — precisely the
    /// state the old code could never leave.
    func testOverdueScheduledPagePolls() {
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "scheduled", streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(-300), now: anchor
            ),
            .poll(every: 60)
        )
    }

    func testDistantScheduledPagePollsSlowlyButNotNever() {
        let plan = EventRefreshPlan.decide(
            status: "scheduled", streamDelivering: false,
            commenceTime: anchor.addingTimeInterval(3 * 3600), now: anchor
        )
        XCTAssertEqual(plan, .poll(every: 300))
        XCTAssertNotEqual(plan, .idle, "a page left open must not be indefinitely wrong")
    }

    /// The boundary itself, so `<=` cannot silently become `<`.
    func testKickoffExactlyAtTheImminentBoundaryIsImminent() {
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "scheduled", streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(EventRefreshPlan.imminentWindow),
                now: anchor
            ),
            .poll(every: 60)
        )
        // One second the far side of it is not.
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "scheduled", streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(EventRefreshPlan.imminentWindow + 1),
                now: anchor
            ),
            .poll(every: 300)
        )
    }

    func testDatelessScheduledRowTakesTheAttentiveCadence() {
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "scheduled", streamDelivering: false, commenceTime: nil, now: anchor
            ),
            .poll(every: 60)
        )
    }

    /// Defect 2 — a rain-delayed match is in play and returns to `live`.
    func testSuspendedAndStartedMatchIsTreatedAsInPlay() {
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "suspended", streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(-3600), now: anchor
            ),
            .poll(every: 30)
        )
    }

    /// …but #4021's future-dated suspended fixture is a PRE-GAME row, and must
    /// not be given the in-play cadence just because of its status string.
    func testFutureDatedSuspendedFixtureIsPreGameNotInPlay() {
        XCTAssertEqual(
            EventRefreshPlan.decide(
                status: "suspended", streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(4 * 3600), now: anchor
            ),
            .poll(every: 300)
        )
    }

    /// The denylist lesson `EventState` exists for: the first unfamiliar status
    /// must not inherit the settled claim.
    func testUnknownStatusPollsRatherThanGoingIdle() {
        for status in ["postponed", "in_review", "", nil] as [String?] {
            let plan = EventRefreshPlan.decide(
                status: status, streamDelivering: false,
                commenceTime: anchor.addingTimeInterval(600), now: anchor
            )
            XCTAssertNotEqual(plan, .idle, "unknown status \(status ?? "nil") went idle")
        }
    }

    // MARK: - Fakes for the wired lifecycle

    private enum Reply { case ok(EventDetail); case fail(Error) }

    /// Serves a scripted sequence of `fetchEvent` results and refuses every
    /// secondary fetch (the view model logs and carries on, which is what it
    /// does in production when a secondary endpoint is down).
    private nonisolated final class ScriptedClient: EventDetailProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var script: [Reply]
        private var last: Reply?
        private(set) var eventFetches = 0

        init(_ script: [Reply]) { self.script = script }

        var fetchCount: Int { lock.withLock { eventFetches } }

        func fetchEvent(id: Int) async throws -> EventDetail {
            await Task.yield()
            let reply: Reply = lock.withLock {
                eventFetches += 1
                if !script.isEmpty { last = script.removeFirst() }
                return last ?? .fail(URLError(.badServerResponse))
            }
            switch reply {
            case .ok(let e): return e
            case .fail(let err): throw err
            }
        }

        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            throw URLError(.badServerResponse)
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse {
            throw URLError(.badServerResponse)
        }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse {
            throw URLError(.badServerResponse)
        }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse {
            throw URLError(.badServerResponse)
        }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse {
            throw URLError(.badServerResponse)
        }
    }

    /// The poll's sleep, under the test's control. Records every interval it was
    /// asked for — which is what makes the CADENCE assertable and not merely the
    /// fact of a poll — and parks the loop until the test opens the gate.
    ///
    /// A GATE RATHER THAN A ONE-SHOT RELEASE, and the first version was the
    /// one-shot. It could not survive a plan change: when the stream starts
    /// delivering, the 30s loop is cancelled WHILE PARKED here and a 120s loop
    /// replaces it, so the queue holds a dead continuation the live loop has not
    /// even reached yet. Releasing "one cycle" woke the corpse, banked nothing,
    /// and the test reported that the score never moved — about a product that
    /// was working correctly. A fake that can report a false RED on a plan
    /// change can report a false GREEN on one too.
    ///
    /// Tests that assert on cadence never open the gate, so `recorded` stays
    /// exact for them.
    private nonisolated final class Ticker: @unchecked Sendable {
        private let lock = NSLock()
        private var waiters: [CheckedContinuation<Void, Never>] = []
        private var asked: [TimeInterval] = []
        private var open = false

        var recorded: [TimeInterval] { lock.withLock { asked } }

        func sleep(_ seconds: TimeInterval) async {
            let alreadyOpen: Bool = lock.withLock {
                asked.append(seconds)
                return open
            }
            if alreadyOpen {
                // Not a spin: yields the actor so the assertions can observe.
                try? await Task.sleep(nanoseconds: 100_000)
                return
            }
            await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                lock.lock()
                if open {
                    lock.unlock()
                    cont.resume()
                } else {
                    waiters.append(cont)
                    lock.unlock()
                }
            }
        }

        /// From here the poll runs at full speed. Whatever is parked — live or
        /// cancelled — is released; the cancelled ones re-check
        /// `Task.isCancelled` and exit, and the live loop carries on.
        func openGate() {
            lock.lock()
            open = true
            let parked = waiters
            waiters.removeAll()
            lock.unlock()
            for c in parked { c.resume() }
        }
    }

    /// `@unchecked Sendable` is honest here: `LiveStreamHandle` is a `@MainActor`
    /// protocol and every member below is only ever touched on that actor.
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

    // MARK: - Fixtures

    private func event(
        status: String?, commenceOffset: TimeInterval?, home: Int? = nil, away: Int? = nil
    ) throws -> EventDetail {
        var fields: [String] = [
            "\"id\": 4242",
            "\"home_team\": \"Red Sox\"",
            "\"away_team\": \"Yankees\""
        ]
        fields.append(status.map { "\"status\": \"\($0)\"" } ?? "\"status\": null")
        if let commenceOffset {
            fields.append("\"commence_time\": \"\(iso(commenceOffset))\"")
        }
        if let home { fields.append("\"home_score\": \(home)") }
        if let away { fields.append("\"away_score\": \(away)") }
        let json = "{\(fields.joined(separator: ","))}"
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    /// Bounded spin. The wall clock is a TIMEOUT here, never an assertion
    /// anchor — no case reads a value off it.
    private func waitUntil(
        _ description: String,
        timeout: TimeInterval = 3,
        _ condition: @MainActor () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            await Task.yield()
            try? await Task.sleep(nanoseconds: 200_000)
        }
        XCTFail("timed out waiting for: \(description)")
    }

    private func makeVM(
        client: ScriptedClient, ticker: Ticker, handle: FakeHandle? = nil
    ) -> EventDetailViewModel {
        EventDetailViewModel(
            eventId: 4242,
            client: client,
            makeStreamHandle: handle.map { h in { _ in h } },
            now: { [anchor] in anchor.timeIntervalSince1970 },
            sleep: { [ticker] seconds in await ticker.sleep(seconds) }
        )
    }

    // MARK: - The wired lifecycle

    /// THE SHIP. A page opened before kick-off, never reopened, learns that the
    /// game started and shows the score. On the old code this assertion was
    /// unreachable: nothing would have made the second request.
    func testScheduledPageGoesLiveWithoutBeingReopened() async throws {
        let client = ScriptedClient([
            .ok(try event(status: "scheduled", commenceOffset: 120)),
            .ok(try event(status: "live", commenceOffset: 120, home: 3, away: 1))
        ])
        let ticker = Ticker()
        let handle = FakeHandle()
        let vm = makeVM(client: client, ticker: ticker, handle: handle)

        await vm.load()
        XCTAssertEqual(vm.event?.status, "scheduled")
        XCTAssertTrue(vm.isAutoRefreshing, "a scheduled page installed no poll — the deadlock")
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 60))

        // Let the poll run. No reopen, no second `.task`, no `onAppear` — the
        // test calls `load()` exactly once, so every later fetch is the loop's.
        ticker.openGate()

        await waitUntil("the page to notice it went live") { vm.event?.status == "live" }
        XCTAssertEqual(vm.event?.homeScore, 3)
        XCTAssertEqual(vm.event?.awayScore, 1)
        XCTAssertGreaterThanOrEqual(client.fetchCount, 2, "the loop never re-fetched")
        // And it re-plans onto the live cadence off its own refresh.
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 30))

        vm.stopRefresh()
    }

    /// The sibling. A finished page installs nothing at all — the saving the
    /// original guard was protecting is still protected.
    func testFinishedPageInstallsNoPoll() async throws {
        let client = ScriptedClient([.ok(try event(status: "completed", commenceOffset: -7200))])
        let ticker = Ticker()
        let vm = makeVM(client: client, ticker: ticker)

        await vm.load()
        XCTAssertFalse(vm.isAutoRefreshing)
        XCTAssertNil(vm.currentRefreshPlan)
        XCTAssertEqual(ticker.recorded, [], "a settled page asked to sleep — it installed a loop")
        XCTAssertEqual(client.fetchCount, 1)
    }

    /// Defect 3, wired: with the stream DELIVERING, the score still refreshes.
    /// The old code installed no poll here, so `homeScore` could never move.
    func testDeliveringStreamStillRefreshesTheScore() async throws {
        let client = ScriptedClient([
            .ok(try event(status: "live", commenceOffset: -600, home: 0, away: 0)),
            .ok(try event(status: "live", commenceOffset: -600, home: 4, away: 2))
        ])
        let ticker = Ticker()
        let handle = FakeHandle()
        let vm = makeVM(client: client, ticker: ticker, handle: handle)

        await vm.load()
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 30))

        // The server starts delivering. `open` is what flips the controller.
        handle.fire("open")
        XCTAssertTrue(vm.streamDelivering)
        XCTAssertEqual(
            vm.currentRefreshPlan, .poll(every: 120),
            "a delivering stream must slow the poll, not stop it"
        )
        XCTAssertTrue(vm.isAutoRefreshing)

        ticker.openGate()
        await waitUntil("the score to move under a live stream") { vm.event?.homeScore == 4 }
        XCTAssertEqual(vm.event?.awayScore, 2)

        vm.stopRefresh()
    }

    /// Defect 2, wired.
    func testSuspendedMatchKeepsPolling() async throws {
        let client = ScriptedClient([
            .ok(try event(status: "suspended", commenceOffset: -3600)),
            .ok(try event(status: "live", commenceOffset: -3600, home: 1, away: 0))
        ])
        let ticker = Ticker()
        let handle = FakeHandle()
        let vm = makeVM(client: client, ticker: ticker, handle: handle)

        await vm.load()
        XCTAssertTrue(vm.isAutoRefreshing, "a rain-delayed match was frozen for good")
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 30))

        ticker.openGate()
        await waitUntil("the match to resume") { vm.event?.status == "live" }

        vm.stopRefresh()
    }

    /// The cadence the loop actually SLEEPS on is the cadence the plan names —
    /// a plan that were only reported and never used would pass every assertion
    /// above this one.
    func testTheLoopSleepsOnThePlansInterval() async throws {
        let client = ScriptedClient([
            .ok(try event(status: "scheduled", commenceOffset: 3 * 3600))
        ])
        let ticker = Ticker()
        let vm = makeVM(client: client, ticker: ticker)

        await vm.load()
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 300))
        await waitUntil("the loop to reach its sleep") { !ticker.recorded.isEmpty }
        XCTAssertEqual(ticker.recorded.first, 300)

        vm.stopRefresh()
    }

    /// `stopRefresh` is what `onDisappear` calls. Nothing may survive it — a
    /// poll that outlived its page is how a scheduled-page fix turns into a
    /// battery complaint.
    func testStopRefreshTearsEverythingDown() async throws {
        let client = ScriptedClient([.ok(try event(status: "scheduled", commenceOffset: 120))])
        let ticker = Ticker()
        let vm = makeVM(client: client, ticker: ticker)

        await vm.load()
        XCTAssertTrue(vm.isAutoRefreshing)

        vm.stopRefresh()
        XCTAssertFalse(vm.isAutoRefreshing)
        XCTAssertNil(vm.currentRefreshPlan, "currentRefreshPlan named a cadence nothing runs at")
    }

    /// Re-`load()`ing must not churn the loop. `load()` calls
    /// `configureAutoRefresh`, and the loop calls `load()`, so an unconditional
    /// reinstall would have every cycle cancel the task it is running inside.
    func testUnchangedPlanDoesNotReinstallTheLoop() async throws {
        let client = ScriptedClient([
            .ok(try event(status: "scheduled", commenceOffset: 120)),
            .ok(try event(status: "scheduled", commenceOffset: 120))
        ])
        let ticker = Ticker()
        let vm = makeVM(client: client, ticker: ticker)

        await vm.load()
        await waitUntil("first sleep") { !ticker.recorded.isEmpty }
        XCTAssertEqual(ticker.recorded.count, 1)

        // A manual pull-to-refresh at the same state.
        await vm.load()
        await Task.yield()
        XCTAssertEqual(
            ticker.recorded.count, 1,
            "the loop was rebuilt on an unchanged plan and slept a second time"
        )

        vm.stopRefresh()
    }
}
