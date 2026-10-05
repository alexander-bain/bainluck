import XCTest
import SwiftUI
import Charts
import UIKit
@testable import Bain_Luck

/// #4974 — **a finished game's chart draws the checkpoints the server recorded
/// and leaves what it did not record empty.**
///
/// `PublicationCheckpointRenderPlan4974` decides what the layer draws from an
/// ADOPTED journey and the chart's own observation runs. These tests pin that
/// partition with real `ChartDataPoint` and `Journey` values, and one hosted
/// render proves two separated checkpoints draw as two dots with nothing
/// between them.
@MainActor
final class PublicationCheckpointLayer4974Tests: XCTestCase {

    private typealias Plan = PublicationCheckpointRenderPlan4974

    /// 2026-10-04T20:15:00Z (same epoch as `PublicationJourney4974Tests.t201500`).
    private let t0 = Date(timeIntervalSince1970: 1_791_144_900)
    private let eventID = 15_321_333

    // MARK: - Fixtures

    private func at(_ seconds: TimeInterval) -> Date { t0.addingTimeInterval(seconds) }

    private func point(_ seconds: TimeInterval, _ probability: Double,
                       liveEdge: Bool = false) -> ChartDataPoint {
        var point = ChartDataPoint(date: at(seconds), probability: probability, source: "aggregate")
        point.isLiveEdge = liveEdge
        return point
    }

    /// Adopts a served body through Lane1b's real `adopt`, never a hand-built window.
    private func adoptedJourney(
        _ vertices: [(rev: Int64, seconds: TimeInterval, p: Double)],
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws -> PublicationJourney4974.Journey {
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
            XCTFail("expected adoption, got \(refusal)", file: file, line: line)
            throw refusal
        }
    }

    /// Checkpoints at 20:15:10 and 20:15:50 — the window sits inside one minute.
    private func sameMinuteJourney() throws -> PublicationJourney4974.Journey {
        try adoptedJourney([(7, 10, 0.61), (9, 50, 0.58)])
    }

    private func legacyPoints(_ plan: Plan) -> [ChartDataPoint] {
        plan.lines.flatMap(\.points) + plan.dots.map(\.point)
    }

    /// Independent of `permitsLegacySegment`: no drawn legacy point inside the
    /// closed window, and no drawn segment whose closed interval meets it.
    private func assertNothingLegacyTouchesTheWindow(
        _ plan: Plan, _ journey: PublicationJourney4974.Journey,
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let lo = journey.window.lowerBound, hi = journey.window.upperBound
        for point in legacyPoints(plan) {
            XCTAssertFalse(point.date >= lo && point.date <= hi,
                           "legacy point drawn inside the window at \(point.date)", file: file, line: line)
        }
        for run in plan.lines {
            for (a, b) in zip(run.points, run.points.dropFirst()) {
                let start = min(a.date, b.date), end = max(a.date, b.date)
                XCTAssertTrue(end < lo || start > hi,
                              "legacy segment \(start)...\(end) meets the window \(lo)...\(hi)",
                              file: file, line: line)
            }
        }
    }

    // MARK: - Window cuts

    func testAWindowInsideOneMinuteBreaksTheLineBetweenTheTwoMinuteRows() throws {
        let journey = try sameMinuteJourney()
        let before = point(0, 0.40), after = point(60, 0.60)
        let plan = Plan(journey: journey, observationRuns: [[before, after]])

        XCTAssertTrue(plan.lines.isEmpty, "the 20:15→20:16 segment crosses 20:15:10...20:15:50")
        XCTAssertEqual(plan.dots.map(\.point.id), [before.id, after.id])
        assertNothingLegacyTouchesTheWindow(plan, journey)
    }

    func testLegacyRowsInsideTheWindowAreAbsent() throws {
        let journey = try sameMinuteJourney()
        let inside = [point(20, 0.5), point(30, 0.52), point(40, 0.49)]
        let run = [point(-120, 0.40), point(-60, 0.42)] + inside + [point(120, 0.60), point(180, 0.62)]
        let plan = Plan(journey: journey, observationRuns: [run])

        let drawn = Set(legacyPoints(plan).map(\.id))
        XCTAssertTrue(drawn.isDisjoint(with: inside.map(\.id)))
        XCTAssertEqual(plan.lines.map { $0.points.map(\.id) },
                       [[run[0].id, run[1].id], [run[5].id, run[6].id]])
        XCTAssertTrue(plan.dots.isEmpty)
        assertNothingLegacyTouchesTheWindow(plan, journey)
    }

