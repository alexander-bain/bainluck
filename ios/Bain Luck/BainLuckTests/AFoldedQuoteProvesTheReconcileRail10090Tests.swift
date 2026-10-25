import XCTest
import Foundation
@testable import Bain_Luck

/// #10090 — ROOT-COHERENT-RAIL-PAYMENT-DECISION, folded follow-through. On a
/// folded page (canonical + duplicate rows) the only rail proof is a full
/// folded quote the existing authoritative path ADOPTED: its price, complete
/// rail and full revision, read back from the page it wrote. It proves the
/// reconcile floor's detail half only while the page still holds that exact
/// revision and those sources; history is still a pinned covering edge. Raw
/// sibling frames, a held/older quote and a remembered floor prove nothing.
@MainActor
final class AFoldedQuoteProvesTheReconcileRail10090Tests: XCTestCase {
    private static let both = #""kalshi":{"value":0.5,"updated_at":"2026-09-27T17:00:00Z"},"polymarket":{"value":0.82,"updated_at":"2026-09-27T17:00:00Z"}"#
    private static func kalshiOnly(_ p: Double, at: String) -> String {
        #""kalshi":{"value":\#(p),"updated_at":"\#(at)"}"#
    }
    private static func withPolymarket(_ p: Double, at: String) -> String {
        #""kalshi":{"value":\#(p),"updated_at":"\#(at)"},"polymarket":{"value":0.3,"updated_at":"\#(at)"}"#
    }
    /// The fold: canonical row 4242 at `r`, duplicate row 4243 at 5.
    private static func fold(_ r: Int) -> String { #"{"4242":\#(r),"4243":5}"# }

    private static func control(_ custody: String = "c-1", floor: String = #"{"4242":11}"#) -> String {
        #"{"event_id":4242,"custody_id":"\#(custody)","removal_rev":\#(floor)}"#
    }

    private static func raw(_ r: Int, at: String) -> String {
        #""event_id":4242,"p":0.9,"source":null,"source_value":null,"updated_at":"\#(at)","status":"live","rev":{"4242":\#(r)}"#
    }

    private static func quote(_ r: Int, _ p: Double, sources: String, at: String, status: String = "live") -> String {
        """
        {"event_id":4242,"hero_probability":\(p),"hero_probability_away":\(1 - p),
         "hero_probability_source":"blend","hero_probability_observed_at":"\(at)",
         "blend_fold_revision":\(fold(r)),"win_probability_sources":{\(sources)},
         "hero_sportsbook_count":null,"status":"\(status)","sport":"americanfootball_nfl","hero_settled_result":null}
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
        /// A pending raw row write, then its authoritative full-fold quote.
        func push(_ r: Int, _ p: Double, sources: String, at: String) {
            let raw = AFoldedQuoteProvesTheReconcileRail10090Tests.raw(r, at: at)
            fire("probability", "{\(raw),\"folded_quote_pending\":true}")
            fire("folded_probability", "{\(raw),\"folded_quote_pending\":false,\"folded_quote\":\(AFoldedQuoteProvesTheReconcileRail10090Tests.quote(r, p, sources: sources, at: at))}")
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

    @MainActor private final class Client: EventDetailProviding {
        struct Declined: Error {}
        struct Pair {
            var revision: String
            var p: Double
            var sources: String
            var at: String
            var fails = false
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
            return try AFoldedQuoteProvesTheReconcileRail10090Tests.detail(
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
            return try AFoldedQuoteProvesTheReconcileRail10090Tests.history(p: pair.p, edge: edge, at: pair.at)
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

    /// A live FOLDED blend at {4242:10, 4243:5}: hero 60, rail Kalshi 50 + Polymarket 82.
    private func opened(pairs: [Client.Pair], holdPairs: Set<Int> = []) async throws
        -> (Client, Handle, EventDetailViewModel) {
        let client = Client(
            page: try Self.detail(p: 0.6, revision: Self.fold(10), sources: Self.both),
            history: try Self.history(p: 0.6, edge: Self.fold(10), at: "2026-09-27T17:00:00Z")
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

    private static let at11 = "2026-09-27T17:01:00Z"
    private static let at12 = "2026-09-27T17:02:00Z"
    private static let at13 = "2026-09-27T17:03:00Z"
    /// A detail at {4242:11, 4243:5} without Polymarket; history pinned at its own revision.
    private static let served11 = Client.Pair(revision: fold(11), p: 0.5, sources: kalshiOnly(0.5, at: at11), at: at11)
    private static let served12 = Client.Pair(revision: fold(12), p: 0.47, sources: kalshiOnly(0.47, at: at12), at: at12)
    /// A sibling row's write: unorderable on a folded hero, so the page asks one pair.
    private static let siblingRaw = #"{"event_id":4242,"p":0.4,"source":"kalshi","source_value":0.4,"updated_at":"2026-09-27T17:00:40Z","status":"live","rev":{"4243":6}}"#

    private func polymarket(_ vm: EventDetailViewModel) -> Double? {
        vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue
    }

    // MARK: - F1 continuous full quotes overtake every pair

    func testContinuousFoldedQuotesLetTheFirstCoveringHistoryPay() async throws {
        var unpinned = Self.served11
        unpinned.edge = .some(nil)
        let (client, handle, vm) = try await opened(pairs: [unpinned, Self.served12], holdPairs: [0, 1])
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        XCTAssertNil(polymarket(vm), "the adopted quote's rail")
        clock += 2
        client.release()
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "an unpinned history pays nothing, whatever the rail")

        try await elapse(1.5)
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        handle.push(13, 0.46, sources: Self.kalshiOnly(0.46, at: Self.at13), at: Self.at13)
        clock += 2
        client.release()
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertNil(vm.reconcileOwedSince, "the adopted full quote's rail + a pinned covering edge pay it")
        XCTAssertEqual(client.detailReads, 2)
        XCTAssertEqual(reconcileAsks, [1.5])
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.46, "the newest quote is kept")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 13, "4243": 5])
    }

    // MARK: - F2 raw sibling frames prove nothing

    func testRawSiblingFramesAndANullResultRecordNoProof() async throws {
        var staleCoveredHistory = Client.Pair(revision: Self.fold(10), p: 0.6, sources: Self.both,
                                              at: "2026-09-27T17:00:00Z")
        staleCoveredHistory.edge = .some(Self.fold(11))
        let (client, handle, vm) = try await opened(pairs: [staleCoveredHistory])
        // A raw row write carrying a row snapshot (a producer that failed to
        // strip it), answered by an explicit null quote, and a sibling's write.
        let rawWithSnapshot = #""event_id":4242,"p":0.5,"source":"kalshi","source_value":0.5,"updated_at":"2026-09-27T17:01:00Z","status":"live","rev":{"4242":11},"source_snapshot":{"event_id":4242,"rev":{"4242":11},"win_probability_sources":{"kalshi":{"value":0.5,"updated_at":"2026-09-27T17:01:00Z"}}}"#
        handle.fire("probability", "{\(rawWithSnapshot),\"folded_quote_pending\":true}")
        handle.fire("folded_probability", "{\(rawWithSnapshot),\"folded_quote_pending\":false,\"folded_quote\":null}")
        try await settle { client.detailReads == 1 }
        try await quiet()
        clock += 2
        handle.fire("probability", Self.siblingRaw)
        try await settle { client.detailReads == 2 }
        try await quiet()
        XCTAssertEqual(polymarket(vm), 0.82, "no raw frame replaced the folded rail")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6)

        clock += 2
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 3 }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "a covering history beside an uncovered detail and no adopted quote")
        XCTAssertEqual(polymarket(vm), 0.82)
    }

    // MARK: - F3 a later mutation invalidates the old proof

    /// The page moved to a later revision with the same sources (a newer read):
    /// the quote it adopted earlier proves nothing about this rail.
    func testALaterRevisionOnThePageFailsTheOldProof() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.served11, Self.served12])
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        client.page = try Self.detail(p: 0.46, revision: Self.fold(13), sources: Self.kalshiOnly(0.46, at: Self.at13),
                                      observedAt: Self.at13)
        await vm.load(fresh: false)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 13, "4243": 5])
        clock += 2
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "page 13 is neither the served 11 nor the adopted 12")
    }

    /// The page kept the quote's revision but now lists other sources (a read
    /// at the same revision listing Polymarket): the rail identity changed.
    func testADifferentSourceListAtTheSameRevisionFailsTheOldProof() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.served11])
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        client.page = try Self.detail(p: 0.47, revision: Self.fold(12), sources: Self.withPolymarket(0.47, at: Self.at12),
                                      observedAt: Self.at12)
        await vm.load(fresh: false)
        XCTAssertEqual(polymarket(vm), 0.3)
        clock += 2
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "the rail on the page is not the quote's rail")
        XCTAssertEqual(polymarket(vm), 0.3)
    }

    /// An old once-shown quote, delivered again after the page moved on, is
    /// held and records nothing.
    func testAnOldOnceShownQuoteIsNotProof() async throws {
        let newer13 = Client.Pair(revision: Self.fold(13), p: 0.46, sources: Self.withPolymarket(0.46, at: Self.at13),
                                  at: Self.at13)
        let (client, handle, vm) = try await opened(pairs: [newer13, Self.served11])
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        clock += 2
        handle.fire("probability", Self.siblingRaw)
        try await settle { client.detailReads == 1 && polymarket(vm) == 0.3 }
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        XCTAssertEqual(polymarket(vm), 0.3, "an older quote is held")
        clock += 2
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 2 && client.historyReads == 2 }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince)
    }

    // MARK: - F4 removal then genuine re-addition

    func testRemovalThenReAdditionFollowsQuoteOrderAndTheCurrentRailPays() async throws {
        let older12 = Client.Pair(revision: Self.fold(12), p: 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12),
                                  at: Self.at12)
        let (client, handle, vm) = try await opened(pairs: [older12])
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        XCTAssertNil(polymarket(vm), "12 drops Polymarket")
        handle.push(13, 0.46, sources: Self.withPolymarket(0.46, at: Self.at13), at: Self.at13)
        XCTAssertEqual(polymarket(vm), 0.3, "13 restores it, in quote order")
        clock += 2
        handle.fire("reconcile", Self.control(floor: #"{"4242":12}"#))
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertNil(vm.reconcileOwedSince, "the rail on the page is 13's, past the floor; history 12 covers it")
        XCTAssertEqual(polymarket(vm), 0.3, "an older read at 12 prunes nothing")
        XCTAssertEqual(client.detailReads, 1)
    }

    // MARK: - F5 a missing floor row

    func testAFloorRowOutsideTheFoldRefuses() async throws {
        var coveringEveryRow = Self.served11
        coveringEveryRow.edge = .some(#"{"4242":11,"4243":5,"77":1}"#)
        let (client, handle, vm) = try await opened(pairs: [coveringEveryRow])
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        clock += 2
        handle.fire("reconcile", Self.control(floor: #"{"4242":11,"77":1}"#))
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince, "row 77 is not in the adopted quote's revision")
    }

    // MARK: - F6 failed and unproven history stay owed

    func testFailedAndUnprovenHistoryStayOwedBesideTheQuoteRail() async throws {
        var failing = Self.served11
        failing.fails = true
        var unpinned = Self.served11
        unpinned.edge = .some(nil)
        var staleEdge = Self.served11
        staleEdge.edge = .some(Self.fold(10))
        let (client, handle, vm) = try await opened(pairs: [failing, unpinned, staleEdge, Self.served11])
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        let owedAt = clock
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && vm.pricePairRefreshFailed }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a failed pair keeps it")

        try await settle { sleeper.pending(2) == 1 }
        clock += 2
        sleeper.fire(2)
        try await settle { client.detailReads == 2 && !vm.pricePairRefreshFailed }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "an adopted quote never pays history: unpinned keeps it")

        try await elapse(3)
        try await settle { client.detailReads == 3 }
        try await quiet()
        XCTAssertEqual(vm.reconcileOwedSince, owedAt, "a pinned edge below the floor keeps it")

        try await elapse(6)
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 4, "a covering edge pays on the retry clock alone")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 12, "4243": 5])
    }

    // MARK: - F7 final and navigation keep their owners

    func testAPushedFinalTakesNoLaterQuoteAndNavigationRetiresTheFloor() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.served11], holdPairs: [0])
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        handle.fire("probability", #"{"event_id":4242,"p":null,"source":null,"source_value":null,"updated_at":"2026-09-27T17:05:00Z","status":"completed","rev":{"4242":14}}"#)
        XCTAssertEqual(vm.event?.status, "completed")
        let quote13 = Self.quote(13, 0.46, sources: Self.withPolymarket(0.46, at: Self.at13), at: Self.at13)
        handle.fire("folded_probability",
                    "{\(Self.raw(13, at: Self.at13)),\"folded_quote_pending\":false,\"folded_quote\":\(quote13)}")
        XCTAssertEqual(vm.event?.status, "completed", "no quote reopens a pushed final")
        XCTAssertNil(polymarket(vm), "nor replaces its rail")
        clock += 2
        client.release()
        try await settle { vm.reconcileOwedSince == nil }
        try await quiet()
        XCTAssertEqual(vm.event?.status, "completed", "a live response keeps the pushed final")
        let reads = client.detailReads
        handle.fire("reconcile", Self.control("c-late"))
        try await quiet()
        XCTAssertEqual(client.detailReads, reads, "a finished page takes no control")
        XCTAssertNil(vm.reconcileOwedSince)
    }

    func testLeavingThePageRetiresTheFloorWithItsProof() async throws {
        var unpinned = Self.served11
        unpinned.edge = .some(nil)
        let (client, handle, vm) = try await opened(pairs: [unpinned])
        handle.push(12, 0.47, sources: Self.kalshiOnly(0.47, at: Self.at12), at: Self.at12)
        handle.fire("reconcile", Self.control())
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        try await quiet()
        XCTAssertNotNil(vm.reconcileOwedSince)
        vm.stopRefresh()
        XCTAssertNil(vm.reconcileOwedSince, "the reader left: its named owner retires the floor")
        sleeper.drain()
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "and nothing re-asks")
    }

    // MARK: - F8 the pure rule

    func testTheCommittedRailProvesTheDetailHalfOnlyWhileThePageHoldsIt() throws {
        let floor = try XCTUnwrap(FoldRevision(["4242": 11]))
        let quote12 = try XCTUnwrap(FoldRevision(["4242": 12, "4243": 5]))
        let rail = LiveEventPriceReconciliation.CommittedRail(revision: quote12, sources: ["kalshi"])
        let page12 = try Self.detail(p: 0.47, revision: Self.fold(12), sources: Self.kalshiOnly(0.47, at: Self.at12))
        let page12PM = try Self.detail(p: 0.47, revision: Self.fold(12), sources: Self.withPolymarket(0.47, at: Self.at12))
        let page13 = try Self.detail(p: 0.46, revision: Self.fold(13), sources: Self.kalshiOnly(0.46, at: Self.at13))
        let pinned = try Self.history(p: 0.5, edge: Self.fold(11), at: Self.at11)
        let unpinned = try Self.history(p: 0.5, edge: nil, at: Self.at11)
        let byRail = LiveEventPriceReconciliation.reconcileFloorShownByCommittedRail
        XCTAssertTrue(byRail(floor, rail, pinned, page12))
        XCTAssertFalse(byRail(floor, nil, pinned, page12), "no adopted quote, no proof")
        XCTAssertFalse(byRail(floor, rail, pinned, page13), "the page moved past it")
        XCTAssertFalse(byRail(floor, rail, pinned, page12PM), "the page lists other sources")
        XCTAssertFalse(byRail(floor, rail, unpinned, page12), "a quote never pays history")
        XCTAssertFalse(byRail(try XCTUnwrap(FoldRevision(["4242": 11, "77": 1])), rail,
                              try Self.history(p: 0.5, edge: #"{"4242":11,"4243":5,"77":1}"#, at: Self.at11), page12),
                       "a missing floor row")
        var finished = page12
        finished.status = "completed"
        XCTAssertFalse(byRail(floor, rail, pinned, finished), "a finished page holds no live blend")
    }
}
