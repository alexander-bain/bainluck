import XCTest
import Foundation
@testable import Bain_Luck

/// #10643 (child of #10090) — Root's regression: a newer frame arriving during
/// the initial opening -> blend pair read must not need another frame or a
/// polling tick. Red on a7dcf4fb26 (headline and chart held 0.55, one pair).
@MainActor
final class ALatestOpeningFrameSurvivesAnInflightPair10090Tests: XCTestCase {
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
        func push(_ revision: Int, _ probability: Double) {
            fire("probability", """
            {"event_id":4242,"p":\(probability),"source":"polymarket",
             "source_value":\(probability),"updated_at":"2026-09-27T17:00:0\(revision - 10)Z",
             "status":"live","rev":{"4242":\(revision)}}
            """)
        }
    }

    @MainActor private final class Client: EventDetailProviding {
        struct Declined: Error {}
        private var detailCount = 0
        private var historyCount = 0
        private(set) var openingFreshReads = 0
        private var released = false
        private var waiters: [CheckedContinuation<Void, Never>] = []
        /// The revisions the first (held) and the trailing pair answer with.
        private let pairs: (Int, Int)
        init(pairs: (Int, Int) = (11, 12)) { self.pairs = pairs }
        static func probability(_ revision: Int) -> Double {
            [10: 0.60, 11: 0.55, 12: 0.52, 13: 0.49][revision]!
        }
        func counts() -> (Int, Int) { (detailCount, historyCount) }
        func releaseFirstPair() {
            released = true
            let pending = waiters
            waiters.removeAll()
            for waiter in pending { waiter.resume() }
        }
        private func holdFirstPair() async {
            guard !released else { return }
            await withCheckedContinuation { waiters.append($0) }
        }
        private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(type, from: Data(json.utf8))
        }
        private func detail(_ revision: Int, opening: Bool = false) throws -> EventDetail {
            let p = Self.probability(revision)
            let source = opening ? "opening" : "blend"
            return try decode(EventDetail.self, """
            {"id":4242,"home_team":"Home","away_team":"Away","sport":"tennis_atp","status":"live",
             "current_odds":{"home_probability":\(p),"away_probability":\(1-p)},
             "hero_probability":\(p),"hero_probability_source":"\(source)",
             "hero_probability_observed_at":"2026-09-27T17:00:0\(revision - 10)Z",
             "blend_fold_revision":{"4242":\(revision)},
             "win_probability_sources":{"polymarket":{"value":\(p),"updated_at":"2026-09-27T17:00:0\(revision - 10)Z"}}}
            """)
        }
        private func history(_ revision: Int) throws -> EventHistoryResponse {
            let p = Self.probability(revision)
            return try decode(EventHistoryResponse.self, """
            {"event_id":4242,"home_team":"Home","away_team":"Away","status":"live","history":[],
             "aggregate_line":[{"timestamp":"2026-09-27T17:00:0\(revision - 10)Z","home_probability":\(p)}],
             "blend_edge_fold_revision":{"4242":\(revision)},
             "blend_edge_observed_at":"2026-09-27T17:00:0\(revision - 10)Z"}
            """)
        }
        func fetchEvent(id: Int) async throws -> EventDetail { try detail(10, opening: true) }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { try history(10) }
        func fetchFreshEvent(id: Int) async throws -> EventDetail {
            // The explicit initial open now asks fresh too. It serves the
            // opening independently; only the later stream-triggered pair is
            // held while newer frames arrive, preserving this regression guard.
            if openingFreshReads == 0 {
                openingFreshReads += 1
                return try detail(10, opening: true)
            }
            detailCount += 1
            let revision = detailCount == 1 ? pairs.0 : pairs.1
            if detailCount == 1 { await holdFirstPair() }
            return try detail(revision)
        }
        func fetchFreshEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            historyCount += 1
            let revision = historyCount == 1 ? pairs.0 : pairs.1
            if historyCount == 1 { await holdFirstPair() }
            return try history(revision)
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private var clock: TimeInterval = 1_800_000_000

    func testLastFrameDuringOpeningPairIsNotLostWhenStreamGoesQuiet() async throws {
        let client = Client(), handle = Handle()
        let vm = EventDetailViewModel(
            eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { [weak self] in self?.clock ?? 0 },
            // No fallback poll may rescue this case. Clock advancement below
            // clears the existing one-second rate limit before the read returns.
            sleep: { _ in try? await Task.sleep(for: .seconds(60)) }
        )
        defer { vm.stopRefresh() }
        await vm.load()
        XCTAssertEqual(client.openingFreshReads, 1)
        XCTAssertEqual(vm.event?.heroProbabilitySource, "opening")
        handle.fire("open")
        handle.push(11, 0.55)
        for _ in 0..<200 {
            let counts = await client.counts()
            if counts.0 == 1 && counts.1 == 1 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let started = await client.counts()
        XCTAssertEqual(started.0, 1)
        XCTAssertEqual(started.1, 1)
        // First pair is frozen at revision 11. The last real frame is 12.
        handle.push(12, 0.52)
        clock += 2
        await client.releaseFirstPair()
        // Deliberately send no third frame and do not wake fallback polling.
        for _ in 0..<200 {
            if vm.event?.currentOdds?.homeProbability == 0.52,
               vm.history?.aggregateLine?.last?.homeProbability == 0.52 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52,
                       "Last received revision must reach the headline without a third frame or fallback poll")
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.52,
                       "The same authoritative pair must reach the chart")
        let finished = await client.counts()
        XCTAssertEqual(finished.0, 2, "Coalesce the burst into one trailing pair")
        XCTAssertEqual(finished.1, 2, "Do not start overlapping or unbounded re-reads")
    }

    /// #10643 — a delayed older frame cannot erase the newer requirement. The
    /// held pair answers 12; frames 13 and then a late 12 arrive during it. The
    /// pair covers 12 but not 13, so exactly one trailing pair is still owed.
    func testADelayedOlderFrameDoesNotEraseTheNewerRequirement() async throws {
        let client = Client(pairs: (12, 13)), handle = Handle()
        let vm = EventDetailViewModel(
            eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { [weak self] in self?.clock ?? 0 },
            sleep: { _ in try? await Task.sleep(for: .seconds(60)) }
        )
        defer { vm.stopRefresh() }
        await vm.load()
        XCTAssertEqual(client.openingFreshReads, 1)
        handle.fire("open")
        handle.push(11, 0.55)
        for _ in 0..<200 {
            let counts = await client.counts()
            if counts.0 == 1 && counts.1 == 1 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        handle.push(13, 0.49)
        handle.push(12, 0.52)
        clock += 2
        await client.releaseFirstPair()
        for _ in 0..<200 {
            if vm.event?.currentOdds?.homeProbability == 0.49,
               vm.history?.aggregateLine?.last?.homeProbability == 0.49 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.49, "revision 13 reaches the headline")
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.49, "and the chart")
        let finished = await client.counts()
        XCTAssertEqual(finished.0, 2, "one trailing pair, no more")
        XCTAssertEqual(finished.1, 2)
    }
}
