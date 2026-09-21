import XCTest
@testable import Bain_Luck

/// #920 on the phone — the match chart's right edge must reach the same moment
/// the hero does.
///
/// Two independent causes, and a test class for each half, because fixing either
/// one alone still leaves a reader looking at a stale line:
///
///   * **The chart never adopted a fresher payload.** `OddsChartView` keeps its
///     history in a `@StateObject`, and SwiftUI evaluates that autoclosure once
///     per view identity — so the 120 s poll's payload arrived at `init` and was
///     discarded, while `load()`, guarded on `history == nil`, declined to fetch
///     a replacement. The chart was pinned to page-open for as long as the page
///     stayed open. (`EventHistoryFreshness`, `OddsChartViewModel.adopt`.)
///   * **Pushed frames stopped at the hero.** `apply` wrote `currentOdds`; the
///     chart reads history and does not look at `currentOdds` at all.
///     (`LiveBlendBuffer`, `OddsChartView.extendingBlendToLiveEdge`.)
///
/// A note on what proves these. A pre-fix strawman cannot be run for this ship:
/// every assertion below names API that does not exist on master, so the "before"
/// tree does not compile rather than failing honestly. The load-bearing proof is
/// therefore the mutation battery (`tools/native-287-mutations-920.py`), and the
/// sweeps here are pinned by `testTheFixturesAreAboutWhatTheseTestsClaim` so that
/// none of them can pass by measuring nothing.
final class LiveChartEdgeTests920: XCTestCase {

    // MARK: - Fixtures

    private func history(_ json: String) throws -> EventHistoryResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func at(_ iso: String) -> Date {
        guard let d = iso.asDate else {
            XCTFail("fixture timestamp \(iso) does not parse — the test, not the product")
            return .distantPast
        }
        return d
    }

    /// A live multi-source payload whose blend stops at 12:10.
    private static let blendedJSON = """
    {
      "event_id": 1, "home_team": "H", "away_team": "A", "status": "live",
      "history": [
        {"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.40},
        {"timestamp": "2026-09-21T12:05:00Z", "home_probability": 0.44}
      ],
      "win_prob_history": {
        "espn": [{"timestamp": "2026-09-21T12:06:00Z", "home_probability": 0.47}]
      },
      "aggregate_line": [
        {"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.41},
        {"timestamp": "2026-09-21T12:10:00Z", "home_probability": 0.46}
      ]
    }
    """

    /// The same game with NO backend blend — sportsbook consensus only.
    private static let consensusOnlyJSON = """
    {
      "event_id": 1, "home_team": "H", "away_team": "A", "status": "live",
      "history": [
        {"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.40},
        {"timestamp": "2026-09-21T12:05:00Z", "home_probability": 0.44}
      ],
      "win_prob_history": {
        "espn": [
          {"timestamp": "2026-09-21T12:01:00Z", "home_probability": 0.50},
          {"timestamp": "2026-09-21T12:06:00Z", "home_probability": 0.47}
        ]
      }
    }
    """

    private func blended() throws -> EventHistoryResponse { try history(Self.blendedJSON) }

    /// Two pushed frames after the backend's 12:10 edge.
    private func framesAfterEdge() -> [LiveBlendPoint] {
        [
            LiveBlendPoint(date: at("2026-09-21T12:12:00Z"), homeProbability: 0.52),
            LiveBlendPoint(date: at("2026-09-21T12:14:00Z"), homeProbability: 0.58),
        ]
    }

    private func aggregate(_ points: [ChartDataPoint]) -> [(Date, Double)] {
        points.filter { $0.source == "aggregate" }
            .sorted { $0.date < $1.date }
            .map { ($0.date, $0.probability) }
    }

    // MARK: - The sweeps are about something (the M10 lesson)

    /// Every refusal test below asserts that something is ABSENT. Each of them
    /// passes just as happily when the input was empty, when the premise it is
    /// built on ("these frames are newer than the edge") is false, or when the
    /// fixture quietly stopped being the shape it is named for. This pins all
    /// three, so a refusal test can never pass by measuring nothing.
    func testTheFixturesAreAboutWhatTheseTestsClaim() throws {
        let blended = try blended()
        let consensusOnly = try history(Self.consensusOnlyJSON)

        // The blended fixture really carries a backend blend, and its edge is
        // where the refusal tests assume it is.
        XCTAssertEqual(blended.aggregateLine?.count, 2)
        XCTAssertEqual(
            aggregate(OddsChartView.chartPoints(from: blended)).last?.0,
            at("2026-09-21T12:10:00Z")
        )

        // The consensus-only fixture really has NO blend, and is really
        // multi-source — otherwise the fail-closed test below would be proving
        // that the single-source early return works, which is a different claim.
        XCTAssertNil(consensusOnly.aggregateLine)
        XCTAssertFalse(consensusOnly.winProbHistory?.isEmpty ?? true)

        // The frames really are non-empty and really are after the edge.
        let frames = framesAfterEdge()
        XCTAssertEqual(frames.count, 2)
        for frame in frames {
            XCTAssertGreaterThan(frame.date, at("2026-09-21T12:10:00Z"))
        }
    }

