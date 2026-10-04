import Combine
import SwiftUI
import XCTest
import Vision
@testable import Bain_Luck

/// #9436 — on a live chart the current number sits on a dot at the end of the
/// line, and when a real update is accepted the dot, that number and the hero
/// move together.
///
/// Root's corrections are each one arm here: the dot is the DRAWN end of the
/// line (the plot stops one vertex short, the overlay draws the rest), the
/// label is the hero's own string, a glide happens only on a genuine append
/// or a same-predecessor pin replacement, and the label stays inside the plot
/// at both edges and at 0/100.
///
/// Review delta on b4df59b81a: (1) a reread's pin replacement glides, (2) the
/// number goes only on the series proven to carry it — venue-only pages
/// included — and (3) a background scene hides the dot and number and
/// cancels any glide or slide in flight.
@MainActor
final class TheLiveChartEndCarriesTheHeroNumber9436Tests: XCTestCase {

    // MARK: - Fixtures

    private func date(_ minute: Int) -> Date {
        Date(timeIntervalSinceReferenceDate: 780_000_000 + Double(minute) * 60)
    }

    private func point(_ minute: Int, _ p: Double, _ source: String = "aggregate") -> ChartDataPoint {
        ChartDataPoint(date: date(minute), probability: p, source: source)
    }

    private func vertex(_ minute: Int, _ p: Double) -> LiveEdgeVertex {
        LiveEdgeVertex(date: date(minute), probability: p)
    }

