import XCTest
import SwiftUI
@testable import Bain_Luck

/// #10456 — **an admitted binary game chart wears its teams' colors above and
/// below 50%, and both teams' accepted values stay readable beside it.**
///
/// `BinaryWinChartBalanceInk` only presents what the caller already holds: the
/// displayed path runs, the supplied home and away values, and an explicit
/// binary admission. These pin the three ways it could stop being honest:
///
/// 1. **Refusal.** A refused admission, a missing away value or a broken
///    vertex yields no plan, so the caller keeps today's line. The away slot is
///    never filled with `1 − home`.
/// 2. **No invented path.** Each run is drawn from its own vertices only: no
///    crossing point inserted at 50%, no fill or line joining two runs, and a
///    lone observation stays visible as a dot.
/// 3. **One split.** Home ink is everything above the projected even line and
///    away ink everything at or below it, on the chart's existing 0–1 scale.
@MainActor
final class BinaryWinChartBalanceInkTests: XCTestCase {

    private let t0 = Date(timeIntervalSince1970: 1_900_000_000)
    private var plot: CGRect { CGRect(x: 0, y: 0, width: 300, height: 200) }

    private func v(_ minutes: Double, _ p: Double) -> BinaryWinPathVertex {
        BinaryWinPathVertex(date: t0.addingTimeInterval(minutes * 60), probability: p)
    }

    /// Two runs with a capture hole between them; the first crosses 50%.
    private var twoRuns: [[BinaryWinPathVertex]] {
        [[v(0, 0.55), v(10, 0.40), v(20, 0.62)],
         [v(40, 0.70), v(50, 0.66)]]
    }

    private func admittedPlan(_ segments: [[BinaryWinPathVertex]]? = nil,
                              home: Double? = 0.66, away: Double? = 0.34) -> BinaryWinBalancePlan? {
        BinaryWinChartBalanceInk.plan(admission: .admittedBinary, segments: segments ?? twoRuns,
                                      home: home, away: away)
    }

    private var projector: (Date, Double) -> CGPoint? {
        BinaryWinChartBalanceInk.linearProjector(
            xDomain: t0...t0.addingTimeInterval(50 * 60), plotRect: plot)
    }

    // MARK: - 1. Refusal

    func testAnAdmittedBinaryWithBothValuesIsPlanned() throws {
        // The control for every refusal below: the same inputs, admitted, plan.
        let plan = try XCTUnwrap(admittedPlan())
        XCTAssertEqual(plan.segments, twoRuns, "The runs are the caller's, unchanged and in order.")
        XCTAssertEqual(plan.home, 0.66)
        XCTAssertEqual(plan.away, 0.34)
    }

    func testARefusedAdmissionIsNeverInked() {
        XCTAssertNil(
            BinaryWinChartBalanceInk.plan(admission: .refused, segments: twoRuns, home: 0.66, away: 0.34),
            "A draw-priced, multi-contender or threshold question is refused by the caller; the ink must stand down.")
    }

    func testAMissingAwayValueRefusesRatherThanComplementing() {
        XCTAssertNil(admittedPlan(away: nil),
                     "No away value is a refusal. Printing 1 − home as the away side is #5271's defect.")
        XCTAssertNil(admittedPlan(home: nil), "No home value: nothing to read.")
    }

    func testTheAwayValuePrintedIsTheSuppliedOneNotTheComplement() throws {
        // 0.62 / 0.30 is a real venue pair that does not sum to 1. The readout
        // prints what was supplied; the complement would print 38%.
        let plan = try XCTUnwrap(admittedPlan(home: 0.62, away: 0.30))
        XCTAssertEqual(plan.away, 0.30)
        XCTAssertEqual(plan.homeText, "62%")
        XCTAssertEqual(plan.awayText, "30%")
        XCTAssertNotEqual(plan.awayText, "38%")
    }

    func testTheReadoutUsesTheGameCardsOwnPrintedLabels() throws {
        // Same formatter as the card and the scrub readout: a live 0.996 is ">99%", never "100%".
        let plan = try XCTUnwrap(admittedPlan(home: 0.996, away: 0.004))
        let card = GamePlayCardView.printedLabels(home: 0.996, away: 0.004)
        XCTAssertEqual(plan.homeText, card.home)
        XCTAssertEqual(plan.awayText, card.away)
        XCTAssertEqual(plan.homeText, ">99%")
    }

