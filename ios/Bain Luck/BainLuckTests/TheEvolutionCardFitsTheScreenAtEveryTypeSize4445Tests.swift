import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4445 — AT `.accessibility5` THE EVOLUTION CARD RAN OFF BOTH EDGES OF A 375pt
/// PHONE, and one control was the reason for all of it.
///
/// Photographed on master `a57fe0c84` (`artifacts/native-288/4445-BEFORE-a11y5-*.png`):
/// the leaderboard's rank, colour dot and logo are gone off the left edge, the
/// probability is gone off the right, the header reads `articipant … P`, the y-axis
/// reads `0` where it means `0%`, and `Reset` reads `Re`. Nothing is scrollable
/// horizontally, so all of it is simply lost.
///
/// ═══ THE CAUSE WAS NOT THE THINGS THAT WERE CLIPPED ═══
///
/// Measured at 375pt (the probe that produced these numbers is what this file
/// replaces): offered a 375pt phone, `EvolutionLeaderboardRow` demands 375 and
/// `EvolutionLeaderboardHeader` demands 375 — they FIT — while
/// `EvolutionControlBar` demands **433 at `.accessibility3`** and **545 at
/// `.accessibility5`**. A card is as wide as its widest child, so the bar set the
/// card's width and SwiftUI centred everything in it: ~85pt of ink off each edge,
/// on rows that had no width problem of their own.
///
/// **That is why this file measures the BAR and not the clipping.** A test written
/// against what the reader saw would have chased six symptoms; the defect is one
/// control with no arm that fits.
///
/// ═══ WHY THE ASSERTION IS "DEMANDS NO MORE THAN IT IS OFFERED" ═══
///
/// `EvolutionControlBarLayoutTests` already proves no CHIP wraps mid-word, and it
/// proves it at `.large`. It cannot see this defect: the bar there is drawing an arm
/// intact, at its own full height, off the side of the phone. Fitting and
/// not-wrapping are two different properties and #4445 is the one nobody measured.
@MainActor
final class TheEvolutionCardFitsTheScreenAtEveryTypeSize4445Tests: XCTestCase {

    /// iPhone SE — the narrowest phone the app ships to, and #4445's own frame.
    private let narrowPhone: CGFloat = 375
    /// iPhone 17.
    private let standardPhone: CGFloat = 402

    /// Every size a reader can actually choose. The defect is a slope, not a cliff:
    /// it starts at `.accessibility3` and is worst at `.accessibility5`, so a test
    /// that only checked the extreme would pass the day someone half-fixed it.
    private let everyTypeSize = DynamicTypeSize.allCases

    private let regularRanges: [EvolutionTimeRange] = [.season, .week, .day, .today]
    private let tournamentRanges: [EvolutionTimeRange] = [.season, .tournament, .day, .today]

    // MARK: - Measurement

