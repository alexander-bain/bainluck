import XCTest
import SwiftUI
import Charts
import UIKit
@testable import Bain_Luck

/// #12639 (Decision 164) — one connected straight-segment line on the iPhone
/// game page's win probability and projected final points charts, with no
/// smoothing.
@MainActor
final class ConnectedChartLines12639Tests: XCTestCase {

    private let epoch = Date(timeIntervalSince1970: 1_791_144_900)
    private let eventID = 15_344_730

    private func at(_ seconds: TimeInterval) -> Date {
        epoch.addingTimeInterval(seconds)
    }

    private func chartPoint(_ seconds: TimeInterval, _ probability: Double,
                            source: String = "aggregate", liveEdge: Bool = false) -> ChartDataPoint {
        var point = ChartDataPoint(date: at(seconds), probability: probability, source: source)
        point.isLiveEdge = liveEdge
        return point
    }

    private func adoptedJourney(_ vertices: [(rev: Int64, seconds: TimeInterval, p: Double)]) throws -> PublicationJourney4974.Journey {
        let response = PublicationCheckpointsResponse(
            eventId: eventID,
            schemaVersion: 1,
            timeBasis: "recorded_at_insert_before_commit",
            truncated: false,
            vertices: vertices.map {
                PublicationCheckpointVertex(rev: $0.rev, t: at($0.seconds).ISO8601Format(), p: $0.p)
            }
        )
        switch PublicationJourney4974.adopt(response, expectedEventID: eventID, finished: true) {
        case .success(let journey):
            return journey
        case .failure(let refusal):
            XCTFail("expected adoption, got \(refusal)")
            throw refusal
        }
    }

    // MARK: - Win probability: publication checkpoints (#4974 -> #12639)

    func testPublicationCheckpointsConnectChronologicallyWithSurvivingLegacyOutsideWindow() throws {
        // Checkpoints arrive in rev order with non-monotonic timestamps inside the window;
        // surviving legacy readings sit before and after the closed checkpoint minute.
        let journey = try adoptedJourney([
            (10, 45, 0.72),
            (11, 15, 0.58),
            (12, 3_620, 0.84),
        ])
        let legacyRun = [
            chartPoint(-600, 0.50),
            chartPoint(20, 0.99),      // inside closed checkpoint window -> dropped
            chartPoint(7_200, 0.91),
        ]
        let plan = PublicationCheckpointRenderPlan4974(
            journey: journey,
            observationRuns: [legacyRun]
        )

        XCTAssertEqual(
            plan.connectedPoints.map(\.date),
            [at(-600), at(15), at(45), at(3_620), at(7_200)],
            "connectedPoints orders surviving pre-window legacy, chronological checkpoints, and surviving post-window legacy"
        )
        XCTAssertEqual(
            plan.connectedPoints.map(\.probability),
            [0.50, 0.58, 0.72, 0.84, 0.91]
        )

        let mount = PublicationCheckpointMount4974(
            journey: try adoptedJourney([(10, 15, 0.58), (11, 3_620, 0.84)]),
            points: legacyRun,
            gameStart: at(0),
            admits: { _ in true }
        )
        let ink = OddsChartView.primaryInk9483(dataPoints: legacyRun, checkpoints: mount, gameStart: at(0))
        XCTAssertEqual(ink.runs.count, 1)
        XCTAssertEqual(ink.runs[0].count, 4)
        XCTAssertTrue(ink.draws(date: at(3_620), probability: 0.84))
    }