    func testABrokenValueRefuses() {
        XCTAssertNil(admittedPlan(home: .nan, away: 0.34))
        XCTAssertNil(admittedPlan(home: 0.66, away: .infinity))
        XCTAssertNil(admittedPlan(home: 1.2, away: 0.34), "Off the 0–1 scale is not a probability.")
        XCTAssertNil(admittedPlan(home: 0.66, away: -0.1))
    }

    func testABrokenVertexRefusesTheWholePlanRatherThanRedrawingThePath() {
        // Dropping the vertex would draw a path the caller never drew.
        XCTAssertNil(admittedPlan([[v(0, 0.55), v(10, .nan), v(20, 0.62)]]))
        XCTAssertNil(admittedPlan([[v(0, 0.55), v(10, 1.5)]]))
    }

    func testNoVerticesIsNoPlan() {
        XCTAssertNil(admittedPlan([]))
        XCTAssertNil(admittedPlan([[], []]))
    }

    func testAnEmptyRunIsDroppedAndTheRealRunsAreKept() throws {
        let plan = try XCTUnwrap(admittedPlan([[], [v(0, 0.55), v(10, 0.60)], []]))
        XCTAssertEqual(plan.segments, [[v(0, 0.55), v(10, 0.60)]])
    }

    // MARK: - 2. No invented path

    func testEveryProjectedVertexIsTheCallersVertexAndNoneIsAdded() throws {
        let plan = try XCTUnwrap(admittedPlan())
        let geometry = try XCTUnwrap(BinaryWinBalanceGeometry(plan: plan, project: projector))
        let expected = twoRuns.map { run in run.map { projector($0.date, $0.probability)! } }
        XCTAssertEqual(geometry.runs, expected,
                       "Run one crosses 50% between 0.55 and 0.40; no crossing vertex may be inserted there.")
    }

    func testEachRunIsFilledToTheEvenLineAtItsOwnEndsAndNeverAcrossTheHole() throws {
        let plan = try XCTUnwrap(admittedPlan())
        let geometry = try XCTUnwrap(BinaryWinBalanceGeometry(plan: plan, project: projector))
        let polygons = geometry.fillPolygons
        XCTAssertEqual(polygons.count, 2, "One fill per observed run.")
        for (polygon, run) in zip(polygons, geometry.runs) {
            XCTAssertEqual(polygon.count, run.count + 2)
            XCTAssertEqual(polygon.first, CGPoint(x: run.first!.x, y: geometry.evenY))
            XCTAssertEqual(polygon.last, CGPoint(x: run.last!.x, y: geometry.evenY))
            XCTAssertEqual(Array(polygon.dropFirst().dropLast()), run)
        }
        let firstRunEnds = polygons[0].map(\.x).max()!
        let secondRunStarts = polygons[1].map(\.x).min()!
        XCTAssertLessThan(firstRunEnds, secondRunStarts,
                          "Nothing is drawn over the capture hole between minute 20 and minute 40.")
    }

    func testTheLineHasOneSubpathPerRun() throws {
        let plan = try XCTUnwrap(admittedPlan())
        let geometry = try XCTUnwrap(BinaryWinBalanceGeometry(plan: plan, project: projector))
        var moves = 0
        geometry.linePath.forEach { if case .move = $0 { moves += 1 } }
        XCTAssertEqual(moves, 2, "A single subpath would join the two runs with a line nobody observed.")
    }

    func testALoneObservationStaysVisibleAsADotOnItsSide() throws {
        let plan = try XCTUnwrap(admittedPlan([[v(0, 0.55), v(10, 0.60)], [v(30, 0.42)], [v(50, 0.50)]]))
        let geometry = try XCTUnwrap(BinaryWinBalanceGeometry(plan: plan, project: projector))
        XCTAssertEqual(geometry.lineRuns.count, 1)
        XCTAssertEqual(geometry.fillPolygons.count, 1, "A lone point has no width to fill.")
        XCTAssertEqual(geometry.singletons, [projector(t0.addingTimeInterval(30 * 60), 0.42)!,
                                             projector(t0.addingTimeInterval(50 * 60), 0.50)!])
        XCTAssertEqual(geometry.singletonIsHomeSide, [false, true],
                       "Below 50% is the away side; exactly 50% reads as home, v24's tip rule.")
    }

