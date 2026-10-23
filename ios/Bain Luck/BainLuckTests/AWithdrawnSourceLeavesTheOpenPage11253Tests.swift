import XCTest
import Foundation
@testable import Bain_Luck

/// #11253 (child of #10090) — Live's R1 frame says a venue withdrew from a
/// one-row live blend: a strictly newer revision with no price. Before this,
/// `apply` found no `p`, wrote nothing and asked for nothing, so the hero and
/// the rail kept Polymarket until the 120 s poll. Web reads the authoritative
/// detail + history pair on `p === null`; so must the iPhone, without dating
/// the held value with the new revision, losing a newer quote, or looping.
@MainActor
final class AWithdrawnSourceLeavesTheOpenPage11253Tests: XCTestCase {
    private static let both = #""kalshi":{"value":0.5,"updated_at":"2026-09-27T17:00:00Z"},"polymarket":{"value":0.82,"updated_at":"2026-09-27T17:00:00Z"}"#
    private static func kalshiOnly(_ p: Double, at: String) -> String {
        #""kalshi":{"value":\#(p),"updated_at":"\#(at)"}"#
    }

    /// Live's R1 frame, literally — including the keys this client ignores.
    private static func invalidation(_ revision: Int, at: String = "2026-09-27T17:01:00Z") -> String {
        """
        {"event_id":4242,"p":null,"source":null,"source_value":null,"updated_at":"\(at)",
         "status":"live","rev":{"4242":\(revision)},"invalidation":true,"origin_event_id":4242}
        """
    }

    private static func priced(_ revision: Int, _ p: Double, source: String = "kalshi",
                               at: String = "2026-09-27T17:02:00Z") -> String {
        """
        {"event_id":4242,"p":\(p),"source":"\(source)","source_value":\(p),"updated_at":"\(at)",
         "status":"live","rev":{"4242":\(revision)}}
        """
    }

