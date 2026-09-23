import XCTest
@testable import Bain_Luck

/// #836 / #837 / #920, the single-source arm on the phone.
///
/// The backend publishes `aggregate_line` only where it blended TWO OR MORE
/// sources. On a Kalshi-only or Polymarket-only live game the one line on the
/// chart is that venue's own series — and nothing pushed ever reached it:
/// `apply` buffered the frame's blend `p` and dropped `source`/`source_value`,
/// and `extendingBlendToLiveEdge` (rightly) refuses to mint a blend where none
/// was served. So the hero ticked on the push while the only line on the plot
/// waited for the 120 s poll. Web repaired the same class in `fd4af82bf0`
/// (`extendServedSourceSeries`, `frontend/lib/liveChartHistory.ts`).
///
/// The rules are web's, verbatim in intent:
///   1. NEVER MINT A SERIES — a source the payload does not already serve is
///      skipped however good its frames.
///   2. STRICTLY NEWER THAN THAT SERIES' OWN SERVED EDGE — ties go to the
///      served point.
///   3. The SOURCE'S value at the frame's STAMPED time — never the blend `p`,
///      never the arrival time.
///   4. Where the backend DID blend, the blend carries the push and the source
///      series stay exactly as served (the multi-source control).
///
/// Driven through the real `LiveStreamController` + `EventDetailViewModel.apply`
/// with a fake socket, then the chart's own pure transform — the path
/// production uses.
@MainActor
final class ASingleSourceLiveChartKeepsItsPushSpeed920Tests: XCTestCase {

    // MARK: - Fakes (the LiveBlendCaptureTests920 rig)

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

