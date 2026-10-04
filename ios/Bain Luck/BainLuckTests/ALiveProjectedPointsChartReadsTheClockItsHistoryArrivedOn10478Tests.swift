import XCTest
@testable import Bain_Luck

/// #10239 / #10478 — **a live NFL page's projected final points read the clock
/// the history arrived on, not the clock of each rebuild.**
///
/// `ProjectedFinalPointsMount.input` mounts nothing before or during the game
/// without an `asOf`. The page supplies `EventDetailViewModel.historyArrivedAt`:
/// these tests pin that it is stamped when a history is adopted, holds still
/// between payloads, moves only with the next one, and is what lets a live page
/// with recorded captures mount the module at all.
@MainActor
final class ALiveProjectedPointsChartReadsTheClockItsHistoryArrivedOn10478Tests: XCTestCase {

    private nonisolated final class Client: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let event: EventDetail
        private let history: EventHistoryResponse
        init(event: EventDetail, history: EventHistoryResponse) {
            self.event = event
            self.history = history
        }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { history }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchFreshGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    /// A stream that never delivers, so a live page opens no real socket.
    private final class SilentStream: LiveStreamHandle {
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
        func close() {}
        var isClosed: Bool { false }
        var isConnecting: Bool { false }
    }

    /// The reader's clock, moved by hand.
    private final class Clock: @unchecked Sendable {
        private let lock = NSLock()
        private var value: TimeInterval
        init(_ stamp: String) { value = stamp.asDate!.timeIntervalSince1970 }
        func set(_ stamp: String) { lock.withLock { value = stamp.asDate!.timeIntervalSince1970 } }
        func read() -> TimeInterval { lock.withLock { value } }
    }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    /// A live NFL game as `/history` serves it after #10461: two recorded
    /// captures with their original instants, an observed first quarter, one score.
    private func liveHistory() throws -> EventHistoryResponse {
        try decode(EventHistoryResponse.self, """
        {"event_id":14780549,"home_team":"Home","away_team":"Away","status":"live",
         "completed_at":null,"history":[],
         "bookmaker_history":{"draftkings":[
           {"timestamp":"2026-09-14T00:10:00+00:00","home_probability":0.8,"projected_home_score":27.0,
            "projected_away_score":10.0,"kind":"recorded","observed_at":"2026-09-14T00:10:30.123456+00:00"},
           {"timestamp":"2026-09-14T00:40:00+00:00","home_probability":0.8,"projected_home_score":28.0,
            "projected_away_score":10.0,"kind":"recorded","observed_at":"2026-09-14T00:40:30.123456+00:00"}]},
         "score_history":[{"timestamp":"2026-09-14T00:50:00+00:00","home_score":7,"away_score":0}],
         "period_markers":[{"period":"1st Quarter","source":"espn_state","precision":"first_seen",
                            "not_before":"2026-09-14T00:20:00Z"}]}
        """)
    }

    private func liveEvent() throws -> EventDetail {
        try decode(EventDetail.self, """
        {"id": 14780549, "home_team": "Home", "away_team": "Away", "status": "live",
         "sport": "americanfootball_nfl", "home_score": 7, "away_score": 0}
        """)
    }

    func testTheArrivalClockIsStampedOnAdoptionAndHoldsBetweenPayloads() async throws {
        let clock = Clock("2026-09-14T01:00:00Z")
        let vm = EventDetailViewModel(eventId: 14780549,
                                      client: Client(event: try liveEvent(), history: try liveHistory()),
                                      makeStreamHandle: { _ in SilentStream() },
                                      now: { clock.read() })
        XCTAssertNil(vm.historyArrivedAt, "no history, no clock")

        await vm.load()
        vm.stopRefresh()
        XCTAssertNotNil(vm.history)
        let arrived = try XCTUnwrap(vm.historyArrivedAt)
        XCTAssertGreaterThanOrEqual(arrived, "2026-09-14T01:00:00Z".asDate!)

        // The reader's clock moves; nothing new arrived, so the chart's clock does not.
        clock.set("2026-09-14T01:30:00Z")
        XCTAssertEqual(vm.historyArrivedAt, arrived)

        // The next payload carries the clock it arrived on.
        await vm.load()
        vm.stopRefresh()
        XCTAssertEqual(vm.historyArrivedAt, "2026-09-14T01:30:00Z".asDate)
    }

    func testTheCallSiteClockIsWhatMountsALiveGame() async throws {
        let clock = Clock("2026-09-14T01:00:00Z")
        let event = try liveEvent()
        let vm = EventDetailViewModel(eventId: 14780549,
                                      client: Client(event: event, history: try liveHistory()),
                                      makeStreamHandle: { _ in SilentStream() },
                                      now: { clock.read() })
        await vm.load()
        vm.stopRefresh()

        // Exactly the page's call (EventDetailView), with and without the clock.
        let withClock = ProjectedFinalPointsMount.input(
            sportKey: event.sport, eventStatus: event.status, history: vm.history,
            finalHome: event.homeScore, finalAway: event.awayScore, asOf: vm.historyArrivedAt)
        let input = try XCTUnwrap(withClock, "a live game with recorded captures mounts once the page supplies its clock")
        XCTAssertEqual(input.asOf, vm.historyArrivedAt)
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(input))
        XCTAssertEqual(series.phase, .during)
        XCTAssertEqual(series.latest.home, 28)
        XCTAssertEqual(series.latestActual?.home, 7)

        XCTAssertNil(ProjectedFinalPointsMount.input(
            sportKey: event.sport, eventStatus: event.status, history: vm.history,
            finalHome: event.homeScore, finalAway: event.awayScore),
            "without the clock a live page still mounts nothing")
    }
}
