import XCTest
import Foundation
@testable import Bain_Luck

/// #10090 — Live's committed `source_snapshot` (PR #11264) on a singleton
/// page (NATIVE-SOURCE-SNAPSHOT-CONSUMER-CONTRACT, ROOT-COHERENT-RAIL-PAYMENT-
/// DECISION). A newer valid priced write with a real source replaces price and
/// the WHOLE rail in one turn; refused is absent; an unpriced map shows nothing
/// and owes the rail; a folded hero never takes a raw row's map. The snapshot
/// may pay only the reconcile floor's detail half, and only while the page
/// still holds its revision: history is still a pinned covering edge.
@MainActor
final class ASourceSnapshotAdoption10090Tests: XCTestCase {
    private static let both = #""kalshi":{"value":0.5,"updated_at":"2026-09-27T17:00:00Z"},"polymarket":{"value":0.82,"updated_at":"2026-09-27T17:00:00Z"}"#
    private static func kalshiOnly(_ p: Double, at: String) -> String {
        #""kalshi":{"value":\#(p),"updated_at":"\#(at)"}"#
    }
    private static func withPolymarket(_ p: Double, at: String, polymarket: Double = 0.3) -> String {
        #""kalshi":{"value":\#(p),"updated_at":"\#(at)"},"polymarket":{"value":\#(polymarket),"updated_at":"\#(at)"}"#
    }

    private static func control(_ custody: String = "c-1", floor: String = #"{"4242":11}"#) -> String {
        #"{"event_id":4242,"custody_id":"\#(custody)","removal_rev":\#(floor)}"#
    }

    /// A raw singleton frame. `snapshot: nil` is a legacy frame (no key).
    private static func frame(
        _ revision: Int, _ p: Double?, snapshot sources: String?, at: String = "2026-09-27T17:02:00Z",
        status: String = "live", source: String = "kalshi", snapshotEvent: Int = 4242,
        snapshotRev: String? = nil, extra: String = ""
    ) -> String {
        let price = p.map { "\($0)" } ?? "null"
        let snap = sources.map {
            #","source_snapshot":{"event_id":\#(snapshotEvent),"rev":\#(snapshotRev ?? #"{"4242":\#(revision)}"#),"win_probability_sources":{\#($0)}}"#
        } ?? ""
        return """
        {"event_id":4242,"p":\(price),"source":"\(source)","source_value":\(price),"updated_at":"\(at)",
         "status":"\(status)","rev":{"4242":\(revision)}\(snap)\(extra)}
        """
    }

    private static func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    fileprivate static func detail(p: Double, revision: String, sources: String, status: String = "live",
                                   observedAt: String = "2026-09-27T17:00:00Z") throws -> EventDetail {
        try decode(EventDetail.self, """
        {"id":4242,"sport":"americanfootball_nfl","home_team":"Home","away_team":"Away","status":"\(status)",
         "home_score":7,"away_score":3,
         "current_odds":{"home_probability":\(p),"away_probability":\(1 - p)},
         "hero_probability":\(p),"hero_probability_source":"blend",
         "hero_probability_observed_at":"\(observedAt)",
         "blend_fold_revision":\(revision),"win_probability_sources":{\(sources)}}
        """)
    }

