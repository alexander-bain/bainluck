import Foundation
import XCTest
@testable import Bain_Luck

/// #1833 — the phone chart's time axis on the CORRECT domain of Alex's own
/// specimen, at the three phone widths the issue names, plus the still-served
/// contamination it was filed on.
///
/// The issue's "still owed" clause: label density/formatting at 440pt "has not
/// been re-measured on a correct 2.5-hour domain". Native's frame
/// `n297-836-kalshi-t300.png` (codex, 2026-09-22) put the axis behind the
/// bottom bar, so no rendered frame has paid it yet. This file pays the
/// PLANNER half on the real payload; the rendered half stays Native's (the
/// LOOK rig instructions are in the #1833 delivery REPORT).
///
/// SPECIMEN: `GET /api/events/15192596/history` (Blue Jays–Red Sox, 2026-08-13,
/// `commence_time` 19:07:00Z), fetched 2026-09-23 against `/health` `0411e045`.
/// Read straight off the payload, not re-derived:
///   * the LAST `espn_history` row and the last odds row are both
///     `2026-08-13T21:35:00Z`, so `sharedChartDomain` ends at 21:35:30Z
///     (`domain(upTo:)` adds 30 s);
///   * the FIRST period-bearing `espn_history` row is `19:33:13Z` (`Top 2nd`),
///     so `min(scheduled, 19:32:13)` = the scheduled 19:07:00Z;
///   * the first 75 `espn_history` rows are STILL the previous night's game —
///     `2026-08-12T23:10:10Z` onward, scores 0-0, `period: null`. The #1833
///     write-up says the backend stopped serving cross-game rows (#1828); this
///     payload shows they are still there, only with their period nulled. The
///     2-hour warm-up clamp is therefore still load-bearing, and the mutant
///     below is what it protects against.
///
/// WIDTHS: the plot area is screen − 32 card padding − 24 team gutter − 44
/// y-axis gutter (`OddsChartAxisFitTests.phonePlotWidth`, 293 at 393pt).
///   375pt → 275   390pt → 290   440pt → 340
///
/// DYNAMIC TYPE: the axis labels are `.font(.system(size: 9))` — a fixed size,
/// not a text style — so the accessibility sizes do not widen them; what they
/// widen is the team-name gutter, which is a separate, already-measured layout
/// (#3978). No arm here varies the font because the font does not vary.
///
/// NATIVE EXECUTION: NOT RUN by the author (no Xcode in the authoring
/// environment). Statically validated only; Native runs this file.
final class OddsChartAxisFitsTheRealGameDomain1833Tests: XCTestCase {