    func testRowsOnEitherClosedBoundaryAreAbsent() throws {
        let journey = try sameMinuteJourney()
        let lower = point(10, 0.61), upper = point(50, 0.58)
        let run = [point(-60, 0.40), lower, upper, point(120, 0.60)]
        let plan = Plan(journey: journey, observationRuns: [run])

        let drawn = Set(legacyPoints(plan).map(\.id))
        XCTAssertFalse(drawn.contains(lower.id))
        XCTAssertFalse(drawn.contains(upper.id))
        XCTAssertEqual(plan.dots.map(\.point.id), [run[0].id, run[3].id])
        assertNothingLegacyTouchesTheWindow(plan, journey)
    }

    func testOutsidePointsKeepTheirIdentityValueDateSourceAndOrder() throws {
        let journey = try sameMinuteJourney()
        let run = [point(-180, 0.4012345), point(-120, 0.43), point(-60, 0.47),
                   point(25, 0.5), point(120, 0.6098765), point(240, 0.64)]
        let plan = Plan(journey: journey, observationRuns: [run])

        let expected = [run[0], run[1], run[2], run[4], run[5]]
        let drawn = plan.lines.flatMap(\.points)
        XCTAssertEqual(drawn.map(\.id), expected.map(\.id))
        XCTAssertEqual(drawn.map(\.date), expected.map(\.date))
        XCTAssertEqual(drawn.map(\.probability), expected.map(\.probability))
        XCTAssertEqual(drawn.map(\.source), expected.map(\.source))
    }

    func testValidConnectionsOutsideTheWindowArePreserved() throws {
        let journey = try sameMinuteJourney()
        let early = [point(-300, 0.40), point(-240, 0.41), point(-180, 0.45)]
        let late = [point(120, 0.55), point(180, 0.57)]
        let plan = Plan(journey: journey, observationRuns: [early + late])

        XCTAssertEqual(plan.lines.map { $0.points.map(\.id) }, [early.map(\.id), late.map(\.id)])
        assertNothingLegacyTouchesTheWindow(plan, journey)
    }

    func testTwoIncomingRunsNeverMergeEvenWhereTheyMeet() throws {
        let journey = try sameMinuteJourney()
        let first = [point(-600, 0.40), point(-540, 0.42)]
        let second = [point(-540, 0.42), point(-480, 0.44)]
        let plan = Plan(journey: journey, observationRuns: [first, second])

        XCTAssertEqual(plan.lines.map { $0.points.map(\.id) }, [first.map(\.id), second.map(\.id)])
        XCTAssertNotEqual(plan.lines[0].id, plan.lines[1].id)
    }

    func testAnUnchangedOutsideFortyToSixtyRunCarriesNoCrossingMetadata() throws {
        let journey = try sameMinuteJourney()
        let run = [point(-400, 0.40), point(-300, 0.60)]
        let plan = Plan(journey: journey, observationRuns: [run])

        XCTAssertEqual(plan.lines.count, 1)
        XCTAssertEqual(plan.lines[0].points.map(\.id), run.map(\.id))
        XCTAssertEqual(plan.lines[0].points.map(\.probability), [0.40, 0.60])
        XCTAssertTrue(plan.dots.isEmpty)
        // The plan says what is drawn and nothing about where a line "crosses"
        // a checkpoint: exactly three stored fields.
        XCTAssertEqual(Mirror(reflecting: plan).children.compactMap(\.label), ["lines", "dots", "checkpoints"])
        XCTAssertEqual(Mirror(reflecting: plan.lines[0]).children.compactMap(\.label), ["id", "points"])
    }

    func testNoBoundaryPointIsInterpolatedOrInserted() throws {
        let journey = try sameMinuteJourney()
        let run = [point(-60, 0.40), point(0, 0.45), point(30, 0.50), point(60, 0.55), point(120, 0.60)]
        let plan = Plan(journey: journey, observationRuns: [run])

        let drawn = legacyPoints(plan)
        XCTAssertTrue(Set(drawn.map(\.id)).isSubset(of: run.map(\.id)))
        XCTAssertFalse(drawn.contains { $0.date == journey.window.lowerBound || $0.date == journey.window.upperBound })
        XCTAssertEqual(drawn.count, 4, "only the 30s row is inside; nothing added in its place")
        assertNothingLegacyTouchesTheWindow(plan, journey)
    }

    func testTheWindowAppliesWithNoVisibleDomainInput() throws {
        // A window far from the legacy rows still cuts a segment that straddles
        // it: the plan never asks whether a checkpoint is on screen.
        let journey = try adoptedJourney([(1, 3_600, 0.5), (2, 3_660, 0.52)])
        let run = [point(0, 0.40), point(7_200, 0.60)]
        let plan = Plan(journey: journey, observationRuns: [run])

        XCTAssertTrue(plan.lines.isEmpty)
        XCTAssertEqual(plan.dots.map(\.point.id), run.map(\.id))
    }

    // MARK: - Checkpoints

