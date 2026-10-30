import XCTest
import Foundation
import Combine
@testable import Bain_Luck

/// #10090 / #11253 — Root's paired decision (reconciliation-contract-20261019):
/// the server sends a named `reconcile` control carrying a withdrawn source's
/// stable custody id and a row-wise `removal_rev` floor. It is not a price.
/// The page owes one authoritative detail + history pair that covers every
/// floor row and is what the page then shows, and the owed floor survives
/// failed, stale, in-flight and overtaken reads, resuming on its own.
@MainActor
final class AReconcileControlPaysAWithdrawnSourceFloor10090Tests: XCTestCase {
    private static let both = #""kalshi":{"value":0.5,"updated_at":"2026-09-27T17:00:00Z"},"polymarket":{"value":0.82,"updated_at":"2026-09-27T17:00:00Z"}"#
    private static func kalshiOnly(_ p: Double, at: String) -> String {
        #""kalshi":{"value":\#(p),"updated_at":"\#(at)"}"#
    }

    private static func control(_ custody: String = "c-1", floor: String = #"{"4242":11}"#,
                                extra: String = "") -> String {
        #"{"event_id":4242,"custody_id":"\#(custody)","removal_rev":\#(floor)\#(extra)}"#
    }

    private static func priced(_ revision: Int, _ p: Double, at: String = "2026-09-27T17:02:00Z",
                               status: String = "live") -> String {
        """
        {"event_id":4242,"p":\(p),"source":"kalshi","source_value":\(p),"updated_at":"\(at)",
         "status":"\(status)","rev":{"4242":\(revision)}}
        """
    }

    private static let finalFrame = """
        {"event_id":4242,"p":null,"source":null,"source_value":null,"updated_at":"2026-09-27T17:05:00Z",
         "status":"completed","rev":{"4242":10}}
        """

    private static func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    fileprivate static func detail(p: Double, revision: String, sources: String, status: String = "live",
                                   observedAt: String = "2026-09-27T17:00:00Z", id: Int = 4242) throws -> EventDetail {
        try decode(EventDetail.self, """
        {"id":\(id),"sport":"americanfootball_nfl","home_team":"Home","away_team":"Away","status":"\(status)",
         "home_score":7,"away_score":3,
         "current_odds":{"home_probability":\(p),"away_probability":\(1 - p)},
         "hero_probability":\(p),"hero_probability_source":"blend",
         "hero_probability_observed_at":"\(observedAt)",
         "blend_fold_revision":\(revision),"win_probability_sources":{\(sources)}}
        """)
    }

    /// `edge: nil` serves an unpinned history, which makes no revision claim.
    fileprivate static func history(p: Double, edge: String?, at: String, eventId: Int = 4242,
                                    pinned: Bool = true) throws -> EventHistoryResponse {
        let pin = edge.map { #""blend_edge_pinned":\#(pinned),"blend_edge_fold_revision":\#($0),"blend_edge_observed_at":"\#(at)","# } ?? ""
        return try decode(EventHistoryResponse.self, """
        {"event_id":\(eventId),"home_team":"Home","away_team":"Away","status":"live","history":[],\(pin)
         "aggregate_line":[{"timestamp":"\(at)","home_probability":\(p)}]}
        """)
    }

    /// #10090 history-consumer admission — a history carrying the producer's
    /// complete-build `history_fold_revision`, as raw JSON text so a malformed
    /// vector can be served (`nil` leaves the key out). `pin` is the raw pin
    /// fragment; the default is the producer's explicit unpinned shape.
    fileprivate static let unpinnedFragment = #""blend_edge_pinned":false,"blend_edge_fold_revision":null,"#
    fileprivate static func coverageHistory(p: Double, at: String, coverage: String?,
                                            pin: String = unpinnedFragment,
                                            eventId: Int = 4242) throws -> EventHistoryResponse {
        let vector = coverage.map { #""history_fold_revision":\#($0),"# } ?? ""
        return try decode(EventHistoryResponse.self, """
        {"event_id":\(eventId),"home_team":"Home","away_team":"Away","status":"live","history":[],\(pin)\(vector)
         "aggregate_line":[{"timestamp":"\(at)","home_probability":\(p)}]}
        """)
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        func fire(_ event: String, _ data: String = "") {
            for handler in handlers[event] ?? [] { handler(data) }
        }
        /// A decision-J heartbeat carrying `confirmed_at` (#10090).
        func beat(_ confirmed: String) {
            fire("heartbeat", #"{"t":"2026-09-27T17:30:00.000+00:00","confirmed_at":"\#(confirmed)"}"#)
        }
    }

    /// Every injected sleep waits here until the test fires its delay, so a
    /// retry happens only when the test says time has passed — and the delays
    /// asked are the recovery schedule, read off exactly.
    @MainActor private final class Sleeper {
        private(set) var asked: [TimeInterval] = []
        private var waiting: [(delay: TimeInterval, resume: CheckedContinuation<Void, Never>)] = []
        func sleep(_ delay: TimeInterval) async {
            asked.append(delay)
            await withCheckedContinuation { waiting.append((delay, $0)) }
        }
        func pending(_ delay: TimeInterval) -> Int { waiting.filter { $0.delay == delay }.count }
        func fire(_ delay: TimeInterval) {
            let due = waiting.filter { $0.delay == delay }
            waiting.removeAll { $0.delay == delay }
            due.forEach { $0.resume.resume() }
        }
        func drain() {
            let all = waiting
            waiting.removeAll()
            all.forEach { $0.resume.resume() }
        }
    }

    /// `load()` reads `page`; once `armed`, fresh reads are stream pairs served
    /// from `pairs` by absolute read index (the last repeats). A held index
    /// freezes both halves until `release()`.
    @MainActor private final class Client: EventDetailProviding {
        struct Declined: Error {}
        struct Pair {
            var revision: String
            var p: Double
            var sources: String
            var at: String
            var status = "live"
            var fails = false
            /// The history's pinned edge; defaults to the detail's revision.
            var edge: String?? = .none
            /// When set, the history is `coverageHistory` with this raw
            /// `history_fold_revision` (`.some(nil)`: key absent), `pin` its raw
            /// pin fragment and `historyEventId` its event.
            var coverage: String?? = .none
            var pin = AReconcileControlPaysAWithdrawnSourceFloor10090Tests.unpinnedFragment
            var historyEventId = 4242
            /// When set, the history half is exactly this payload.
            var servedHistory: EventHistoryResponse?
        }
        var page: EventDetail
        var pageHistory: EventHistoryResponse
        var pairs: [Pair] = []
        var holdPairs: Set<Int> = []
        var armed = false
        private(set) var detailReads = 0
        private(set) var historyReads = 0
        private(set) var inFlight = 0
        private(set) var maxInFlight = 0
        private var waiters: [(Int, CheckedContinuation<Void, Never>)] = []
        /// When set, the next ordinary (cached) history read waits for
        /// `releaseOrdinaryHistory()` and then serves this payload.
        var heldOrdinaryHistory: EventHistoryResponse?
        private(set) var ordinaryHistoryReads = 0
        private var ordinaryWaiter: CheckedContinuation<Void, Never>?
        func releaseOrdinaryHistory() {
            let waiter = ordinaryWaiter
            ordinaryWaiter = nil
            waiter?.resume()
        }
        init(page: EventDetail, history: EventHistoryResponse) {
            self.page = page
            self.pageHistory = history
        }
        func release() {
            let pending = waiters
            waiters.removeAll()
            for (index, waiter) in pending {
                holdPairs.remove(index)
                waiter.resume()
            }
        }
        private func hold(_ index: Int) async {
            guard holdPairs.contains(index) else { return }
            await withCheckedContinuation { waiters.append((index, $0)) }
        }
        func fetchEvent(id: Int) async throws -> EventDetail { page }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            ordinaryHistoryReads += 1
            guard let held = heldOrdinaryHistory else { return pageHistory }
            heldOrdinaryHistory = nil
            await withCheckedContinuation { ordinaryWaiter = $0 }
            return held
        }
        func fetchFreshEvent(id: Int) async throws -> EventDetail {
            guard armed else { return page }
            let index = detailReads
            detailReads += 1
            inFlight += 1
            maxInFlight = max(maxInFlight, inFlight)
            defer { inFlight -= 1 }
            let pair = pairs[min(index, pairs.count - 1)]
            await hold(index)
            if pair.fails { throw Declined() }
            return try AReconcileControlPaysAWithdrawnSourceFloor10090Tests.detail(
                p: pair.p, revision: pair.revision, sources: pair.sources, status: pair.status, observedAt: pair.at)
        }
        func fetchFreshEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            guard armed else { return pageHistory }
            let index = historyReads
            historyReads += 1
            let pair = pairs[min(index, pairs.count - 1)]
            await hold(index)
            if pair.fails { throw Declined() }
            if let served = pair.servedHistory { return served }
            if case .some(let coverage) = pair.coverage {
                return try AReconcileControlPaysAWithdrawnSourceFloor10090Tests.coverageHistory(
                    p: pair.p, at: pair.at, coverage: coverage, pin: pair.pin, eventId: pair.historyEventId)
            }
            let edge: String?
            switch pair.edge {
            case .none: edge = pair.revision
            case .some(let value): edge = value
            }
            return try AReconcileControlPaysAWithdrawnSourceFloor10090Tests.history(p: pair.p, edge: edge, at: pair.at)
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private var clock: TimeInterval = 1_800_000_000
    private var sleeper: Sleeper!
    private var teardown: [() -> Void] = []

    override func tearDown() async throws {
        teardown.forEach { $0() }
        teardown.removeAll()
        sleeper?.drain()
        try await super.tearDown()
    }

    /// A live one-row blend at revision 10: hero 60, rail Kalshi 50 + Polymarket 82.
    private func opened(
        page: EventDetail? = nil, history: EventHistoryResponse? = nil, pairs: [Client.Pair], holdPairs: Set<Int> = []
    ) async throws -> (Client, Handle, EventDetailViewModel) {
        let client = Client(
            page: try page ?? Self.detail(p: 0.6, revision: #"{"4242":10}"#, sources: Self.both),
            history: try history ?? Self.history(p: 0.6, edge: #"{"4242":10}"#, at: "2026-09-27T17:00:00Z")
        )
        client.pairs = pairs
        client.holdPairs = holdPairs
        let handle = Handle()
        let sleeper = Sleeper()
        self.sleeper = sleeper
        let vm = EventDetailViewModel(
            eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { [weak self] in self?.clock ?? 0 },
            sleep: { delay in await sleeper.sleep(delay) }
        )
        teardown.append { vm.stopRefresh() }
        await vm.load()
        client.armed = true
        handle.fire("open")
        return (client, handle, vm)
    }

    private func settle(_ done: () -> Bool) async throws {
        for _ in 0..<400 where !done() { try await Task.sleep(for: .milliseconds(5)) }
    }

    private func quiet() async throws { try await Task.sleep(for: .milliseconds(150)) }

    /// The reconcile re-ask: the clock moves with it, so the coalescer's
    /// one-second window never adds a sleep of its own.
    private func elapse(_ delay: TimeInterval) async throws {
        try await settle { sleeper.pending(delay) == 1 }
        XCTAssertEqual(sleeper.pending(delay), 1, "a \(delay)s re-ask is armed")
        clock += delay
        sleeper.fire(delay)
    }

    private static let reconcileDelays = Set(EventDetailViewModel.reconcileRetryDelays)
    private var reconcileAsks: [TimeInterval] { sleeper.asked.filter { Self.reconcileDelays.contains($0) } }

    private static let removedAt = "2026-09-27T17:00:30Z"
    private static let stale10 = Client.Pair(revision: #"{"4242":10}"#, p: 0.6, sources: both,
                                             at: "2026-09-27T17:00:00Z")
    private static let without11 = Client.Pair(revision: #"{"4242":11}"#, p: 0.5,
                                               sources: kalshiOnly(0.5, at: removedAt), at: removedAt)

    // MARK: - R1 the control itself

    func testAControlWritesNothingItselfAndOnePairDropsTheWithdrawnSource() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.without11])
        let blend = vm.liveBlend
        let activity = vm.priceActivity
        // A producer bug that adds price-shaped keys changes nothing: none is read.
        handle.fire("reconcile", Self.control(extra: #","p":0.99,"status":"completed","updated_at":"2026-09-27T18:00:00Z","rev":{"4242":99}"#))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6, "a control is not a price")
        XCTAssertEqual(vm.event?.status, "live", "nor a status")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 10], "nor a revision to adopt")
        XCTAssertEqual(vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue, 0.82)
        XCTAssertEqual(vm.liveBlend, blend, "no chart point")
        XCTAssertEqual(vm.priceActivity, activity, "no receipt")
        XCTAssertFalse(vm.streamHasPushedPrice, "no delivery")
        XCTAssertEqual(vm.reconcileOwedSince, clock, "owed from its arrival")

        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "exactly one paired read")
        XCTAssertEqual(client.historyReads, 1)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"], "the withdrawn venue leaves the rail")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5)
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.5)
        XCTAssertFalse(vm.streamHasPushedPrice, "a control-asked pair earns no delivery on the control's account")
        XCTAssertTrue(reconcileAsks.isEmpty, "a paid floor arms no re-ask")
    }

