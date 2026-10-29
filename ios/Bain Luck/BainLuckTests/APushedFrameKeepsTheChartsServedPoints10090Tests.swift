import XCTest
@testable import Bain_Luck

/// #10090 — **a pushed frame extends the chart's served points; it does not
/// rebuild them.**
///
/// Every new live frame misses the chart's points memo (it is keyed on the
/// frames), and on a miss the whole payload was rebuilt: every stamp parsed,
/// every point minted a fresh `id`, the game-state rows parsed and sorted
/// again — on the main thread, before the frame carrying the new price could
/// commit the hero and the chart. Measured on an 8,321-point live payload
/// (Debug simulator): ~20 ms of points per frame inside a ~93 ms hosted chart
/// update. The served points and the game-state lookup are now built once per
/// payload; a frame only extends them.
///
/// The identity test is the RED one: before, no served point survived a frame.
/// The equivalence tests are the control: the memoized path draws exactly what
/// the plain transform draws, frame by frame and across a new payload.
final class APushedFrameKeepsTheChartsServedPoints10090Tests: XCTestCase {

    private static func decode(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// A live blend payload with game state: consensus, two venues, the
    /// aggregate line, ESPN rows, a score sighting and a scoring play.
    private static func blend(edge: String = "2026-10-29T12:10:00Z", edgeValue: Double = 0.6) throws -> EventHistoryResponse {
        try decode("""
        {"event_id":1,"home_team":"Home","away_team":"Away","status":"live",
         "history":[{"timestamp":"2026-10-29T12:00:00Z","home_probability":0.5},
                    {"timestamp":"2026-10-29T12:05:00Z","home_probability":0.52}],
         "win_prob_history":{
           "kalshi":[{"timestamp":"2026-10-29T12:01:00Z","home_probability":0.55},
                     {"timestamp":"2026-10-29T12:06:00Z","home_probability":0.57}],
           "polymarket":[{"timestamp":"2026-10-29T12:02:00Z","home_probability":0.58}]},
         "aggregate_line":[{"timestamp":"2026-10-29T12:00:00Z","home_probability":0.5},
                           {"timestamp":"2026-10-29T12:04:00Z","home_probability":0.54},
                           {"timestamp":"\(edge)","home_probability":\(edgeValue)}],
         "espn_history":[{"timestamp":"2026-10-29T12:00:30Z","home_probability":0.5,
                          "game_clock":"15:00","period":"1","home_score":0,"away_score":0},
                         {"timestamp":"2026-10-29T12:07:10Z","home_probability":0.6,
                          "game_clock":"9:12","period":"1","home_score":7,"away_score":0}],
         "score_history":[{"timestamp":"2026-10-29T12:06:40Z","home_score":7,"away_score":0}],
         "scoring_plays":[{"timestamp":"2026-10-29T12:06:40Z","team":"Home","type":"TD",
                           "home_score":7,"away_score":0,"period":"1","game_clock":"9:30"}]}
        """)
    }

    /// No `win_prob_history`: the sportsbooks-only shape, which no frame extends.
    private static func sportsbooksOnly() throws -> EventHistoryResponse {
        try decode("""
        {"event_id":1,"home_team":"Home","away_team":"Away","status":"live",
         "history":[{"timestamp":"2026-10-29T12:00:00Z","home_probability":0.5},
                    {"timestamp":"2026-10-29T12:05:00Z","home_probability":0.52}]}
        """)
    }

    private static func at(_ minute: Int, _ second: Int = 0) -> Date {
        Date(timeIntervalSince1970: 1_793_275_200 + Double(minute * 60 + second))  // 2026-10-29T12:00:00Z
    }

    /// After the edge, inside the served blend (a held reading), and a venue reading.
    private static let frames: [LiveBlendPoint] = [
        LiveBlendPoint(date: at(10, 20), homeProbability: 0.62, source: "kalshi", sourceProbability: 0.63),
        LiveBlendPoint(date: at(11), homeProbability: 0.64),
        LiveBlendPoint(date: at(12, 5), homeProbability: 0.61, source: "polymarket", sourceProbability: 0.6),
    ]

    /// Everything a point carries except its `id`.
    private func drawn(_ points: [ChartDataPoint]) -> [String] {
        points.map { point in
            Mirror(reflecting: point).children
                .filter { $0.label != "id" }
                .map { "\($0.label ?? "?")=\(String(describing: $0.value))" }
                .joined(separator: " ")
        }
    }

    private func transform(_ history: EventHistoryResponse, _ frames: [LiveBlendPoint]) -> [String] {
        drawn(OddsChartView.enrichWithGameState(
            OddsChartView.chartPoints(from: history, liveFrames: frames), history: history))
    }

    // MARK: - RED before: a frame re-minted every served point

    func testAPushedFrameKeepsEveryServedPointsIdentity() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try Self.blend())
        let served = { (points: [ChartDataPoint]) in
            Set(points.filter { $0.source == "consensus" || $0.source == "polymarket" }.map(\.id))
        }
        let one = vm.enrichedChartPoints(liveFrames: Array(Self.frames.prefix(1)))
        let two = vm.enrichedChartPoints(liveFrames: Array(Self.frames.prefix(2)))
        XCTAssertEqual(served(one).count, 3, "the fixture's served consensus and polymarket points are not all drawn")
        XCTAssertEqual(served(one), served(two),
                       "a pushed frame rebuilt the payload's points — every price paid for the whole history again")
        XCTAssertTrue(two.contains { $0.source == "aggregate" && $0.date == Self.at(11) && $0.probability == 0.64 },
                      "the second frame is not on the chart")
    }

    func testANewPayloadIsNewServedPoints() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try Self.blend())
        let before = vm.chartPoints(liveFrames: Self.frames)
        vm.history = try Self.blend(edge: "2026-10-29T12:11:00Z", edgeValue: 0.66)
        let after = vm.chartPoints(liveFrames: Self.frames)
        XCTAssertTrue(Set(before.map(\.id)).isDisjoint(with: after.map(\.id)),
                      "a new payload was answered from the served memo")
        XCTAssertTrue(after.contains { $0.source == "aggregate" && $0.probability == 0.66 })
    }

    // MARK: - The control: the memo draws exactly what the transform draws

    func testTheMemoDrawsWhatTheTransformDrawsFrameByFrame() throws {
        for history in [try Self.blend(), try Self.sportsbooksOnly()] {
            let vm = OddsChartViewModel(eventId: 1, preloaded: history)
            for count in 0...Self.frames.count {
                let frames = Array(Self.frames.prefix(count))
                XCTAssertEqual(drawn(vm.enrichedChartPoints(liveFrames: frames)), transform(history, frames),
                               "\(count) frame(s) on a \(history.winProbHistory == nil ? "sportsbooks-only" : "blend") payload")
                XCTAssertEqual(drawn(vm.chartPoints(liveFrames: frames)),
                               drawn(OddsChartView.chartPoints(from: history, liveFrames: frames)))
            }
        }
    }

    func testTheMemoDrawsWhatTheTransformDrawsAcrossANewPayload() throws {
        let first = try Self.blend()
        let second = try Self.blend(edge: "2026-10-29T12:11:30Z", edgeValue: 0.66)
        let vm = OddsChartViewModel(eventId: 1, preloaded: first)
        _ = vm.enrichedChartPoints(liveFrames: Self.frames)
        vm.history = second
        XCTAssertEqual(drawn(vm.enrichedChartPoints(liveFrames: Self.frames)), transform(second, Self.frames),
                       "the served points or the game state of the old payload survived a new one")
        vm.history = try Self.sportsbooksOnly()
        XCTAssertEqual(drawn(vm.enrichedChartPoints(liveFrames: Self.frames)),
                       transform(try Self.sportsbooksOnly(), Self.frames))
    }

    func testTheScoringPlayAndCarriedStateReachTheMemoizedPoints() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try Self.blend())
        let points = vm.enrichedChartPoints(liveFrames: Self.frames)
        XCTAssertTrue(points.contains { $0.scoringPlay?.type == "TD" }, "the fixture's touchdown attached to no point")
        XCTAssertTrue(points.contains { $0.homeScore == 7 && $0.period == "1" },
                      "the game-state lookup did not reach the memoized path")
    }
}