    func testEveryCheckpointIsItsOwnDotAtTheStoredHomeProbability() throws {
        let journey = try adoptedJourney([(3, 10, 0.6149999), (5, 30, 0.38), (8, 50, 0.0)])
        let plan = Plan(journey: journey, observationRuns: [])

        XCTAssertEqual(plan.checkpoints.map(\.id), [3, 5, 8])
        XCTAssertEqual(plan.checkpoints.map(\.probability), [0.6149999, 0.38, 0.0])
        XCTAssertEqual(plan.checkpoints.map(\.date), journey.checkpoints.map(\.date))
    }

    func testTwoRevisionsAtOneInstantStayTwoDots() throws {
        let journey = try adoptedJourney([(7, 30, 0.61), (9, 30, 0.58)])
        let before = point(0, 0.40), on = point(30, 0.5), after = point(60, 0.60)
        let plan = Plan(journey: journey, observationRuns: [[before, on, after]])

        XCTAssertEqual(plan.checkpoints.map(\.id), [7, 9])
        XCTAssertEqual(plan.checkpoints.map(\.probability), [0.61, 0.58])
        XCTAssertEqual(Set(plan.checkpoints.map(\.date)).count, 1)
        // A zero-width window still cuts: the row on it is gone and nothing bridges it.
        XCTAssertTrue(plan.lines.isEmpty)
        XCTAssertEqual(plan.dots.map(\.point.id), [before.id, after.id])
        assertNothingLegacyTouchesTheWindow(plan, journey)
    }

    func testNonMonotonicRecordingTimesUseTheJourneyWindowNotFirstAndLastRevision() throws {
        // Commit order 40s, 10s, 50s, 20s: first/last rev would be 20...40.
        let journey = try adoptedJourney([(1, 40, 0.5), (2, 10, 0.52), (3, 50, 0.49), (4, 20, 0.51)])
        XCTAssertEqual(journey.window, at(10)...at(50))
        let early = point(12, 0.45), late = point(45, 0.47)
        let run = [point(-60, 0.40), early, late, point(120, 0.60)]
        let plan = Plan(journey: journey, observationRuns: [run])

        let drawn = Set(legacyPoints(plan).map(\.id))
        XCTAssertFalse(drawn.contains(early.id))
        XCTAssertFalse(drawn.contains(late.id))
        assertNothingLegacyTouchesTheWindow(plan, journey)
    }

    // MARK: - Singletons

    func testASurvivingRealSingletonIsADot() throws {
        let journey = try sameMinuteJourney()
        let lone = point(-60, 0.40)
        let plan = Plan(journey: journey, observationRuns: [[lone, point(30, 0.5)]])

        XCTAssertEqual(plan.dots.map(\.point.id), [lone.id])
        XCTAssertTrue(plan.lines.isEmpty)
    }

    func testASyntheticLiveEdgeCannotBecomeALoneDot() throws {
        let journey = try sameMinuteJourney()
        let real = point(-30, 0.40)
        let edge = point(90, 0.40, liveEdge: true)
        let plan = Plan(journey: journey, observationRuns: [[real, point(20, 0.5), edge], [point(600, 0.6, liveEdge: true)]])

        XCTAssertEqual(plan.dots.map(\.point.id), [real.id])
        XCTAssertFalse(legacyPoints(plan).contains(where: \.isLiveEdge))
    }

    func testALiveEdgeEndingARetainedRunStaysItsEndpoint() throws {
        // The caller's runs already decided this trailing interval is supported.
        let journey = try sameMinuteJourney()
        let run = [point(120, 0.55), point(180, 0.57, liveEdge: true)]
        let plan = Plan(journey: journey, observationRuns: [run])

        XCTAssertEqual(plan.lines.map { $0.points.map(\.id) }, [run.map(\.id)])
    }

    // MARK: - Series identity

    func testEverySeriesIsLayerPrefixedAndNamesItsRunAndPart() throws {
        let journey = try sameMinuteJourney()
        let runs = [
            [point(-600, 0.40), point(-540, 0.41)],
            [point(-120, 0.42), point(-60, 0.43), point(30, 0.5), point(120, 0.55), point(180, 0.56)],
            [point(300, 0.60)],
        ]
        let plan = Plan(journey: journey, observationRuns: runs)

        let ids = plan.lines.map(\.id) + plan.dots.map(\.id)
        XCTAssertEqual(Set(ids).count, ids.count)
        XCTAssertTrue(ids.allSatisfy { $0.hasPrefix(Plan.seriesPrefix + "#") })
        XCTAssertEqual(plan.lines.map(\.id), [
            "\(Plan.seriesPrefix)#0.0", "\(Plan.seriesPrefix)#1.0", "\(Plan.seriesPrefix)#1.1",
        ])
        XCTAssertEqual(plan.dots.map(\.id), ["\(Plan.seriesPrefix)#2.0"])
    }