    // MARK: - R2 row-wise coverage

    func testAPairMissingAFloorRowDoesNotPayIt() async throws {
        let withSibling = Client.Pair(revision: #"{"4242":11,"77":3}"#, p: 0.5,
                                      sources: Self.kalshiOnly(0.5, at: Self.removedAt), at: Self.removedAt)
        let (client, handle, vm) = try await opened(pairs: [Self.without11, withSibling])
        let owedAt = clock
        handle.fire("reconcile", Self.control(floor: #"{"4242":11,"77":3}"#))
        try await settle { client.detailReads == 1 && vm.event?.winProbabilitySources?["polymarket"] == nil }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "row 77 is not in the response, so it is not covered")
        try await elapse(1.5)
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 2)
        XCTAssertEqual(reconcileAsks, [1.5])
    }

    /// Root's D4 ruling: the history half pays only on affirmative proof. A
    /// covering detail beside an unpinned history, a failed pair and a pinned
    /// edge below the floor all keep it owed; a proven covering history later
    /// pays with nothing but time passing.
    func testAnUnprovenHistoryNeverPaysAndAProvenOneLaterPaysWithNoNewInput() async throws {
        var unpinned = Self.without11
        unpinned.edge = .some(nil)
        var failing = Self.without11
        failing.fails = true
        var staleEdge = Self.without11
        staleEdge.edge = .some(#"{"4242":10}"#)
        let (client, handle, vm) = try await opened(pairs: [unpinned, failing, staleEdge, Self.without11])
        let owedAt = clock
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && vm.event?.winProbabilitySources?["polymarket"] == nil }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a covering detail beside an unpinned history pays nothing")

        try await elapse(1.5)
        try await settle { client.detailReads == 2 && vm.pricePairRefreshFailed }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a failed pair keeps it")

        try await settle { sleeper.pending(2) == 1 }
        clock += 2
        sleeper.fire(2)
        try await settle { client.detailReads == 3 && !vm.pricePairRefreshFailed }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a pinned edge below the floor keeps it")

        try await elapse(6)
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 4)
        XCTAssertEqual(reconcileAsks, [1.5, 6], "the reconcile re-ask, with the pair retry owning the failure")
    }

    // MARK: - R3 an older/equal control after a newer sibling

    func testAnOlderControlAfterANewerQuoteIsStillOwedAndAKeptHeadlinePaysNothing() async throws {
        let fresh12 = Client.Pair(revision: #"{"4242":12}"#, p: 0.46,
                                  sources: Self.kalshiOnly(0.46, at: "2026-09-27T17:02:00Z"), at: "2026-09-27T17:02:00Z")
        let (client, handle, vm) = try await opened(pairs: [Self.without11, fresh12])
        handle.fire("probability", Self.priced(12, 0.46))
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 12])
        handle.fire("reconcile", Self.control(floor: #"{"4242":11}"#))
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "a held revision past the floor proves nothing: read")
        // Served 11 loses to held 12, which keeps the held rail with it.
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.46, "the newer price is kept")
        XCTAssertEqual(vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue, 0.82)
        XCTAssertNotNil(vm.reconcileOwedSince, "a kept headline is not the response on the page")

        try await elapse(1.5)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertEqual(client.detailReads, 2)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.46)
    }

    // MARK: - R4 a stale server: resumes alone, backs off, never gives up

    func testAStaleServerKeepsTheFloorOwedAndTheRetryResumesWithNoNewInput() async throws {
        let stale = Array(repeating: Self.stale10, count: 6)
        let (client, handle, vm) = try await opened(pairs: stale + [Self.without11])
        let owedAt = clock
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 }
        // No frame, control, tap or load from here on: only time passes.
        for delay in [1.5, 3, 6, 12, 24, 24] {
            XCTAssertEqual(vm.reconcileOwedSince, owedAt, "still owed before the \(delay)s re-ask")
            XCTAssertEqual(vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue, 0.82,
                           "nothing claims the venue left")
            let reads = client.detailReads
            try await elapse(delay)
            try await settle { client.detailReads == reads + 1 }
        }
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 7)
        XCTAssertEqual(client.maxInFlight, 1, "one pair at a time")
        XCTAssertEqual(reconcileAsks, [1.5, 3, 6, 12, 24, 24], "capped backoff, no retry cap")
        XCTAssertEqual(reconcileAsks.reduce(0, +), 70.5, "measured remaining delay after six stale answers")
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
    }

    // MARK: - R5 failures

    func testAFailedPairKeepsTheFloorAndThePairRetryOwnsTheReask() async throws {
        var failing = Self.without11
        failing.fails = true
        let (client, handle, vm) = try await opened(pairs: [failing, Self.without11])
        let owedAt = clock
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && vm.pricePairRefreshFailed }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a failure pays nothing")
        XCTAssertEqual(sleeper.pending(2), 1, "the #9657 pair retry owns the re-ask")
        XCTAssertEqual(sleeper.pending(1.5), 0, "and no second retry stacks beside it")
        clock += 2
        sleeper.fire(2)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertEqual(client.detailReads, 2)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
    }

    /// The pair retry does NOT run here: a newer accepted push overtook the
    /// failed read, so the page is not marked failed (#9657). Reusing that
    /// retry alone would strand the floor; the reconcile re-ask resumes it.
    func testAFailedPairOvertakenByAPushStillResumesTheFloor() async throws {
        var failing = Self.without11
        failing.fails = true
        let fresh12 = Client.Pair(revision: #"{"4242":12}"#, p: 0.46,
                                  sources: Self.kalshiOnly(0.46, at: "2026-09-27T17:02:00Z"), at: "2026-09-27T17:02:00Z")
        let (client, handle, vm) = try await opened(pairs: [failing, fresh12], holdPairs: [0])
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        handle.fire("probability", Self.priced(12, 0.46))
        clock += 2
        client.release()
        try await quiet()
        XCTAssertFalse(vm.pricePairRefreshFailed, "overtaken, so no pair retry is armed")
        XCTAssertEqual(sleeper.pending(2), 0)
        XCTAssertNotNil(vm.reconcileOwedSince)
        try await elapse(1.5)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertEqual(client.detailReads, 2)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
    }

    // MARK: - R6 a pair already in flight

    func testAControlDuringAnInflightPairCoalescesIntoOneTrailingPair() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.stale10, Self.without11], holdPairs: [0, 1])
        // An unrelated pair (an unorderable frame) is in flight first.
        handle.fire("probability", """
        {"event_id":4242,"p":null,"source":null,"source_value":null,"updated_at":null,"status":"live","rev":{"9999":1}}
        """)
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        let owedAt = clock
        handle.fire("reconcile", Self.control("c-a", floor: #"{"4242":11}"#))
        clock += 5
        // Older than the floor already owed: it tightens nothing and loosens nothing.
        handle.fire("reconcile", Self.control("c-b", floor: #"{"4242":10}"#))
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "no parallel pair")
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "the earliest unpaid arrival is kept")
        clock += 2
        client.release()
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "the in-flight pair (10) cannot pay the merged floor (11)")
        client.release()
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 2, "one trailing pair pays it")
        XCTAssertEqual(client.maxInFlight, 1)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
    }

    // MARK: - R7 repeatedly overtaken reads

    /// Progress under continuous ticks: each pair is overtaken by a newer
    /// price, so the floor stays owed and the re-ask backs off; the first pair
    /// a price does not overtake pays it. If prices never paused, the floor
    /// would stay owed at one pair per 24 s — unresolved, never declared paid.
    func testRepeatedlyOvertakenPairsKeepTheNewestPriceAndTheFirstUnovertakenPairPays() async throws {
        let served12 = Client.Pair(revision: #"{"4242":12}"#, p: 0.47,
                                   sources: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z"), at: "2026-09-27T17:02:00Z")
        let served13 = Client.Pair(revision: #"{"4242":13}"#, p: 0.46,
                                   sources: Self.kalshiOnly(0.46, at: "2026-09-27T17:03:00Z"), at: "2026-09-27T17:03:00Z")
        let (client, handle, vm) = try await opened(pairs: [Self.without11, served12, served13], holdPairs: [0, 1])
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        handle.fire("probability", Self.priced(12, 0.47))
        clock += 2
        client.release()
        try await quiet()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.47)
        XCTAssertNotNil(vm.reconcileOwedSince)
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.5, "the pair's history half still lands")

        try await elapse(1.5)
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        handle.fire("probability", Self.priced(13, 0.46, at: "2026-09-27T17:03:00Z"))
        clock += 2
        client.release()
        try await quiet()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.46)
        XCTAssertNotNil(vm.reconcileOwedSince)

        try await elapse(3)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertEqual(client.detailReads, 3)
        XCTAssertEqual(reconcileAsks, [1.5, 3])
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.46)
    }

    // MARK: - R8 final

    func testAControlAfterAPushedFinalIsIgnoredAndCannotReopenIt() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.without11])
        handle.fire("probability", Self.finalFrame)
        XCTAssertEqual(vm.event?.status, "completed")
        handle.fire("reconcile", Self.control())
        try await quiet()
        XCTAssertEqual(client.detailReads, 0, "a finished page takes no control")
        XCTAssertNil(vm.reconcileOwedSince)
        XCTAssertEqual(vm.event?.status, "completed")
    }

    func testAFinalDuringTheReadStaysFinalAndALateControlAsksNothing() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.without11], holdPairs: [0])
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        handle.fire("probability", Self.finalFrame)
        clock += 2
        client.release()
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(vm.event?.status, "completed", "a live response never reopens a pushed final")
        handle.fire("reconcile", Self.control("c-late"))
        try await quiet()
        XCTAssertEqual(client.detailReads, 1)
        XCTAssertEqual(vm.event?.status, "completed")
        XCTAssertTrue(reconcileAsks.isEmpty)
    }

    func testAServedFinalRetiresTheFloorThroughItsNamedOwner() async throws {
        var served = Self.stale10
        served.status = "completed"
        let (client, handle, vm) = try await opened(pairs: [served])
        handle.fire("reconcile", Self.control())
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(vm.event?.status, "completed")
        XCTAssertEqual(client.detailReads, 1)
        XCTAssertTrue(reconcileAsks.isEmpty, "nothing re-asks a finished page")
    }

    // MARK: - R9 transport activity is not delivery

    func testControlsAndTheirPairsDoNotPostponeTheDataSilenceFallback() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.stale10])
        XCTAssertTrue(vm.streamDelivering)
        for step in 1...5 {
            clock += 20
            handle.fire("reconcile", Self.control("c-\(step)", floor: #"{"4242":10}"#))
            try await settle { client.detailReads == step && vm.reconcileOwedSince == nil }
            vm.tickStream()
        }
        XCTAssertFalse(vm.streamDelivering, "100 s of controls and unchanged pairs is data silence")
    }

    // MARK: - R10 bounded dedup

    func testAPaidCustodyIsDedupedInBoundedMemoryAndAnEvictedOneCostsOneRead() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.without11])
        handle.fire("reconcile", Self.control("c-0"))
        try await settle { vm.reconcileOwedSince == nil }
        clock += 2  // outside the coalescer's window, so an owed read would start at once
        handle.fire("reconcile", Self.control("c-0"))
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "a paid custody re-sent asks nothing")
        XCTAssertNil(vm.reconcileOwedSince)
        clock += 2
        handle.fire("reconcile", Self.control("c-0", floor: #"{"4242":12}"#))
        try await settle { client.detailReads == 2 }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "the same custody naming a row past its paid floor is owed again")
        vm.stopRefresh()
        XCTAssertNil(vm.reconcileOwedSince)
        // Back on the page (its fresh load is itself one read here).
        clock += 2
        await vm.load()
        handle.fire("open")

        for n in 1...EventDetailViewModel.reconcileSettledMemory {
            let reads = client.detailReads
            clock += 2
            handle.fire("reconcile", Self.control("c-\(n)"))
            try await settle { client.detailReads == reads + 1 && vm.reconcileOwedSince == nil }
        }
        XCTAssertEqual(vm.reconcileMemory.settled, EventDetailViewModel.reconcileSettledMemory, "bounded")
        let reads = client.detailReads
        clock += 2
        handle.fire("reconcile", Self.control("c-0"))
        try await settle { client.detailReads == reads + 1 }
        XCTAssertEqual(client.detailReads, reads + 1, "evicted from the paid memory: one defensive read")
    }

    func testOwedCustodyMemoryIsBoundedWhileTheFloorKeepsEveryRow() async throws {
        let wide = Client.Pair(revision: #"{"4242":11,"1":1,"2":1,"3":1,"4":1,"5":1,"6":1,"7":1,"8":1,"9":1,"10":1,"11":1}"#,
                               p: 0.5, sources: Self.kalshiOnly(0.5, at: Self.removedAt), at: Self.removedAt)
        let (client, handle, vm) = try await opened(pairs: [Self.without11, Self.without11, wide], holdPairs: [0])
        handle.fire("reconcile", Self.control("c-0"))
        try await settle { client.detailReads == 1 }
        for n in 1...11 { handle.fire("reconcile", Self.control("c-\(n)", floor: #"{"\#(n)":1}"#)) }
        XCTAssertEqual(vm.reconcileMemory.owed, EventDetailViewModel.reconcileOwedCustodyMemory, "bounded")
        clock += 2
        client.release()
        // The in-flight pair and the one trailing pair both lack rows 1–11.
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "every row stays owed though only eight ids are remembered")
        try await elapse(3)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertEqual(client.detailReads, 3)
    }

    // MARK: - R11 navigation and rollover

    func testLeavingThePageRetiresTheFloorAndItsReask() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.stale10])
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && sleeper.pending(1.5) == 1 }
        vm.stopRefresh()
        XCTAssertNil(vm.reconcileOwedSince, "the return's fresh load and next connection own it")
        clock += 1.5
        sleeper.fire(1.5)
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "a left page asks nothing")
    }

    func testARolloverKeepsTheFloorAndTheReaskStillPaysIt() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.stale10, Self.without11])
        let owedAt = clock
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && sleeper.pending(1.5) == 1 }
        clock += 120
        handle.fire("reconnect")
        XCTAssertFalse(vm.streamDelivering)
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "the debt describes the page, not the socket")
        sleeper.fire(1.5)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertEqual(client.detailReads, 2)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
    }

    // MARK: - #11772 R1: a confirmation waits for this delivery's connect reconcile

    /// The server sends the first confirmed heartbeat BEFORE its connect
    /// reconcile (lane1's probe at live f8c96b59), and only that reconcile's
    /// floor makes a served price too old to replay owe its pair read. So a
    /// beat dates nothing until the reconcile has arrived and its floor is paid.
    func testAConfirmationWaitsForThisDeliverysReconcileAndItsFloor() async throws {
        let below = Client.Pair(revision: #"{"4242":11}"#, p: 0.55, sources: Self.both, at: "2026-09-27T17:01:00Z")
        let covering = Client.Pair(revision: #"{"4242":12}"#, p: 0.56, sources: Self.both, at: "2026-09-27T17:02:00Z")
        let (client, handle, vm) = try await opened(pairs: [below, covering])
        handle.beat("2026-09-27T17:05:00.000+00:00")
        XCTAssertNotNil(vm.streamConfirmedAt, "kept")
        XCTAssertNil(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "open → beat: no reconcile yet")
        XCTAssertEqual(vm.liveUpdateStatus, .awaitingUpdate)
        // A floor past the held revision; a pair below it pays nothing.
        handle.fire("reconcile", Self.control(floor: #"{"4242":12}"#))
        try await settle { client.detailReads == 1 && vm.event?.blendFoldRevision?.revision?.rows == ["4242": 11] }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "still owed")
        XCTAssertNil(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "the shown 11 is below the floor")
        XCTAssertEqual(vm.liveUpdateStatus, .awaitingUpdate)
        // The re-ask covers it: the confirmation now dates the number on screen.
        try await elapse(1.5)
        try await settle { vm.reconcileOwedSince == nil }
        let shown = try XCTUnwrap(vm.event)
        XCTAssertEqual(shown.blendFoldRevision?.revision?.rows, ["4242": 12])
        XCTAssertEqual(vm.confirmedAtCoveringShown(shown), "2026-09-27T17:05:00Z".asDate)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
    }

    /// A reconnect re-sends a custody this page already paid: nothing is owed,
    /// and the reconcile still counts, so its confirmation applies at once.
    func testAReconnectsPaidReconcileAppliesTheConfirmationRightAfterIt() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.without11])
        handle.fire("reconcile", Self.control("c-1"))
        try await settle { vm.reconcileOwedSince == nil }
        handle.beat("2026-09-27T17:05:00.000+00:00")
        XCTAssertEqual(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "2026-09-27T17:05:00Z".asDate)
        // Back on the page: a new delivery, whose first beat again comes first.
        vm.stopRefresh()
        clock += 2
        await vm.load()
        handle.fire("open")
        // The reload's own chart re-read settles first; nothing is owed after it.
        try await quiet()
        let reads = client.detailReads
        handle.beat("2026-09-27T17:06:00.000+00:00")
        XCTAssertNil(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "this delivery has no reconcile yet")
        XCTAssertEqual(vm.liveUpdateStatus, .awaitingUpdate)
        clock += 2
        handle.fire("reconcile", Self.control("c-1"))
        XCTAssertNil(vm.reconcileOwedSince, "a paid custody owes nothing")
        XCTAssertEqual(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "2026-09-27T17:06:00Z".asDate,
                       "applied right after the reconcile")
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        try await quiet()
        XCTAssertEqual(client.detailReads, reads, "and asked nothing")
    }

    /// A dropped delivery takes its reconcile with its confirmation: the
    /// transport's own retry (#920) opens a new delivery that waits for its own.
    func testADroppedDeliveryTakesItsReconcileWithItsConfirmation() async throws {
        let (_, handle, vm) = try await opened(pairs: [Self.without11])
        handle.fire("reconcile", Self.control("c-1"))
        try await settle { vm.reconcileOwedSince == nil }
        handle.beat("2026-09-27T17:05:00.000+00:00")
        XCTAssertEqual(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "2026-09-27T17:05:00Z".asDate)
        handle.fire("error")
        XCTAssertFalse(vm.streamDelivering)
        XCTAssertNil(vm.streamConfirmedAt)
        handle.fire("open")
        XCTAssertTrue(vm.streamDelivering)
        handle.beat("2026-09-27T17:06:00.000+00:00")
        XCTAssertNil(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)),
                     "the dropped delivery's reconcile does not carry over")
        handle.fire("reconcile", Self.control("c-1"))
        XCTAssertEqual(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "2026-09-27T17:06:00Z".asDate)
    }

    /// Leaving the page takes the reconcile too, even one that arrived while
    /// no delivery was up (after an error, before the retry's `open`): the
    /// stop changes no delivery, so only the page's own stop clears it.
    func testLeavingThePageTakesAReconcileThatArrivedWithNoDelivery() async throws {
        let (_, handle, vm) = try await opened(pairs: [Self.without11])
        handle.fire("reconcile", Self.control("c-1"))
        try await settle { vm.reconcileOwedSince == nil }
        handle.fire("error")
        XCTAssertFalse(vm.streamDelivering)
        handle.fire("reconcile", Self.control("c-1"))
        vm.stopRefresh()
        clock += 2
        await vm.load()
        handle.fire("open")
        try await quiet()
        handle.beat("2026-09-27T17:06:00.000+00:00")
        XCTAssertNil(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "the left page's reconcile does not carry over")
    }

    // MARK: - #11772 R4: the reconcile belongs to the connection; R5: its flip re-renders

    /// A quiet market: 90 s with no adopted price reports delivery down on a
    /// socket that stays open, and that socket never re-sends its connect
    /// reconcile. The connection's reconcile still stands, so the next beat
    /// confirms the shown price again with no new reconcile.
    func testAQuietLapseOnTheOpenSocketKeepsThisConnectionsReconcile() async throws {
        let (_, handle, vm) = try await opened(pairs: [Self.without11])
        handle.fire("reconcile", Self.control("c-1"))
        try await settle { vm.reconcileOwedSince == nil }
        handle.beat("2026-09-27T17:05:00.000+00:00")
        XCTAssertEqual(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "2026-09-27T17:05:00Z".asDate)
        // Beats keep the transport alive; no price is adopted for 100 s.
        for _ in 1...5 {
            clock += 20
            handle.beat("2026-09-27T17:05:00.000+00:00")
            vm.tickStream()
        }
        XCTAssertFalse(vm.streamDelivering, "data silence: delivery is down")
        XCTAssertFalse(handle.isClosed, "on a socket that stays open")
        XCTAssertNil(vm.streamConfirmedAt, "the delivery took its confirmation")
        handle.beat("2026-09-27T17:06:00.000+00:00")
        let shown = try XCTUnwrap(vm.event)
        XCTAssertEqual(vm.confirmedAtCoveringShown(shown), "2026-09-27T17:06:00Z".asDate,
                       "the next beat confirms with no new reconcile")
        XCTAssertEqual(vm.displayedProbabilityAgeClock(shown), "2026-09-27T17:06:00Z".asDate)
    }

    /// A reconcile that arrives between a transport error and its retry's
    /// `open` belongs to no connection: the retry's `open` clears it, and that
    /// connection's beats wait for its own reconcile.
    func testAReconcileBetweenAnErrorAndTheRetrysOpenDoesNotCarryOver() async throws {
        let (_, handle, vm) = try await opened(pairs: [Self.without11])
        handle.fire("reconcile", Self.control("c-1"))
        try await settle { vm.reconcileOwedSince == nil }
        handle.fire("error")
        XCTAssertFalse(vm.streamDelivering)
        handle.fire("reconcile", Self.control("c-1"))
        handle.fire("open")
        XCTAssertTrue(vm.streamDelivering)
        handle.beat("2026-09-27T17:06:00.000+00:00")
        XCTAssertNil(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)),
                     "this connection has no reconcile of its own yet")
        handle.fire("reconcile", Self.control("c-1"))
        XCTAssertEqual(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "2026-09-27T17:06:00Z".asDate)
    }

    /// R5: a reconnect's paid re-send changes nothing else the page reads (the
    /// beat before it already set the same confirmation), so opening the
    /// claim must publish by itself, or the status keeps "waiting".
    func testAPaidReconcileThatOpensTheConfirmationPublishes() async throws {
        let (_, handle, vm) = try await opened(pairs: [Self.without11])
        handle.fire("reconcile", Self.control("c-1"))
        try await settle { vm.reconcileOwedSince == nil }
        handle.fire("error")
        handle.fire("open")
        handle.beat("2026-09-27T17:06:00.000+00:00")
        XCTAssertNil(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)))
        XCTAssertEqual(vm.liveUpdateStatus, .awaitingUpdate)
        var published = 0
        let watch = vm.objectWillChange.sink { _ in published += 1 }
        defer { watch.cancel() }
        handle.fire("reconcile", Self.control("c-1"))
        XCTAssertNil(vm.reconcileOwedSince, "paid: the early return")
        XCTAssertGreaterThanOrEqual(published, 1, "the flip re-renders the page")
        XCTAssertEqual(vm.confirmedAtCoveringShown(try XCTUnwrap(vm.event)), "2026-09-27T17:06:00Z".asDate)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        // A repeat flips nothing, so it publishes nothing.
        published = 0
        handle.fire("reconcile", Self.control("c-1"))
        XCTAssertEqual(published, 0)
    }

    // MARK: - R12 the pure rules

    func testCoverageIsRowWise() throws {
        let floor = try XCTUnwrap(FoldRevision(["1": 5, "2": 7]))
        XCTAssertTrue(try XCTUnwrap(FoldRevision(["1": 5, "2": 7])).covers(floor))
        XCTAssertTrue(try XCTUnwrap(FoldRevision(["1": 6, "2": 9, "3": 1])).covers(floor))
        XCTAssertFalse(try XCTUnwrap(FoldRevision(["1": 9])).covers(floor), "a missing row refuses")
        XCTAssertFalse(try XCTUnwrap(FoldRevision(["1": 9, "2": 6])).covers(floor))
    }

    func testFloorShownRefusesAnotherEventAKeptHeadlineAndAStaleEdge() throws {
        let floor = try XCTUnwrap(FoldRevision(["4242": 11]))
        let served = try Self.detail(p: 0.5, revision: #"{"4242":11}"#, sources: Self.kalshiOnly(0.5, at: Self.removedAt))
        let edge11 = try Self.history(p: 0.5, edge: #"{"4242":11}"#, at: Self.removedAt)
        let shown = LiveEventPriceReconciliation.reconcileFloorShown
        XCTAssertTrue(shown(floor, served, edge11, served))
        XCTAssertFalse(shown(floor, served, try Self.history(p: 0.5, edge: nil, at: Self.removedAt), served),
                       "an unpinned history proves nothing")
        XCTAssertFalse(shown(floor, served, try Self.history(p: 0.5, edge: #"{"4242":11}"#, at: Self.removedAt,
                                                             pinned: false), served),
                       "a revision on an edge the server did not pin proves nothing")
        XCTAssertFalse(shown(floor, served, edge11, nil))
        XCTAssertFalse(shown(floor, served, try Self.history(p: 0.5, edge: #"{"4242":10}"#, at: Self.removedAt), served))
        XCTAssertFalse(shown(floor, served, try Self.history(p: 0.5, edge: #"{"4242":11}"#, at: Self.removedAt, eventId: 1), served))
        let kept = try Self.detail(p: 0.46, revision: #"{"4242":12}"#, sources: Self.both)
        XCTAssertFalse(shown(floor, served, edge11, kept), "the page shows a different revision")
        let otherEvent = try Self.detail(p: 0.5, revision: #"{"4242":11}"#,
                                         sources: Self.kalshiOnly(0.5, at: Self.removedAt), id: 1)
        XCTAssertFalse(shown(floor, served, edge11, otherEvent))
        let finished = try Self.detail(p: 0.6, revision: #"{"4242":10}"#, sources: Self.both, status: "completed")
        XCTAssertFalse(shown(floor, finished, try Self.history(p: 0.6, edge: #"{"4242":10}"#, at: Self.removedAt), finished),
                       "a served final pays nothing; leaving the priced states retires the floor instead")
    }

    // MARK: - R13 a complete fresh history pays the history half without a pin

    private static func covering(_ coverage: String?, _ base: Client.Pair = without11) -> Client.Pair {
        var pair = base
        pair.coverage = .some(coverage)
        return pair
    }

    private static let pinnedBelowFragment = #""blend_edge_pinned":true,"blend_edge_fold_revision":{"4242":10},"#
    private static let pinnedNoRevisionFragment = #""blend_edge_pinned":true,"blend_edge_fold_revision":null,"#

    /// Fires whichever reconcile re-ask is armed next, moving the clock with it.
    private func elapseNextReask() async throws {
        var due: TimeInterval?
        for _ in 0..<400 {
            due = EventDetailViewModel.reconcileRetryDelays.first { sleeper.pending($0) == 1 }
            if due != nil { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let delay = try XCTUnwrap(due, "a reconcile re-ask is armed")
        clock += delay
        sleeper.fire(delay)
    }

    /// Root's history-consumer admission. Every response that does not prove
    /// the history half keeps the floor owed — null, absent, malformed, empty,
    /// row-missing, older, another event's, a pinned edge below the floor or
    /// without a revision beside a covering vector, and a failed pair — and
    /// the first complete fresh history whose vector covers the floor pays it
    /// with nothing but time passing: no quote, no pin, no new point.
    func testRefusedHistoryVectorsStayOwedAndALaterCompleteOnePaysWithNoQuote() async throws {
        var failing = Self.covering(#"{"4242":11}"#)
        failing.fails = true
        var otherEvent = Self.covering(#"{"4242":11}"#)
        otherEvent.historyEventId = 1
        var pinnedBelow = Self.covering(#"{"4242":11}"#)
        pinnedBelow.pin = Self.pinnedBelowFragment
        var pinnedNoRevision = Self.covering(#"{"4242":11}"#)
        pinnedNoRevision.pin = Self.pinnedNoRevisionFragment
        let refusals: [(name: String, pair: Client.Pair)] = [
            ("a null vector", Self.covering("null")),
            ("an absent vector", Self.covering(nil)),
            ("a string vector", Self.covering(#""4242:11""#)),
            ("an array vector", Self.covering("[11]")),
            ("an empty vector", Self.covering("{}")),
            ("a fractional row", Self.covering(#"{"4242":11.5}"#)),
            ("a string row", Self.covering(#"{"4242":"11"}"#)),
            ("a failed pair", failing),
            ("a null row", Self.covering(#"{"4242":null}"#)),
            ("a negative row", Self.covering(#"{"4242":-1}"#)),
            ("an unsafe-integer row", Self.covering(#"{"4242":9007199254740992}"#)),
            ("a vector missing the floor row", Self.covering(#"{"77":11}"#)),
            ("an older vector", Self.covering(#"{"4242":10}"#)),
            ("another event's history", otherEvent),
            ("a pinned edge below the floor beside a covering vector", pinnedBelow),
            ("a pinned edge without a revision beside a covering vector", pinnedNoRevision),
        ]
        let good = Self.covering(#"{"4242":11}"#)
        let (client, handle, vm) = try await opened(pairs: refusals.map(\.pair) + [good])
        let owedAt = clock
        handle.fire("reconcile", Self.control())
        var expectedAsks: [TimeInterval] = []
        for (index, refusal) in refusals.enumerated() {
            if index > 0 {
                if refusals[index - 1].pair.fails {
                    try await settle { sleeper.pending(2) == 1 }
                    clock += 2
                    sleeper.fire(2)
                } else {
                    try await elapseNextReask()
                }
            }
            let failed = refusal.pair.fails
            try await settle {
                client.detailReads == index + 1 && client.historyReads == index + 1
                    && vm.pricePairRefreshFailed == failed
            }
            try await quiet()
            XCTAssertEqual(vm.reconcileOwedSince, owedAt, "\(refusal.name) keeps the floor owed")
            if !failed {
                let delays = EventDetailViewModel.reconcileRetryDelays
                expectedAsks.append(delays[min(index + 1, delays.count) - 1])
            }
        }
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5, "the detail half has been on the page throughout")
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])

        try await elapseNextReask()
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertNil(vm.reconcileOwedSince, "the complete fresh history pays the floor")
        XCTAssertEqual(client.detailReads, refusals.count + 1, "with no quote and no further read")
        XCTAssertEqual(reconcileAsks, expectedAsks)
        XCTAssertTrue(EventDetailViewModel.reconcileRetryDelays.allSatisfy { sleeper.pending($0) == 0 },
                      "nothing is re-asked after payment")
        // The vector is read ordering only: the chart is the served one, unpinned
        // and with no point added, and the hero is the detail's.
        XCTAssertEqual(vm.history?.blendEdgePinned, false)
        XCTAssertEqual(vm.history?.aggregateLine?.map(\.timestamp), [Self.removedAt])
        XCTAssertEqual(vm.history?.aggregateLine?.map(\.homeProbability), [0.5])
        XCTAssertTrue(vm.liveBlend.isEmpty, "no live point is invented")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5)
    }

    /// A covering vector proves the history half only: a detail below the floor
    /// and a page now showing a newer pushed price (so not this pair's rail)
    /// both keep the floor owed; the first pair whose detail qualifies pays.
    func testACoveringVectorPaysOnlyBesideAQualifyingDetail() async throws {
        let below = Self.covering(#"{"4242":11}"#, Self.stale10)
        let overtaken = Self.covering(#"{"4242":11}"#)
        let served12 = Self.covering(#"{"4242":12}"#, Client.Pair(
            revision: #"{"4242":12}"#, p: 0.47, sources: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z"),
            at: "2026-09-27T17:02:00Z"))
        let (client, handle, vm) = try await opened(pairs: [below, overtaken, served12], holdPairs: [1])
        let owedAt = clock
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a detail below the floor is not paid by a covering history")
        XCTAssertNotNil(vm.event?.winProbabilitySources?["polymarket"])

        try await elapse(1.5)
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        handle.fire("probability", Self.priced(12, 0.47))
        clock += 2
        client.release()
        try await quiet()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.47)
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "the page shows a newer pushed price, not this pair's detail")

        try await elapse(3)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertEqual(client.detailReads, 3)
        XCTAssertEqual(reconcileAsks, [1.5, 3])
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
    }

    /// A covering pair still in flight when the reader leaves belongs to that
    /// page lifetime: landing after the page reopens and owes a new floor, it
    /// pays nothing there.
    func testACoveringPairFromAnEarlierPageLifetimePaysNothingInTheNextOne() async throws {
        let unproven = Self.covering(nil)
        let (client, handle, vm) = try await opened(pairs: [Self.covering(#"{"4242":11}"#), unproven],
                                                    holdPairs: [0])
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        vm.stopRefresh()
        clock += 5
        await vm.load()
        handle.fire("open")
        let owedAt = clock
        handle.fire("reconcile", Self.control("c-2"))
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "the new lifetime's own unproven pair keeps it owed")
        client.release()
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "the earlier lifetime's covering pair pays nothing")
        XCTAssertNil(vm.history?.historyFoldRevision?.revision, "and is never adopted")
    }

    /// Authority's adoption rule: the history half is paid by the chart the
    /// reader is shown. A covering pair whose history the chart refuses — its
    /// live edge is behind the drawn one (`EventHistoryFreshness`) — pays
    /// nothing, by the vector or by a pinned covering edge; the next covering
    /// pair the chart takes pays.
    func testACoveringHistoryTheChartRefusesPaysNothing() async throws {
        let behind = "2026-09-27T16:59:00Z"
        var vectorBehind = Self.covering(#"{"4242":11}"#)
        vectorBehind.at = behind
        var pinnedBehind = Self.without11
        pinnedBehind.at = behind
        let (client, handle, vm) = try await opened(pairs: [vectorBehind, pinnedBehind, Self.covering(#"{"4242":11}"#)])
        let drawnEdge = vm.historyDigest?.edge
        let owedAt = clock
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertEqual(vm.history?.historyFoldRevision?.revision, FoldRevision(["4242": 11]))
        XCTAssertFalse(vm.historyIsDrawn, "the chart refuses a payload whose edge is behind the drawn one")
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "so its covering vector pays nothing")

        try await elapse(1.5)
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        try await quiet()
        XCTAssertEqual(vm.history?.blendEdgePinned, true)
        XCTAssertFalse(vm.historyIsDrawn)
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "nor does a pinned covering edge the chart refuses")

        try await elapse(3)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertTrue(vm.historyIsDrawn)
        XCTAssertGreaterThan(try XCTUnwrap(vm.historyDigest?.edge), try XCTUnwrap(drawnEdge))
        XCTAssertEqual(client.detailReads, 3)
        XCTAssertEqual(reconcileAsks, [1.5, 3])
    }

    /// Lane1b C1 on d5c76: an ordinary history read issued before the paying
    /// pair, landing after it, is refused. It is a build from before the
    /// withdrawal at the pair's own edge, so the chart would take it, and the
    /// floor has already paid, so nothing would re-ask.
    func testAnOrdinaryHistoryReadIssuedBeforeThePayingPairCannotRedrawTheWithdrawnSeries() async throws {
        let paying = Self.covering(#"{"4242":11}"#)
        let (client, handle, vm) = try await opened(pairs: [paying])
        let stale = try Self.decode(EventHistoryResponse.self, """
        {"event_id":4242,"home_team":"Home","away_team":"Away","status":"live","history":[],
         "blend_edge_pinned":false,"blend_edge_fold_revision":null,
         "win_prob_history":{"polymarket":[{"timestamp":"\(Self.removedAt)","home_probability":0.82}]},
         "aggregate_line":[{"timestamp":"\(paying.at)","home_probability":0.6}]}
        """)
        client.heldOrdinaryHistory = stale
        let issued = client.ordinaryHistoryReads
        let poll = Task { await vm.load(fresh: false, awaitingOptionalSections: false) }
        try await settle { client.ordinaryHistoryReads == issued + 1 }
        XCTAssertEqual(client.ordinaryHistoryReads, issued + 1, "an ordinary read is in flight across the commit")

        handle.fire("reconcile", Self.control())
        try await settle { vm.reconcileOwedSince == nil }
        await poll.value
        try await quiet()
        XCTAssertNil(vm.reconcileOwedSince, "the covering pair pays")
        XCTAssertTrue(vm.historyIsDrawn)
        let paid = try XCTUnwrap(vm.history)
        let generation = vm.historyGeneration
        XCTAssertEqual(vm.historyDigest?.edge, EventHistoryFreshness.lastReading(in: stale),
                       "the stale read sits at the pair's edge, so the chart would take it")

        client.releaseOrdinaryHistory()
        try await quiet()
        XCTAssertEqual(vm.history, paid, "the page keeps the pair's history")
        XCTAssertEqual(vm.historyGeneration, generation, "and offers the chart nothing new")
        XCTAssertNil(vm.history?.winProbHistory?["polymarket"], "the withdrawn series stays gone")
        XCTAssertNil(vm.reconcileOwedSince)
    }

    /// #10090 §3 (Root 1341Z) — the withdrawn series held the drawn payload's
    /// latest reading. The complete fresh build after the withdrawal retains
    /// Kalshi unmoved at 17:00 and has no Polymarket, so its edge is behind
    /// 17:02. Before this, the chart refused it and every re-ask, the floor
    /// stayed owed, and the reader kept seeing Polymarket's line. An older
    /// complete build (Kalshi behind) is still refused and keeps it owed.
    func testACompleteBuildDroppingTheSeriesThatHeldTheEdgeIsDrawnAndPays() async throws {
        typealias Shapes = AWithdrawnSeriesStopsHoldingTheChartEdge10090Tests
        let withdrawnAt = "2026-09-27T17:03:00Z"
        var older = Self.without11
        older.at = withdrawnAt
        older.sources = Self.kalshiOnly(0.5, at: withdrawnAt)
        older.servedHistory = try Shapes.kalshiAlone(at: "16:59:00")
        var paying = older
        paying.servedHistory = try Shapes.kalshiAlone()
        let (client, handle, vm) = try await opened(history: try Shapes.drawn(), pairs: [older, paying])
        XCTAssertNotNil(vm.history?.winProbHistory?["polymarket"])
        XCTAssertTrue(vm.historyIsDrawn)
        let owedAt = clock

        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertFalse(vm.historyIsDrawn, "an older complete build is refused")
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "and pays nothing")

        try await elapse(1.5)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertNil(vm.reconcileOwedSince, "the complete build behind the withdrawn stamp pays")
        XCTAssertTrue(vm.historyIsDrawn, "because the chart takes it")
        XCTAssertNil(vm.history?.winProbHistory?["polymarket"])
        XCTAssertEqual(vm.history?.historyFoldRevision?.revision, FoldRevision(["4242": 11]))
        XCTAssertLessThan(try XCTUnwrap(vm.historyDigest?.edge),
                          try XCTUnwrap(EventHistoryFreshness.lastReading(in: try Shapes.drawn())),
                          "its edge is still behind the drawn one: no point or stamp was made")
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
        XCTAssertEqual(client.detailReads, 2)
        XCTAssertEqual(reconcileAsks, [1.5])
    }

    func testHistoryCoverageIsAnUnpinnedAlternativeThatNeverRescuesAPinnedEdge() throws {
        let floor = try XCTUnwrap(FoldRevision(["4242": 11]))
        func covers(_ coverage: String?, pin: String = Self.unpinnedFragment) throws -> Bool {
            LiveEventPriceReconciliation.historyCoversFloor(
                floor, try Self.coverageHistory(p: 0.5, at: Self.removedAt, coverage: coverage, pin: pin))
        }
        XCTAssertTrue(try covers(#"{"4242":11}"#))
        XCTAssertTrue(try covers(#"{"4242":12,"77":3}"#), "extra rows and higher revisions cover")
        XCTAssertTrue(try covers(#"{"4242":11}"#, pin: ""), "a history with no pin keys is unpinned")
        let refused: [(String, String?)] = [
            ("absent", nil), ("null", "null"), ("string", #""x""#), ("array", "[11]"), ("empty", "{}"),
            ("fractional", #"{"4242":11.5}"#), ("string row", #"{"4242":"11"}"#), ("bool row", #"{"4242":true}"#),
            ("null row", #"{"4242":null}"#), ("negative", #"{"4242":-1}"#),
            ("unsafe integer", #"{"4242":9007199254740992}"#), ("missing row", #"{"77":11}"#),
            ("below the floor", #"{"4242":10}"#),
        ]
        for (name, coverage) in refused {
            XCTAssertFalse(try covers(coverage), "a \(name) vector proves nothing")
        }
        XCTAssertFalse(try covers(#"{"4242":11}"#, pin: Self.pinnedBelowFragment),
                       "a pinned edge below the floor is not rescued by a covering read prefix")
        XCTAssertFalse(try covers(#"{"4242":11}"#, pin: Self.pinnedNoRevisionFragment),
                       "nor is a pinned edge with no revision")
        XCTAssertFalse(try covers(#"{"4242":11}"#, pin: #""blend_edge_pinned":true,"blend_edge_fold_revision":"x","#))
        XCTAssertTrue(try covers(nil, pin: #""blend_edge_pinned":true,"blend_edge_fold_revision":{"4242":11},"#),
                      "D4's pinned covering edge still pays alone")
        XCTAssertFalse(try covers(nil, pin: #""blend_edge_pinned":false,"blend_edge_fold_revision":{"4242":11},"#),
                       "a revision on an edge the server did not pin is still no claim")
        // Never throws: a malformed vector is no claim, and the chart decodes whole.
        let malformed = try Self.coverageHistory(p: 0.5, at: Self.removedAt, coverage: #""x""#)
        XCTAssertNil(malformed.historyFoldRevision?.revision)
        XCTAssertEqual(malformed.aggregateLine?.count, 1)
    }

    func testACoveringVectorPaysBesideEitherRailProofAndNothingElse() throws {
        let floor = try XCTUnwrap(FoldRevision(["4242": 11]))
        let served = try Self.detail(p: 0.5, revision: #"{"4242":11}"#, sources: Self.kalshiOnly(0.5, at: Self.removedAt))
        let vector11 = try Self.coverageHistory(p: 0.5, at: Self.removedAt, coverage: #"{"4242":11}"#)
        let shown = LiveEventPriceReconciliation.reconcileFloorShown
        XCTAssertTrue(shown(floor, served, vector11, served))
        let below = try Self.detail(p: 0.6, revision: #"{"4242":10}"#, sources: Self.both)
        XCTAssertFalse(shown(floor, below, vector11, below), "a detail below the floor")
        let kept = try Self.detail(p: 0.46, revision: #"{"4242":12}"#, sources: Self.both)
        XCTAssertFalse(shown(floor, served, vector11, kept), "the page shows a different revision")
        XCTAssertFalse(shown(floor, served, try Self.coverageHistory(p: 0.5, at: Self.removedAt,
                                                                     coverage: #"{"4242":11}"#, eventId: 1), served))
        XCTAssertFalse(shown(floor, served, try Self.coverageHistory(p: 0.5, at: Self.removedAt, coverage: nil), served))

        let rail = LiveEventPriceReconciliation.CommittedRail(revision: try XCTUnwrap(FoldRevision(["4242": 11])),
                                                              sources: ["kalshi"])
        let byRail = LiveEventPriceReconciliation.reconcileFloorShownByCommittedRail
        XCTAssertTrue(byRail(floor, rail, vector11, served))
        XCTAssertFalse(byRail(floor, rail, try Self.coverageHistory(p: 0.5, at: Self.removedAt, coverage: nil), served),
                       "a rail never pays the history half")
        XCTAssertFalse(byRail(floor, rail, try Self.coverageHistory(p: 0.5, at: Self.removedAt, coverage: #"{"4242":11}"#,
                                                                    pin: Self.pinnedBelowFragment), served))
        let otherSources = LiveEventPriceReconciliation.CommittedRail(revision: rail.revision,
                                                                      sources: ["kalshi", "polymarket"])
        XCTAssertFalse(byRail(floor, otherSources, vector11, served), "the page lists other sources")
        XCTAssertFalse(byRail(floor, nil, vector11, served))
    }
}

/// #10090 — the `reconcile` envelope at the controller: bounded, never a
/// price, and transport activity only.
@MainActor
final class LiveStreamReconcileControlTests: XCTestCase {
    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        func fire(_ event: String, _ data: String = "") {
            for handler in handlers[event] ?? [] { handler(data) }
        }
    }

    private var clock: TimeInterval = 1_000
    private var handles: [Handle] = []
    private var controls: [LiveStreamReconcile] = []
    private var frames = 0
    private var resyncs = 0
    private var scheduled: [@MainActor () -> Void] = []

    private func controller(reconcile: Bool = true) -> LiveStreamController {
        let onReconcile: @MainActor (LiveStreamReconcile) -> Void = reconcile
            ? { [unowned self] in self.controls.append($0) } : { _ in }
        return LiveStreamController(
            open: { [unowned self] in
                let handle = Handle()
                self.handles.append(handle)
                return handle
            },
            now: { [unowned self] in self.clock },
            onFrame: { [unowned self] _ in self.frames += 1 },
            onDeliveringChange: { _ in },
            onResync: { [unowned self] in self.resyncs += 1 },
            onReconcile: onReconcile,
            schedule: { [unowned self] _, action in
                self.scheduled.append(action)
                return {}
            }
        )
    }

    func testAValidControlReachesTheOwnerAndNothingElse() throws {
        let stream = controller()
        stream.start()
        handles[0].fire("open")
        handles[0].fire("reconcile", #"{"event_id":15332323,"custody_id":"obl-9","removal_rev":{"15332402":1129},"p":0.4}"#)
        XCTAssertEqual(controls, [LiveStreamReconcile(eventId: 15332323, custodyId: "obl-9",
                                                      removalRev: try XCTUnwrap(FoldRevision(["15332402": 1129])))])
        XCTAssertEqual(frames, 0, "never the price decoder")
        XCTAssertEqual(resyncs, 0, "never a resync")
    }

    func testAnUnboundedOrMalformedEnvelopeIsRefused() {
        let stream = controller()
        stream.start()
        let manyRows = (1...17).map { #""\#($0)":1"# }.joined(separator: ",")
        let refused = [
            #"{"event_id":1,"custody_id":"","removal_rev":{"2":1}}"#,
            #"{"event_id":1,"custody_id":"\#(String(repeating: "x", count: 257))","removal_rev":{"2":1}}"#,
            #"{"event_id":1,"custody_id":"a","removal_rev":{\#(manyRows)}}"#,
            #"{"event_id":1,"custody_id":"a","removal_rev":{}}"#,
            #"{"event_id":1,"custody_id":"a","removal_rev":{"2":-1}}"#,
            #"{"event_id":1,"custody_id":"a","removal_rev":{"2":1.5}}"#,
            #"{"event_id":1,"custody_id":"a","removal_rev":{"2":true}}"#,
            #"{"event_id":1,"custody_id":"a","removal_rev":{"abc":1}}"#,
            #"{"event_id":1,"custody_id":"a","removal_rev":{"123456789012345678901":1}}"#,
            #"{"event_id":1,"custody_id":"a","removal_rev":"{\"2\":1}"}"#,
            #"{"event_id":1,"removal_rev":{"2":1}}"#,
            #"{"custody_id":"a","removal_rev":{"2":1}}"#,
            #"{"event_id":1,"custody_id":"a","removal_rev":{"2":1},"pad":"\#(String(repeating: "x", count: 4096))"}"#,
            "not json",
            "",
        ]
        for raw in refused { handles[0].fire("reconcile", raw) }
        XCTAssertTrue(controls.isEmpty)
        handles[0].fire("reconcile", #"{"event_id":1,"custody_id":"a","removal_rev":{"2":1}}"#)
        XCTAssertEqual(controls.count, 1, "the same handler still takes a bounded control")
    }

    func testAControlKeepsTheTransportAliveButNeverRenewsDelivery() {
        let stream = controller()
        stream.start()
        handles[0].fire("open")
        XCTAssertTrue(stream.state.delivering)
        for _ in 0..<4 {
            clock += 30
            handles[0].fire("reconcile", #"{"event_id":1,"custody_id":"a","removal_rev":{"2":1}}"#)
            stream.tick()
        }
        XCTAssertFalse(stream.state.stopped, "the transport is alive")
        XCTAssertFalse(stream.state.delivering, "120 s with no adopted price is data silence")
    }

    func testARetiredConnectionsControlIsIgnoredAndALegacyOwnerIgnoresAll() {
        let stream = controller()
        stream.start()
        clock += 120
        handles[0].fire("reconnect")
        scheduled.forEach { $0() }
        XCTAssertEqual(handles.count, 2)
        handles[0].fire("reconcile", #"{"event_id":1,"custody_id":"a","removal_rev":{"2":1}}"#)
        XCTAssertTrue(controls.isEmpty, "the old socket speaks for nothing")
        handles[1].fire("reconcile", #"{"event_id":1,"custody_id":"a","removal_rev":{"2":1}}"#)
        XCTAssertEqual(controls.count, 1)

        let legacy = controller(reconcile: false)
        legacy.start()
        handles[2].fire("reconcile", #"{"event_id":1,"custody_id":"a","removal_rev":{"2":1}}"#)
        XCTAssertEqual(controls.count, 1)
        XCTAssertEqual(frames, 0)
        XCTAssertEqual(resyncs, 0)
    }
}
