import XCTest
import SwiftUI
@testable import Bain_Luck

/// #2903 — the chart gutter's rotated name overdrew the section heading beside it
/// and lost its own ends off the top and bottom.
///
/// The rendered geometry is not reachable from a unit test, so this file guards the
/// two things that ARE: the arithmetic that gives a label a run to be bounded by,
/// and the source shape of the defect itself. The rendered proof is a simulator
/// screenshot, in the PR.
final class ChartGutterRunTests: XCTestCase {

    func testTwoLabelsAndTheirGapExactlyFillTheChartHeight() {
        // The run is only meaningful if two of them plus the gap account for the
        // whole usable height — otherwise the labels are bounded by a number that
        // has nothing to do with the space they are in.
        let height: CGFloat = 260
        let padding: CGFloat = 8
        let run = ChartGutter.run(chartHeight: height, verticalPadding: padding)

        XCTAssertEqual(
            run * 2 + ChartGutter.interLabelGap,
            height - padding * 2,
            accuracy: 0.001,
            "two runs plus the gap must be exactly the height inside the padding"
        )
    }

    func testTheRunLeavesRoomForAnOrdinaryNameOnAPhone() {
        // The phone event page: chartHeight 260, 8pt of padding. A run this size
        // has to hold an uppercase surname at 11pt bold without truncating, or the
        // fix trades a clipped name for an ellipsised one and gains nothing.
        let run = ChartGutter.run(chartHeight: 260, verticalPadding: 8)

        // "SABALENKA" at 11pt bold measures ~85pt; the longest names we draw sit
        // under ~110pt. The bound below is the claim that matters.
        XCTAssertGreaterThan(run, 110, "an ordinary surname must fit the run untruncated")
    }

    func testTheScoreDifferentialGutterGetsAPositiveRun() {
        // The short chart is the one most at risk of a nonsense run, because its
        // height is the smallest in the app.
        let run = ChartGutter.run(
            chartHeight: ScoreDifferentialChartView.chartHeight,
            verticalPadding: 8
        )
        XCTAssertGreaterThan(run, 0)
        XCTAssertEqual(run * 2 + ChartGutter.interLabelGap, 160 - 16, accuracy: 0.001)
    }

    func testARunNeverGoesNegativeOnAChartShorterThanItsOwnFurniture() {
        // A caller may hand in a height smaller than the padding and gap it also
        // asked for. A negative frame height is a runtime crash in SwiftUI, so the
        // floor is load-bearing, not defensive decoration.
        let run = ChartGutter.run(chartHeight: 10, verticalPadding: 8)
        XCTAssertEqual(run, 0)
    }
}

/// The call-site guard. `ChartGutterLabel` fixes the gutter labels that exist
/// today; this stops the sixth one from being written the old way.
final class ChartGutterLabelShapeTests: XCTestCase {

    /// Every app source file, walked from this test's own location so the census
    /// reads the shipping tree rather than a copy that can drift.
    private func appSources() throws -> [(path: String, text: String)] {
        let here = URL(fileURLWithPath: #filePath)
        let appRoot = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")

        guard let walker = FileManager.default.enumerator(
            at: appRoot,
            includingPropertiesForKeys: nil
        ) else {
            return []
        }

        var found: [(String, String)] = []
        for case let url as URL in walker where url.pathExtension == "swift" {
            let text = try String(contentsOf: url, encoding: .utf8)
            found.append((url.lastPathComponent, text))
        }
        return found
    }

    func testTheAppSourcesAreActuallyReadable() throws {
        // A census whose pass and fail look identical is not a check: if the walk
        // finds nothing, every offender test below passes vacuously forever.
        let sources = try appSources()
        XCTAssertGreaterThan(sources.count, 100, "the source walk found almost nothing — the census is not running")
        XCTAssertTrue(
            sources.contains { $0.path == "ChartGutterLabel.swift" },
            "the walk must reach the Components directory"
        )
    }

    func testFixedSizeNeverSitsImmediatelyAboveAMinusNinetyRotation() throws {
        // THE DEFECT SHAPE, exactly. `.fixedSize()` demands the full natural width
        // and `rotationEffect` then turns pixels without telling layout — together
        // they are #2903. Apart they are both fine, which is why this matches the
        // pair and not either half: the progress rings elsewhere in the app rotate
        // a trimmed Circle by -90 and must keep working.
        var offenders: [String] = []

        for source in try appSources() {
            let lines = source.text.components(separatedBy: .newlines)
            for (index, line) in lines.enumerated() {
                guard line.contains(".rotationEffect(.degrees(-90))") else { continue }
                if line.trimmingCharacters(in: .whitespaces).hasPrefix("///") { continue }

                // The nearest preceding line that is neither blank nor a comment.
                let previous = lines[..<index].reversed().first { candidate in
                    let trimmed = candidate.trimmingCharacters(in: .whitespaces)
                    return !trimmed.isEmpty && !trimmed.hasPrefix("//")
                }
                guard let previous, previous.contains(".fixedSize()") else { continue }

                offenders.append("\(source.path):\(index + 1) — \(line.trimmingCharacters(in: .whitespaces))")
            }
        }

        XCTAssertTrue(
            offenders.isEmpty,
            """
            A rotated label is sized as if it were never rotated (#2903). \
            `.fixedSize()` above `.rotationEffect(.degrees(-90))` gives the label a \
            layout box the width of the unrotated text, so it overdraws whatever is \
            beside it and its own ends are clipped by the box it was given. Use \
            `ChartGutterLabel(run:)`, which bounds the run before rotating and states \
            the rotated footprint after. Offenders:
            \(offenders.joined(separator: "\n"))
            """
        )
    }
}