    /// `edge: nil` serves an unpinned history, which makes no revision claim.
    fileprivate static func history(p: Double, edge: String?, at: String) throws -> EventHistoryResponse {
        let pin = edge.map { #""blend_edge_pinned":true,"blend_edge_fold_revision":\#($0),"blend_edge_observed_at":"\#(at)","# } ?? ""
        return try decode(EventHistoryResponse.self, """
        {"event_id":4242,"home_team":"Home","away_team":"Away","status":"live","history":[],\(pin)
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
            let pair = pairs[min(index, pairs.count - 1)]
            await hold(index)
            if pair.fails { throw Declined() }
            return try ASourceSnapshotAdoption10090Tests.detail(
                p: pair.p, revision: pair.revision, sources: pair.sources, observedAt: pair.at)
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
            return try ASourceSnapshotAdoption10090Tests.history(p: pair.p, edge: edge, at: pair.at)
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
        page: EventDetail? = nil, pairs: [Client.Pair] = [ASourceSnapshotAdoption10090Tests.stale10],
        holdPairs: Set<Int> = []
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

    private func elapse(_ delay: TimeInterval) async throws {
        try await settle { sleeper.pending(delay) == 1 }
        XCTAssertEqual(sleeper.pending(delay), 1, "a \(delay)s re-ask is armed")
        clock += delay
        sleeper.fire(delay)
    }

    private static let reconcileDelays = Set(EventDetailViewModel.reconcileRetryDelays)
    private var reconcileAsks: [TimeInterval] { sleeper.asked.filter { Self.reconcileDelays.contains($0) } }

    private static let stale10 = Client.Pair(revision: #"{"4242":10}"#, p: 0.6, sources: both,
                                             at: "2026-09-27T17:00:00Z")
    private static let removedAt = "2026-09-27T17:00:30Z"
    private static let without11 = Client.Pair(revision: #"{"4242":11}"#, p: 0.5,
                                               sources: kalshiOnly(0.5, at: removedAt), at: removedAt)
    /// An unorderable frame: the page asks one pair, nothing else.
    private static let unorderable = """
        {"event_id":4242,"p":null,"source":null,"source_value":null,"updated_at":null,"status":"live","rev":{"9999":1}}
        """

    private func polymarket(_ vm: EventDetailViewModel) -> Double? {
        vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue
    }

    // MARK: - S1 a newer priced snapshot

    func testANewerSnapshotReplacesPriceAndTheWholeRailTogether() async throws {
        let (client, handle, vm) = try await opened()
        let points = vm.liveBlend.count
        let activity = vm.priceActivity
        handle.fire("probability", Self.frame(11, 0.5, snapshot: Self.kalshiOnly(0.5, at: Self.removedAt)))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5)
        XCTAssertEqual(vm.event?.heroProbability, 0.5)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 11])
        XCTAssertEqual(vm.event?.winProbabilitySources, try Self.decode(
            [String: WinProbSource].self, "{\(Self.kalshiOnly(0.5, at: Self.removedAt))}"),
            "the rail is the committed map, whole: the withdrawn venue left with its price")
        XCTAssertEqual(vm.liveBlend.count, points + 1, "one chart point, the legacy arm's")
        XCTAssertNotEqual(vm.priceActivity, activity, "one receipt")
        XCTAssertTrue(vm.streamHasPushedPrice)
        try await quiet()
        XCTAssertEqual(client.detailReads, 0, "the map is on the page: nothing to read")
    }

    // MARK: - S2 removal then genuine re-addition

    func testRemovalThenReAdditionFollowsWriteOrderAndAnOlderReadChangesNeither() async throws {
        let older12 = Client.Pair(revision: #"{"4242":12}"#, p: 0.49, sources: Self.both, at: "2026-09-27T17:00:00Z")
        let (client, handle, vm) = try await opened(pairs: [older12])
        handle.fire("probability", Self.frame(13, 0.48, snapshot: Self.kalshiOnly(0.48, at: "2026-09-27T17:03:00Z"),
                                              at: "2026-09-27T17:03:00Z"))
        XCTAssertNil(polymarket(vm), "13 drops Polymarket")
        clock += 2
        handle.fire("probability", Self.unorderable)
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertNil(polymarket(vm), "an older read at 12 restores nothing")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 13])

        handle.fire("probability", Self.frame(14, 0.47, snapshot: Self.withPolymarket(0.47, at: "2026-09-27T17:04:00Z"),
                                              at: "2026-09-27T17:04:00Z"))
        XCTAssertEqual(polymarket(vm), 0.3, "14 restores it, in write order")
        clock += 2
        handle.fire("probability", Self.unorderable)
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        try await quiet()
        XCTAssertEqual(polymarket(vm), 0.3, "an older read at 12 prunes nothing")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.47)
    }

    // MARK: - S3 equal, older, replayed

    func testAnEqualOlderOrReplayedSnapshotAdoptsNothing() async throws {
        let (_, handle, vm) = try await opened()
        let drop = Self.kalshiOnly(0.5, at: Self.removedAt)
        handle.fire("probability", Self.frame(10, 0.5, snapshot: drop))
        handle.fire("probability", Self.frame(9, 0.5, snapshot: drop))
        XCTAssertEqual(polymarket(vm), 0.82, "an equal or older write adopts no map")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6)

        let eleven = Self.frame(11, 0.55, snapshot: Self.withPolymarket(0.55, at: "2026-09-27T17:02:00Z"))
        handle.fire("probability", eleven)
        XCTAssertEqual(polymarket(vm), 0.3)
        let points = vm.liveBlend.count
        let activity = vm.priceActivity
        handle.fire("probability", eleven)
        XCTAssertEqual(vm.liveBlend.count, points, "a replay of the same write is nothing")
        XCTAssertEqual(vm.priceActivity, activity)
        XCTAssertEqual(polymarket(vm), 0.3)
    }

    // MARK: - S4 refused is absent

    func testARefusedSnapshotIsExactlyTheLegacyFrame() async throws {
        let drop = Self.kalshiOnly(0.5, at: Self.removedAt)
        let refused = [
            Self.frame(11, 0.5, snapshot: drop, snapshotEvent: 77),
            Self.frame(11, 0.5, snapshot: drop, snapshotRev: #"{"4242":12}"#),
            Self.frame(11, 0.5, snapshot: drop, snapshotRev: #"{"77":11}"#),
            Self.frame(11, 0.5, snapshot: drop, snapshotRev: #"{"4242":11,"77":1}"#),
            Self.frame(11, 0.5, snapshot: #""kalshi":{"value":1.5}"#),
            Self.frame(11, 0.5, snapshot: drop, extra: #","pad":"\#(String(repeating: "x", count: 16 * 1024))""#),
        ]
        for raw in refused {
            let (_, handle, vm) = try await opened()
            handle.fire("probability", raw)
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5, "the price still moves, as legacy")
            XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 11])
            XCTAssertEqual(polymarket(vm), 0.82, "a refused map is never half-adopted")
        }
    }

    // MARK: - S5 unpriced: no real source, or no price

    func testAnUnpricedSnapshotShowsNothingAndOwesTheRail() async throws {
        let unpriced = [
            Self.frame(11, 0.5, snapshot: ""),
            Self.frame(11, 0.5, snapshot: #""betting_book_count":{"value":3}"#),
            Self.frame(11, 0.5, snapshot: #""final_result":{"value":1}"#),
        ]
        for raw in unpriced {
            let (client, handle, vm) = try await opened(pairs: [Self.without11])
            let points = vm.liveBlend.count
            let activity = vm.priceActivity
            handle.fire("probability", raw)
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6, "a fallback p is not a blend: no hero")
            XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 10], "not dated onto the held value")
            XCTAssertEqual(vm.liveBlend.count, points, "no chart point")
            XCTAssertEqual(vm.priceActivity, activity, "no receipt")
            XCTAssertFalse(vm.streamHasPushedPrice, "no delivery")
            XCTAssertEqual(polymarket(vm), 0.82, "the map is not adopted either")
            try await settle { client.detailReads == 1 && polymarket(vm) == nil }
            try await quiet()
            XCTAssertEqual(client.detailReads, 1, "one pair brings the authoritative label and rail")
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5)
        }
    }

    func testUnpricedSnapshotsDoNotPostponeTheDataSilenceFallback() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.stale10])
        XCTAssertTrue(vm.streamDelivering)
        for step in 1...5 {
            clock += 20
            handle.fire("probability", Self.frame(10 + step, 0.5, snapshot: ""))
            try await settle { client.detailReads >= step }
            vm.tickStream()
        }
        XCTAssertFalse(vm.streamDelivering, "100 s of unpriced snapshots is data silence")
    }

    // MARK: - S6 a null price ignores its snapshot

    func testANullPriceFrameIgnoresItsSnapshot() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.without11], holdPairs: [0])
        handle.fire("probability", Self.frame(11, nil, snapshot: Self.kalshiOnly(0.5, at: Self.removedAt)))
        XCTAssertEqual(polymarket(vm), 0.82, "the #11253 arm, byte for byte: nothing is shown before its pair")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6)
        try await settle { client.detailReads == 1 }
        clock += 2
        client.release()
        try await settle { polymarket(vm) == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 1)
    }

    // MARK: - S7 final

    func testAFinalFrameKeepsTheLegacyPathAndALaterSnapshotDoesNothing() async throws {
        let (_, handle, vm) = try await opened(pairs: [Self.stale10])
        handle.fire("probability", Self.frame(11, 1.0, snapshot: Self.kalshiOnly(1.0, at: Self.removedAt),
                                              status: "completed"))
        XCTAssertEqual(vm.event?.status, "completed")
        XCTAssertEqual(polymarket(vm), 0.82, "a frame that ends the game never replaces the rail")
        handle.fire("probability", Self.frame(12, 0.4, snapshot: Self.kalshiOnly(0.4, at: "2026-09-27T17:03:00Z")))
        XCTAssertEqual(polymarket(vm), 0.82, "nor does a snapshot after a pushed final")
    }

    // MARK: - S8 a folded page

    func testARawSnapshotOnAFoldedPageChangesNothing() async throws {
        let folded = try Self.detail(p: 0.6, revision: #"{"4242":10,"4243":5}"#, sources: Self.both)
        var results: [(Double?, Double?, Int, [String: Int]?)] = []
        for carriesSnapshot in [true, false] {
            let (client, handle, vm) = try await opened(page: folded, pairs: [Self.stale10])
            for pending in [true, false] {
                clock += 2
                handle.fire("probability", Self.frame(
                    11, 0.5, snapshot: carriesSnapshot ? Self.kalshiOnly(0.5, at: Self.removedAt) : nil,
                    extra: pending ? #","folded_quote_pending":true"# : ""))
                try await quiet()
            }
            results.append((vm.event?.currentOdds?.homeProbability, polymarket(vm), client.detailReads,
                            vm.event?.blendFoldRevision?.revision?.rows))
        }
        XCTAssertEqual(results[0].0, results[1].0)
        XCTAssertEqual(results[0].1, results[1].1)
        XCTAssertEqual(results[0].1, 0.82, "no raw-row map replaces a folded hero's rail")
        XCTAssertEqual(results[0].2, results[1].2)
        XCTAssertEqual(results[0].3, results[1].3)
    }

    // MARK: - S9 continuous newer quotes pay the floor's detail half

    /// Each pair is overtaken by a newer snapshot, which keeps the rail on the
    /// page coherent at its own revision. The first completed pair whose
    /// history is a pinned covering edge pays, with no quiet market needed.
    func testContinuousSnapshotsLetTheFirstCoveringHistoryPayTheFloor() async throws {
        var unpinned = Self.without11
        unpinned.edge = .some(nil)
        let served12 = Client.Pair(revision: #"{"4242":12}"#, p: 0.47,
                                   sources: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z"), at: "2026-09-27T17:02:00Z")
        let (client, handle, vm) = try await opened(pairs: [unpinned, served12], holdPairs: [0, 1])
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        handle.fire("probability", Self.frame(12, 0.47, snapshot: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z")))
        XCTAssertNil(polymarket(vm))
        clock += 2
        client.release()
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "an unpinned history pays nothing, whatever the rail")

        try await elapse(1.5)
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        handle.fire("probability", Self.frame(13, 0.46, snapshot: Self.kalshiOnly(0.46, at: "2026-09-27T17:03:00Z"),
                                              at: "2026-09-27T17:03:00Z"))
        clock += 2
        client.release()
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertNil(vm.reconcileOwedSince, "the pinned covering edge pays beside the snapshot rail")
        XCTAssertEqual(client.detailReads, 2)
        XCTAssertEqual(reconcileAsks, [1.5])
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.46, "the newest price is kept")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 13])
        XCTAssertNil(polymarket(vm))
    }

    /// The same run with legacy frames: the kept headline keeps the held rail
    /// (Polymarket included) and no pair it overtook pays.
    func testLegacyFramesUnderContinuousTicksKeepTheFloorOwed() async throws {
        var unpinned = Self.without11
        unpinned.edge = .some(nil)
        let served12 = Client.Pair(revision: #"{"4242":12}"#, p: 0.47,
                                   sources: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z"), at: "2026-09-27T17:02:00Z")
        let (client, handle, vm) = try await opened(pairs: [unpinned, served12], holdPairs: [0, 1])
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        handle.fire("probability", Self.frame(12, 0.47, snapshot: nil))
        clock += 2
        client.release()
        try await quiet()
        try await elapse(1.5)
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        handle.fire("probability", Self.frame(13, 0.46, snapshot: nil, at: "2026-09-27T17:03:00Z"))
        clock += 2
        client.release()
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "a newer price proves neither its rail nor history")
        XCTAssertEqual(polymarket(vm), 0.82, "the held rail still carries the withdrawn venue")
    }

    /// (b) is the page holding the snapshot's revision NOW: a later legacy
    /// frame moves it away, and the remembered snapshot proves nothing.
    func testALegacyFrameAfterTheSnapshotBreaksTheRailProof() async throws {
        let served12 = Client.Pair(revision: #"{"4242":12}"#, p: 0.47,
                                   sources: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z"), at: "2026-09-27T17:02:00Z")
        let served13 = Client.Pair(revision: #"{"4242":13}"#, p: 0.46,
                                   sources: Self.kalshiOnly(0.46, at: "2026-09-27T17:03:00Z"), at: "2026-09-27T17:03:00Z")
        let (client, handle, vm) = try await opened(pairs: [served12, served13])
        handle.fire("probability", Self.frame(12, 0.47, snapshot: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z")))
        handle.fire("probability", Self.frame(13, 0.46, snapshot: nil, at: "2026-09-27T17:03:00Z"))
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 13])
        handle.fire("reconcile", Self.control(floor: #"{"4242":12}"#))
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "page 13 is neither the served 12 nor the snapshot's 12")
        try await elapse(1.5)
        try await settle { vm.reconcileOwedSince == nil }
        XCTAssertEqual(client.detailReads, 2, "the served 13 pays it the ordinary way")
    }

    // MARK: - S10 failed, stale and unpinned history stay owed

    func testFailedStaleAndUnpinnedHistoryKeepTheFloorOwedUntilACoveringEdge() async throws {
        var failing = Self.without11
        failing.fails = true
        var staleEdge = Self.without11
        staleEdge.edge = .some(#"{"4242":10}"#)
        var unpinned = Self.without11
        unpinned.edge = .some(nil)
        let (client, handle, vm) = try await opened(pairs: [failing, staleEdge, unpinned, Self.without11])
        handle.fire("probability", Self.frame(12, 0.47, snapshot: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z")))
        let owedAt = clock
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && vm.pricePairRefreshFailed }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a failed pair keeps it, snapshot rail or not")

        try await settle { sleeper.pending(2) == 1 }
        clock += 2
        sleeper.fire(2)
        try await settle { client.detailReads == 2 && !vm.pricePairRefreshFailed }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a pinned edge below the floor keeps it")

        try await elapse(3)
        try await settle { client.detailReads == 3 }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a map never pays history: unpinned keeps it")

        try await elapse(6)
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 4, "a covering edge pays on the retry clock alone")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 12])
    }

    // MARK: - S11 #11253 debt and retired bars

    func testASnapshotClearsAWithdrawalOwedByANullPriceFrame() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.stale10], holdPairs: [0])
        handle.fire("probability", Self.frame(11, nil, snapshot: nil))
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        handle.fire("probability", Self.frame(12, 0.47, snapshot: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z")))
        XCTAssertNil(polymarket(vm))
        clock += 2
        client.release()
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "the rail is shown at 12, past the owed 11: no trailing pair")
        XCTAssertNil(polymarket(vm))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.47)
    }

    func testAWithdrawnVenuesPushedBarIsRetiredWithIt() async throws {
        let readded13 = Client.Pair(revision: #"{"4242":13}"#, p: 0.46,
                                    sources: Self.withPolymarket(0.46, at: "2026-09-27T17:00:30Z"),
                                    at: "2026-09-27T17:00:30Z")
        let (client, handle, vm) = try await opened(pairs: [readded13])
        handle.fire("probability", Self.frame(11, 0.55, snapshot: nil, at: "2026-09-27T17:01:00Z", source: "polymarket"))
        XCTAssertEqual(polymarket(vm), 0.55, "Polymarket's own pushed bar")
        handle.fire("probability", Self.frame(12, 0.47, snapshot: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z")))
        XCTAssertNil(polymarket(vm))
        clock += 2
        handle.fire("probability", Self.unorderable)
        try await settle { client.detailReads == 1 && polymarket(vm) != nil }
        try await quiet()
        XCTAssertEqual(polymarket(vm), 0.3, "the re-added venue reads as served, not its pre-withdrawal push")
    }

    // MARK: - S12 the pure rules

    private func decoded(_ raw: String) throws -> LiveStreamFrame {
        try XCTUnwrap(LiveStreamFrame.decode(raw))
    }

    func testDecoderRefusalsReadAsAbsent() throws {
        let drop = Self.kalshiOnly(0.5, at: Self.removedAt)
        XCTAssertNotNil(try decoded(Self.frame(11, 0.5, snapshot: drop)).validSourceSnapshot)
        XCTAssertNotNil(try decoded(Self.frame(11, 0.5, snapshot: "")).validSourceSnapshot, "{} is a complete map")
        let many = (1...33).map { #""k\#($0)":{"value":1}"# }.joined(separator: ",")
        let refused = [
            Self.frame(11, 0.5, snapshot: drop, snapshotEvent: 77),
            Self.frame(11, 0.5, snapshot: drop, snapshotRev: #"{"4242":12}"#),
            Self.frame(11, 0.5, snapshot: drop, snapshotRev: #"{"77":11}"#),
            Self.frame(11, 0.5, snapshot: drop, snapshotRev: #"{"4242":11,"77":1}"#),
            Self.frame(11, 0.5, snapshot: drop, snapshotRev: #"{"4242":9007199254740992}"#),
            Self.frame(11, 0.5, snapshot: drop, snapshotRev: #"{"4242":-1}"#),
            Self.frame(11, 0.5, snapshot: drop, snapshotRev: #"{}"#),
            Self.frame(11, 0.5, snapshot: many),
            Self.frame(11, 0.5, snapshot: #""kalshi":{"value":1.5}"#),
            Self.frame(11, 0.5, snapshot: #""kalshi":{"value":-0.1}"#),
            Self.frame(11, 0.5, snapshot: #""betting_book_count":{"value":-1}"#),
            Self.frame(11, 0.5, snapshot: #""kalshi":{"updated_at":"2026-09-27T17:00:00Z"}"#),
            Self.frame(11, 0.5, snapshot: #""kalshi":{"value":0.5,"updated_at":"yesterday"}"#),
            Self.frame(11, 0.5, snapshot: #""\#(String(repeating: "k", count: 65))":{"value":1}"#),
            Self.frame(11, 0.5, snapshot: #""":{"value":1}"#),
            Self.frame(11, 0.5, snapshot: drop, extra: #","pad":"\#(String(repeating: "x", count: 16 * 1024))""#),
            #"{"event_id":4242,"p":0.5,"source":"kalshi","source_value":0.5,"updated_at":"2026-09-27T17:02:00Z","status":"live","rev":{"4242":11},"source_snapshot":"{}"}"#,
            #"{"event_id":4242,"p":0.5,"source":"kalshi","source_value":0.5,"updated_at":"2026-09-27T17:02:00Z","status":"live","source_snapshot":{"event_id":4242,"rev":{"4242":11},"win_probability_sources":{}}}"#,
        ]
        for raw in refused {
            let result = try decoded(raw)
            XCTAssertNil(result.validSourceSnapshot, String(raw.prefix(160)))
            XCTAssertEqual(result.p, 0.5, "the frame around it is never thrown")
        }
        XCTAssertEqual(try decoded(Self.frame(11, 0.5, snapshot: many.replacingOccurrences(of: #""k33":{"value":1},"#, with: "")
                                            .replacingOccurrences(of: #","k33":{"value":1}"#, with: "")))
                        .validSourceSnapshot?.sources.count, 32, "32 entries is inside the client bound")
        // Not the controller's decode: no size, so no snapshot.
        XCTAssertNil(try Self.decode(LiveStreamFrame.self, Self.frame(11, 0.5, snapshot: drop)).validSourceSnapshot)
    }

    func testEvidenceAndUnknownKeysNeverRefuseOrChangeTheEntry() throws {
        let plain = #""polymarket":{"value":0.5,"updated_at":"2026-09-27T17:00:00Z"}"#
        let variants = [
            #""polymarket":{"value":0.5,"updated_at":"2026-09-27T17:00:00Z","price_evidence":"tradeable_book"}"#,
            #""polymarket":{"value":0.5,"updated_at":"2026-09-27T17:00:00Z","price_evidence":"not_evaluated"}"#,
            #""polymarket":{"value":0.5,"updated_at":"2026-09-27T17:00:00Z","evidence_status":"unproven","eligible":false}"#,
        ]
        let reference = try XCTUnwrap(try decoded(Self.frame(11, 0.5, snapshot: plain)).validSourceSnapshot)
        for raw in variants {
            XCTAssertEqual(try decoded(Self.frame(11, 0.5, snapshot: raw)).validSourceSnapshot, reference)
        }
    }

    func testTheAdoptionRuleIsSingletonNewerPricedOnly() throws {
        let page = try Self.detail(p: 0.6, revision: #"{"4242":10}"#, sources: Self.both)
        let drop = Self.kalshiOnly(0.5, at: Self.removedAt)
        let rule = LiveEventPriceReconciliation.sourceSnapshotAdoption
        guard case .adopt = rule(try decoded(Self.frame(11, 0.5, snapshot: drop)), page) else {
            return XCTFail("a newer priced singleton write adopts")
        }
        XCTAssertEqual(rule(try decoded(Self.frame(10, 0.5, snapshot: drop)), page), .legacy, "same")
        XCTAssertEqual(rule(try decoded(Self.frame(9, 0.5, snapshot: drop)), page), .legacy, "older")
        XCTAssertEqual(rule(try decoded(Self.frame(11, 0.5, snapshot: drop, status: "completed")), page), .legacy, "final")
        XCTAssertEqual(rule(try decoded(Self.frame(11, 0.5, snapshot: nil)), page), .legacy, "absent")
        var result = try decoded(Self.frame(11, 0.5, snapshot: drop))
        result.foldedResult = true
        XCTAssertEqual(rule(result, page), .legacy, "a folded result carries no row map")
        let folded = try Self.detail(p: 0.6, revision: #"{"4242":10,"4243":5}"#, sources: Self.both)
        XCTAssertEqual(rule(try decoded(Self.frame(11, 0.5, snapshot: drop)), folded), .legacy, "a folded hero")
        let opening = try Self.decode(EventDetail.self, """
        {"id":4242,"sport":"americanfootball_nfl","home_team":"Home","away_team":"Away","status":"live",
         "current_odds":{"home_probability":0.6,"away_probability":0.4},
         "hero_probability":0.6,"hero_probability_source":"opening","blend_fold_revision":{"4242":10},
         "win_probability_sources":{\(Self.both)}}
        """)
        XCTAssertEqual(rule(try decoded(Self.frame(11, 0.5, snapshot: drop)), opening), .legacy, "not a live blend")
        let eleven = try XCTUnwrap(FoldRevision(["4242": 11]))
        XCTAssertEqual(rule(try decoded(Self.frame(11, 0.5, snapshot: "")), page), .unpriced(eleven))
        XCTAssertEqual(rule(try decoded(Self.frame(11, nil, snapshot: drop)), page), .unpriced(eleven))
        XCTAssertEqual(rule(try decoded(Self.frame(11, 0.5, snapshot: #""final_result":{"value":1}"#)), page),
                       .unpriced(eleven))
    }

    func testTheSnapshotRailProvesTheDetailHalfOnlyWhileThePageHoldsIt() throws {
        let floor = try XCTUnwrap(FoldRevision(["4242": 11]))
        let rail12 = try XCTUnwrap(FoldRevision(["4242": 12]))
        let page12 = try Self.detail(p: 0.47, revision: #"{"4242":12}"#, sources: Self.kalshiOnly(0.47, at: "2026-09-27T17:02:00Z"))
        let page13 = try Self.detail(p: 0.46, revision: #"{"4242":13}"#, sources: Self.kalshiOnly(0.46, at: "2026-09-27T17:03:00Z"))
        let servedOld = try Self.detail(p: 0.6, revision: #"{"4242":10}"#, sources: Self.both)
        let pinned11 = try Self.history(p: 0.5, edge: #"{"4242":11}"#, at: Self.removedAt)
        let unpinned = try Self.history(p: 0.5, edge: nil, at: Self.removedAt)
        let pinned13 = try Self.history(p: 0.5, edge: #"{"4242":13}"#, at: Self.removedAt)
        let pinnedBoth = try Self.history(p: 0.5, edge: #"{"4242":11,"77":1}"#, at: Self.removedAt)
        let kalshi: Set<String> = ["kalshi"]
        let shown = { (floor: FoldRevision, served: EventDetail, history: EventHistoryResponse,
                       page: EventDetail, rail: FoldRevision?) in
            LiveEventPriceReconciliation.reconcileFloorShown(floor, served: served, servedHistory: history, page: page)
                || LiveEventPriceReconciliation.reconcileFloorShownByCommittedRail(
                    floor, committedRail: rail.map { .init(revision: $0, sources: kalshi) },
                    servedHistory: history, page: page)
        }
        XCTAssertTrue(shown(floor, servedOld, pinned11, page12, rail12))
        XCTAssertFalse(shown(floor, servedOld, pinned11, page12, nil), "no snapshot, no second proof")
        XCTAssertFalse(shown(floor, servedOld, pinned11, page13, rail12), "the page moved past it")
        XCTAssertFalse(shown(floor, servedOld, unpinned, page12, rail12), "a rail never pays history")
        XCTAssertFalse(shown(try XCTUnwrap(FoldRevision(["4242": 13])), servedOld, pinned13, page12, rail12),
                       "a rail below the floor")
        XCTAssertFalse(shown(try XCTUnwrap(FoldRevision(["4242": 11, "77": 1])), servedOld, pinnedBoth, page12, rail12),
                       "a missing floor row")
    }
}