    private struct LiveOnlyClient: EventDetailProviding {
        struct Declined: Error {}
        let event: EventDetail
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private let anchor = Date(timeIntervalSince1970: 1_757_000_000)

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    private func withLivePage(
        _ body: @MainActor (EventDetailViewModel, FakeHandle) throws -> Void
    ) async throws {
        let handle = FakeHandle()
        let event = try decode(EventDetail.self, """
        {
          "id": 4242, "home_team": "Red Sox", "away_team": "Yankees",
          "status": "live",
          "current_odds": {"home_probability": 0.40, "away_probability": 0.60}
        }
        """)
        let vm = EventDetailViewModel(
            eventId: 4242,
            client: LiveOnlyClient(event: event),
            makeStreamHandle: { _ in handle },
            now: { [anchor] in anchor.timeIntervalSince1970 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        defer { vm.stopRefresh() }
        await vm.load()
        handle.fire("open")
        XCTAssertTrue(vm.streamDelivering, "every case here is about a DELIVERING stream")
        try body(vm, handle)
    }

    private func frame(p: Double, source: String?, value: Double?, at stamp: String) -> String {
        let src = source.map { "\"\($0)\"" } ?? "null"
        let val = value.map { "\($0)" } ?? "null"
        return """
        {"event_id": 4242, "p": \(p), "source": \(src), "source_value": \(val), \
        "updated_at": "\(stamp)", "status": "live"}
        """
    }

    /// A live game only ONE venue prices: no `aggregate_line` (the backend
    /// blends two or more), consensus absent, the venue's series ending 12:10.
    private func singleSource(_ venue: String) throws -> EventHistoryResponse {
        try decode(EventHistoryResponse.self, """
        {
          "event_id": 4242, "home_team": "Red Sox", "away_team": "Yankees", "status": "live",
          "history": [],
          "win_prob_history": {"\(venue)": [
            {"timestamp": "2026-09-23T12:00:00Z", "home_probability": 0.41},
            {"timestamp": "2026-09-23T12:10:00Z", "home_probability": 0.44}
          ]}
        }
        """)
    }

    private func series(_ source: String, _ points: [ChartDataPoint]) -> [(Date, Double)] {
        points.filter { $0.source == source }.sorted { $0.date < $1.date }.map { ($0.date, $0.probability) }
    }

    // MARK: - The ship: Kalshi and Polymarket, separately

    /// The one line on a Kalshi-only page reaches the pushed reading — at the
    /// SOURCE's value (0.47, 0.53), not the blend `p` (0.46, 0.52), and at the
    /// stamped times.
    func testAKalshiOnlyLiveChartTakesThePushedKalshiReadings() async throws {
        try await assertSingleSourceExtends("kalshi")
    }

    func testAPolymarketOnlyLiveChartTakesThePushedPolymarketReadings() async throws {
        try await assertSingleSourceExtends("polymarket")
    }

    private func assertSingleSourceExtends(_ venue: String,
                                           file: StaticString = #filePath, line: UInt = #line) async throws {
        try await withLivePage { vm, handle in
            handle.fire("probability", frame(p: 0.46, source: venue, value: 0.47, at: "2026-09-23T12:12:00Z"))
            handle.fire("probability", frame(p: 0.52, source: venue, value: 0.53, at: "2026-09-23T12:14:00Z"))

            let history = try singleSource(venue)
            XCTAssertNil(history.aggregateLine, "premise: nothing blended", file: file, line: line)
            let points = OddsChartView.chartPoints(from: history, liveFrames: vm.liveBlend)
            let line_ = series(venue, points)

            XCTAssertEqual(line_.count, 4, "2 served + 2 pushed", file: file, line: line)
            XCTAssertEqual(line_.map(\.0), [
                "2026-09-23T12:00:00Z", "2026-09-23T12:10:00Z",
                "2026-09-23T12:12:00Z", "2026-09-23T12:14:00Z",
            ].compactMap(\.asDate), file: file, line: line)
            XCTAssertEqual(line_.last?.1 ?? .nan, 0.53, accuracy: 0.0001,
                           "the venue's own reading, not the blend p", file: file, line: line)
            XCTAssertEqual(line_.count > 2 ? line_[2].1 : .nan, 0.47, accuracy: 0.0001,
                           file: file, line: line)
            // Still no blend minted, so the source line stays the one drawn.
            XCTAssertTrue(series("aggregate", points).isEmpty, file: file, line: line)
            XCTAssertTrue(OddsChartView.defaultVisibleSources(in: points).contains(venue),
                          file: file, line: line)
        }
    }

    // MARK: - Refusals

    /// Never mint: a Polymarket frame on a page that serves only Kalshi adds
    /// nothing — no Polymarket series, and Kalshi is not fed Polymarket's price.
    func testAFrameForASourceThePageDoesNotServeMintsNothing() async throws {
        try await withLivePage { vm, handle in
            handle.fire("probability", frame(p: 0.52, source: "polymarket", value: 0.53, at: "2026-09-23T12:14:00Z"))

            let points = OddsChartView.chartPoints(from: try singleSource("kalshi"), liveFrames: vm.liveBlend)
            XCTAssertFalse(vm.liveBlend.isEmpty, "premise: the frame WAS captured")
            XCTAssertTrue(series("polymarket", points).isEmpty, "no minted series")
            XCTAssertEqual(series("kalshi", points).count, 2, "kalshi exactly as served")
        }
    }

    /// Only past that series' own served edge; a tie goes to the served point.
    func testAReadingAtOrBeforeTheServedEdgeIsNotDrawnAgain() async throws {
        try await withLivePage { vm, handle in
            handle.fire("probability", frame(p: 0.40, source: "kalshi", value: 0.39, at: "2026-09-23T12:05:00Z"))
            handle.fire("probability", frame(p: 0.45, source: "kalshi", value: 0.99, at: "2026-09-23T12:10:00Z"))
            handle.fire("probability", frame(p: 0.46, source: "kalshi", value: 0.47, at: "2026-09-23T12:12:00Z"))

            let line_ = series("kalshi", OddsChartView.chartPoints(from: try singleSource("kalshi"),
                                                                 liveFrames: vm.liveBlend))
            XCTAssertEqual(vm.liveBlend.count, 3, "premise: all three captured")
            XCTAssertEqual(line_.count, 3, "2 served + only the 12:12 reading")
            XCTAssertEqual(line_.count > 1 ? line_[1].1 : .nan, 0.44, accuracy: 0.0001,
                           "the served 12:10 point wins the tie")
        }
    }

    /// A frame with no usable source reading is still a good BLEND observation
    /// (the hero takes `p`), but it extends no source line — and `p` is never
    /// substituted for the missing source value.
    func testAFrameWithoutAUsableSourceReadingExtendsNoSourceLine() async throws {
        try await withLivePage { vm, handle in
            handle.fire("probability", frame(p: 0.46, source: "kalshi", value: nil, at: "2026-09-23T12:12:00Z"))
            handle.fire("probability", frame(p: 0.47, source: "kalshi", value: 1.7, at: "2026-09-23T12:13:00Z"))
            handle.fire("probability", frame(p: 0.48, source: nil, value: 0.5, at: "2026-09-23T12:14:00Z"))

            XCTAssertEqual(vm.liveBlend.count, 3, "each is still a blend observation")
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability ?? 0, 0.48, accuracy: 0.0001)
            let line_ = series("kalshi", OddsChartView.chartPoints(from: try singleSource("kalshi"),
                                                                 liveFrames: vm.liveBlend))
            XCTAssertEqual(line_.count, 2, "kalshi exactly as served")
        }
    }

    /// Settled means settled — a finished single-source payload is not extended.
    func testAFinishedSingleSourcePayloadIsNotExtended() async throws {
        try await withLivePage { vm, handle in
            handle.fire("probability", frame(p: 0.52, source: "kalshi", value: 0.53, at: "2026-09-23T12:14:00Z"))
            let finished = try decode(EventHistoryResponse.self, """
            {
              "event_id": 4242, "home_team": "Red Sox", "away_team": "Yankees", "status": "completed",
              "history": [],
              "win_prob_history": {"kalshi": [
                {"timestamp": "2026-09-23T12:00:00Z", "home_probability": 0.41},
                {"timestamp": "2026-09-23T12:10:00Z", "home_probability": 0.44}
              ]}
            }
            """)
            XCTAssertEqual(series("kalshi", OddsChartView.chartPoints(from: finished,
                                                                    liveFrames: vm.liveBlend)).count, 2)
        }
    }

    // MARK: - The multi-source control

    /// Where the backend blended, the push goes to the blend — its authority is
    /// unchanged — and every source series stays exactly as served, even though
    /// the frames name a source it serves.
    func testWhereTheBackendBlendedTheSourceSeriesStayAsServed() async throws {
        try await withLivePage { vm, handle in
            handle.fire("probability", frame(p: 0.52, source: "kalshi", value: 0.53, at: "2026-09-23T12:14:00Z"))
            let blended = try decode(EventHistoryResponse.self, """
            {
              "event_id": 4242, "home_team": "Red Sox", "away_team": "Yankees", "status": "live",
              "history": [],
              "win_prob_history": {
                "kalshi": [{"timestamp": "2026-09-23T12:10:00Z", "home_probability": 0.44}],
                "polymarket": [{"timestamp": "2026-09-23T12:10:00Z", "home_probability": 0.46}]
              },
              "aggregate_line": [
                {"timestamp": "2026-09-23T12:00:00Z", "home_probability": 0.43},
                {"timestamp": "2026-09-23T12:10:00Z", "home_probability": 0.45}
              ]
            }
            """)
            let points = OddsChartView.chartPoints(from: blended, liveFrames: vm.liveBlend)
            XCTAssertEqual(series("kalshi", points).count, 1, "kalshi exactly as served")
            XCTAssertEqual(series("polymarket", points).count, 1)
            let blend = series("aggregate", points)
            XCTAssertEqual(blend.count, 3)
            XCTAssertEqual(blend.last?.1 ?? .nan, 0.52, accuracy: 0.0001, "the blend takes p")
        }
    }
}