    // MARK: - The live edge

    func testAPushedBlendDrawsPastTheBackendsLastPoint() throws {
        let points = OddsChartView.chartPoints(from: try blended(), liveFrames: framesAfterEdge())
        let blend = aggregate(points)

        XCTAssertEqual(blend.count, 4, "2 backend + 2 pushed")
        XCTAssertEqual(blend.last?.0, at("2026-09-21T12:14:00Z"))
        XCTAssertEqual(blend.last?.1 ?? 0, 0.58, accuracy: 0.0001)
    }

    /// The pushed point must land on the BLEND, not beside it. A new source key
    /// would make `defaultVisibleSources` draw two lines and invite the reader to
    /// compare the same number with itself.
    func testThePushedPointExtendsTheBlendRatherThanStartingANewLine() throws {
        let points = OddsChartView.chartPoints(from: try blended(), liveFrames: framesAfterEdge())
        let sources = Set(points.map(\.source))

        XCTAssertEqual(sources, ["consensus", "espn", "aggregate"])
        XCTAssertEqual(OddsChartView.defaultVisibleSources(in: points), ["aggregate"])
        XCTAssertEqual(OddsChartView.primarySource(in: points), "aggregate")
    }

    /// The frame is drawn where the SERVER stamped it, not at the moment it was
    /// handled. Everything either side of it carries a real time.
    func testThePushedPointIsDrawnAtItsStampedTime() throws {
        let stamped = at("2026-09-21T12:12:00Z")
        let points = OddsChartView.chartPoints(
            from: try blended(),
            liveFrames: [LiveBlendPoint(date: stamped, homeProbability: 0.52)]
        )
        XCTAssertEqual(aggregate(points).last?.0, stamped)
    }

    // MARK: - The three refusals

    /// The 120 s poll keeps swallowing the buffer's older half. A frame the
    /// payload already covers must not be drawn twice.
    func testAFrameTheBackendHasAlreadyCaughtUpToIsNotDrawnAgain() throws {
        let stale = [
            LiveBlendPoint(date: at("2026-09-21T12:04:00Z"), homeProbability: 0.43),
            LiveBlendPoint(date: at("2026-09-21T12:09:00Z"), homeProbability: 0.45),
        ]
        let blend = aggregate(OddsChartView.chartPoints(from: try blended(), liveFrames: stale))

        XCTAssertEqual(blend.count, 2, "the two backend points and nothing else")
        XCTAssertEqual(blend.last?.0, at("2026-09-21T12:10:00Z"))
    }

    /// Strictly newer. A frame stamped exactly at the backend's edge is the same
    /// reading arriving by a second road.
    func testAFrameExactlyAtTheBackendsEdgeIsNotDrawnAgain() throws {
        let duplicate = [LiveBlendPoint(date: at("2026-09-21T12:10:00Z"), homeProbability: 0.99)]
        let blend = aggregate(OddsChartView.chartPoints(from: try blended(), liveFrames: duplicate))

        XCTAssertEqual(blend.count, 2)
        XCTAssertEqual(blend.last?.1 ?? 0, 0.46, accuracy: 0.0001, "the backend's value, not the frame's")
    }

    /// THE IMPORTANT ONE. A pushed frame carries the aggregate, so appending it
    /// where the backend published no `aggregate_line` would mint the blend on
    /// the client. That is not merely a labelling problem: `defaultVisibleSources`
    /// returns `["aggregate"]` as soon as one such point exists, so a single
    /// minted point HIDES the consensus line the reader was reading and, being
    /// alone, draws no line in its place. The chart would go blank.
    func testWithNoBackendBlendTheLiveFramesAreRefusedAndTheChartStillDraws() throws {
        let consensusOnly = try history(Self.consensusOnlyJSON)
        let points = OddsChartView.chartPoints(from: consensusOnly, liveFrames: framesAfterEdge())

        XCTAssertTrue(aggregate(points).isEmpty, "no client-minted blend")
        XCTAssertEqual(OddsChartView.primarySource(in: points), "consensus")
        XCTAssertFalse(OddsChartView.defaultVisibleSources(in: points).contains("aggregate"))
        XCTAssertTrue(
            OddsChartView.hasDrawableLine(in: points),
            "the consensus line the reader was already reading must survive"
        )
    }