    private var utc: Calendar = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return cal
    }()

    private func date(_ iso: String) -> Date { ISO8601DateFormatter().date(from: iso)! }

    /// The domain the view derives for the specimen (see the header).
    private var correctDomain: ClosedRange<Date> {
        date("2026-08-13T19:07:00Z")...date("2026-08-13T21:35:30Z")
    }

    /// The domain the pre-#1833 `min()` produced when the prior night's rows
    /// still carried a period (the 22-hour axis Alex photographed).
    private var contaminatedDomain: ClosedRange<Date> {
        date("2026-08-12T23:33:00Z")...date("2026-08-13T21:35:30Z")
    }

    /// The worst the warm-up clamp lets through: the schedule minus two hours.
    private var clampedDomain: ClosedRange<Date> {
        date("2026-08-13T17:07:00Z")...date("2026-08-13T21:35:30Z")
    }

    private let plotWidths: [(screen: String, width: CGFloat)] = [
        ("375pt", 275), ("390pt", 290), ("440pt", 340),
    ]

    private func strideSeconds(_ plan: OddsChartView.XAxisPlan) -> TimeInterval {
        let unit: TimeInterval
        switch plan.component {
        case .minute: unit = 60
        case .hour: unit = 3600
        case .day: unit = 86400
        default: return .infinity
        }
        return unit * Double(plan.count)
    }

    /// The planner's own fit test, re-asked of the plan it chose — the property
    /// a rendered frame would show: labels that clear each other.
    private func assertLegible(_ domain: ClosedRange<Date>, width: CGFloat, screen: String,
                               file: StaticString = #filePath, line: UInt = #line) -> OddsChartView.XAxisPlan {
        let plan = OddsChartView.xAxisPlan(for: domain, plotWidth: width, calendar: utc)
        let intervals = domain.upperBound.timeIntervalSince(domain.lowerBound) / strideSeconds(plan)
        XCTAssertTrue(
            OddsChartView.xAxisFits(intervals: intervals, plotWidth: width, style: plan.labelStyle),
            "\(screen): the chosen stride (\(plan.count) \(plan.component)) does not clear at \(width)pt",
            file: file, line: line)
        return plan
    }

    /// The correct 2h28m domain reads as a game: sub-hour ticks, a time-of-day
    /// label, at least three labels, all clear — at every phone width.
    func testCorrectDomainIsLegibleAtEveryPhoneWidth() {
        for (screen, width) in plotWidths {
            let plan = assertLegible(correctDomain, width: width, screen: screen)
            XCTAssertEqual(plan.labelStyle, .timeOfDay, screen)
            XCTAssertEqual(plan.component, .minute, screen)
            let intervals = correctDomain.upperBound.timeIntervalSince(correctDomain.lowerBound)
                / strideSeconds(plan)
            XCTAssertGreaterThanOrEqual(intervals.rounded(.down), 3,
                "\(screen): a 2.5-hour game needs more than two time labels to be read")
        }
    }

    /// The widest phone gets a FINER axis than the narrowest, never a coarser
    /// one: width buys labels.
    func testWiderPhonesGetNoFewerLabels() {
        let narrow = OddsChartView.xAxisPlan(for: correctDomain, plotWidth: 275, calendar: utc)
        let wide = OddsChartView.xAxisPlan(for: correctDomain, plotWidth: 340, calendar: utc)
        XCTAssertLessThanOrEqual(strideSeconds(wide), strideSeconds(narrow))
    }

    /// The clamp's worst case (4h28m, same calendar day) is still a legible
    /// single-day axis.
    func testClampedDomainStaysLegible() {
        for (screen, width) in plotWidths {
            let plan = assertLegible(clampedDomain, width: width, screen: screen)
            XCTAssertTrue(plan.labelStyle == .timeOfDay || plan.labelStyle == .hourOfDay, screen)
        }
    }

    /// CONTROL — the defect. Without the clamp the specimen's axis spans two
    /// calendar days and 22 hours: the planner has to coarsen to hours and
    /// print a weekday on every label, which is the "timestamp soup" of the
    /// issue's title. Pinned so the clamp cannot be removed "because the
    /// backend filters those rows now" — this payload proves it does not.
    func testContaminatedDomainIsWhyTheClampExists() {
        let plan = OddsChartView.xAxisPlan(for: contaminatedDomain, plotWidth: 290, calendar: utc)
        XCTAssertTrue(plan.labelStyle == .dayAndHour || plan.labelStyle == .dayAndTime,
                      "a two-day domain must name the day: \(plan.labelStyle)")
        XCTAssertGreaterThanOrEqual(strideSeconds(plan), 3600,
                                    "22 hours cannot be labelled in minutes at 290pt")
    }

    /// The clamp itself, on the specimen's numbers — the arithmetic
    /// `EventDetailView.sharedChartDomain` performs, stated as a fact about the
    /// payload rather than re-derived from the view. If the first period-bearing
    /// ESPN row moves, this test names the new number and the header above is
    /// what must be re-read.
    func testSpecimenAnchorsToTheScheduleNotThePriorNight() {
        let scheduled = date("2026-08-13T19:07:00Z")
        let firstPeriodRow = date("2026-08-13T19:33:13Z")
        let priorNightRow = date("2026-08-12T23:33:00Z")
        let earliestPlausible = scheduled.addingTimeInterval(-2 * 60 * 60)

        // Today's payload: the first period-bearing row is after the schedule.
        XCTAssertEqual(max(min(scheduled, firstPeriodRow.addingTimeInterval(-60)), earliestPlausible), scheduled)
        // The contamination, if its period came back: held at the clamp.
        XCTAssertEqual(max(min(scheduled, priorNightRow.addingTimeInterval(-60)), earliestPlausible), earliestPlausible)
        XCTAssertEqual(earliestPlausible, date("2026-08-13T17:07:00Z"))
    }
}
