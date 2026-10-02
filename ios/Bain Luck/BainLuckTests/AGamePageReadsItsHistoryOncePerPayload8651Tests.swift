import XCTest
@testable import Bain_Luck

/// #8651 (build 34) — **a game page left open stays smooth: it reads its
/// history once per payload, not once per rebuild.**
///
/// Alex, Oct 1, build 34, Steelers–Browns 14780550: "I had this page open for a
/// while … the scrolling got very, very choppy to the point where the app
/// became unusable." Measured on build 34's own source (Release, simulator):
/// every update the page takes in rebuilt it, and the rebuild re-parsed every
/// timestamp in the history twice — the chart's live edge and the readout's
/// latest win-probability reading: ~600 ms of a ~860 ms freeze per update on a
/// full NFL game's history, in a simulator.
///
/// The page now holds both in `EventHistoryDigest`, built when `history` is set.
/// These tests pin that (a) the digest picks exactly what the per-rebuild code
/// picked, and (b) the page's digest follows its history.
@MainActor
final class AGamePageReadsItsHistoryOncePerPayload8651Tests: XCTestCase {

    private func history(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func at(_ stamp: String) -> Date? { stamp.asDate }

    /// The comparator this replaced, verbatim from `EventDetailView.lastPlayPoint`
    /// before #8651 — the reference the digest must agree with.
    private func formerPick(_ h: EventHistoryResponse) -> WinProbHistoryPoint? {
        let wpHistory = h.winProbHistory?.sorted { $0.key < $1.key }.flatMap(\.value)
        return wpHistory?.max(by: {
            ($0.timestamp.asDate ?? .distantPast) < ($1.timestamp.asDate ?? .distantPast)
        })
    }

    /// Three sources, a tie on the latest moment between two of them (one stamp
    /// fractional, one not), an unparseable stamp, and the latest rows NOT last
    /// in their arrays — every way the two implementations could disagree.
    private static let mixedJSON = """
    {"event_id": 1, "home_team": "H", "away_team": "A",
     "history": [{"timestamp": "2026-10-01T20:00:00Z", "home_probability": 0.5}],
     "win_prob_history": {
       "polymarket": [
         {"timestamp": "2026-10-01T23:40:00.000Z", "home_probability": 0.61},
         {"timestamp": "2026-10-01T23:10:00Z", "home_probability": 0.55}],
       "espn": [
         {"timestamp": "not a time", "home_probability": 0.99},
         {"timestamp": "2026-10-01T23:40:00Z", "home_probability": 0.62},
         {"timestamp": "2026-10-01T22:00:00Z", "home_probability": 0.40}],
       "kalshi": [
         {"timestamp": "2026-10-01T23:39:59Z", "home_probability": 0.70}]
     }}
    """

    func testTheDigestPicksTheReadingThePageUsedToPick() throws {
        let h = try history(Self.mixedJSON)
        let picked = try XCTUnwrap(EventHistoryDigest.latestWinProb(in: h))
        let former = try XCTUnwrap(formerPick(h))
        XCTAssertEqual(picked.timestamp, former.timestamp)
        XCTAssertEqual(picked.homeProbability, former.homeProbability)
        // And what that is, stated: the 23:40 tie goes to `espn`, first by name.
        XCTAssertEqual(picked.homeProbability, 0.62,
                       "a tie on the latest moment must resolve by source name (#8509), not by array order")
    }

    func testNoSeriesAndEmptySeriesPickNothing() throws {
        let absent = try history(#"{"event_id": 1, "home_team": "H", "away_team": "A", "history": []}"#)
        XCTAssertNil(EventHistoryDigest.latestWinProb(in: absent))
        let empty = try history(#"{"event_id": 1, "home_team": "H", "away_team": "A", "history": [], "win_prob_history": {"espn": []}}"#)
        XCTAssertNil(EventHistoryDigest.latestWinProb(in: empty))
        XCTAssertNil(formerPick(empty), "the reference agrees: nothing to pick")
    }

    func testTheDigestEdgeIsTheFreshnessEdge() throws {
        let h = try history(Self.mixedJSON)
        XCTAssertEqual(EventHistoryDigest(h).edge, EventHistoryFreshness.lastReading(in: h))
        XCTAssertEqual(EventHistoryDigest(h).edge, at("2026-10-01T23:40:00Z"))
    }

    // MARK: - The page's digest follows its history

    private nonisolated final class Client: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private var payload: EventHistoryResponse
        private let event: EventDetail
        init(event: EventDetail, history: EventHistoryResponse) {
            self.event = event
            self.payload = history
        }
        func serve(_ next: EventHistoryResponse) { lock.withLock { payload = next } }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            lock.withLock { payload }
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchFreshGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    func testThePagesDigestIsReadFromTheHistoryItHolds() async throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let event = try decoder.decode(EventDetail.self, from: Data("""
        {"id": 1, "home_team": "H", "away_team": "A", "status": "completed",
         "home_score": 27, "away_score": 24}
        """.utf8))
        let first = try history(Self.mixedJSON)
        let client = Client(event: event, history: first)
        let vm = EventDetailViewModel(eventId: 1, client: client)
        XCTAssertNil(vm.historyDigest, "no history, nothing read")

        await vm.load()
        let held = try XCTUnwrap(vm.history)
        XCTAssertEqual(vm.historyDigest?.edge, EventHistoryFreshness.lastReading(in: held))
        XCTAssertEqual(vm.historyDigest?.latestWinProb?.homeProbability, 0.62)

        // A newer payload replaces the digest with it — a stale digest would pin
        // the chart's edge and freeze its adoption (#920).
        let later = try history(Self.mixedJSON
            .replacingOccurrences(of: "2026-10-01T23:39:59Z", with: "2026-10-02T00:05:00Z"))
        client.serve(later)
        await vm.load()
        XCTAssertEqual(vm.historyDigest?.edge, at("2026-10-02T00:05:00Z"))
        XCTAssertEqual(vm.historyDigest?.latestWinProb?.homeProbability, 0.70)

        // A replacement whose latest moment is UNCHANGED but whose reading at
        // that moment is corrected must still replace the readout's reading —
        // the digest follows every payload, not only a moving edge.
        let corrected = try history(Self.mixedJSON
            .replacingOccurrences(of: "2026-10-01T23:39:59Z", with: "2026-10-02T00:05:00Z")
            .replacingOccurrences(of: "0.70", with: "0.66"))
        client.serve(corrected)
        await vm.load()
        XCTAssertEqual(vm.historyDigest?.edge, at("2026-10-02T00:05:00Z"), "same edge")
        XCTAssertEqual(vm.historyDigest?.latestWinProb?.homeProbability, 0.66,
                       "a corrected reading at the same moment must reach the readout")
    }
}