    func testSeparatedCheckpointsRenderAConnectedStraightSegmentAcrossTheMidpoint() throws {
        let journey = try adoptedJourney([(1, 10, 0.85), (2, 50, 0.15)])
        let plan = PublicationCheckpointRenderPlan4974(journey: journey, observationRuns: [])
        let chart = Chart {
            PublicationCheckpointLayer4974(
                plan: plan,
                color: .red,
                stroke: StrokeStyle(lineWidth: 3)
            )
        }
        .chartXScale(domain: at(0)...at(60))
        .chartYScale(domain: 0.0...1.0)
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartLegend(.hidden)
        .frame(width: 400, height: 200)
        .background(Color.white)

        let renderer = rendererForMeasurement(chart)
        renderer.scale = 1
        let cg = try XCTUnwrap(renderer.cgImage)
        var bytes = [UInt8](repeating: 0, count: cg.width * cg.height * 4)
        try bytes.withUnsafeMutableBytes { buffer in
            let ctx = try XCTUnwrap(CGContext(
                data: buffer.baseAddress,
                width: cg.width,
                height: cg.height,
                bitsPerComponent: 8,
                bytesPerRow: cg.width * 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ))
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        }

        let midpointRedYs = (0..<cg.height).filter { y in
            (198...202).contains { x in
                let i = (y * cg.width + x) * 4
                return bytes[i] > 180 && bytes[i + 1] < 120 && bytes[i + 2] < 120
            }
        }
        XCTAssertFalse(midpointRedYs.isEmpty, "the straight segment bridges separated checkpoints across the midpoint")
        if let minY = midpointRedYs.min(), let maxY = midpointRedYs.max() {
            // For a straight diagonal from 0.85 to 0.15 across x=10...50, at x=30 (center) y is centered near 100 px.
            XCTAssertGreaterThan(minY, 70, "no curved overshoot toward the top")
            XCTAssertLessThan(maxY, 130, "no curved overshoot toward the bottom")
        }
    }

    // MARK: - Win probability: observation segments (#7878 -> #12639)

    func testObservationSegmentsBridgeInteriorGapsWhileStillDroppingUnsupportedLiveEdge() {
        let real = [60.0, 180, 300, 7_800, 7_920].map { chartPoint($0, 0.62, source: "kalshi") }
        let staleEdge = chartPoint(12_000, 0.62, source: "kalshi", liveEdge: true)
        let freshEdge = chartPoint(8_000, 0.62, source: "kalshi", liveEdge: true)

        let withStale = OddsChartView.observationSegments(real + [staleEdge], gameStart: at(0))
        XCTAssertEqual(withStale.count, 1)
        XCTAssertEqual(withStale[0].count, 5, "all five real points bridge in one series while the stale live_edge drops")
        XCTAssertFalse(withStale[0].contains(where: \.isLiveEdge))

        let withFresh = OddsChartView.observationSegments(real + [freshEdge], gameStart: at(0))
        XCTAssertEqual(withFresh.count, 1)
        XCTAssertEqual(withFresh[0].count, 6, "supported trailing live_edge extends the single connected series")
        XCTAssertEqual(withFresh[0].last?.isLiveEdge, true)
    }

    // MARK: - Projected final points (#10239 / #12578 -> #12639)

    func testProjectedFinalPointsSeriesConnectsAcrossLongGapsAndWithheldRowsWithoutAlteringHoldEnd() throws {
        typealias Series = ProjectedFinalPointsSeries
        func pair(_ seconds: Double, _ home: Double? = 114.5, _ away: Double? = 109.5,
                  probability: Double? = 0.64) -> Series.Pair {
            .init(at: at(seconds), home: home, away: away, homeProbability: probability, kind: .recorded)
        }
        let input = Series.Input(
            sportKey: "basketball_nba",
            sourceKey: "fanduel",
            basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: [
                pair(-300, 115.0, 110.0),
                pair(600, 108.0, 112.0, probability: 0.75), // withheld: contradicts homeProbability > 0.55
                pair(3_600, 118.5, 107.5),
            ],
            actuals: [.init(at: at(60), home: 4, away: 2), .init(at: at(3_600), home: 88, away: 80)],
            kickoffAt: at(0),
            scoreObservationStartAt: at(0),
            finalAt: nil,
            asOf: at(3_660),
            windowStartAt: nil,
            requestCutoffAt: nil
        )
        let series = try XCTUnwrap(Series.build(input))

        XCTAssertEqual(series.segments.count, 1, "all valid projections sit in one connected series")
        XCTAssertEqual(series.segments[0].map(\.at), [at(-300), at(3_600)])
        XCTAssertEqual(series.withheld.count, 1, "contradictory capture is still withheld and audited")
        XCTAssertEqual(series.segments[0][0].holdEnd, at(-300),
                       "Point.holdEnd stays honest when the next valid capture is across a withheld row and >15m gap")
        XCTAssertNil(series.kickoffProjection,
                     "kickoffProjection is nil when no held step bridged kickoff")
        XCTAssertEqual(ProjectedFinalPointsChartView.drawnSegments(series).map { $0.map(\.at) },
                       [[at(-300), at(3_600)]])
        XCTAssertFalse(ProjectedFinalPointsChartView.legend(for: series).contains("Gaps mean no usable capture"))
        XCTAssertEqual(
            ProjectedFinalPointsChartView.legend(for: series),
            "Solid: projected final points. Dashed: points actually scored. Forecasts are not results."
        )
    }