    // MARK: - Hosted render

    private struct Pixels {
        let bytes: [UInt8]
        let width: Int
        let height: Int

        func isRed(_ x: Int, _ y: Int) -> Bool {
            let i = (y * width + x) * 4
            return bytes[i] > 180 && bytes[i + 1] < 120 && bytes[i + 2] < 120
        }

        /// Rows holding a red pixel anywhere in columns `xs`.
        func redRows(in xs: ClosedRange<Int>) -> [Int] {
            (0..<height).filter { y in xs.contains { isRed($0, y) } }
        }
    }

    private func render<Content: View>(_ view: Content) throws -> Pixels {
        let renderer = rendererForMeasurement(view)
        renderer.scale = 1
        let cg = try XCTUnwrap(renderer.cgImage)
        var bytes = [UInt8](repeating: 0, count: cg.width * cg.height * 4)
        try bytes.withUnsafeMutableBytes { buffer in
            let ctx = try XCTUnwrap(CGContext(data: buffer.baseAddress, width: cg.width, height: cg.height,
                bitsPerComponent: 8, bytesPerRow: cg.width * 4, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        }
        return Pixels(bytes: bytes, width: cg.width, height: cg.height)
    }

    private func framed<C: ChartContent>(@ChartContentBuilder _ content: () -> C) -> some View {
        Chart { content() }
            .chartXScale(domain: at(-500)...at(500))
            .chartYScale(domain: 0...1)
            .chartXAxis(.hidden)
            .chartYAxis(.hidden)
            .chartLegend(.hidden)
            .frame(width: 400, height: 200)
            .background(Color.white)
    }

    /// 1,000 s over 400 pt: x = (seconds + 500) × 0.4. Checkpoints at −50 s
    /// (40%) and +50 s (60%) sit at x≈180 and x≈220; the midpoint is x≈200.
    /// Legacy rows straddle the window, including three at 50% inside it and
    /// the −200 s → +200 s bridge that would cross x≈200.
    func testHostedChartDrawsTwoSeparatedCheckpointDotsWithABlankMidpoint() throws {
        let journey = try adoptedJourney([(11, -50, 0.40), (12, 50, 0.60)])
        let run = [point(-400, 0.40), point(-300, 0.45), point(-200, 0.40),
                   point(-20, 0.5), point(0, 0.5), point(20, 0.5),
                   point(200, 0.60), point(300, 0.55), point(400, 0.60)]
        let plan = Plan(journey: journey, observationRuns: [run])
        XCTAssertEqual(plan.lines.count, 2)

        let pixels = try render(framed {
            PublicationCheckpointLayer4974(plan: plan, color: .red, stroke: StrokeStyle(lineWidth: 2))
        })
        XCTAssertEqual(pixels.width, 400)

        XCTAssertTrue(pixels.redRows(in: 195...205).isEmpty, "something is drawn between the two checkpoints")

        let fortyRows = pixels.redRows(in: 176...184)
        let sixtyRows = pixels.redRows(in: 216...224)
        XCTAssertFalse(fortyRows.isEmpty, "the 40% checkpoint dot is missing")
        XCTAssertFalse(sixtyRows.isEmpty, "the 60% checkpoint dot is missing")
        // Orientation-free: the two dots sit 20% of 200 pt apart, symmetric about 50%.
        let fortyMid = (fortyRows.min()! + fortyRows.max()!) / 2
        let sixtyMid = (sixtyRows.min()! + sixtyRows.max()!) / 2
        XCTAssertTrue((34...46).contains(abs(fortyMid - sixtyMid)), "dot rows \(fortyMid) / \(sixtyMid)")
        XCTAssertTrue((192...208).contains(fortyMid + sixtyMid), "dot rows \(fortyMid) / \(sixtyMid)")

        XCTAssertFalse(pixels.redRows(in: 98...102).isEmpty, "the legacy line before the window is gone")
        XCTAssertFalse(pixels.redRows(in: 298...302).isEmpty, "the legacy line after the window is gone")
    }

    /// The instrument can see a bridge: the same raw run drawn as one series
    /// colours the midpoint the layer must leave blank.
    func testTheRenderProbeSeesARawBridgeAcrossTheWindow() throws {
        let run = [point(-400, 0.40), point(-200, 0.40), point(0, 0.5), point(200, 0.60), point(400, 0.60)]
        let pixels = try render(framed {
            ForEach(run) { point in
                LineMark(x: .value("Time", point.date), y: .value("Win probability", point.probability),
                         series: .value("Source", "raw"))
                    .foregroundStyle(Color.red)
                    .lineStyle(StrokeStyle(lineWidth: 2))
                    .interpolationMethod(.linear)
            }
        })
        XCTAssertFalse(pixels.redRows(in: 195...205).isEmpty)
    }
}
