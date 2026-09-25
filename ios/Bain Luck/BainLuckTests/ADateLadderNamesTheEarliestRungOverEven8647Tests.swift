import XCTest
@testable import Bain_Luck

/// #8647 — **a "when will it happen" card names the earliest date the market
/// calls more likely than not, not the loosest one.**
///
/// THE SPECIMEN: Discover card "When will Anthropic officially announce an IPO?"
/// (futures 8430022, Kalshi), ten rungs served 2026-09-25 16:20Z (the same payload
/// the web guard `dateLadderNamesEarliestBetterThanEven8647.test.tsx` pins). Every
/// rung is a cumulative "before this date" question, so chances rise down the
/// ladder:
///
///     Before Nov 1, 2026    6%
///     Before Dec 1, 2026   56%   <- the answer
///     Before Jan 1, 2027   73%
///     …
///     Before Apr 1, 2027   90%   <- what the phone printed
///
/// `HeatMapCardView.lastAbove50Label` took the LAST point at or above 50%, a rule
/// written for comparator ladders where chances fall as the rungs climb.
final class ADateLadderNamesTheEarliestRungOverEven8647Tests: XCTestCase {

    private func date(_ label: String, _ value: Double, _ probability: Double) -> FeedDiscoverThresholdPoint {
        FeedDiscoverThresholdPoint(
            source: "date_bucket", label: label, value: value, unit: nil,
            direction: "before", probability: probability, needsSiblingMarkets: nil
        )
    }

    private func above(_ label: String, _ value: Double, _ probability: Double) -> FeedDiscoverThresholdPoint {
        FeedDiscoverThresholdPoint(
            source: "outcome", label: label, value: value, unit: nil,
            direction: "above", probability: probability, needsSiblingMarkets: nil
        )
    }

    /// The served payload's ten rungs, verbatim.
    private var anthropicIpo: [FeedDiscoverThresholdPoint] {
        [
            date("Before Oct 1, 2026", 20261001, 0.01),
            date("Before Oct 10, 2026", 20261010, 0.01),
            date("Before Oct 17, 2026", 20261017, 0.01),
            date("Before Oct 24, 2026", 20261024, 0.015),
            date("Before Nov 1, 2026", 20261101, 0.055),
            date("Before Dec 1, 2026", 20261201, 0.565),
            date("Before Jan 1, 2027", 20270101, 0.725),
            date("Before Feb 1, 2027", 20270201, 0.845),
            date("Before Mar 1, 2027", 20270301, 0.88),
            date("Before Apr 1, 2027", 20270401, 0.895),
        ]
    }

    // MARK: - The defect

    func testTheProductionDateLadderNamesDecemberNotApril() {
        XCTAssertEqual(heatMapBetterThanEvenRung(anthropicIpo)?.label, "Before Dec 1, 2026")
    }

    /// The card draws five cells; the caption reads every rung. The answer the
    /// market gives must not move with how many rungs are served.
    func testTheAnswerDoesNotDependOnHowManyRungsAreServed() {
        for count in 6...anthropicIpo.count {
            XCTAssertEqual(
                heatMapBetterThanEvenRung(Array(anthropicIpo.prefix(count)))?.label,
                "Before Dec 1, 2026",
                "with the first \(count) rungs"
            )
        }
    }

    // MARK: - Controls

    func testAComparatorLadderStillNamesItsLastRungOverEven() {
        let ladder = [
            above("Above 52", 52, 0.92),
            above("Above 58", 58, 0.88),
            above("Above 64", 64, 0.64),
            above("Above 70", 70, 0.41),
        ]
        XCTAssertEqual(heatMapBetterThanEvenRung(ladder)?.label, "Above 64")
    }

    func testAnExclusiveDateLadderReadsTheSame() {
        let ladder = [
            date("Before 2027", 20270000, 0.58),
            date("2027", 20270100, 0.24),
            date("2029 or later", 20290100, 0.08),
        ]
        XCTAssertEqual(heatMapBetterThanEvenRung(ladder)?.label, "Before 2027")
    }

    func testADateLadderWithNoRungOverEvenNamesNothing() {
        let ladder = [
            date("Before Oct 1, 2026", 20261001, 0.02),
            date("Before Nov 1, 2026", 20261101, 0.11),
            date("Before Dec 1, 2026", 20261201, 0.30),
        ]
        XCTAssertNil(heatMapBetterThanEvenRung(ladder))
    }

    /// Web's rule (`ladderKind`): a ladder is a date ladder only when EVERY rung is
    /// a `date_bucket`. One comparator rung keeps the comparator reading.
    func testAMixedLadderKeepsTheComparatorReading() {
        let ladder = [
            date("Before Dec 1, 2026", 20261201, 0.56),
            above("Above 70", 20270101, 0.73),
        ]
        XCTAssertEqual(heatMapBetterThanEvenRung(ladder)?.label, "Above 70")
    }
}
