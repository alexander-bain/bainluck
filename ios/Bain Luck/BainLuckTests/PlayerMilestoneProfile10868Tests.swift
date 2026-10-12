import XCTest
@testable import Bain_Luck

/// #10868 — the Atlas v6 milestone profile is drawn from the SAME rungs the
/// pre-game target chips print, and refuses every ladder the chips themselves
/// would not vouch for as a shape.
///
/// What these pin, and the mutation each kills:
/// - draw unpriced rungs as dots → `testUnpricedRungsAreNotDrawn`
/// - drop the #5137 flat-ladder refusal → `testAFlatLadderDrawsNoProfile`
/// - pick one of two quotes for one line → `testTwoQuotesForOneLineDrawNoProfile`
/// - lose the chip index (picked chip ≠ large dot) → `testEachMarkKeepsItsChipIndex`
/// - lower the three-line floor → `testTwoPricedLinesAreAChoiceNotAShape`
/// - let the axis run below zero → `testTheAxisPadsHalfAStepAndNeverGoesBelowZero`
/// - tick between the lines ("0.5" under touchdowns) → `testAxisTicksAreTheQuotedLinesOnly`
final class PlayerMilestoneProfile10868Tests: XCTestCase {

    /// D'Andre Swift rushing yards, the atlas's first NFL profile, as rungs.
    private let yards: [Double] = [39.5, 49.5, 59.5, 69.5, 79.5, 89.5]
    private let chances: [Double?] = [0.76, 0.64, 0.53, 0.40, 0.295, 0.22]

    func testAPricedLadderOfThreeOrMoreLinesDrawsEveryLineInOrder() throws {
        let profile = try XCTUnwrap(
            PlayerMilestoneProfile.profile(thresholds: yards.reversed(), probabilities: chances.reversed()))
        XCTAssertEqual(profile.milestones.map(\.threshold), yards)
        XCTAssertEqual(profile.milestones.map(\.probability), chances.compactMap { $0 })
    }

    func testEachMarkKeepsItsChipIndex() throws {
        let profile = try XCTUnwrap(
            PlayerMilestoneProfile.profile(thresholds: yards, probabilities: chances))
        XCTAssertEqual(profile.milestones.map(\.index), Array(yards.indices))
    }

    func testUnpricedRungsAreNotDrawn() throws {
        var withHole = chances
        withHole[2] = nil
        let profile = try XCTUnwrap(
            PlayerMilestoneProfile.profile(thresholds: yards, probabilities: withHole))
        XCTAssertFalse(profile.milestones.contains { $0.threshold == 59.5 })
        XCTAssertEqual(profile.milestones.map(\.index), [0, 1, 3, 4, 5],
                       "the rest keep their chip indices across the hole")
    }

    func testTwoPricedLinesAreAChoiceNotAShape() {
        XCTAssertNil(PlayerMilestoneProfile.profile(
            thresholds: [1, 2, 3], probabilities: [0.36, 0.08, nil]))
        XCTAssertNotNil(PlayerMilestoneProfile.profile(
            thresholds: [1, 2, 3], probabilities: [0.36, 0.08, 0.02]))
    }

    func testAFlatLadderDrawsNoProfile() {
        XCTAssertNil(PlayerMilestoneProfile.profile(
            thresholds: [0.5, 1.5, 2.5, 3.5], probabilities: [0.5, 0.5, 0.5, 0.5]))
    }

    func testTwoQuotesForOneLineDrawNoProfile() {
        XCTAssertNil(PlayerMilestoneProfile.profile(
            thresholds: [49.5, 49.5, 59.5, 69.5], probabilities: [0.62, 0.66, 0.5, 0.4]))
    }

    func testAChanceOutsideZeroToOneIsNotDrawn() throws {
        let profile = try XCTUnwrap(PlayerMilestoneProfile.profile(
            thresholds: [10, 20, 30, 40], probabilities: [0.8, 1.2, 0.4, 0.2]))
        XCTAssertEqual(profile.milestones.map(\.threshold), [10, 30, 40])
    }

    func testTheAxisPadsHalfAStepAndNeverGoesBelowZero() throws {
        let profile = try XCTUnwrap(
            PlayerMilestoneProfile.profile(thresholds: yards, probabilities: chances))
        XCTAssertEqual(profile.domain.lowerBound, 34.5, accuracy: 1e-9)
        XCTAssertEqual(profile.domain.upperBound, 94.5, accuracy: 1e-9)

        // Whole-number lines, as served for touchdowns ("1+", "2+").
        let touchdowns = try XCTUnwrap(PlayerMilestoneProfile.profile(
            thresholds: [1, 2, 3], probabilities: [0.36, 0.08, 0.02]))
        XCTAssertEqual(touchdowns.domain.lowerBound, 0.5, accuracy: 1e-9)
        XCTAssertEqual(touchdowns.domain.upperBound, 3.5, accuracy: 1e-9)

        // Half-step padding that would cross zero stops at zero.
        let halfLines = try XCTUnwrap(PlayerMilestoneProfile.profile(
            thresholds: [0.5, 1.5, 2.5], probabilities: [0.36, 0.08, 0.02]))
        XCTAssertEqual(halfLines.domain.lowerBound, 0, accuracy: 1e-9)
    }

    func testAxisTicksAreTheQuotedLinesOnly() throws {
        var withHole: [Double?] = [0.36, 0.08, 0.02, 0.01]
        withHole[3] = nil
        let touchdowns = try XCTUnwrap(PlayerMilestoneProfile.profile(
            thresholds: [1, 2, 3, 4], probabilities: withHole))
        XCTAssertEqual(touchdowns.axisLines, [1, 2, 3],
                       "no tick between lines and none for an unpriced line")
        XCTAssertEqual(touchdowns.axisLines.map(PlayerPropsFamily.targetLabel), ["1+", "2+", "3+"])
    }

    func testMismatchedInputsDrawNothing() {
        XCTAssertNil(PlayerMilestoneProfile.profile(
            thresholds: [1, 2, 3], probabilities: [0.6, 0.4]))
    }

    func testVoiceOverReadsTheSameNumbersTheChipsPrint() throws {
        let profile = try XCTUnwrap(PlayerMilestoneProfile.profile(
            thresholds: [1, 2, 3], probabilities: [0.36, 0.08, 0.024]))
        XCTAssertEqual(
            PlayerMilestoneProfile.spokenSummary(profile, stat: "Touchdowns"),
            "Touchdowns, chance to reach each line: 1+ 36%, 2+ 8%, 3+ 2%")
    }
}