    private func event(p: Double, status: String = "live", away: Double? = nil,
                       served: (Int, Int)? = nil, sport: String = "baseball_mlb",
                       heroSource: String? = "blend") throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let rendered = served.map { #","home_rendered_percent":\#($0.0),"away_rendered_percent":\#($0.1)"# } ?? ""
        let hero = heroSource.map { #""hero_probability_source":"\#($0)","# } ?? ""
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Red Sox","away_team":"Cubs","sport":"\(sport)","status":"\(status)",
         "home_score":2,"away_score":1,\(hero)
         "current_odds":{"home_probability":\(p),"away_probability":\(away ?? 1 - p)\(rendered)}}
        """.utf8))
    }

    // MARK: - Provenance: the label is the hero's own string

    func testTheEdgeLabelIsTheHeroPrintedHomeString() throws {
        for (p, served) in [(0.6, (40, 60)), (0.445, nil), (0.555, nil), (0.004, nil), (0.996, nil)]
            as [(Double, (Int, Int)?)] {
            let event = try event(p: p, served: served)
            let reading = try XCTUnwrap(LiveEdgeReading.current(in: event), "p=\(p)")
            XCTAssertEqual(reading.homeLabel, LivePriceActivity.displayedLabels(in: event).home, "p=\(p)")
            XCTAssertEqual(reading.homeProbability, p)
            XCTAssertEqual(reading.source, "blend")
        }
    }

    /// The reading carries the hero's provenance, and only a `"blend"` hero
    /// may label a line — an `opening` hero equal to the blend tip, or an
    /// older payload with no source at all, draws no number.
    func testOnlyABlendHeroLabelsALine() throws {
        let points = [point(0, 0.5), point(1, 0.6)]
        for source in ["opening", nil] as [String?] {
            let reading = try XCTUnwrap(LiveEdgeReading.current(in: try event(p: 0.6, heroSource: source)))
            XCTAssertEqual(reading.source, source)
            XCTAssertNil(LiveChartEdgeMarkerPlan.edgeVertex(in: points, visible: ["aggregate"],
                                                            reading: reading, latestFrame: nil),
                         "source \(source ?? "nil")")
        }
        let blend = try XCTUnwrap(LiveEdgeReading.current(in: try event(p: 0.6)))
        XCTAssertEqual(LiveChartEdgeMarkerPlan.edgeVertex(in: points, visible: ["aggregate"],
                                                          reading: blend, latestFrame: nil)?.id, points[1].id)
    }

    /// The .445 complement (#2085): 0.445 must not print 45 beside a hero
    /// whose pair rounds as one decision. Both read the same function, so both
    /// print the same number — pinned so a second rounding path cannot drift.
    func testTheComplementPairRoundsOnceForHeroAndEdge() throws {
        let event = try event(p: 0.445)
        let pair = LivePriceActivity.displayedLabels(in: event)
        XCTAssertEqual(LiveEdgeReading.current(in: event)?.homeLabel, pair.home)
        XCTAssertEqual(pair.home.flatMap { Int($0.dropLast()) }.map { $0 + Int(pair.away!.dropLast())! }, 100)
    }

    func testCurrentQuoteReadingFollowsPriceEligibilityNotSportsLive() throws {
        for status in ["scheduled", "live", "suspended"] {
            XCTAssertEqual(LiveEdgeReading.current(in: try event(p: 0.6, status: status))?.homeProbability, 0.6)
        }
        for status in ["final", "completed", "closed", "postponed"] {
            XCTAssertNil(LiveEdgeReading.current(in: try event(p: 0.6, status: status)))
        }
    }

    func testTheEdgeIsCurrentOnlyWhenTheVertexIsTheHeroValue() {
        let reading = LiveEdgeReading(homeProbability: 0.59, homeLabel: "59%")
        XCTAssertTrue(LiveChartEdgeMarkerPlan.isCurrent(tipProbability: 0.59, reading: reading))
        // A history point the push has not reached is not labelled current,
        // even where it would round to the same printed number.
        XCTAssertFalse(LiveChartEdgeMarkerPlan.isCurrent(tipProbability: 0.588, reading: reading))
        XCTAssertFalse(LiveChartEdgeMarkerPlan.isCurrent(tipProbability: 0.60, reading: reading))
    }

    // MARK: - Finding 2: which series carries the number

    private let hero62 = LiveEdgeReading(homeProbability: 0.62, homeLabel: "62%")

    /// A blend line on the chart is the only candidate: a venue tip that
    /// happens to equal the hero is not promoted to the blend.
    func testWithABlendLineOnlyTheBlendEndCanBeLabelled() {
        let points = [point(0, 0.55), point(1, 0.60), point(0, 0.58, "kalshi"), point(1, 0.62, "kalshi")]
        XCTAssertNil(LiveChartEdgeMarkerPlan.edgeVertex(in: points, visible: ["aggregate"],
                                                        reading: hero62, latestFrame: nil))
        let matching = points + [point(2, 0.62)]
        XCTAssertEqual(LiveChartEdgeMarkerPlan.edgeVertex(in: matching, visible: ["aggregate"],
                                                          reading: hero62, latestFrame: nil)?.id, matching.last?.id)
    }

    /// The real venue-only construction: no `aggregate_line`, one venue series,
    /// and the pushed frame `extendingServedSourceSeries` carries onto it.
    private func venueOnlyHistory() throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":15302923,"home_team":"Red Sox","away_team":"Yankees","status":"live","history":[],
         "win_prob_history":{"kalshi":[{"timestamp":"2026-09-21T12:00:00Z","home_probability":0.42},
                                       {"timestamp":"2026-09-21T12:05:00Z","home_probability":0.50},
                                       {"timestamp":"2026-09-21T12:10:00Z","home_probability":0.55}]}}
        """.utf8))
    }

    private func kalshiFrame(_ blend: Double, venue: Double, source: String = "kalshi") throws -> LiveBlendPoint {
        LiveBlendPoint(date: try XCTUnwrap("2026-09-21T12:12:00Z".asDate), homeProbability: blend,
                       source: source, sourceProbability: venue)
    }

    func testAVenueOnlyChartLabelsTheVenueLineTheAdoptedFrameExtended() throws {
        let frame = try kalshiFrame(0.62, venue: 0.62)
        let points = OddsChartView.chartPoints(from: try venueOnlyHistory(), liveFrames: [frame])
        XCTAssertFalse(points.contains { $0.source == "aggregate" }, "no blend is minted")
        let tip = try XCTUnwrap(LiveChartEdgeMarkerPlan.edgeVertex(
            in: points, visible: OddsChartView.defaultVisibleSources(in: points),
            reading: hero62, latestFrame: frame))
        XCTAssertEqual(tip.source, "kalshi")
        XCTAssertEqual(tip.date, frame.date)
        XCTAssertEqual(tip.probability, 0.62)
        // The old rule's blind spot, pinned: it looked only at aggregate/consensus.
        XCTAssertNil(OddsChartView.latestPrimaryPoint(in: points))
    }

    func testAVenueOnlyChartFailsClosedWithoutProvenance() throws {
        let history = try venueOnlyHistory()
        func vertex(frame: LiveBlendPoint?, reading: LiveEdgeReading) -> ChartDataPoint? {
            let points = OddsChartView.chartPoints(from: history, liveFrames: frame.map { [$0] } ?? [])
            return LiveChartEdgeMarkerPlan.edgeVertex(
                in: points, visible: OddsChartView.defaultVisibleSources(in: points),
                reading: reading, latestFrame: frame)
        }
        XCTAssertNil(vertex(frame: nil, reading: LiveEdgeReading(homeProbability: 0.55, homeLabel: "55%")),
                     "a REST-only hero equal to the venue tip: nothing ties the two")
        XCTAssertNil(vertex(frame: try kalshiFrame(0.62, venue: 0.60), reading: hero62),
                     "the frame's blend is not its venue reading")
        XCTAssertNil(vertex(frame: try kalshiFrame(0.62, venue: 0.62, source: "polymarket"), reading: hero62),
                     "a venue with no drawn series is never minted, so it has no tip")
        XCTAssertNil(vertex(frame: try kalshiFrame(0.62, venue: 0.62),
                            reading: LiveEdgeReading(homeProbability: 0.64, homeLabel: "64%")),
                     "the hero has moved past the frame")
    }

    /// Sportsbooks-only: nothing on the payload says the hero is the consensus.
    func testTheConsensusIsNeverLabelled() {
        let points = [point(0, 0.55, "consensus"), point(1, 0.62, "consensus")]
        XCTAssertNil(LiveChartEdgeMarkerPlan.edgeVertex(in: points, visible: ["consensus"],
                                                        reading: hero62, latestFrame: nil))
    }

    // MARK: - The split: the plot stops one vertex short, nothing is lost

    func testTheSplitMovesOnlyTheNewestVertexToTheOverlay() throws {
        let run = [point(0, 0.6), point(1, 0.61), point(2, 0.59)]
        let split = try XCTUnwrap(LiveChartEdgeMarkerPlan.split(segments: [run], newest: run[2], source: "aggregate"))
        XCTAssertEqual(split.segments.map { $0.map(\.probability) }, [[0.6, 0.61]])
        XCTAssertEqual(split.continuedRun, 0)
        XCTAssertEqual(split.tail, LiveEdgeTail(from: vertex(1, 0.61), to: vertex(2, 0.59)))
    }

    /// The remaining lone vertex of a two-point run is where the overlay's
    /// segment starts, not an isolated observation — it must not get a dot.
    func testALoneRemainderIsMarkedAsContinued() throws {
        let hole = [point(0, 0.5)]
        let run = [point(30, 0.6), point(31, 0.62)]
        let split = try XCTUnwrap(LiveChartEdgeMarkerPlan.split(segments: [hole, run], newest: run[1], source: "aggregate"))
        XCTAssertEqual(split.segments.map(\.count), [1, 1])
        XCTAssertEqual(split.continuedRun, 1, "run 1's lone vertex continues into the overlay")
    }

    /// #7878 — a newest vertex that opens its own run is joined to nothing, so
    /// the overlay draws no segment for it and nothing may glide into it.
    func testANewestVertexAfterAHoleHasNoSegment() throws {
        let before = [point(0, 0.5), point(1, 0.52)]
        let after = [point(40, 0.7)]
        let split = try XCTUnwrap(LiveChartEdgeMarkerPlan.split(segments: [before, after], newest: after[0], source: "aggregate"))
        XCTAssertNil(split.tail.from)
        XCTAssertEqual(split.segments.map(\.count), [2])
        XCTAssertEqual(split.continuedRun, -1)
    }

    func testNoSplitWhenTheNewestVertexIsNotTheLastDrawn() {
        let run = [point(0, 0.6), point(1, 0.61)]
        XCTAssertNil(LiveChartEdgeMarkerPlan.split(segments: [run], newest: point(1, 0.61), source: "aggregate"),
                     "a different point (not the drawn one) must not trim the plot")
        XCTAssertNil(LiveChartEdgeMarkerPlan.split(segments: [], newest: run[0], source: "aggregate"))
    }

    // MARK: - Glide: only a genuine append, never invented motion

    func testAGenuineAppendGlides() {
        let old = LiveEdgeTail(from: vertex(0, 0.6), to: vertex(1, 0.61))
        let new = LiveEdgeTail(from: vertex(1, 0.61), to: vertex(2, 0.59))
        XCTAssertTrue(LiveChartEdgeMarkerPlan.glides(from: old, to: new, reduceMotion: false, sceneActive: true))
    }

    func testEverythingElseSnaps() {
        let old = LiveEdgeTail(from: vertex(0, 0.6), to: vertex(1, 0.61))
        let append = LiveEdgeTail(from: vertex(1, 0.61), to: vertex(2, 0.59))
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(from: old, to: append, reduceMotion: true, sceneActive: true),
                       "Reduce Motion keeps the dot and number, drops the slide")
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(from: old, to: append, reduceMotion: false, sceneActive: false),
                       "a background scene does not animate what nobody sees")
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(
            from: old, to: LiveEdgeTail(from: nil, to: vertex(40, 0.7)), reduceMotion: false, sceneActive: true),
                       "a segment break has no line to glide along")
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(
            from: old, to: LiveEdgeTail(from: vertex(1, 0.64), to: vertex(3, 0.66)), reduceMotion: false, sceneActive: true),
                       "a replacement on a different predecessor is neither an append nor a pin replacement")
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(from: old, to: old, reduceMotion: false, sceneActive: true),
                       "an unchanged receipt moves nothing")
    }

    /// Finding 1 — the normal folded path. `rereadPricePair` adopts a history
    /// whose last observation is unchanged and whose response-time pin is new
    /// (`_pin_blend_edge`); the old pin was never persisted, so the new tail
    /// does NOT start at the old tip. It shares the old predecessor, and that
    /// is the replacement that glides.
    func testAPinReplacementOnTheSamePredecessorGlides() {
        let bucket = vertex(10, 0.60)
        let old = LiveEdgeTail(from: bucket, to: vertex(12, 0.61))
        let new = LiveEdgeTail(from: bucket, to: vertex(14, 0.59))
        XCTAssertTrue(LiveChartEdgeMarkerPlan.replacesPin(old: old, new: new))
        XCTAssertTrue(LiveChartEdgeMarkerPlan.glides(from: old, to: new, reduceMotion: false, sceneActive: true))
        // Same pin re-stamped at a new response time: the edge moves right.
        XCTAssertTrue(LiveChartEdgeMarkerPlan.glides(
            from: old, to: LiveEdgeTail(from: bucket, to: vertex(14, 0.61)), reduceMotion: false, sceneActive: true))
    }

    func testAPinReplacementStillSnapsWhereItMust() {
        let bucket = vertex(10, 0.60)
        let old = LiveEdgeTail(from: bucket, to: vertex(12, 0.61))
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(
            from: old, to: LiveEdgeTail(from: bucket, to: vertex(11, 0.59)), reduceMotion: false, sceneActive: true),
                       "a pin earlier than the one on screen is not a newer reading of the edge")
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(
            from: old, to: LiveEdgeTail(from: vertex(13, 0.62), to: vertex(14, 0.59)), reduceMotion: false, sceneActive: true),
                       "a new last observation: the plot itself changed shape, the overlay snaps with it")
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(
            from: LiveEdgeTail(from: nil, to: vertex(12, 0.61)), to: LiveEdgeTail(from: nil, to: vertex(14, 0.59)),
            reduceMotion: false, sceneActive: true),
                       "a lone vertex has no segment; nothing is bridged")
        let new = LiveEdgeTail(from: bucket, to: vertex(14, 0.59))
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(from: old, to: new, reduceMotion: true, sceneActive: true))
        XCTAssertFalse(LiveChartEdgeMarkerPlan.glides(from: old, to: new, reduceMotion: false, sceneActive: false))
    }

    /// The replaced pin is held (drawn off the same predecessor) until the
    /// glide starts; held under any other predecessor it is off the line.
    func testTheReplacedPinIsHeldOnlyOffTheSamePredecessor() {
        let bucket = vertex(10, 0.60)
        let tail = LiveEdgeTail(from: bucket, to: vertex(14, 0.59))
        XCTAssertEqual(LiveChartEdgeMarkerPlan.drawnTip(shown: vertex(12, 0.61), shownFrom: bucket, tail: tail),
                       vertex(12, 0.61))
        XCTAssertEqual(LiveChartEdgeMarkerPlan.drawnTip(shown: vertex(12, 0.61), shownFrom: vertex(9, 0.5), tail: tail),
                       vertex(14, 0.59))
        XCTAssertEqual(LiveChartEdgeMarkerPlan.drawnTip(shown: vertex(12, 0.61), shownFrom: nil, tail: tail),
                       vertex(14, 0.59))
    }

    /// The tip drawn in any frame lies on the line: the held tip while it is
    /// one of the new segment's two ends, otherwise the new end.
    func testTheDrawnTipIsNeverOffTheLine() {
        let tail = LiveEdgeTail(from: vertex(1, 0.61), to: vertex(2, 0.59))
        XCTAssertEqual(LiveChartEdgeMarkerPlan.drawnTip(shown: vertex(1, 0.61), tail: tail), vertex(1, 0.61))
        XCTAssertEqual(LiveChartEdgeMarkerPlan.drawnTip(shown: vertex(2, 0.59), tail: tail), vertex(2, 0.59))
        XCTAssertEqual(LiveChartEdgeMarkerPlan.drawnTip(shown: vertex(0, 0.4), tail: tail), vertex(2, 0.59))
        XCTAssertEqual(LiveChartEdgeMarkerPlan.drawnTip(shown: nil, tail: tail), vertex(2, 0.59))
    }

    /// A fall slides down, a rise (or an unknown direction) slides up — both
    /// strings, the same way.
    func testTheValueSlidesTheWayThePriceMoved() {
        XCTAssertEqual(LiveChartEdgeMarkerPlan.shiftDirection(rising: false), 1)
        XCTAssertEqual(LiveChartEdgeMarkerPlan.shiftDirection(rising: true), -1)
        XCTAssertEqual(LiveChartEdgeMarkerPlan.shiftDirection(rising: nil), -1)
    }

    // MARK: - Placement: inside the plot at both edges and at 0/100

    func testTheLabelSitsBesideTheDotWhereThereIsRoom() {
        let c = LiveChartEdgeMarkerPlan.labelCenter(tip: CGPoint(x: 100, y: 120),
                                                    label: CGSize(width: 60, height: 20),
                                                    plot: CGSize(width: 300, height: 240))
        XCTAssertEqual(c.y, 120)
        XCTAssertGreaterThan(c.x - 30, 100, "entirely right of the dot")
    }

    func testAtTheRightEdgeItStacksAwayFromTheNearestEdge() {
        let plot = CGSize(width: 300, height: 240)
        let label = CGSize(width: 60, height: 20)
        let low = LiveChartEdgeMarkerPlan.labelCenter(tip: CGPoint(x: 300, y: 200), label: label, plot: plot)
        XCTAssertLessThan(low.y + 10, 200, "a dot in the lower half gets its label above")
        let high = LiveChartEdgeMarkerPlan.labelCenter(tip: CGPoint(x: 300, y: 40), label: label, plot: plot)
        XCTAssertGreaterThan(high.y - 10, 40, "a dot in the upper half gets its label below")
    }

    /// The newest move is what the reader is watching: when the preferred
    /// side would cover the last segment and the other would not, the label
    /// takes the other side.
    func testTheLabelNeverHidesTheLastSegmentWhenItNeedNot() {
        let plot = CGSize(width: 293, height: 214)
        let label = CGSize(width: 64, height: 20)
        let tip = CGPoint(x: 293, y: 60), from = CGPoint(x: 263, y: 140)
        let c = LiveChartEdgeMarkerPlan.labelCenter(tip: tip, from: from, label: label, plot: plot)
        XCTAssertFalse(LiveChartEdgeMarkerPlan.covers(c, label: label, from: from, to: tip))
        XCTAssertLessThan(c.y, tip.y, "a steep rise into an upper-half dot puts the label above")
        // Control: with no segment to protect the upper-half rule stands.
        XCTAssertGreaterThan(LiveChartEdgeMarkerPlan.labelCenter(tip: tip, label: label, plot: plot).y, tip.y)
    }

    func testTheLabelNeverLeavesThePlot() {
        let plot = CGSize(width: 293, height: 214)
        // `.large` and the capped `.xxLarge` label.
        for label in [CGSize(width: 64, height: 20), CGSize(width: 96, height: 28)] {
            for x in [0, 4, 146, 250, 289, 293] as [CGFloat] {
                for y in [0, 2, 107, 212, 214] as [CGFloat] {
                    let c = LiveChartEdgeMarkerPlan.labelCenter(tip: CGPoint(x: x, y: y), label: label, plot: plot)
                    let frame = CGRect(x: c.x - label.width / 2, y: c.y - label.height / 2,
                                       width: label.width, height: label.height)
                    XCTAssertTrue(CGRect(origin: .zero, size: plot).contains(frame),
                                  "tip (\(x),\(y)) label \(label) → \(frame)")
                }
            }
        }
    }

    // MARK: - Rendered: the dot and the hero's number are on the chart

    private static let commence = "2026-09-21T11:55:00Z"

    private func history() throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":15302923,"home_team":"Red Sox","away_team":"Yankees","status":"live","history":[],
         "win_prob_history":{"kalshi":[{"timestamp":"2026-09-21T12:00:00Z","home_probability":0.42},
                                       {"timestamp":"2026-09-21T12:10:00Z","home_probability":0.47}],
                             "polymarket":[{"timestamp":"2026-09-21T12:00:00Z","home_probability":0.40},
                                           {"timestamp":"2026-09-21T12:10:00Z","home_probability":0.45}]},
         "aggregate_line":[{"timestamp":"2026-09-21T12:00:00Z","home_probability":0.41},
                           {"timestamp":"2026-09-21T12:05:00Z","home_probability":0.43},
                           {"timestamp":"2026-09-21T12:10:00Z","home_probability":0.46}]}
        """.utf8))
    }

    private func frames(_ ps: [Double]) -> [LiveBlendPoint] {
        ps.enumerated().compactMap { i, p in
            "2026-09-21T12:1\(i + 1):00Z".asDate.map { LiveBlendPoint(date: $0, homeProbability: p) }
        }
    }

    private func render(_ name: String, frames: [LiveBlendPoint], liveEdge: LiveEdgeReading?,
                        selection: OddsChartSelection? = nil, history: EventHistoryResponse? = nil,
                        scenePhase: ScenePhase = .active) throws -> (UIImage, String) {
        let view = OddsChartView(
            eventId: 15302923, commenceTime: Self.commence, status: "live",
            homeTeamName: "Red Sox", awayTeamName: "Yankees",
            homeTeamAbbrev: "BOS", awayTeamAbbrev: "NYY",
            refreshStreaming: true, liveUpdateStatus: .live, liveEdge: liveEdge,
            preloadedHistory: try history ?? self.history(), liveFrames: frames, selection: selection)
            .frame(width: 390)
            .environment(\.colorScheme, .light)
            .environment(\.scenePhase, scenePhase)
        let renderer = rendererForMeasurement(view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, name)
        let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["BL_ARTIFACTS"]
            ?? FileManager.default.temporaryDirectory.path)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("9436-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("#9436 render artifact [\(name)]: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " | ")
        return (image, text)
    }

    func testTheLiveEdgeDrawsTheHeroNumberBesideTheDot() throws {
        let (_, text) = try render("live-edge", frames: frames([0.49, 0.55, 0.78]),
                                   liveEdge: LiveEdgeReading(homeProbability: 0.78, homeLabel: "78%"))
        XCTAssertTrue(text.contains("BOS 78%"), text)
    }

    /// Control: the same chart with the hero reading something the line has
    /// not reached draws no current number at all.
    func testAMismatchedEdgeDrawsNoNumber() throws {
        let (_, text) = try render("mismatch", frames: frames([0.49, 0.55, 0.78]),
                                   liveEdge: LiveEdgeReading(homeProbability: 0.80, homeLabel: "80%"))
        XCTAssertFalse(text.contains("78%"), text)
        XCTAssertFalse(text.contains("80%"), text)
    }

    func testAScrubHidesTheNumber() throws {
        let selection = OddsChartSelection()
        selection.select("2026-09-21T12:05:00Z".asDate)
        let (_, text) = try render("scrubbing", frames: frames([0.49, 0.55, 0.78]),
                                   liveEdge: LiveEdgeReading(homeProbability: 0.78, homeLabel: "78%"),
                                   selection: selection)
        XCTAssertFalse(text.contains("BOS 78%"), text)
    }

    func testAVenueOnlyChartDrawsTheHeroNumberOnTheVenueLine() throws {
        let (_, text) = try render("venue-only", frames: [try kalshiFrame(0.62, venue: 0.62)],
                                   liveEdge: hero62, history: try venueOnlyHistory())
        XCTAssertTrue(text.contains("BOS 62%"), text)
    }

    /// Finding 3 — a scene that is not active keeps the line and hides the
    /// dot and number.
    func testABackgroundSceneHidesTheNumber() throws {
        let (image, text) = try render("background", frames: frames([0.49, 0.55, 0.78]),
                                       liveEdge: LiveEdgeReading(homeProbability: 0.78, homeLabel: "78%"),
                                       scenePhase: .background)
        XCTAssertFalse(text.contains("78%"), text)
        XCTAssertNotNil(tipColumn(image), "the line itself is still drawn")
    }

    // MARK: - Hosted: the dot glides along the drawn segment and settles

    private final class Feed: ObservableObject {
        @Published var frames: [LiveBlendPoint]
        @Published var edge: LiveEdgeReading
        @Published var history: EventHistoryResponse?
        @Published var phase: ScenePhase = .active
        init(frames: [LiveBlendPoint], edge: LiveEdgeReading, history: EventHistoryResponse? = nil) {
            self.frames = frames; self.edge = edge; self.history = history
        }
    }

    private struct FedChart: View {
        @ObservedObject var feed: Feed
        let history: EventHistoryResponse
        var body: some View {
            OddsChartView(
                eventId: 15302923, commenceTime: "2026-09-21T11:55:00Z", status: "live",
                homeTeamName: "Red Sox", awayTeamName: "Yankees",
                homeTeamAbbrev: "BOS", awayTeamAbbrev: "NYY",
                refreshStreaming: true, liveUpdateStatus: .live, liveEdge: feed.edge,
                preloadedHistory: feed.history ?? history, liveFrames: feed.frames)
            .frame(width: 390)
            .environment(\.chartScrubSurfaces, false)
            .environment(\.colorScheme, .light)
            // A bare hosting controller is not an active scene, and the glide
            // correctly refuses to animate a background one.
            .environment(\.scenePhase, feed.phase)
        }
    }

    @MainActor
    private final class Hosted {
        let host: UIViewController
        let window: UIWindow
        let previousKeyWindow: UIWindow?
        init<V: View>(_ view: V) throws {
            let scene = try XCTUnwrap(UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }
                .first { $0.activationState == .foregroundActive },
                "Motion capture requires a foreground-active window scene")
            previousKeyWindow = scene.windows.first { $0.isKeyWindow }
            host = hostForMeasurement(view)
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 360)
            window = UIWindow(windowScene: scene)
            window.frame = host.view.frame
            window.rootViewController = host
            window.makeKeyAndVisible()
        }
        func close() {
            window.isHidden = true
            previousKeyWindow?.makeKey()
        }
        func shot(afterScreenUpdates: Bool = true, scale: CGFloat? = nil) -> UIImage {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            // Only motion sampling opts into 1x. Cancellation equalities retain
            // screen resolution so small unfinished motion remains detectable.
            let format = UIGraphicsImageRendererFormat()
            if let scale { format.scale = scale }
            var captured = false
            let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: format).image { _ in
                captured = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: afterScreenUpdates)
            }
            XCTAssertTrue(captured, "The motion probe failed to capture its view hierarchy")
            return image
        }
    }

    /// Sample the tip column for `seconds` after a change.
    private func sampleTip(_ hosted: Hosted, seconds: Double, measuresMarker: Bool = true) async throws -> (columns: [Int], stamps: [Double], starts: [Double]) {
        var captures: [(image: UIImage, acquiredAt: Double, duration: Double)] = []
        let start = CACurrentMediaTime()
        while CACurrentMediaTime() - start < seconds {
            try await Task.sleep(for: .milliseconds(30))
            let captureStart = CACurrentMediaTime()
            // Read the displayed frame; waiting for the next update can consume
            // most of this short animation before the observer gets another turn.
            let image = hosted.shot(afterScreenUpdates: false, scale: 1)
            let acquiredAt = CACurrentMediaTime()
            captures.append((image, acquiredAt - start, acquiredAt - captureStart))
        }
        // Scanning pixels must not delay the next animation observation. Timestamp
        // after acquisition, never before it: capture cost is still paid honestly.
        var columns: [Int] = [], stamps: [Double] = [], starts: [Double] = []
        for (index, capture) in captures.enumerated() {
            // Retain the real frame so an apparent reversal can be distinguished
            // from label pixels or changing chart axes, without relaxing the gate.
            recordMotionFrame(capture.image, name: "motion-frame-\(index)-at-\(capture.acquiredAt)")
            let measured = measuresMarker ? markerColumn(capture.image) : tipColumn(capture.image)
            let x = try XCTUnwrap(measured, "Sample must contain one unambiguous rendered endpoint")
            columns.append(x)
            stamps.append(capture.acquiredAt)
            starts.append(capture.acquiredAt - capture.duration)
        }
        print("#9436 sampling acquisitions: \(captures.map(\.acquiredAt)); capture durations: \(captures.map(\.duration))")
        return (columns, stamps, starts)
    }

    /// Every frame whose capture began after the glide window plus a frame of
    /// slack shows the settled end. When no capture began that late, the
    /// independent final shot (taken after sampling, and already asserted equal
    /// to the last sample) is the only reading past the window.
    private func assertSettledByTheGlideWindow(_ columns: [Int], starts: [Double], stamps: [Double],
                                               settled: Int, file: StaticString = #filePath, line: UInt = #line) {
        let window = LiveChartEdgeMarkerPlan.glideDuration + 0.25
        let late = zip(columns, starts).filter { $0.1 >= window }
        let moving = late.filter { $0.0 != settled }
        XCTAssertTrue(moving.isEmpty, "still short of the settled end \(settled) after \(window) s: \(moving) starts=\(starts) stamps=\(stamps)",
                      file: file, line: line)
        if late.isEmpty { print("#9436 no capture began after \(window) s; the final shot bounds the settle: starts=\(starts)") }
    }

    /// A history ending on the same last observation (12:10, 46%) with a
    /// response-time pin after it — the shape `_pin_blend_edge` serves.
    private func pinnedHistory(pinAt minute: Int, _ p: Double) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":15302923,"home_team":"Red Sox","away_team":"Yankees","status":"live","history":[],
         "win_prob_history":{"kalshi":[{"timestamp":"2026-09-21T12:00:00Z","home_probability":0.42},
                                       {"timestamp":"2026-09-21T12:10:00Z","home_probability":0.47}],
                             "polymarket":[{"timestamp":"2026-09-21T12:00:00Z","home_probability":0.40},
                                           {"timestamp":"2026-09-21T12:10:00Z","home_probability":0.45}]},
         "aggregate_line":[{"timestamp":"2026-09-21T12:00:00Z","home_probability":0.41},
                           {"timestamp":"2026-09-21T12:05:00Z","home_probability":0.43},
                           {"timestamp":"2026-09-21T12:10:00Z","home_probability":0.46},
                           {"timestamp":"2026-09-21T12:\(minute):00Z","home_probability":\(p)}]}
        """.utf8))
    }

    private func recordMotionFrame(_ image: UIImage, name: String) {
        let attachment = XCTAttachment(image: image)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("#9436 \(name) detected pixel: \(String(describing: tipPixel(image))); marker column: \(String(describing: markerColumn(image)))")
    }

    /// Rightmost line-colour pixel. Retained frames distinguish the endpoint
    /// from label pixels when the chart's domain changes.
    private func tipColumn(_ image: UIImage) -> Int? { tipPixel(image)?.x }

    /// Detect the compact filled dot, not the same-colour animated label.
    /// The 1x fixture draws an 8pt dot with a 1.5pt white outline. Require one
    /// isolated, near-square green core and a white collar; ambiguity fails.
    private func markerColumn(_ image: UIImage) -> Int? {
        guard let cg = image.cgImage else { return nil }
        let (w, h) = (cg.width, cg.height)
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        guard let ctx = CGContext(data: &bytes, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                                  space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
        var green = (0..<(w * h)).map { pixel in
            let i = pixel * 4
            return abs(Int(bytes[i]) - 5) < 24 && abs(Int(bytes[i + 1]) - 150) < 24
                && abs(Int(bytes[i + 2]) - 105) < 24
        }
        var candidates: [Int] = []
        for seed in green.indices where green[seed] {
            var queue = [seed], count = 0
            var minX = w, maxX = 0, minY = h, maxY = 0
            green[seed] = false
            while let pixel = queue.popLast() {
                let x = pixel % w, y = pixel / w
                count += 1
                minX = min(minX, x); maxX = max(maxX, x)
                minY = min(minY, y); maxY = max(maxY, y)
                for (dx, dy) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
                    let nx = x + dx, ny = y + dy
                    guard nx >= 0, nx < w, ny >= 0, ny < h else { continue }
                    let next = ny * w + nx
                    if green[next] { green[next] = false; queue.append(next) }
                }
            }
            let width = maxX - minX + 1, height = maxY - minY + 1
            guard (4...7).contains(width), (4...7).contains(height), abs(width - height) <= 1,
                  count >= 16, count * 3 >= width * height * 2 else { continue }
            let cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
            let collar = [(minX - 2, cy), (maxX + 2, cy), (cx, minY - 2), (cx, maxY + 2)]
            let white = collar.filter { x, y in
                guard x >= 0, x < w, y >= 0, y < h else { return false }
                let i = (y * w + x) * 4
                return bytes[i] > 230 && bytes[i + 1] > 230 && bytes[i + 2] > 230
            }.count
            // The joining line can occupy one collar point.
            if white >= 3 { candidates.append(maxX) }
        }
        return candidates.count == 1 ? candidates[0] : nil
    }

    private func detectorFixture(dotCenters: [CGPoint]) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let green = UIColor(red: 5 / 255.0, green: 150 / 255.0, blue: 105 / 255.0, alpha: 1)
        return UIGraphicsImageRenderer(size: CGSize(width: 220, height: 80), format: format).image { context in
            UIColor.white.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 220, height: 80))
            ("BOS 50%" as NSString).draw(at: CGPoint(x: 120, y: 25), withAttributes: [
                .font: UIFont.boldSystemFont(ofSize: 13), .foregroundColor: green])
            for center in dotCenters {
                let circle = CGRect(x: center.x - 4, y: center.y - 4, width: 8, height: 8)
                context.cgContext.setFillColor(green.cgColor)
                context.cgContext.fillEllipse(in: circle)
                context.cgContext.setStrokeColor(UIColor.white.cgColor)
                context.cgContext.setLineWidth(1.5)
                context.cgContext.strokeEllipse(in: circle)
            }
        }
    }

    func testTheMotionDetectorIgnoresFartherRightLabelPixels() throws {
        let image = detectorFixture(dotCenters: [CGPoint(x: 60, y: 40)])
        let dot = try XCTUnwrap(markerColumn(image))
        XCTAssertTrue((61...63).contains(dot))
        XCTAssertGreaterThan(try XCTUnwrap(tipColumn(image)), dot)
    }

    func testTheMotionDetectorRejectsLabelOnlyAndAmbiguousDots() {
        XCTAssertNil(markerColumn(detectorFixture(dotCenters: [])))
        XCTAssertNil(markerColumn(detectorFixture(dotCenters: [CGPoint(x: 60, y: 40), CGPoint(x: 90, y: 40)])))
    }

    private func tipPixel(_ image: UIImage) -> (x: Int, y: Int)? {
        // Redrawn into a known RGBA layout: a snapshot's own byte order is BGRA.
        guard let cg = image.cgImage else { return nil }
        let (w, h) = (cg.width, cg.height)
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        guard let ctx = CGContext(data: &bytes, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                                  space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
        for x in stride(from: w - 1, through: 0, by: -1) {
            for y in 0..<h {
                let i = (y * w + x) * 4
                let (r, g, b) = (Int(bytes[i]), Int(bytes[i + 1]), Int(bytes[i + 2]))
                if abs(r - 5) < 24 && abs(g - 150) < 24 && abs(b - 105) < 24 { return (x, y) }
            }
        }
        return nil
    }

    func testAnAcceptedAppendGlidesTheDotAlongTheLineAndSettles() async throws {
        let feed = Feed(frames: frames([0.49, 0.55, 0.78]),
                        edge: LiveEdgeReading(homeProbability: 0.78, homeLabel: "78%"))
        let hosted = try Hosted(FedChart(feed: feed, history: try history()))
        defer { hosted.close() }
        try await Task.sleep(for: .milliseconds(600))
        let before = try XCTUnwrap(markerColumn(hosted.shot(scale: 1)))

        // One accepted frame a minute later, at 60% — hero and chart together.
        let next = try XCTUnwrap("2026-09-21T12:14:00Z".asDate)
        feed.frames.append(LiveBlendPoint(date: next, homeProbability: 0.60))
        feed.edge = LiveEdgeReading(homeProbability: 0.60, homeLabel: "60%")
        let (columns, stamps, starts) = try await sampleTip(hosted, seconds: 0.8)
        let sampledLast = try XCTUnwrap(columns.last)
        let settled = try XCTUnwrap(markerColumn(hosted.shot(scale: 1)))
        XCTAssertEqual(sampledLast, settled, "Sampling must reach the independently captured final endpoint")
        print("#9436 glide tip columns: before=\(before) frames=\(columns)")

        // The glide is visible: at least two distinct positions short of the
        // settled end (a snap has none — this arm is red when `glides` is
        // false), never reversing. Two, not more: sampling is real time on a
        // shared machine, and 60 fps is the recording's claim, not this test's.
        let inBetween = Set(columns.filter { $0 < settled })
        XCTAssertGreaterThanOrEqual(inBetween.count, 2, "no visible glide: \(columns)")
        XCTAssertLessThan(columns.first!, settled, "the first frame after the change was already settled")
        XCTAssertEqual(columns, columns.sorted(), "the tip reversed: \(columns)")
        // Bounded: no frame read after the glide window (plus a frame of
        // slack) is still short of the settled end. A frame's time is when its
        // capture BEGAN — the displayed frame is read then — so a slow capture
        // on a loaded runner cannot carry a settled dot past the window (hosted
        // run 37203716941: the last moving frame was read at 0.54 s, the first
        // settled one began at 0.75 s and was stamped 0.81 s, red against 0.6),
        // while a dot still moving after the window stays red.
        assertSettledByTheGlideWindow(columns, starts: starts, stamps: stamps, settled: settled)
    }

    /// Finding 1, rendered: the folded reread path. The history is REPLACED
    /// (same last observation, new pin) with no pushed frame at all, and the
    /// dot glides to the new pin instead of snapping.
    func testAPinReplacementGlidesTheDotAndSettles() async throws {
        let feed = Feed(frames: [], edge: LiveEdgeReading(homeProbability: 0.50, homeLabel: "50%"),
                        history: try pinnedHistory(pinAt: 12, 0.50))
        let hosted = try Hosted(FedChart(feed: feed, history: try history()))
        defer { hosted.close() }
        try await Task.sleep(for: .milliseconds(600))
        let beforeImage = hosted.shot(scale: 1)
        recordMotionFrame(beforeImage, name: "pin-before")
        let before = try XCTUnwrap(markerColumn(beforeImage))

        feed.history = try pinnedHistory(pinAt: 16, 0.58)
        feed.edge = LiveEdgeReading(homeProbability: 0.58, homeLabel: "58%")
        let (columns, stamps, starts) = try await sampleTip(hosted, seconds: 0.8)
        let sampledLast = try XCTUnwrap(columns.last)
        let finalImage = hosted.shot(scale: 1)
        recordMotionFrame(finalImage, name: "pin-final")
        let settled = try XCTUnwrap(markerColumn(finalImage))
        XCTAssertEqual(sampledLast, settled, "Sampling must reach the independently captured final endpoint")
        print("#9436 pin-replacement tip columns: before=\(before) frames=\(columns)")

        // A later pin widens the x-domain in the same update, so `before`
        // (old axis) and these columns (new axis) are not comparable; the
        // glide starts at the old pin's data position under the new axis.
        let inBetween = Set(columns.filter { $0 < settled })
        XCTAssertGreaterThanOrEqual(inBetween.count, 2, "no visible glide on a pin replacement: \(columns)")
        XCTAssertLessThan(columns.first!, settled, "the first frame after the replacement was already settled")
        XCTAssertEqual(columns, columns.sorted(), "the tip reversed: \(columns)")
        assertSettledByTheGlideWindow(columns, starts: starts, stamps: stamps, settled: settled)
    }

    func testTheSamplingRigDoesNotInventAnAppendGlideInAnInactiveScene() async throws {
        try await assertNoSampledGlideInAnInactiveScene(pinReplacement: false)
    }

    func testTheSamplingRigDoesNotInventAPinGlideInAnInactiveScene() async throws {
        try await assertNoSampledGlideInAnInactiveScene(pinReplacement: true)
    }

    private func assertNoSampledGlideInAnInactiveScene(pinReplacement: Bool) async throws {
        let feed = Feed(frames: pinReplacement ? [] : frames([0.49, 0.55, 0.78]),
                        edge: LiveEdgeReading(homeProbability: pinReplacement ? 0.50 : 0.78,
                                              homeLabel: pinReplacement ? "50%" : "78%"),
                        history: pinReplacement ? try pinnedHistory(pinAt: 12, 0.50) : nil)
        feed.phase = .background
        let hosted = try Hosted(FedChart(feed: feed, history: try history()))
        defer { hosted.close() }
        try await Task.sleep(for: .milliseconds(600))
        let before = try XCTUnwrap(tipColumn(hosted.shot(scale: 1)))
        if pinReplacement {
            feed.history = try pinnedHistory(pinAt: 16, 0.58)
            feed.edge = LiveEdgeReading(homeProbability: 0.58, homeLabel: "58%")
        } else {
            feed.frames.append(LiveBlendPoint(date: try XCTUnwrap("2026-09-21T12:14:00Z".asDate), homeProbability: 0.60))
            feed.edge = LiveEdgeReading(homeProbability: 0.60, homeLabel: "60%")
        }
        let (columns, _, _) = try await sampleTip(hosted, seconds: 0.8, measuresMarker: false)
        let settled = try XCTUnwrap(tipColumn(hosted.shot(scale: 1)))
        XCTAssertNotEqual(before, settled, "Control must actually display the accepted update")
        XCTAssertEqual(columns.last, settled, "Control must reach the independent final capture")
        // A not-yet-presented update may leave an initial old frame. Neither
        // that old endpoint nor the settled endpoint is an intermediate glide.
        XCTAssertTrue(columns.allSatisfy { $0 == before || $0 == settled },
                      "Sampling invented motion in an inactive scene: \(columns)")
        print("#9436 inactive-scene control pin=\(pinReplacement): before=\(before) frames=\(columns) settled=\(settled)")
    }

    /// Finding 3, rendered: the scene leaving `.active` mid-glide cancels the
    /// glide — the line is drawn to its settled end at once, not over the
    /// rest of the 350 ms.
    func testLeavingTheActiveSceneMidGlideCancelsIt() async throws {
        let feed = Feed(frames: frames([0.49, 0.55, 0.78]),
                        edge: LiveEdgeReading(homeProbability: 0.78, homeLabel: "78%"))
        let hosted = try Hosted(FedChart(feed: feed, history: try history()))
        defer { hosted.close() }
        try await Task.sleep(for: .milliseconds(600))

        feed.frames.append(LiveBlendPoint(date: try XCTUnwrap("2026-09-21T12:14:00Z".asDate), homeProbability: 0.60))
        feed.edge = LiveEdgeReading(homeProbability: 0.60, homeLabel: "60%")
        try await Task.sleep(for: .milliseconds(60))
        let midGlide = try XCTUnwrap(tipColumn(hosted.shot()))
        feed.phase = .background
        try await Task.sleep(for: .milliseconds(40))
        let afterCancel = try XCTUnwrap(tipColumn(hosted.shot()))
        try await Task.sleep(for: .milliseconds(600))
        let settled = try XCTUnwrap(tipColumn(hosted.shot()))
        print("#9436 cancel: mid=\(midGlide) afterCancel=\(afterCancel) settled=\(settled)")

        XCTAssertLessThan(midGlide, settled, "precondition: the glide was in flight when the scene left")
        XCTAssertEqual(afterCancel, settled, "the glide kept running in a background scene")
    }

    /// Finding 3 for the hero's whole-string change: a slide in flight when
    /// the scene leaves `.active` is cancelled — the next frame is the settled
    /// new string, pixel for pixel, not the rest of the slide.
    func testLeavingTheActiveSceneMidSlideCancelsTheHeroChange() async throws {
        final class Value: ObservableObject {
            @Published var text = "60%"
            @Published var phase: ScenePhase = .active
        }
        struct Hero: View {
            @ObservedObject var value: Value
            var body: some View {
                Text(value.text)
                    .acceptedValueChange(value.text, rising: false)
                    .font(.system(size: 44, weight: .black, design: .rounded).monospacedDigit())
                    .foregroundStyle(.black)
                    .frame(width: 390, height: 360)
                    .background(Color.white)
                    .environment(\.scenePhase, value.phase)
            }
        }
        func bytes(_ image: UIImage) -> Data? { image.pngData() }
        let value = Value()
        let hosted = try Hosted(Hero(value: value))
        defer { hosted.close() }
        try await Task.sleep(for: .milliseconds(400))

        value.text = "59%"
        try await Task.sleep(for: .milliseconds(80))
        let midSlide = bytes(hosted.shot())
        value.phase = .background
        try await Task.sleep(for: .milliseconds(40))
        let afterCancel = bytes(hosted.shot())
        try await Task.sleep(for: .milliseconds(600))
        let settled = bytes(hosted.shot())

        XCTAssertNotEqual(midSlide, settled, "precondition: the slide was in flight when the scene left")
        XCTAssertEqual(afterCancel, settled, "the slide kept running in a background scene")
    }
}
