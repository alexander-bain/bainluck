import XCTest
import SwiftUI
@testable import Bain_Luck

/// #9140 — A ONE-OUTCOME CHART OFFERED FOUR CONTROLS THAT DID NOTHING.
///
/// Discover → "Xi Jinping out before 2027?" (Polymarket, /futures/112894, one
/// outcome). Above the chart the bar offered `Sum` and `Top 5 / Top 10 / Top 20`.
/// `Sum` cannot draw on a selection of one (`EvolutionCombinedLinePolicy` refuses
/// it), and no `Top N` chip can cut a board that is already smaller than the
/// smallest chip. The reader taps, nothing changes, and the chart looks broken.
///
/// ═══ WHAT THESE PIN ═══
///
/// The rule `sumToggle` already follows for #8158: a control that means nothing
/// here is ABSENT, not disabled. Both directions are pinned, because a gate that
/// only ever hides would pass its own red test while taking `Top N` off every
/// championship board on the site.
@MainActor
final class AControlThatChangesNothingIsAbsent9140Tests: XCTestCase {

    private typealias Bar = EvolutionControlBar

    // MARK: - The counts

    func testSumNeedsTwoLinesToAdd() {
        XCTAssertFalse(Bar.sumHasSomethingToAdd(drawableOutcomes: 0))
        XCTAssertFalse(
            Bar.sumHasSomethingToAdd(drawableOutcomes: 1),
            "112894: one Yes/No line has nothing to add it to")
        XCTAssertTrue(
            Bar.sumHasSomethingToAdd(drawableOutcomes: 2),
            "two alternatives to one question can be summed — keep the control")
        XCTAssertTrue(Bar.sumHasSomethingToAdd(drawableOutcomes: 30))
    }

    func testTopNNeedsMoreRowsThanItsSmallestChip() {
        XCTAssertEqual(Bar.topChoices.first, 5, "the fixture below assumes Top 5 is the smallest chip")
        XCTAssertFalse(Bar.topHasSomethingToCut(drawableOutcomes: 1), "112894")
        XCTAssertFalse(
            Bar.topHasSomethingToCut(drawableOutcomes: 5),
            "Top 5 of five rows is all five rows — every chip draws the same board")
        XCTAssertTrue(
            Bar.topHasSomethingToCut(drawableOutcomes: 6),
            "six rows: Top 5 hides one, so the group changes something")
        XCTAssertTrue(Bar.topHasSomethingToCut(drawableOutcomes: 30))
    }

    // MARK: - The group is really gone from the bar

    /// Pins the WIRING: the real bar's arms lose the group when told to. Measured off
    /// the hosted view, so a change that keeps the counts right and forgets to wrap
    /// `topGroup` fails here.
    func testTheBarsArmsDropTheTopGroupWhenItCannotCut() {
        let ranges: [EvolutionTimeRange] = [.season, .week, .day, .today]
        func bar(topAvailable: Bool) -> Bar {
            Bar(availableRanges: ranges,
                selectedRange: .constant(.week),
                showCombinedProbability: .constant(false),
                sumAvailable: true,
                topAvailable: topAvailable,
                topFilter: .constant(10))
        }

        let with = intrinsicSize(of: bar(topAvailable: true).row(chipPadding: 8))
        let without = intrinsicSize(of: bar(topAvailable: false).row(chipPadding: 8))
        XCTAssertLessThan(
            without.width, with.width - 60,
            "three chips gone must narrow the one-row arm by three chips, not a hairline")

        let tall = intrinsicSize(of: bar(topAvailable: true).wrappedRows(chipPadding: 8))
        let short = intrinsicSize(of: bar(topAvailable: false).wrappedRows(chipPadding: 8))
        XCTAssertLessThan(
            short.height, tall.height - 5,
            "the terminal arm gives Top N its own row; without it the bar is a row shorter")
    }

    /// The 112894 bar: one outcome, so neither `Sum` nor `Top N`. What is left must be
    /// exactly the range chips — nothing drawn in the gap.
    func testAOneOutcomeBarIsJustItsRanges() {
        let ranges: [EvolutionTimeRange] = [.season, .week, .day, .today]
        let bar = Bar(
            availableRanges: ranges,
            selectedRange: .constant(.week),
            showCombinedProbability: .constant(false),
            sumAvailable: Bar.sumHasSomethingToAdd(drawableOutcomes: 1),
            topAvailable: Bar.topHasSomethingToCut(drawableOutcomes: 1),
            topFilter: .constant(10))

        let row = intrinsicSize(of: bar.row(chipPadding: 8))
        let rangesOnly = intrinsicSize(of: bar.rangeGroup(chipPadding: 8))
        // The row's one group gap to its Spacer is all that may remain; the
        // narrowest control it could still be drawing (`Sum`) is ~45pt.
        XCTAssertLessThanOrEqual(row.width, rangesOnly.width + 8.5,
                                 "the one-outcome bar must be its range chips and nothing else")
    }

    /// The default keeps every existing caller — and the layout tests measuring the
    /// widest vocabulary — on the bar WITH `Top N`.
    func testTheBarStillShowsTopNByDefault() {
        let ranges: [EvolutionTimeRange] = [.season, .week]
        let defaulted = Bar(
            availableRanges: ranges, selectedRange: .constant(.week),
            showCombinedProbability: .constant(false), topFilter: .constant(10))
        let explicit = Bar(
            availableRanges: ranges, selectedRange: .constant(.week),
            showCombinedProbability: .constant(false), topAvailable: true,
            topFilter: .constant(10))

        XCTAssertEqual(
            intrinsicSize(of: defaulted.row(chipPadding: 8)).width,
            intrinsicSize(of: explicit.row(chipPadding: 8)).width, accuracy: 0.5)
    }

    // MARK: - The call site counts the served field, not the visible rows

    /// 🪤 `displayedOutcomes` is truncated BY the `Top N` chip. Counting it would let
    /// the group hide itself: tap Top 5 on a twelve-row board, the count becomes five,
    /// and the chips that could bring the other seven back disappear. The count has to
    /// be taken over the served field (minus `Field`), and both controls have to be
    /// fed it.
    func testTheChartCountsTheServedFieldForBothControls() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
        let source = try String(
            contentsOf: root.appendingPathComponent("Bain Luck/Components/EvolutionChartView.swift"),
            encoding: .utf8)
        let body = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertTrue(
            body.contains("(data?.outcomes ?? []).filter { $0.name != \"Field\" }.count"),
            "the drawable count is the served field without Field")
        XCTAssertTrue(
            body.contains("EvolutionControlBar.sumHasSomethingToAdd(drawableOutcomes: drawableOutcomeCount)"),
            "Sum must be gated on the drawable count as well as the #8158 policy")
        XCTAssertTrue(
            body.contains("topAvailable: EvolutionControlBar.topHasSomethingToCut(drawableOutcomes: drawableOutcomeCount)"),
            "Top N must be gated on the drawable count")
        XCTAssertFalse(
            body.contains("drawableOutcomes: displayedOutcomes.count"),
            "displayedOutcomes is truncated by the Top N chip itself")
    }

    /// Through `hostForMeasurement` (#4207), pinned to `.large`, for the reason the
    /// #8158 suite gives: an unpinned chip width is a function of whatever Dynamic
    /// Type the last screenshot left the simulator at.
    private func intrinsicSize<V: View>(of view: V, at size: DynamicTypeSize = .large) -> CGSize {
        let host = hostForMeasurement(view, at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: 1200, height: 2000)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(in: CGSize(
            width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude))
    }
}