    private static func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    private static func detail(p: Double, revision: String, sources: String, status: String = "live",
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

    private static func history(p: Double, revision: String, at: String,
                                winProb: String = "") throws -> EventHistoryResponse {
        try decode(EventHistoryResponse.self, """
        {"event_id":4242,"home_team":"Home","away_team":"Away","status":"live","history":[],
         \(winProb.isEmpty ? "" : "\"win_prob_history\":{\(winProb)},")
         "aggregate_line":[{"timestamp":"\(at)","home_probability":\(p)}],
         "blend_edge_pinned":true,"blend_edge_fold_revision":\(revision),
         "blend_edge_observed_at":"\(at)"}
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

    /// `load()` reads `page`; once `armed`, every fresh read is a stream pair
    /// answered from `pairs` by absolute read index (the last repeats). Each
    /// index in `holdPairs` freezes that pair's two halves until `release()`.
    @MainActor private final class Client: EventDetailProviding {
        struct Declined: Error {}
        struct Pair { let revision: Int; let p: Double; let sources: String; let at: String }
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
        /// Releases every pair waiting now; later held indexes still hold.
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
            return try AWithdrawnSourceLeavesTheOpenPage11253Tests.detail(
                p: pair.p, revision: #"{"4242":\#(pair.revision)}"#, sources: pair.sources, observedAt: pair.at)
        }
        func fetchFreshEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            guard armed else { return pageHistory }
            let index = historyReads
            historyReads += 1
            let pair = pairs[min(index, pairs.count - 1)]
            await hold(index)
            return try AWithdrawnSourceLeavesTheOpenPage11253Tests.history(
                p: pair.p, revision: #"{"4242":\#(pair.revision)}"#, at: pair.at)
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private var clock: TimeInterval = 1_800_000_000

    /// A live one-row blend at revision 10: hero 60, rail Kalshi 50 + Polymarket 82.
    private func opened(
        page: EventDetail? = nil, pairs: [Client.Pair], holdPairs: Set<Int> = []
    ) async throws -> (Client, Handle, EventDetailViewModel) {
        let client = Client(
            page: try page ?? Self.detail(p: 0.6, revision: #"{"4242":10}"#, sources: Self.both),
            history: try Self.history(p: 0.6, revision: #"{"4242":10}"#, at: "2026-09-27T17:00:00Z")
        )
        client.pairs = pairs
        client.holdPairs = holdPairs
        let handle = Handle()
        let vm = EventDetailViewModel(
            eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { [weak self] in self?.clock ?? 0 },
            // No fallback poll may rescue any case here.
            sleep: { _ in try? await Task.sleep(for: .seconds(60)) }
        )
        await vm.load()
        client.armed = true
        handle.fire("open")
        return (client, handle, vm)
    }

    private func settle(_ done: () -> Bool) async throws {
        for _ in 0..<400 where !done() { try await Task.sleep(for: .milliseconds(5)) }
    }

    /// Long enough for any wrongly scheduled read to have started.
    private func quiet() async throws { try await Task.sleep(for: .milliseconds(150)) }

    private static let removedAt = "2026-09-27T17:00:30Z"
    private static let withoutPolymarket = Client.Pair(
        revision: 11, p: 0.5, sources: kalshiOnly(0.5, at: removedAt), at: removedAt)

    // MARK: - T1 the core

    func testANewerPricelessFrameReadsThePairAndDropsTheWithdrawnSource() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.withoutPolymarket])
        defer { vm.stopRefresh() }
        let blend = vm.liveBlend
        let frame = try Self.decode(LiveStreamFrame.self, Self.invalidation(11))
        XCTAssertNil(frame.p, "R1 decodes, extra keys and all")
        XCTAssertEqual(frame.rev?.revision?.rows, ["4242": 11])

        handle.fire("probability", Self.invalidation(11))
        // The frame itself writes nothing and borrows no revision.
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 10],
                       "the held value is never dated with the withdrawal's revision")
        XCTAssertEqual(vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue, 0.82)
        XCTAssertNil(vm.event?.winProbabilitySources?["null"])
        XCTAssertEqual(vm.liveBlend, blend, "no chart point without a price")

        try await settle { vm.event?.winProbabilitySources?["polymarket"] == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "exactly one paired read")
        XCTAssertEqual(client.historyReads, 1)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"], "the withdrawn venue leaves the rail")
        XCTAssertEqual(vm.event?.winProbabilitySources?["kalshi"]?.value?.doubleValue, 0.5)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 11])
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.5, "the chart is replaced with it")
        XCTAssertEqual(vm.liveUpdateStatus, .live, "a newer adopted pair is a delivery")
    }

    // MARK: - T2 replay and reconnect

    func testAReplayedWithdrawalAsksNothingAndOnlyAGenuinelyNewerPriceLands() async throws {
        let (client, handle, vm) = try await opened(pairs: [Self.withoutPolymarket])
        defer { vm.stopRefresh() }
        handle.fire("probability", Self.invalidation(11))
        try await settle { client.detailReads == 1 && vm.event?.winProbabilitySources?["polymarket"] == nil }

        handle.fire("probability", Self.invalidation(11))
        handle.fire("open")
        handle.fire("probability", Self.invalidation(11))
        // A delayed pre-withdrawal price still folds Polymarket in: refused.
        handle.fire("probability", Self.priced(10, 0.6, source: "polymarket", at: "2026-09-27T17:00:20Z"))
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "a replay, before or after a transport open, is not a new withdrawal")
        XCTAssertEqual(client.historyReads, 1)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])

        handle.fire("probability", Self.priced(12, 0.47))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.47)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 12])
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
        try await quiet()
        XCTAssertEqual(client.detailReads, 1, "a priced newer frame asks nothing")
    }

    // MARK: - T3 controls with no read owed

    func testAnOlderOrSamePricelessFrameAsksNothing() async throws {
        let page = try Self.detail(p: 0.6, revision: #"{"4242":12}"#, sources: Self.both)
        let (client, handle, vm) = try await opened(page: page, pairs: [Self.withoutPolymarket])
        defer { vm.stopRefresh() }
        handle.fire("probability", Self.invalidation(11))
        handle.fire("probability", Self.invalidation(12))
        try await quiet()
        XCTAssertEqual(client.detailReads, 0)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6)
        XCTAssertEqual(vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue, 0.82)
    }

    func testAFinishedOrUnversionedPageMakesNoClaimAndAsksNothing() async throws {
        for page in [try Self.detail(p: 0.6, revision: #"{"4242":10}"#, sources: Self.both, status: "final"),
                     try Self.detail(p: 0.6, revision: "null", sources: Self.both)] {
            let (client, handle, vm) = try await opened(page: page, pairs: [Self.withoutPolymarket])
            handle.fire("probability", Self.invalidation(11))
            try await quiet()
            XCTAssertEqual(client.detailReads, 0, page.status ?? "")
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6, page.status ?? "")
            XCTAssertEqual(vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue, 0.82)
            vm.stopRefresh()
        }
    }

    // MARK: - T4 a newer quote during the pair (Root's case)

    /// The pair is served at 11 — exactly the owed withdrawal — while Kalshi 48
    /// at 12 lands during it. The held headline (12) correctly beats the pair,
    /// and keeps the held rail with it: Polymarket 82 would survive. The
    /// requirement is the served rail on the page, not `served < owed`.
    func testANewerQuoteDuringThePairKeepsTheHeadlineAndOneTrailingPairDropsTheSource() async throws {
        let trailing = Client.Pair(revision: 12, p: 0.48, sources: Self.kalshiOnly(0.48, at: "2026-09-27T17:02:00Z"),
                                   at: "2026-09-27T17:02:00Z")
        let (client, handle, vm) = try await opened(pairs: [Self.withoutPolymarket, trailing], holdPairs: [0])
        defer { vm.stopRefresh() }
        handle.fire("probability", Self.invalidation(11))
        try await settle { client.detailReads == 1 && client.historyReads == 1 }

        handle.fire("probability", Self.priced(12, 0.48))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.48)
        clock += 2
        client.release()
        try await settle { client.detailReads == 2 && vm.event?.winProbabilitySources?["polymarket"] == nil }
        try await quiet()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.48, "the newer quote is never lost")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 12])
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"], "the withdrawn venue leaves despite the race")
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.48)
        XCTAssertEqual(client.detailReads, 2, "one trailing pair, no more")
        XCTAssertEqual(client.historyReads, 2)
    }

    /// The bound, and the debt it must not drop: a server still serving 11
    /// after the trailing ask cannot make the page loop, and the page does not
    /// pretend the venue left. One trailing pair per HELD revision whenever
    /// another pair lands; a priced quote never asks on its own.
    func testAStaleServerAfterTheTrailingPairDoesNotLoopOrDropTheDebt() async throws {
        let stale12 = Client.Pair(revision: 12, p: 0.48, sources: Self.kalshiOnly(0.48, at: "2026-09-27T17:02:00Z"),
                                  at: "2026-09-27T17:02:00Z")
        let fresh13 = Client.Pair(revision: 13, p: 0.46, sources: Self.kalshiOnly(0.46, at: "2026-09-27T17:03:00Z"),
                                  at: "2026-09-27T17:03:00Z")
        let (client, handle, vm) = try await opened(
            pairs: [Self.withoutPolymarket, Self.withoutPolymarket, stale12, fresh13], holdPairs: [0, 2])
        defer { vm.stopRefresh() }
        handle.fire("probability", Self.invalidation(11))
        try await settle { client.detailReads == 1 && client.historyReads == 1 }
        handle.fire("probability", Self.priced(12, 0.48))
        clock += 2
        client.release()
        try await settle { client.detailReads == 2 }
        clock += 2
        try await Task.sleep(for: .milliseconds(300))
        XCTAssertEqual(client.detailReads, 2, "the same held revision asks once")
        XCTAssertEqual(client.historyReads, 2)
        // The honest residual: nothing claims the venue left.
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.48)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 12])
        XCTAssertEqual(vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue, 0.82)

        handle.fire("probability", Self.priced(13, 0.46, at: "2026-09-27T17:03:00Z"))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.46)
        try await quiet()
        XCTAssertEqual(client.detailReads, 2, "a priced quote asks nothing")
        XCTAssertEqual(vm.event?.winProbabilitySources?["polymarket"]?.value?.doubleValue, 0.82)

        // An unrelated pair (an unorderable frame) lands: still stale (12),
        // beaten by held 13, so the kept debt asks once more at 13.
        handle.fire("probability", """
        {"event_id":4242,"p":null,"source":null,"source_value":null,"updated_at":null,
         "status":"live","rev":{"9999":1}}
        """)
        try await settle { client.detailReads == 3 && client.historyReads == 3 }
        clock += 2
        client.release()
        try await settle { client.detailReads == 4 && vm.event?.winProbabilitySources?["polymarket"] == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 4, "the debt survived the stale reads and is paid by the fresh one")
        XCTAssertEqual(client.historyReads, 4)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.46)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 13])
    }

    // MARK: - T5 folded controls (unchanged behaviour)

    private static let folded = #"{"4242":20,"999":5}"#
    private static let pendingNil = #""event_id":4242,"p":null,"source":null,"source_value":null,"updated_at":"2026-09-27T17:01:00Z","status":"live","rev":{"4242":21}"#
    private static let quoteWithoutPolymarket = """
        {"event_id":4242,"hero_probability":0.5,"hero_probability_away":0.5,
         "hero_probability_source":"blend","hero_probability_observed_at":"2026-09-27T17:01:00Z",
         "blend_fold_revision":{"4242":21,"999":5},
         "win_probability_sources":{"kalshi":{"value":0.5,"display_name":"Kalshi","type":"market","color":"#000","updated_at":"2026-09-27T17:01:00Z"}},
         "hero_sportsbook_count":null,"status":"live","sport":"americanfootball_nfl","hero_settled_result":null}
        """

    func testAFoldedPagesPricelessPendingFrameAwaitsTheQuoteWhichCarriesTheFullRail() async throws {
        let page = try Self.detail(p: 0.6, revision: Self.folded, sources: Self.both)
        let (client, handle, vm) = try await opened(page: page, pairs: [Self.withoutPolymarket])
        defer { vm.stopRefresh() }
        handle.fire("probability", "{\(Self.pendingNil),\"folded_quote_pending\":true}")
        try await quiet()
        XCTAssertEqual(client.detailReads, 0, "the promise holds the read back")
        handle.fire("folded_probability",
                    "{\(Self.pendingNil),\"folded_quote_pending\":false,\"folded_quote\":\(Self.quoteWithoutPolymarket)}")
        try await quiet()
        XCTAssertEqual(client.detailReads, 0)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 21, "999": 5])
    }

    func testAFoldedPagesNullResultRunsOnePair() async throws {
        let page = try Self.detail(p: 0.6, revision: Self.folded, sources: Self.both)
        let (client, handle, vm) = try await opened(page: page, pairs: [Self.withoutPolymarket])
        defer { vm.stopRefresh() }
        handle.fire("probability", "{\(Self.pendingNil),\"folded_quote_pending\":true}")
        handle.fire("folded_probability", "{\(Self.pendingNil),\"folded_quote_pending\":false,\"folded_quote\":null}")
        try await settle { client.detailReads == 1 && vm.event?.winProbabilitySources?["polymarket"] == nil }
        try await quiet()
        XCTAssertEqual(client.detailReads, 1)
        XCTAssertEqual(client.historyReads, 1)
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])
    }

    // MARK: - T6 reopened after the withdrawal, then silence

    func testAReopenedPageShowsNoWithdrawnSourceAndSilenceAsksNothing() async throws {
        let page = try Self.detail(p: 0.5, revision: #"{"4242":11}"#, sources: Self.kalshiOnly(0.5, at: Self.removedAt),
                                   observedAt: Self.removedAt)
        let client = Client(page: page, history: try Self.history(
            p: 0.5, revision: #"{"4242":11}"#, at: Self.removedAt,
            winProb: """
            "polymarket":[{"timestamp":"2026-09-27T17:00:00Z","home_probability":0.82},
                          {"timestamp":"\(Self.removedAt)","home_probability":null}],
            "kalshi":[{"timestamp":"2026-09-27T17:00:00Z","home_probability":0.5},
                      {"timestamp":"\(Self.removedAt)","home_probability":0.5}]
            """))
        client.pairs = [Self.withoutPolymarket]
        let handle = Handle()
        let vm = EventDetailViewModel(
            eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { [weak self] in self?.clock ?? 0 },
            sleep: { _ in try? await Task.sleep(for: .seconds(60)) }
        )
        defer { vm.stopRefresh() }
        await vm.load()
        client.armed = true
        handle.fire("open")
        let history = try XCTUnwrap(vm.history)
        let removed = try XCTUnwrap(Self.removedAt.asDate)
        let points = OddsChartView.chartPoints(from: history, liveFrames: vm.liveBlend)
        XCTAssertFalse(points.contains { $0.source == "polymarket" && $0.date >= removed },
                       "the null vertex ends Polymarket's line at its withdrawal")
        XCTAssertTrue(points.contains { $0.source == "polymarket" && $0.date < removed }, "its history before stays")
        XCTAssertNil(LiveEventPriceReconciliation.chartRevisionRefreshKey(
            event: vm.event, history: history, liveBlend: vm.liveBlend), "the edge already ends on the hero")
        XCTAssertNil(vm.event?.winProbabilitySources?["polymarket"])

        clock += 120
        vm.tickStream()
        try await quiet()
        XCTAssertEqual(client.detailReads, 0, "silence after the final withdrawal invents no read")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.5)
    }
}
