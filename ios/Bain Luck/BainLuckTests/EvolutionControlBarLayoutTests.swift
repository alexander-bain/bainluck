import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4199 — the Evolution chart's control bar wrapped its own words at every phone
/// width, and the control that decides what the chart is showing became unreadable.
///
/// Photographed on master, `bainluck://futures/86832`:
///
/// * **402pt** (`artifacts-native-082/BEFORE-4199-p402b.png`)
///   `Sea/son  7d  24/h  To-/day  [ ]Sum  Top/5 Top/10 Top/20`
/// * **375pt** (#4199's own frame) — roughly one character per line: `Se/aso/n`
///
/// Three independent groups competed for one row, and `Text` was the only thing in
/// it that could give, so SwiftUI took the width out of the words.
///
/// ═══ WHY THESE TESTS COMPARE THE VIEW WITH ITSELF ═══
///
/// Every number here is measured off the real `EvolutionControlBar`, and none of
/// them is a literal anybody chose. The production fix is `ViewThatFits`, which
/// measures the real chips at the real text size; a geometry model asserting the
/// same thing in parallel arithmetic would be a second copy that can drift — the
/// failure #3817 spent a whole ship undoing. So there is no model: the suite hosts
/// the view.
///
/// "Did a chip wrap?" is therefore answered WITHOUT knowing which arm was chosen.
/// Each arm is laid out unconstrained, where nothing can be forced to wrap, and
/// those heights become the permitted set. A wrap adds a line to a chip, so it
/// lands the bar on a height that is in none of them.
///
/// ⚠️ AND THE PERMITTED SET IS ITSELF CHECKED AGAINST THE REAL DEFECT: the control
/// below reproduces the pre-fix chips, and the suite asserts its wrapped height is
/// NOT in the permitted set. Otherwise a set generous enough to contain the bug
/// would make every assertion above unfalsifiable — which is the shape this ship
/// already found once in #4351's scan.
@MainActor
final class EvolutionControlBarLayoutTests: XCTestCase {

    // MARK: - Widths the app really has to draw at

    /// iPhone SE — the narrowest phone #3966 names.
    private let narrowPhone: CGFloat = 375
    /// iPhone 17.
    private let standardPhone: CGFloat = 402
    /// Wide enough that nothing in this bar can be forced to wrap, so the height
    /// measured here IS the one-line height, discovered rather than declared.
    private let unconstrained: CGFloat = 1200

    /// The two vocabularies `availableRanges` can produce. The mid-tournament one
    /// is not a curiosity — `Event` is a fifth string the bar has to fit, and
    /// #4199's acceptance names it.
    private let regularRanges: [EvolutionTimeRange] = [.season, .week, .day, .today]
    private let tournamentRanges: [EvolutionTimeRange] = [.season, .tournament, .day, .today]

    // MARK: - Measurement

