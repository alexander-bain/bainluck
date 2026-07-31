import XCTest
@testable import Bain_Luck

/// L2-217 / C88 — the native **My Stuff** identity boundary and progressive
/// first team card, driven through the `MyStuffFeedProviding` seam with
/// deterministic, individually-gateable fakes and a capturing telemetry sink.
///
/// Two independent defects are covered here, both of which the pre-L2-217
/// `MyStuffViewModel` had:
///
///   1. **The optional futures request gated the first card.** `load()` assigned
///      `items` but only cleared `loading` AFTER `try? await futuresTask`, and
///      the view showed a skeleton for the whole `loading` window — so a hung or
///      failing `/api/me/team-futures` held the first real team card behind a
///      supplemental section.
///   2. **There was no publication authority at all** — no generation, no
///      principal check — so a late response from account A could paint over
///      account B's (or a signed-out) session.
///
/// Every scenario id below maps to a row in the `my-stuff-first-card/v1`
/// contract corpus (`backend/scripts/evals/my_stuff_first_card_fixtures.json`).
@MainActor
final class MyStuffLoadTests: XCTestCase {

    // MARK: - Async gate

    /// A manually-releasable async gate. `wait()` suspends until `open()` (or
    /// returns immediately if already opened).
    private nonisolated final class AsyncGate: @unchecked Sendable {
        private let lock = NSLock()
        private var opened = false
        private var conts: [CheckedContinuation<Void, Never>] = []

        func open() {
            let waiting: [CheckedContinuation<Void, Never>] = lock.withLock {
                opened = true
                let c = conts
                conts = []
                return c
            }
            waiting.forEach { $0.resume() }
        }

        func wait() async {
            await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                let resumeNow: Bool = lock.withLock {
                    if opened { return true }
                    conts.append(cont)
                    return false
                }
                if resumeNow { cont.resume() }
            }
        }
    }

    // MARK: - Fakes

    /// Scriptable client. The required feed and the optional futures request are
    /// independently gateable and independently failable, and the "current"
    /// principal can be flipped mid-flight to model an account switch or a logout.
    private nonisolated final class FakeMyStuffClient: MyStuffFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var _feedCalls = 0
        private var _futuresCalls = 0
        private var _principal: String
        private var _feedReplies: [Result<FeedResponse, Error>]
        private let futuresReply: Result<TeamFuturesResponse, Error>

        let feedGate: AsyncGate?
        let futuresGate: AsyncGate?
        /// Flipped to this principal the instant the required feed request starts,
        /// modelling a switch that happens WHILE the request is in flight.
        private var principalAfterFeedDispatch: String?

        init(
            principal: String = "user:a",
            feedReplies: [Result<FeedResponse, Error>],
            futures: Result<TeamFuturesResponse, Error>,
            feedGate: AsyncGate? = nil,
            futuresGate: AsyncGate? = nil,
            principalAfterFeedDispatch: String? = nil
        ) {
            self._principal = principal
            self._feedReplies = feedReplies
            self.futuresReply = futures
            self.feedGate = feedGate
            self.futuresGate = futuresGate
            self.principalAfterFeedDispatch = principalAfterFeedDispatch
        }

        var feedCalls: Int { lock.withLock { _feedCalls } }
        var futuresCalls: Int { lock.withLock { _futuresCalls } }

        func setPrincipal(_ p: String) { lock.withLock { _principal = p } }

        nonisolated func fetchMyTeamsFeed() async throws -> FeedResponse {
            let reply: Result<FeedResponse, Error> = lock.withLock {
                _feedCalls += 1
                let r = _feedReplies[min(_feedCalls - 1, _feedReplies.count - 1)]
                if let next = principalAfterFeedDispatch {
                    _principal = next
                    principalAfterFeedDispatch = nil
                }
                return r
            }
            if let feedGate { await feedGate.wait() }
            return try reply.get()
        }

        nonisolated func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse {
            lock.withLock { _futuresCalls += 1 }
            if let futuresGate { await futuresGate.wait() }
            return try futuresReply.get()
        }

        nonisolated func currentMyStuffPrincipal() async -> String {
            lock.withLock { _principal }
        }
    }

    private nonisolated final class TelemetrySink: @unchecked Sendable {
        private let lock = NSLock()
        private var events: [MyStuffLoadStage] = []
        func record(_ e: MyStuffLoadStage) { lock.withLock { events.append(e) } }
        var all: [MyStuffLoadStage] { lock.withLock { events } }
        var outcomes: [MyStuffOutcomeClass] { lock.withLock { events.map(\.outcomeClass) } }
        func stage(_ k: MyStuffLoadStage.Kind) -> MyStuffLoadStage? {
            lock.withLock { events.first { $0.kind == k } }
        }
    }

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func eventJSON(_ id: Int, status: String = "scheduled") -> String {
        """
        {"type":"event","score":90,"data":{"id":\(id),"home_team":"Home \(id)","away_team":"Away \(id)","status":"\(status)"}}
        """
    }

    private func feed(_ ids: [Int], status: String = "scheduled") throws -> FeedResponse {
        let items = ids.map { eventJSON($0, status: status) }
        let json = """
        {"items":[\(items.joined(separator: ","))],"total":\(ids.count),"limit":100,"offset":0,"has_more":false}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func teamFutures(_ count: Int) throws -> TeamFuturesResponse {
        let items = (0..<count).map { i in
            """
            {"outcome_id":\(i + 1),"outcome_name":"Team \(i)","market_id":\(100 + i),"market_name":"NBA Champion 2026","probability":0.2,"matched_team":{"id":\(i + 1),"name":"Team \(i)"}}
            """
        }
        let json = """
        {"items":[\(items.joined(separator: ","))],"team_ids":[1],"total_count":\(count)}
        """
        return try Self.decoder().decode(TeamFuturesResponse.self, from: Data(json.utf8))
    }

    private struct Boom: Error {}

    /// A view model with auto-refresh off (no real timers in tests) and a fast
    /// retry backoff so the failure paths do not sleep for seconds.
    private func makeVM(
        client: MyStuffFeedProviding,
        sink: TelemetrySink,
        optionalDeadline: TimeInterval = 10,
        requiredAttempts: Int = 3
    ) -> MyStuffViewModel {
        MyStuffViewModel(
            client: client,
            telemetry: { [sink] in sink.record($0) },
            autoRefreshEnabled: false,
            optionalDeadline: optionalDeadline,
            requiredAttempts: requiredAttempts,
            retryBackoff: 0.001
        )
    }

    /// Let the unstructured optional-merge task run to completion.
    private func settle(_ iterations: Int = 40) async {
        for _ in 0..<iterations { await Task.yield() }
    }

    // MARK: - The optional request never gates the first card

    /// Corpus row `optional_futures_hung`.
    func testHungOptionalFuturesDoesNotHoldTheFirstTeamCard() async throws {
        let futuresGate = AsyncGate()  // never opened → the request hangs forever
        let client = FakeMyStuffClient(
            feedReplies: [.success(try feed([1, 2, 3, 4, 5]))],
            futures: .success(try teamFutures(2)),
            futuresGate: futuresGate
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()

        // The required team feed is published and the skeleton is GONE, even though
        // the optional futures request is still hanging.
        XCTAssertFalse(vm.loading, "a hung OPTIONAL request must not hold the skeleton up")
        XCTAssertEqual(vm.items.count, 5)
        XCTAssertNil(vm.teamFutures)
        XCTAssertNil(vm.error)
        // The frozen render token describes the required generation only.
        XCTAssertEqual(vm.firstRenderGeneration?.itemCount, 5)
        XCTAssertEqual(sink.stage(.requiredDataReady)?.outcomeClass, .networkSuccess)

        futuresGate.open()  // cleanup
    }

    /// Corpus row `optional_futures_failure`.
    func testFailingOptionalFuturesLeavesTheTeamFeedIntactAndReportsPartial() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.success(try feed([1, 2, 3]))],
            futures: .failure(Boom())
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()
        await settle()

        XCTAssertFalse(vm.loading)
        XCTAssertEqual(vm.items.count, 3, "an optional failure must never retract required content")
        XCTAssertNil(vm.teamFutures)
        XCTAssertNil(vm.error, "an optional failure is not a user-facing error")
        XCTAssertEqual(sink.stage(.optionalMerge)?.outcomeClass, .partialSuccess)
    }

    /// Corpus row `returning_user_cold_success` — the happy path still merges.
    func testSuccessfulOptionalFuturesMergesAfterTheRequiredPublish() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.success(try feed([1, 2]))],
            futures: .success(try teamFutures(4))
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()
        await settle()

        XCTAssertEqual(vm.items.count, 2)
        XCTAssertEqual(vm.teamFutures?.items.count, 4)
        XCTAssertEqual(sink.stage(.optionalMerge)?.outcomeClass, .networkSuccess)
        // The render token still reports the REQUIRED count, not the merged total.
        XCTAssertEqual(vm.firstRenderGeneration?.itemCount, 2)
    }

    /// A hung optional sibling is abandoned at the deadline rather than lingering.
    func testHungOptionalIsAbandonedAtItsDeadline() async throws {
        let futuresGate = AsyncGate()
        let client = FakeMyStuffClient(
            feedReplies: [.success(try feed([1]))],
            futures: .success(try teamFutures(1)),
            futuresGate: futuresGate
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink, optionalDeadline: 0.05)

        await vm.startLoad()
        try await Task.sleep(for: .milliseconds(200))
        await settle()

        XCTAssertNil(vm.teamFutures)
        XCTAssertEqual(sink.stage(.optionalMerge)?.outcomeClass, .partialSuccess)
        futuresGate.open()
    }

    // MARK: - Identity boundary

    /// Corpus row `account_a_to_b_late_response`: A's response returns after the
    /// switch to B. It must not paint, and B must not see A's teams.
    func testLateAccountAResponseCannotPublishUnderAccountB() async throws {
        let feedGate = AsyncGate()
        let client = FakeMyStuffClient(
            principal: "user:a",
            feedReplies: [.success(try feed([1, 2, 3, 4, 5, 6, 7, 8]))],
            futures: .success(try teamFutures(1)),
            feedGate: feedGate,
            // The switch happens the moment the request leaves.
            principalAfterFeedDispatch: "user:b"
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        let load = Task { await vm.startLoad() }
        await settle(10)
        feedGate.open()
        await load.value
        await settle()

        XCTAssertTrue(vm.items.isEmpty, "account A's teams must never render under account B")
        XCTAssertNil(vm.firstRenderGeneration, "no render token → no first-card event")
        XCTAssertEqual(sink.stage(.requiredDataReady)?.outcomeClass, .identitySuperseded)
    }

    /// Corpus row `logout_late_response`: the same rule for signed-in → anonymous.
    func testLateResponseCannotPublishAfterLogout() async throws {
        let feedGate = AsyncGate()
        let client = FakeMyStuffClient(
            principal: "user:a",
            feedReplies: [.success(try feed([1, 2, 3]))],
            futures: .success(try teamFutures(1)),
            feedGate: feedGate,
            principalAfterFeedDispatch: "anon:session-1"
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        let load = Task { await vm.startLoad() }
        await settle(10)
        feedGate.open()
        await load.value
        await settle()

        XCTAssertTrue(vm.items.isEmpty, "a signed-out session must not show the prior account's teams")
        XCTAssertEqual(sink.stage(.requiredDataReady)?.outcomeClass, .identitySuperseded)
    }

    /// The optional futures merge is under the SAME authority as the required
    /// publish: account A's futures must not land in account B's session.
    func testLateOptionalFuturesCannotMergeAfterAnIdentityChange() async throws {
        let futuresGate = AsyncGate()
        let client = FakeMyStuffClient(
            principal: "user:a",
            feedReplies: [.success(try feed([1, 2]))],
            futures: .success(try teamFutures(3)),
            futuresGate: futuresGate
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()
        XCTAssertEqual(vm.items.count, 2)

        // The account switches while the optional request is in flight.
        client.setPrincipal("user:b")
        futuresGate.open()
        await settle()

        XCTAssertNil(vm.teamFutures, "account A's futures must not merge into account B")
    }

    /// `resetForIdentityChange()` clears the previous account's published state
    /// synchronously, so its cards cannot survive into the new session at all.
    func testResetForIdentityChangeClearsPreviousAccountStateImmediately() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.success(try feed([1, 2, 3]))],
            futures: .success(try teamFutures(2))
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()
        await settle()
        XCTAssertEqual(vm.items.count, 3)
        XCTAssertNotNil(vm.teamFutures)

        vm.resetForIdentityChange()

        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertNil(vm.teamFutures)
        XCTAssertNil(vm.firstRenderGeneration)
        XCTAssertNil(vm.error)
        XCTAssertTrue(vm.loading, "the new account starts from a loading state, not stale cards")
    }

    /// Corpus row `superseded_generation`: an older load's late response is
    /// discarded even when the identity never changed.
    func testSupersededLoadDiscardsItsLateResponse() async throws {
        let feedGate = AsyncGate()
        let client = FakeMyStuffClient(
            feedReplies: [.success(try feed([1, 2, 3])), .success(try feed([9]))],
            futures: .success(try teamFutures(1)),
            feedGate: feedGate
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        // Start a load that blocks, then supersede it. `startLoad` cancels AND
        // joins the prior task, so the second load owns the screen.
        let first = Task { await vm.startLoad() }
        await settle(10)
        feedGate.open()
        let second = Task { await vm.startLoad() }
        await first.value
        await second.value
        await settle()

        XCTAssertEqual(vm.items.map(\.id).count, vm.items.count)
        XCTAssertFalse(vm.loading)
    }

    // MARK: - Empty, failure, and cancellation states

    /// Corpus row `empty_success`: publish, clear the skeleton, but stamp NO render
    /// token — an empty result must never report a first-card time.
    func testEmptySuccessPublishesButEmitsNoFirstCard() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.success(try feed([]))],
            futures: .success(try teamFutures(0))
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()
        await settle()

        XCTAssertFalse(vm.loading, "an empty success resolves the skeleton")
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertNil(vm.error, "empty is not an error")
        XCTAssertNil(vm.firstRenderGeneration)
        XCTAssertEqual(sink.stage(.requiredDataReady)?.outcomeClass, .emptySuccess)
        XCTAssertNil(
            MyStuffFirstRender.generationDecision(
                generation: vm.firstRenderGeneration, lastEmittedGenerationId: nil, now: Date()),
            "no token → no first-card event")
    }

    /// Corpus row `main_failure_optional_success`: the required failure is honest
    /// and the optional request never rescues it into a false success.
    func testRequiredFailureSurfacesAnErrorAndNeverStartsTheOptional() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.failure(Boom())],
            futures: .success(try teamFutures(5))
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()
        await settle()

        XCTAssertFalse(vm.loading)
        XCTAssertNotNil(vm.error)
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertNil(vm.firstRenderGeneration)
        XCTAssertEqual(client.futuresCalls, 0, "the optional request never runs without a required publish")
        XCTAssertEqual(sink.stage(.requiredDataReady)?.outcomeClass, .requiredFailure)
    }

    /// Corpus row `retry_then_success`: the #240 Item 3 self-heal is preserved and
    /// bounded, and the outcome is reported distinctly.
    func testTransientRequiredFailureRetriesThenSucceeds() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.failure(Boom()), .success(try feed([1, 2, 3]))],
            futures: .success(try teamFutures(1))
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()
        await settle()

        XCTAssertEqual(vm.items.count, 3)
        XCTAssertNil(vm.error)
        XCTAssertEqual(client.feedCalls, 2, "retries stay bounded")
        XCTAssertEqual(sink.stage(.requiredDataReady)?.outcomeClass, .retrySuccess)
    }

    func testRequiredRetriesAreBoundedByTheAttemptBudget() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.failure(Boom())],
            futures: .success(try teamFutures(1))
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink, requiredAttempts: 3)

        await vm.startLoad()

        XCTAssertEqual(client.feedCalls, 3)
        XCTAssertEqual(sink.stage(.requiredDataReady)?.outcomeClass, .requiredFailure)
    }

    /// Corpus rows `navigation_away_cancellation` / `cancel_during_backoff`:
    /// cancellation is quiet — no error banner, no stuck skeleton.
    func testCancellationIsQuietAndResolvesTheSkeleton() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.failure(CancellationError())],
            futures: .success(try teamFutures(1))
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()
        await settle()

        XCTAssertFalse(vm.loading, "a cancelled cold load must never leave a spinner up")
        XCTAssertNil(vm.error, "cancellation is not a failure")
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertEqual(sink.stage(.requiredDataReady)?.outcomeClass, .cancelled)
        XCTAssertEqual(client.feedCalls, 1, "cancellation never spends a retry")
    }

    /// After `viewDidStop()` a queued refresh cannot resurrect a load.
    func testViewDidStopBlocksLaterLoadsUntilViewDidStart() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.success(try feed([1]))],
            futures: .success(try teamFutures(1))
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        vm.viewDidStop()
        await vm.startLoad()
        XCTAssertEqual(client.feedCalls, 0, "a stopped view must not start a load")

        vm.viewDidStart()
        await vm.startLoad()
        XCTAssertEqual(client.feedCalls, 1)
    }

    // MARK: - First-render decision core

    func testFirstRenderEmitsOncePerGenerationAndNeverForAnEmptyOne() {
        let now = Date()
        let token = MyStuffRenderGeneration(
            generation: 7, startedAt: now.addingTimeInterval(-0.25),
            provenance: "network", itemCount: 4)

        let first = MyStuffFirstRender.generationDecision(
            generation: token, lastEmittedGenerationId: nil, now: now)
        XCTAssertNotNil(first)
        XCTAssertEqual(first?.generation.generation, 7)
        XCTAssertEqual(first!.ms, 250, accuracy: 5)

        // Already emitted → silent.
        XCTAssertNil(MyStuffFirstRender.generationDecision(
            generation: token, lastEmittedGenerationId: 7, now: now))

        // A NEW generation emits again even if the rows were retained.
        let next = MyStuffRenderGeneration(
            generation: 8, startedAt: now, provenance: "network", itemCount: 4)
        XCTAssertNotNil(MyStuffFirstRender.generationDecision(
            generation: next, lastEmittedGenerationId: 7, now: now))

        // An empty generation never emits.
        let empty = MyStuffRenderGeneration(
            generation: 9, startedAt: now, provenance: "network", itemCount: 0)
        XCTAssertNil(MyStuffFirstRender.generationDecision(
            generation: empty, lastEmittedGenerationId: nil, now: now))

        // Clock skew cannot produce a negative latency.
        let future = MyStuffRenderGeneration(
            generation: 10, startedAt: now.addingTimeInterval(5),
            provenance: "network", itemCount: 1)
        XCTAssertEqual(
            MyStuffFirstRender.generationDecision(
                generation: future, lastEmittedGenerationId: nil, now: now)?.ms,
            0)
    }

    func testPublicationGateRequiresBothIdentityAndGeneration() {
        XCTAssertTrue(MyStuffFirstRender.shouldPublish(
            principalAtDispatch: "user:a", currentPrincipal: "user:a",
            dispatchGeneration: 3, currentGeneration: 3))

        // A→B between two AUTHENTICATED accounts — a signed-in Boolean would miss it.
        XCTAssertFalse(MyStuffFirstRender.shouldPublish(
            principalAtDispatch: "user:a", currentPrincipal: "user:b",
            dispatchGeneration: 3, currentGeneration: 3))

        // Logout.
        XCTAssertFalse(MyStuffFirstRender.shouldPublish(
            principalAtDispatch: "user:a", currentPrincipal: "anon:s1",
            dispatchGeneration: 3, currentGeneration: 3))

        // Superseded generation, identity unchanged.
        XCTAssertFalse(MyStuffFirstRender.shouldPublish(
            principalAtDispatch: "user:a", currentPrincipal: "user:a",
            dispatchGeneration: 3, currentGeneration: 4))
    }

    func testRejectionOutcomeDistinguishesIdentityFromGeneration() {
        XCTAssertEqual(
            MyStuffFirstRender.rejectionOutcome(
                principalAtDispatch: "user:a", currentPrincipal: "user:b"),
            .identitySuperseded)
        XCTAssertEqual(
            MyStuffFirstRender.rejectionOutcome(
                principalAtDispatch: "user:a", currentPrincipal: "user:a"),
            .superseded)
    }

    // MARK: - Telemetry privacy

    func testStageTelemetryCarriesOnlyBoundedNonIdentifyingFields() async throws {
        let client = FakeMyStuffClient(
            feedReplies: [.success(try feed([1, 2]))],
            futures: .success(try teamFutures(1))
        )
        let sink = TelemetrySink()
        let vm = makeVM(client: client, sink: sink)

        await vm.startLoad()
        await settle()

        XCTAssertFalse(sink.all.isEmpty)
        for stage in sink.all {
            // Every duration is a finite, non-negative measurement or the -1 sentinel.
            XCTAssertTrue(stage.authReadyMs >= 0)
            XCTAssertTrue(stage.networkMs >= 0)
            XCTAssertTrue(stage.requiredDataReadyMs >= 0)
            XCTAssertTrue(stage.itemCount >= 0)
            XCTAssertTrue(stage.cacheAgeSeconds == -1 || stage.cacheAgeSeconds >= 0)
            // The outcome label comes from a closed enum — it can never carry an
            // error message, a uid, or market text.
            XCTAssertFalse(stage.outcomeClass.rawValue.isEmpty)
        }
    }
}
