import XCTest
@testable import Bain_Luck

/// #9175 — the iPhone Score Differential draws a goal when it was read, and keeps
/// drawing the score after it.
///
/// Fixture: production's `score_history` for `/events/15196509` (Serbia home,
/// Netherlands away, 2026-09-27): 0-0 at 16:00:59Z, 0-1 at 16:30:37Z, read live
/// at 16:39Z. The chart stepped at 16:15Z (`.stepCenter`) and ended at 16:30Z.
final class ScoreStepsAtTheReadingThatSawIt9175Tests: XCTestCase {

    private func at(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

    private lazy var readings: [(date: Date, diff: Double)] = [
        (at("2026-09-27T16:30:37Z"), -1),   // arrives out of order on purpose
        (at("2026-09-27T16:00:59Z"), 0),
    ]

    func testTheChangeIsDrawnAtTheLaterReadingNotBetweenThem() {
        // stepEnd holds each value to the next reading, then steps there.
        // stepCenter (the defect) and stepStart both draw the goal early.
        XCTAssertTrue(String(describing: ScoreDifferentialChartView.actualInterpolation).contains("stepEnd"),
                      "got \(ScoreDifferentialChartView.actualInterpolation)")
    }

    func testTheLastScoreIsCarriedToTheRightEdge() {
        let edge = at("2026-09-27T16:39:00Z")
        let steps = ScoreDifferentialChartView.actualSteps(readings, carriedTo: edge)
        XCTAssertEqual(steps.map(\.date), [at("2026-09-27T16:00:59Z"), at("2026-09-27T16:30:37Z"), edge])
        XCTAssertEqual(steps.map(\.diff), [0, -1, -1], "NED 1–0 is still the score at 38'")
    }

    func testNothingIsCarriedBackwardOrPastAnEarlierEdge() {
        // An edge at or before the last reading adds nothing, and nothing is
        // ever drawn before the first reading.
        let steps = ScoreDifferentialChartView.actualSteps(readings, carriedTo: at("2026-09-27T16:30:37Z"))
        XCTAssertEqual(steps.count, 2)
        XCTAssertEqual(steps.first?.date, at("2026-09-27T16:00:59Z"))
        XCTAssertTrue(ScoreDifferentialChartView.actualSteps([], carriedTo: at("2026-09-27T16:39:00Z")).isEmpty)
    }
}