    /// Settled means settled: the backend's history is the complete journey and a
    /// late frame must not add a twitch past the end of the game.
    /// The statuses are `EventState.isFinished`'s own — `completed` and `closed`.
    /// Spelling a third one here would test a vocabulary the app does not have:
    /// this case was first written against `"final"`, which `isFinished` has
    /// never recognised, and it failed for that reason and not a product one.
    func testAFinishedPayloadIsNotExtended() throws {
        for settled in ["completed", "closed"] {
            let finishedByStatus = try history(
                Self.blendedJSON.replacingOccurrences(
                    of: "\"status\": \"live\"", with: "\"status\": \"\(settled)\""
                )
            )
            XCTAssertTrue(
                EventState.isFinished(finishedByStatus.status),
                "\(settled) must be a status this app calls finished, or this case proves nothing"
            )
            XCTAssertEqual(
                aggregate(OddsChartView.chartPoints(from: finishedByStatus, liveFrames: framesAfterEdge())).count,
                2,
                "\(settled): the backend's history is the complete journey"
            )
        }

        let finishedByCompletion = try history(
            Self.blendedJSON.replacingOccurrences(
                of: "\"status\": \"live\"",
                with: "\"status\": \"live\", \"completed_at\": \"2026-09-21T12:11:00Z\""
            )
        )
        XCTAssertNotNil(finishedByCompletion.completedAt, "the fixture really does carry a completion")
        XCTAssertEqual(
            aggregate(OddsChartView.chartPoints(from: finishedByCompletion, liveFrames: framesAfterEdge())).count,
            2
        )
    }

    /// Every other caller of this transform asks a question about a payload and
    /// knows nothing about a socket. They must be untouched.
    func testWithNoLiveFramesTheTransformIsUnchanged() throws {
        let blended = try blended()
        XCTAssertEqual(
            OddsChartView.chartPoints(from: blended, liveFrames: []).count,
            OddsChartView.chartPoints(from: blended).count
        )
        XCTAssertEqual(aggregate(OddsChartView.chartPoints(from: blended, liveFrames: [])).count, 2)
    }

    // MARK: - The buffer

    func testTheBufferKeepsFramesInTheOrderTheyWereStamped() {
        var buffer: [LiveBlendPoint] = []
        for frame in framesAfterEdge() {
            buffer = LiveBlendBuffer.appending(frame, to: buffer)
        }
        XCTAssertEqual(buffer.map(\.date), [at("2026-09-21T12:12:00Z"), at("2026-09-21T12:14:00Z")])
    }

    /// The stream replays its most recent frame on reconnect.
    func testTheBufferDropsARepeatedOrOutOfOrderStamp() {
        let first = LiveBlendPoint(date: at("2026-09-21T12:12:00Z"), homeProbability: 0.52)
        var buffer = LiveBlendBuffer.appending(first, to: [])

        buffer = LiveBlendBuffer.appending(first, to: buffer)
        XCTAssertEqual(buffer.count, 1, "a replayed frame is not a second point")

        let older = LiveBlendPoint(date: at("2026-09-21T12:11:00Z"), homeProbability: 0.31)
        buffer = LiveBlendBuffer.appending(older, to: buffer)
        XCTAssertEqual(buffer.count, 1, "an out-of-order frame does not bend the line backwards")
        XCTAssertEqual(buffer.first?.homeProbability ?? 0, 0.52, accuracy: 0.0001)
    }

    /// A value that is not a probability costs its own point and nothing else.
    /// A `NaN` reaching a plot does not print a wrong number — it takes the axis
    /// with it and blanks the frame.
    func testTheBufferDropsAValueThatIsNotAProbability() {
        let good = LiveBlendPoint(date: at("2026-09-21T12:12:00Z"), homeProbability: 0.52)
        let buffer = LiveBlendBuffer.appending(good, to: [])

        for bad in [Double.nan, .infinity, -0.2, 1.4] {
            let after = LiveBlendBuffer.appending(
                LiveBlendPoint(date: at("2026-09-21T12:13:00Z"), homeProbability: bad),
                to: buffer
            )
            XCTAssertEqual(after.count, 1, "\(bad) is not a probability")
            XCTAssertEqual(after.last?.homeProbability ?? 0, 0.52, accuracy: 0.0001,
                           "\(bad): the good point before it must survive")
        }

        // …and the boundaries ARE probabilities. A settled-looking 0 or 1 is a
        // real reading on a blowout, and refusing it would silently stop the
        // chart at exactly the moment the game became certain.
        for edge in [0.0, 1.0] {
            let after = LiveBlendBuffer.appending(
                LiveBlendPoint(date: at("2026-09-21T12:13:00Z"), homeProbability: edge),
                to: buffer
            )
            XCTAssertEqual(after.count, 2, "\(edge) is a probability")
        }
    }