    private func height<V: View>(of view: V, width: CGFloat, at size: DynamicTypeSize = .large) -> CGFloat {
        let host = hostForMeasurement(view.frame(width: width), at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 2000))
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        return host.sizeThatFits(
            in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude)).height
    }

    private func bar(
        _ ranges: [EvolutionTimeRange],
        selected: EvolutionTimeRange = .season,
        sum: Bool = false,
        top: Int = 10
    ) -> some View {
        StateHolder(ranges: ranges, selected: selected, sum: sum, top: top)
    }

    /// `EvolutionControlBar` takes bindings, so the measurement needs something to
    /// own the state. Nothing here varies during a measurement.
    private struct StateHolder: View {
        let ranges: [EvolutionTimeRange]
        @State var selected: EvolutionTimeRange
        @State var sum: Bool
        @State var top: Int

        init(ranges: [EvolutionTimeRange], selected: EvolutionTimeRange, sum: Bool, top: Int) {
            self.ranges = ranges
            _selected = State(initialValue: selected)
            _sum = State(initialValue: sum)
            _top = State(initialValue: top)
        }

        var body: some View {
            EvolutionControlBar(
                availableRanges: ranges,
                selectedRange: $selected,
                showCombinedProbability: $sum,
                topFilter: $top
            )
        }
    }

    // MARK: - The acceptance

    /// The heights the bar is ALLOWED to have: one per arm, each measured
    /// unconstrained so no chip in it can have wrapped.
    ///
    /// A wrap adds a line to a chip, so it produces a height that is in none of
    /// these. That is the whole test, and it does not require knowing which arm
    /// `ViewThatFits` chose — only that the bar is drawing one of them intact.
    private func permittedHeights(_ ranges: [EvolutionTimeRange]) -> [CGFloat] {
        let probe = EvolutionControlBar(
            availableRanges: ranges,
            selectedRange: .constant(ranges[0]),
            showCombinedProbability: .constant(false),
            topFilter: .constant(10))
        return EvolutionControlBar.chipPaddings.map {
            height(of: probe.row(chipPadding: $0), width: unconstrained)
        } + [height(of: probe.stackedRows(chipPadding: EvolutionControlBar.chipPaddings[0]),
                    width: unconstrained)]
    }

    private func assertNoChipWrapped(
        _ ranges: [EvolutionTimeRange], selected: EvolutionTimeRange, sum: Bool, top: Int,
        width: CGFloat, permitted: [CGFloat], line: UInt = #line
    ) {
        // The bar adds its own 16pt vertical padding around whichever arm it draws;
        // `permitted` is measured on the bare arms, so compare the difference.
        let drawn = height(of: bar(ranges, selected: selected, sum: sum, top: top), width: width)
        let matched = permitted.contains { abs(drawn - ($0 + 16)) < 0.5 }
        XCTAssertTrue(
            matched,
            """
            At \(width)pt the bar drew \(drawn)pt, which is not any arm's own height \
            (\(permitted.map { $0 + 16 })) — so a chip wrapped. \
            ranges=\(ranges.map(\.rawValue)) selected=\(selected.rawValue) sum=\(sum) top=\(top)
            """,
            line: line)
    }

    func testNoChipWrapsAtAnyPhoneWidth() {
        for ranges in [regularRanges, tournamentRanges] {
            let permitted = permittedHeights(ranges)
            for width in [narrowPhone, standardPhone] {
                assertNoChipWrapped(ranges, selected: ranges[0], sum: false, top: 10,
                                    width: width, permitted: permitted)
            }
        }
    }

    /// Every chip is measured with the selection on it, because the selected chip
    /// is drawn `.semibold` and is therefore the WIDEST that chip ever gets. A
    /// suite that only ever measured the default selection would pass while the
    /// bar wrapped for a reader who had tapped `Season`.
    func testNoSelectionMakesAChipWrap() {
        for ranges in [regularRanges, tournamentRanges] {
            let permitted = permittedHeights(ranges)
            for range in ranges {
                for sum in [false, true] {
                    for top in [5, 10, 20] {
                        assertNoChipWrapped(ranges, selected: range, sum: sum, top: top,
                                            width: narrowPhone, permitted: permitted)
                    }
                }
            }
        }
    }

    // MARK: - The control, because a height comparison that cannot fail proves nothing

    /// The pre-fix chips, copied from `origin/master` `edf9fe13` — no `lineLimit`,
    /// no `fixedSize`, 8pt padding — in the same three groups.
    ///
    /// This is a CONTROL and deliberately not production code. Its whole job is to
    /// fail the assertion above, so that a green run of `testTheBarIsOneLineTall…`
    /// means the tree is fixed rather than the camera is broken. A negative layout
    /// assertion is exactly the shape that passes on an empty render.
    private struct PreFixControlBar: View {
        let ranges: [EvolutionTimeRange]

        var body: some View {
            VStack(spacing: 8) {
                HStack(spacing: 8) {
                    HStack(spacing: 0) {
                        ForEach(ranges) { range in
                            Text(range.rawValue)
                                .font(.caption2)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 5)
                        }
                    }
                    Spacer()
                    HStack(spacing: 4) {
                        Image(systemName: "square").font(.system(size: 11))
                        Text("Sum").font(.caption2).fontWeight(.medium)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    HStack(spacing: 0) {
                        ForEach([5, 10, 20], id: \.self) { n in
                            Text("Top \(n)")
                                .font(.caption2)
                                .fontWeight(.medium)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 5)
                        }
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }

    func testTheControlReproducesTheDefectThisShipFixed() {
        let control = PreFixControlBar(ranges: regularRanges)
        let oneLine = height(of: control, width: unconstrained)

        // The defect #4199 photographed: taller at BOTH phone widths, so it is not
        // a narrow-phone edge case.
        XCTAssertGreaterThan(
            height(of: control, width: narrowPhone), oneLine + 0.5,
            "the control did not wrap at 375pt — the height camera cannot see wrapping")
        XCTAssertGreaterThan(
            height(of: control, width: standardPhone), oneLine + 0.5,
            "the control did not wrap at 402pt — #4199 photographed it wrapping there")

        // …and the wrap it produces is a height the real bar is NOT allowed to have,
        // which is what `assertNoChipWrapped` keys on. Without this the acceptance
        // could be satisfied by a permitted-height list that happens to be generous.
        let permitted = permittedHeights(regularRanges).map { $0 + 16 }
        for width in [narrowPhone, standardPhone] {
            let wrapped = height(of: control, width: width)
            XCTAssertFalse(
                permitted.contains { abs(wrapped - $0) < 0.5 },
                "the wrapped control's \(wrapped)pt is inside the permitted set \(permitted) — the acceptance cannot fail")
        }
    }

    // MARK: - The row's real ink, so the numbers behind ViewThatFits are on record

    /// Not an assertion about which arm gets picked — a test cannot ask
    /// `ViewThatFits` that. It pins the property the LAST arm has to have: it is
    /// narrow enough that there is always something for `ViewThatFits` to choose,
    /// so the bar can never fall off the end of its own list.
    ///
    /// ⚠️ **THE FIRST VERSION OF THIS TEST WAS GREEN WHILE THE APP CLIPPED A CHIP.**
    /// It compared the tightest single-row arm against `375 − 32 = 343pt` and
    /// passed at 335pt — but 343 was an ASSUMED content width. The screenshot
    /// (`artifacts-native-082/AFTER-4199-se375.png`) showed `Top 20` cut off at the
    /// right edge: the bar lives inside a card that is itself inset, so the real
    /// content is nearer 310pt. An assumed bound is not a measurement, and this one
    /// was wrong in the direction that reads as a pass.
    ///
    /// So the threshold is no longer an arithmetic guess about the page. The last
    /// arm stacks the groups over two rows, making its width the wider of the two
    /// rows rather than the sum of three groups — comfortably inside any phone —
    /// and the fit itself is proven by photograph, not by a subtraction.
    func testTheLastArmIsNarrowerThanAnythingItHasToFitInside() {
        let widths = EvolutionControlBar.chipPaddings.map { naturalWidth(of: probe.row(chipPadding: $0)) }
        let stacked = naturalWidth(of: probe.stackedRows(chipPadding: EvolutionControlBar.chipPaddings[0]))

        // Roomiest first, and the rung really does buy width — an arm that bought
        // nothing would be one `ViewThatFits` could never usefully fall to.
        XCTAssertEqual(widths, widths.sorted(by: >), "chipPaddings is not roomiest-first: \(widths)")

        // Eight chips (4 ranges + Sum + 3 Top), so one point of padding is worth
        // 16pt across the row: 8pt → 5pt should buy about 48.
        XCTAssertEqual(widths[0] - widths[1], 48, accuracy: 3,
                       "the padding arithmetic does not match the chip count")

        // The whole reason the last arm exists: it is dramatically narrower than
        // any single-row arm, which is what makes it a terminal arm rather than
        // another rung that can also overflow.
        XCTAssertLessThan(stacked, widths.min()! - 100,
                          "the stacked arm is not meaningfully narrower (\(stacked) vs \(widths))")

        // 310pt is the card's measured content width on the narrowest phone, read
        // off the 375pt frame rather than derived from the screen width.
        XCTAssertLessThan(
            stacked, 310,
            "the stacked arm (\(stacked)pt) does not fit an iPhone SE card, and there is no arm behind it")
    }

    /// The stacked arm is a second ROW, never a second LINE inside a chip. That
    /// distinction is the whole ship, so it is asserted rather than assumed.
    func testTheStackedArmsChipsAreStillWhole() {
        let padding = EvolutionControlBar.chipPaddings[0]
        let stacked = probe.stackedRows(chipPadding: padding)
        let unconstrainedHeight = height(of: stacked, width: unconstrained)

        // Squeeze it well below any real phone. `fixedSize` means the chips keep
        // their words no matter how mean the container is, so the height must not
        // move — if a chip wrapped, this grows.
        for width in [narrowPhone, standardPhone, 280] as [CGFloat] {
            XCTAssertEqual(
                height(of: stacked, width: width), unconstrainedHeight, accuracy: 0.5,
                "a chip in the stacked arm wrapped at \(width)pt")
        }
    }

    /// One `EvolutionControlBar` to measure arms off. The bindings are inert —
    /// nothing here mutates during a measurement.
    private var probe: EvolutionControlBar {
        EvolutionControlBar(
            availableRanges: regularRanges,
            selectedRange: .constant(.season),
            showCombinedProbability: .constant(false),
            topFilter: .constant(10))
    }

    private func naturalWidth<V: View>(of view: V) -> CGFloat {
        let host = hostForMeasurement(view)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }
}