    func testAnUnplaceableVertexDrawsNothing() throws {
        let plan = try XCTUnwrap(admittedPlan())
        let refusesLateVertices: (Date, Double) -> CGPoint? = { date, value in
            date > self.t0.addingTimeInterval(45 * 60) ? nil : self.projector(date, value)
        }
        XCTAssertNil(BinaryWinBalanceGeometry(plan: plan, project: refusesLateVertices),
                     "A partial path is a different path; draw none and let the caller's line stand.")
    }

    // MARK: - 3. One split at 50%

    func testTheLinearProjectorKeepsTheChartsZeroToOneAxis() {
        XCTAssertEqual(projector(t0, 1.0)!.y, plot.minY)
        XCTAssertEqual(projector(t0, 0.0)!.y, plot.maxY)
        XCTAssertEqual(projector(t0, 0.5)!.y, plot.midY)
        XCTAssertEqual(projector(t0, 0.5)!.x, plot.minX)
        XCTAssertEqual(projector(t0.addingTimeInterval(50 * 60), 0.5)!.x, plot.maxX)
    }

    func testAnEmptyDomainCannotProject() {
        let flat = BinaryWinChartBalanceInk.linearProjector(xDomain: t0...t0, plotRect: plot)
        XCTAssertNil(flat(t0, 0.5))
    }

    func testHomeInkIsAboveTheEvenLineAndAwayInkAtOrBelowIt() throws {
        let plan = try XCTUnwrap(admittedPlan())
        let geometry = try XCTUnwrap(BinaryWinBalanceGeometry(plan: plan, project: projector))
        XCTAssertEqual(geometry.evenY, plot.midY)
        let pad = BinaryWinChartBalanceInk.lineWidth
        let home = geometry.homeClip(in: plot, pad: pad)
        let away = geometry.awayClip(in: plot, pad: pad)
        XCTAssertEqual(home.maxY, geometry.evenY)
        XCTAssertEqual(away.minY, geometry.evenY)
        XCTAssertFalse(home.intersects(away), "The two halves share only the even line.")
        XCTAssertLessThanOrEqual(home.minY, plot.minY - pad, "A stroke at 100% keeps its full width.")
        XCTAssertGreaterThanOrEqual(away.maxY, plot.maxY + pad, "A stroke at 0% keeps its full width.")
        XCTAssertTrue(home.union(away).contains(plot))
    }

    func testTheSpokenPairNamesBothTeamsHomeFirstWithTheSuppliedValues() throws {
        let plan = try XCTUnwrap(admittedPlan(home: 0.62, away: 0.30))
        XCTAssertEqual(BinaryWinPairedReadout.spokenPair(plan: plan, homeLabel: "NYY", awayLabel: "BOS"),
                       "NYY 62%, BOS 30%")
    }

    // MARK: - Source guards

    func testTheInkNeverComplementsAnimatesOrSmooths() throws {
        let source = try code(at: Self.component)
        XCTAssertTrue(source.contains("GamePlayCardView.printedLabels("),
                      "Anchor: the readout goes through the existing formatter. If this moved, re-aim the guard.")
        for forbidden in ["1 - ", "1.0 - ", "1-", "withAnimation", ".animation(", "repeatForever",
                          ".transition(", "interpolationMethod", "catmullRom", "monotone", "DrawPricedWinner"] {
            XCTAssertFalse(source.contains(forbidden),
                           "\(forbidden) — the ink presents supplied values on a supplied path, with no motion and no admission of its own.")
        }
    }

    // MARK: - Helpers

    private static var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
    }

    private static var component: URL {
        projectRoot.appendingPathComponent("Bain Luck/Components/BinaryWinChartBalanceInk.swift")
    }

    /// The file with `//` comment lines removed, so prose that names a
    /// forbidden pattern (this file's own header does) can't redden the guard.
    private func code(at url: URL) throws -> String {
        try String(contentsOf: url, encoding: .utf8)
            .components(separatedBy: "\n")
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }
}