    /// Bounded, and bounded at the OLD end: a page left open all afternoon keeps
    /// the frames nearest the live edge, which are the ones on screen.
    func testTheBufferIsBoundedAndKeepsTheNewestFrames() {
        let base = at("2026-09-21T12:00:00Z")
        var buffer: [LiveBlendPoint] = []
        let overflow = LiveBlendBuffer.capacity + 5
        for i in 0..<overflow {
            buffer = LiveBlendBuffer.appending(
                LiveBlendPoint(date: base.addingTimeInterval(Double(i) * 30), homeProbability: 0.5),
                to: buffer
            )
        }
        XCTAssertEqual(buffer.count, LiveBlendBuffer.capacity)
        XCTAssertEqual(buffer.last?.date, base.addingTimeInterval(Double(overflow - 1) * 30))
        XCTAssertEqual(buffer.first?.date, base.addingTimeInterval(Double(overflow - LiveBlendBuffer.capacity) * 30))
    }

    // MARK: - Which payload is fresher

    /// Every series the chart can draw counts, not just the blend — any one of
    /// them advancing moves a line the reader is looking at.
    func testTheLiveEdgeIsTheLatestReadingAcrossEverySeries() throws {
        let latestIsWinProb = try history("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.4}],
          "aggregate_line": [{"timestamp": "2026-09-21T12:05:00Z", "home_probability": 0.41}],
          "win_prob_history": {"espn": [{"timestamp": "2026-09-21T12:20:00Z", "home_probability": 0.6}]}
        }
        """)
        XCTAssertEqual(
            EventHistoryFreshness.lastReading(in: latestIsWinProb),
            at("2026-09-21T12:20:00Z")
        )

        let latestIsEspn = try history("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.4}],
          "espn_history": [{"timestamp": "2026-09-21T12:30:00Z", "home_probability": 0.7}]
        }
        """)
        XCTAssertEqual(EventHistoryFreshness.lastReading(in: latestIsEspn), at("2026-09-21T12:30:00Z"))
    }

    func testAPayloadWithNoReadingsHasNoLiveEdge() throws {
        let empty = try history("""
        {"event_id": 1, "home_team": "H", "away_team": "A", "history": []}
        """)
        XCTAssertNil(EventHistoryFreshness.lastReading(in: empty))
    }

    func testAFresherPayloadIsAdoptedAndAnOlderOneIsRefused() throws {
        let older = try blended()
        let newer = try history(
            Self.blendedJSON.replacingOccurrences(of: "12:10:00Z", with: "12:40:00Z")
        )

        XCTAssertTrue(EventHistoryFreshness.shouldAdopt(newer, over: older))
        XCTAssertFalse(
            EventHistoryFreshness.shouldAdopt(older, over: newer),
            "two fetches race this chart; the slow one must not step it backwards"
        )
        XCTAssertTrue(EventHistoryFreshness.shouldAdopt(older, over: nil))
    }

    /// An errored or empty refresh must not blank a chart that is drawing.
    func testAPayloadWithNoReadingsNeverReplacesOneThatHasThem() throws {
        let empty = try history("""
        {"event_id": 1, "home_team": "H", "away_team": "A", "history": []}
        """)
        XCTAssertFalse(EventHistoryFreshness.shouldAdopt(empty, over: try blended()))
        XCTAssertTrue(EventHistoryFreshness.shouldAdopt(try blended(), over: empty))
    }

    // MARK: - The chart actually takes it

    @MainActor
    func testTheChartAdoptsThePagesFresherPayload() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try blended())
        let newer = try history(Self.blendedJSON.replacingOccurrences(of: "12:10:00Z", with: "12:40:00Z"))

        XCTAssertTrue(vm.adopt(newer))
        XCTAssertEqual(
            EventHistoryFreshness.lastReading(in: try XCTUnwrap(vm.history)),
            at("2026-09-21T12:40:00Z")
        )
        XCTAssertFalse(vm.loading)
    }

    @MainActor
    func testTheChartRefusesAnOlderPayloadAndKeepsTheOneOnScreen() throws {
        let newer = try history(Self.blendedJSON.replacingOccurrences(of: "12:10:00Z", with: "12:40:00Z"))
        let vm = OddsChartViewModel(eventId: 1, preloaded: newer)

        XCTAssertFalse(vm.adopt(try blended()))
        XCTAssertEqual(
            EventHistoryFreshness.lastReading(in: try XCTUnwrap(vm.history)),
            at("2026-09-21T12:40:00Z")
        )
    }
}