    func testProjectedFinalKickoffClippedSeriesStaysOneConnectedSegmentFromKickoff() throws {
        typealias Series = ProjectedFinalPointsSeries
        func pair(_ seconds: Double, _ home: Double, _ away: Double) -> Series.Pair {
            .init(at: at(seconds), home: home, away: away, homeProbability: 0.65, kind: .recorded)
        }
        let input = Series.Input(
            sportKey: "basketball_nba",
            sourceKey: "draftkings",
            basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: [
                pair(-300, 115.0, 109.0),
                pair(300, 116.5, 108.5),   // within 15m of -300 -> kickoffProjection holds 115/109 at t=0
                pair(2_700, 121.0, 106.0), // 40m gap after t=300 -> still connected in drawnSegments
            ],
            actuals: [.init(at: at(60), home: 2, away: 0)],
            kickoffAt: at(0),
            scoreObservationStartAt: at(0),
            finalAt: nil,
            asOf: at(2_760),
            windowStartAt: nil,
            requestCutoffAt: nil
        )
        let series = try XCTUnwrap(Series.build(input))
        XCTAssertNotNil(series.kickoffProjection)
        let drawn = ProjectedFinalPointsChartView.drawnSegments(series)
        XCTAssertEqual(drawn.count, 1)
        XCTAssertEqual(drawn[0].map(\.at), [at(0), at(300), at(2_700)])
    }

    func testProjectedFinalReadingMarksThinDenseRunsWhileKeepingFirstAndLast() {
        for index in 0..<36 {
            XCTAssertTrue(
                ProjectedFinalPointsChartView.showsReadingMark(at: index, count: 36),
                "runs up to 36 points keep every reading mark"
            )
        }
        let denseCount = 90 // stride = ceil(90 / 28) = 4
        XCTAssertTrue(ProjectedFinalPointsChartView.showsReadingMark(at: 0, count: denseCount))
        XCTAssertFalse(ProjectedFinalPointsChartView.showsReadingMark(at: 1, count: denseCount))
        XCTAssertTrue(ProjectedFinalPointsChartView.showsReadingMark(at: 4, count: denseCount))
        XCTAssertTrue(ProjectedFinalPointsChartView.showsReadingMark(at: denseCount - 1, count: denseCount))
    }

    // MARK: - No smoothing guard (Decision 164 / C43 P1)

    func testNoChartFileUsesCurvedInterpolation() throws {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
        for relPath in [
            "Components/PublicationCheckpointLayer4974.swift",
            "Components/OddsChartView.swift",
            "Components/ProjectedFinalPointsChartView.swift",
        ] {
            let source = try String(contentsOf: appRoot.appendingPathComponent(relPath), encoding: .utf8)
            for forbidden in [".catmullRom", ".cardinal", ".monotone"] {
                XCTAssertFalse(source.contains(forbidden), "\(relPath) must not smooth chart segments with \(forbidden)")
            }
        }
        let projectedView = try String(
            contentsOf: appRoot.appendingPathComponent("Components/ProjectedFinalPointsChartView.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(projectedView.contains(".interpolationMethod(.linear)"),
                      "ProjectedFinalPointsChartView forecast line uses straight-segment linear interpolation")
        XCTAssertTrue(projectedView.contains(".interpolationMethod(.stepEnd)"),
                      "ProjectedFinalPointsChartView actual score line keeps stepEnd staircase")
    }
}
