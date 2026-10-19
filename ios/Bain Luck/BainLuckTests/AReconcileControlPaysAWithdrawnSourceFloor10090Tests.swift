import XCTest
import Foundation
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
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { pageHistory }
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
        page: EventDetail? = nil, pairs: [Client.Pair], holdPairs: Set<Int> = []
    ) async throws -> (Client, Handle, EventDetailViewModel) {
        let client = Client(
            page: try page ?? Self.detail(p: 0.6, revision: #"{"4242":10}"#, sources: Self.both),
            history: try Self.history(p: 0.6, edge: #"{"4242":10}"#, at: "2026-09-27T17:00:00Z")
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