    /// What the view demands when it is OFFERED exactly `width`. Anything above
    /// `width` here is ink that leaves the screen, in both directions, because a
    /// centred overflow is clipped at both ends.
    ///
    /// Hosted and laid out rather than asked for an ideal size: `ViewThatFits` picks
    /// its arm during layout, so an unhosted `sizeThatFits` is measuring a decision
    /// that has not been taken yet.
    private func demandedWidth<V: View>(
        of view: V, offered width: CGFloat, at size: DynamicTypeSize
    ) -> CGFloat {
        let host = hostForMeasurement(view, at: size)
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
            in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude)).width
    }

    private struct BarHolder: View {
        let ranges: [EvolutionTimeRange]
        let seasonWord: String
        @State var selected: EvolutionTimeRange
        @State var sum: Bool
        @State var top: Int

        init(
            ranges: [EvolutionTimeRange], seasonWord: String,
            selected: EvolutionTimeRange, sum: Bool, top: Int
        ) {
            self.ranges = ranges
            self.seasonWord = seasonWord
            _selected = State(initialValue: selected)
            _sum = State(initialValue: sum)
            _top = State(initialValue: top)
        }

        var body: some View {
            EvolutionControlBar(
                availableRanges: ranges,
                selectedRange: $selected,
                showCombinedProbability: $sum,
                topFilter: $top,
                seasonWord: seasonWord)
        }
    }

    private func outcome(name: String, prob: Double, change: Double?) -> TimelineOutcomeMeta {
        var json: [String: Any] = ["name": name, "current_probability": prob]
        if let change { json["probability_change_24h"] = change }
        let data = try! JSONSerialization.data(withJSONObject: json)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(TimelineOutcomeMeta.self, from: data)
    }

    /// The board #4445 was photographed on: `NFL Super Bowl Winner`, whose longest
    /// name is the longest in the league and whose `100%`/`-100.0%` extremes are
    /// what `EvolutionLeaderboardGeometry` sizes the columns against.
    private func photographedBoard() -> [TimelineOutcomeMeta] {
        [
            outcome(name: "Los Angeles Rams", prob: 0.113, change: nil),
            outcome(name: "San Francisco 49ers", prob: 1.0, change: 1.0),
            outcome(name: "Philadelphia Eagles", prob: 0.0, change: -1.0),
        ]
    }

    // MARK: - The acceptance

    /// THE SHIP: at every type size a reader can choose, on both phone widths and
    /// with both range vocabularies, the control bar asks for no more room than the
    /// phone has.
    func testTheControlBarNeverAsksForMoreWidthThanThePhoneHas() {
        for ranges in [regularRanges, tournamentRanges] {
            // `6M` is the other word the widest chip can carry (#7077); it is
            // narrower than `Season`, and measuring both keeps that a measurement.
            for seasonWord in ["Season", EvolutionRangeVocabulary.genericWidestWindow] {
                for width in [narrowPhone, standardPhone] {
                    for size in everyTypeSize {
                        let demanded = demandedWidth(
                            of: BarHolder(
                                ranges: ranges, seasonWord: seasonWord,
                                selected: ranges[0], sum: false, top: 10),
                            offered: width, at: size)
                        XCTAssertLessThanOrEqual(
                            demanded, width + 0.5,
                            """
                            At \(size) on a \(width)pt phone the control bar demanded \
                            \(demanded)pt — \(demanded - width)pt of it off the edges. \
                            ranges=\(ranges.map(\.rawValue)) seasonWord=\(seasonWord)
                            """)
                    }
                }
            }
        }
    }

    /// The selected chip is drawn `.semibold` and is the widest that chip ever gets,
    /// and `Top 20` is wider than `Top 5`. A bar that fits only on its defaults fits
    /// only until the reader touches it.
    func testNoSelectionMakesTheBarOverflow() {
        for range in regularRanges {
            for sum in [false, true] {
                for top in [5, 10, 20] {
                    for size in [DynamicTypeSize.accessibility3, .accessibility5] {
                        let demanded = demandedWidth(
                            of: BarHolder(
                                ranges: regularRanges, seasonWord: "Season",
                                selected: range, sum: sum, top: top),
                            offered: narrowPhone, at: size)
                        XCTAssertLessThanOrEqual(
                            demanded, narrowPhone + 0.5,
                            "at \(size) with \(range.rawValue)/sum=\(sum)/top=\(top)")
                    }
                }
            }
        }
    }

    /// The other two children of the card, pinned where they already pass.
    ///
    /// They were CLIPPED on the photographed frames and they are not the cause, so
    /// this is the test that would catch someone "fixing" the clipping by widening a
    /// column — and it is the reason the bar assertion above can be read as the
    /// whole story rather than as one of three.
    func testTheLeaderboardRowAndHeaderAlreadyFitAndMustKeepFitting() {
        for size in everyTypeSize {
            let columns = EvolutionLeaderboardGeometry.columns(
                for: photographedBoard(), at: size)
            let row = EvolutionLeaderboardRow(
                position: 1, outcome: photographedBoard()[1], color: .blue,
                isSelected: true, isHighlighted: true, columns: columns)
            XCTAssertLessThanOrEqual(
                demandedWidth(of: row, offered: narrowPhone, at: size),
                narrowPhone + 0.5, "row at \(size)")
            XCTAssertLessThanOrEqual(
                demandedWidth(
                    of: EvolutionLeaderboardHeader(columns: columns),
                    offered: narrowPhone, at: size),
                narrowPhone + 0.5, "header at \(size)")
        }
    }

    /// `everyTypeSize` is the population three assertions above sweep, and an empty
    /// or accessibility-free list would make every one of them pass without
    /// measuring the sizes #4445 is about. Pinned by NAME rather than by count so
    /// that a future `DynamicTypeSize` case does not fail this for the wrong reason.
    func testTheSweptPopulationContainsTheSizesTheDefectLivesAt() {
        for size in [DynamicTypeSize.large, .accessibility1, .accessibility3, .accessibility5] {
            XCTAssertTrue(
                everyTypeSize.contains(size),
                "\(size) is not swept — the assertions above are vacuous at the size that matters")
        }
    }

    // MARK: - The control, because "it fits" is the assertion that passes on nothing

    /// 🔴 THE ARM SET THIS SHIP REPLACED — the three arms master had, with no
    /// wrapping one behind them — hosted here so the assertion above is known to be
    /// able to fail.
    ///
    /// This is a CONTROL and deliberately not production code. A width assertion is
    /// the shape that passes on an empty render, on a view that failed to build, and
    /// on a camera pointed at nothing; without a frame that fails it, a green run
    /// proves the measurement happened, not that the bar fits.
    private struct PreFixArmSetBar: View {
        let ranges: [EvolutionTimeRange]
        @State private var selected: EvolutionTimeRange = .season
        @State private var sum = false
        @State private var top = 10

        var body: some View {
            let bar = EvolutionControlBar(
                availableRanges: ranges,
                selectedRange: $selected,
                showCombinedProbability: $sum,
                topFilter: $top)
            VStack(spacing: 8) {
                ViewThatFits(in: .horizontal) {
                    bar.row(chipPadding: EvolutionControlBar.chipPaddings[0])
                    bar.row(chipPadding: EvolutionControlBar.chipPaddings[1])
                    bar.stackedRows(chipPadding: EvolutionControlBar.chipPaddings[0])
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }

    func testTheControlReproducesTheOverflowThisShipFixed() {
        // At `.large` the old arm set was right, and saying so is what makes the
        // failures below a Dynamic Type defect rather than a broken measurement.
        XCTAssertLessThanOrEqual(
            demandedWidth(of: PreFixArmSetBar(ranges: regularRanges),
                          offered: narrowPhone, at: .large),
            narrowPhone + 0.5,
            "the control overflowed at .large, where master was correct — the camera is wrong")

        for size in [DynamicTypeSize.accessibility3, .accessibility5] {
            XCTAssertGreaterThan(
                demandedWidth(of: PreFixArmSetBar(ranges: regularRanges),
                              offered: narrowPhone, at: size),
                narrowPhone + 0.5,
                """
                The control did not overflow at \(size), so the width camera cannot \
                see #4445 and every assertion in this file is unfalsifiable.
                """)
        }
    }

    /// And the fix is reached by WRAPPING, not by the bar quietly shrinking its
    /// chips: the terminal arm puts the range chips on more than one line at
    /// `.accessibility5`, which is the behaviour that buys the fit.
    func testTheTerminalArmIsTallerThanTheGroupItWraps() {
        let bar = EvolutionControlBar(
            availableRanges: regularRanges,
            selectedRange: .constant(.season),
            showCombinedProbability: .constant(false),
            topFilter: .constant(10))
        let host = hostForMeasurement(
            bar.rangeGroup(chipPadding: EvolutionControlBar.chipPaddings[0], wraps: true)
                .frame(width: 343),
            at: .accessibility5)
        let wrapped = host.sizeThatFits(
            in: CGSize(width: 343, height: CGFloat.greatestFiniteMagnitude)).height
        let oneLine = hostForMeasurement(
            bar.rangeGroup(chipPadding: EvolutionControlBar.chipPaddings[0]),
            at: .accessibility5
        ).sizeThatFits(
            in: CGSize(
                width: CGFloat.greatestFiniteMagnitude,
                height: CGFloat.greatestFiniteMagnitude)).height
        XCTAssertGreaterThan(
            wrapped, oneLine + 0.5,
            "the range group did not wrap at .accessibility5 — it fit by some other means")
    }
}
