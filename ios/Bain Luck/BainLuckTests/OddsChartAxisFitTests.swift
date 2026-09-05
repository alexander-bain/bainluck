import SwiftUI
import XCTest
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

/// #3269 — the MATCH chart's time axis must not print a time that never happened.
///
/// THE DEFECT, photographed on a build of master `77cb2d40` (iPhone 17 simulator,
/// 2026-09-05 10:16 PT, Ball State @ Ohio State, event 14793398): the axis read
///
///     12:30 PM · 2:40 PM · 12:50 PM · 1:00 PM · 1:10 PM
///
/// "2:40 PM" between 12:30 and 12:50 is not a late label — it is `12:40 PM` with
/// its leading "1" drawn on top of the previous label's "M". Measured off the
/// screenshot at 3.07px/pt: ticks 60.3pt apart, the first label's ink ending at
/// the exact point the second label's ink begins.
///
/// THE CAUSE is #3237, this lane's own previous ship, and it is the same lesson
/// that fix wrote down: **a rule that MOVES an element invalidates every spacing
/// decision taken before the move.** #3237 anchored the two END labels inward so
/// they could not truncate at the plot's edges. The stride ladder that decides
/// how many labels to draw was calibrated when every label was CENTRED, where a
/// neighbouring pair clears at one label width of tick spacing. An inward-anchored
/// end label needs one and a half.
///
/// So the fit stops being a count budget and becomes geometry: the axis is handed
/// the plot's measured width and asks whether the labels actually clear.
final class OddsChartAxisFitTests: XCTestCase {

    /// The plot area on the phone the defect was photographed on: 393pt screen
    /// − 32pt card padding − 24pt rotated team-label gutter − 44pt y-axis gutter.
    /// `PeriodChipGeometry.plotWidthPoints` (337) is the same measurement without
    /// the y-axis gutter, which the chip strip is positioned inside of.
    private let phonePlotWidth: CGFloat = 293

    private var utc: Calendar = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return cal
    }()

    private func date(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

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

    // MARK: - The reported defect

    /// 14793398's own domain, to the minute: first quarter of a noon kickoff,
    /// 47 minutes wide once `xAxisDomain`'s 2% padding is applied.
    private var ohioStateDomain: ClosedRange<Date> {
        date("2026-09-05T16:29:00Z")...date("2026-09-05T17:16:00Z")
    }

    /// The chart that printed "2:40 PM" must not choose that stride again.
    func testTheAxisThatPrintedATimeThatNeverHappenedNoLongerFits() {
        let plan = OddsChartView.xAxisPlan(
            for: ohioStateDomain, plotWidth: phonePlotWidth, calendar: utc)

        XCTAssertGreaterThan(
            strideSeconds(plan), 600,
            "the 10-minute stride is the one that collided at this width")

        let intervals = ohioStateDomain.upperBound
            .timeIntervalSince(ohioStateDomain.lowerBound) / strideSeconds(plan)
        let spacing = phonePlotWidth / CGFloat(intervals)
        let required = OddsChartView.xAxisRequiredSpacing(
            labelWidth: OddsChartView.xAxisLabelWidth(for: plan.labelStyle),
            labelCount: Int(intervals.rounded(.down)) + 1)
        XCTAssertGreaterThanOrEqual(
            spacing, required,
            "chose \(Int(strideSeconds(plan)))s ticks: \(spacing)pt apart, needs \(required)pt")
    }

    /// The pre-fix rule, re-run against the new arithmetic, so the guard is proved
    /// to FIRE rather than merely to pass. The count budget said 6 labels of this
    /// style fit; the geometry says this pair touches.
    func testTheOldCountBudgetWouldStillHaveAcceptedTheCollidingStride() {
        let duration = ohioStateDomain.upperBound
            .timeIntervalSince(ohioStateDomain.lowerBound)
        let tenMinuteIntervals = duration / 600

        XCTAssertLessThanOrEqual(
            tenMinuteIntervals, 6,
            "the count budget passed this axis — that is why it shipped")
        XCTAssertFalse(
            OddsChartView.xAxisFits(
                intervals: tenMinuteIntervals, plotWidth: phonePlotWidth, style: .timeOfDay),
            "…and the geometric fit must reject it")
    }

    /// The rung the fit needs to land on. A completed baseball game is 130-180
    /// minutes, which is the single most common chart in the app, and it is
    /// exactly the span that falls off the 30-minute rung once the end pairs are
    /// charged properly. Without a 45-minute rung it lands on HOURS: measured on
    /// 15302914 (Arizona @ Houston, 155 minutes) the axis read `9 PM · 10 PM`.
    func testATwoAndAHalfHourGameKeepsAMinuteAxis() {
        let range = date("2026-09-05T00:10:00Z")...date("2026-09-05T02:45:00Z")
        let plan = OddsChartView.xAxisPlan(
            for: range, plotWidth: phonePlotWidth, calendar: utc)

        XCTAssertEqual(plan.labelStyle, .timeOfDay, "a 2½-hour game still reads in minutes")
        let labels = range.upperBound.timeIntervalSince(range.lowerBound) / strideSeconds(plan)
        XCTAssertGreaterThanOrEqual(labels, 3, "two labels is not an axis for a whole game")
    }

    // MARK: - The rule

    /// Interior labels are centred and end labels are not, so the two pairs have
    /// different costs. Stating the ratio here is what stops the next person from
    /// "simplifying" the end pair back down to one label width.
    func testEndPairsCostHalfALabelMoreThanInteriorPairs() {
        let width: CGFloat = 40
        let gap = OddsChartView.xAxisLabelMinGap

        XCTAssertEqual(
            OddsChartView.xAxisRequiredSpacing(labelWidth: width, labelCount: 5),
            1.5 * width + gap,
            "one end label anchored inward, one neighbour centred")
        XCTAssertEqual(
            OddsChartView.xAxisRequiredSpacing(labelWidth: width, labelCount: 2),
            2 * width + gap,
            "two labels are BOTH end labels, growing towards each other")
    }

    /// An unmeasured plot keeps the old behaviour exactly. This is the first
    /// frame, before the overlay reports a width, and it must not draw a
    /// different axis from the one that lands a moment later at a coarser stride
    /// — it may only be no worse than what shipped.
    func testUnmeasuredPlotFallsBackToTheCountBudget() {
        let planWithoutWidth = OddsChartView.xAxisPlan(for: ohioStateDomain, calendar: utc)
        XCTAssertEqual(strideSeconds(planWithoutWidth), 600, "the documented fallback")
        XCTAssertEqual(planWithoutWidth.labelStyle, .timeOfDay)
    }

    /// A zero-width plot must not divide by it.
    func testZeroWidthPlotIsSafe() {
        XCTAssertFalse(
            OddsChartView.xAxisFits(intervals: 4, plotWidth: 0, style: .timeOfDay))
        let instant = date("2026-09-05T12:00:00Z")
        let plan = OddsChartView.xAxisPlan(
            for: instant...instant, plotWidth: phonePlotWidth, calendar: utc)
        XCTAssertEqual(plan.count, 5, "a zero-width domain still gets the finest stride")
    }

    // MARK: - Every span, not just the reported one

    /// The property the count budget violated: at phone width, NO span from ten
    /// minutes to a year may choose a stride whose labels touch. This is the test
    /// that would have caught #3269 the day #3237 shipped.
    func testNoSpanFromTenMinutesToAYearDrawsLabelsThatTouch() {
        let start = date("2026-09-05T00:00:00Z")
        var span: TimeInterval = 600
        while span <= 365 * 86400 {
            let range = start...start.addingTimeInterval(span)
            let plan = OddsChartView.xAxisPlan(
                for: range, plotWidth: phonePlotWidth, calendar: utc)
            let intervals = span / strideSeconds(plan)
            if intervals > 0 {
                let spacing = phonePlotWidth / CGFloat(intervals)
                let required = OddsChartView.xAxisRequiredSpacing(
                    labelWidth: OddsChartView.xAxisLabelWidth(for: plan.labelStyle),
                    labelCount: Int(intervals.rounded(.down)) + 1)
                XCTAssertGreaterThanOrEqual(
                    spacing, required,
                    "span \(Int(span))s: \(plan.labelStyle) labels \(spacing)pt apart")
            }
            span *= 1.25
        }
    }

    /// …and the axis must still SAY something at every one of those spans. A fit
    /// rule that answers "draw nothing" is not a fix, and coarsening until the
    /// labels clear is exactly the failure mode to watch for.
    func testEverySpanStillDrawsAtLeastTwoLabels() {
        let start = date("2026-09-05T00:00:00Z")
        var span: TimeInterval = 600
        while span <= 365 * 86400 {
            let range = start...start.addingTimeInterval(span)
            let plan = OddsChartView.xAxisPlan(
                for: range, plotWidth: phonePlotWidth, calendar: utc)
            XCTAssertGreaterThanOrEqual(
                span / strideSeconds(plan), 1,
                "span \(Int(span))s coarsened past its own domain")
            span *= 1.25
        }
    }

    /// A wider plot is allowed to say MORE, or at least never less. iPad and the
    /// fullscreen sheet are the same chart with more room, and a fit rule that
    /// ignored the extra room would waste it.
    func testAWiderPlotNeverDrawsFewerLabelsThanANarrowOne() {
        let start = date("2026-09-05T00:00:00Z")
        var span: TimeInterval = 900
        while span <= 30 * 86400 {
            let range = start...start.addingTimeInterval(span)
            let narrow = OddsChartView.xAxisPlan(for: range, plotWidth: 293, calendar: utc)
            let wide = OddsChartView.xAxisPlan(for: range, plotWidth: 700, calendar: utc)
            XCTAssertLessThanOrEqual(
                strideSeconds(wide), strideSeconds(narrow),
                "span \(Int(span))s: 700pt of plot must not be coarser than 293pt")
            span *= 1.4
        }
    }

    // MARK: - Two ticks may never print the same label

    /// #3269's second defect, found by photographing the fix: the 45-minute rung
    /// above put a sub-hour stride on a domain that crosses midnight, `dayAndHour`
    /// dropped the minutes, and the walk-off chart (15302915, 9:40 PM - 12:15 AM)
    /// drew **Fri 9 PM · Fri 10 PM · Fri 11 PM · Fri 11 PM**.
    ///
    /// Two ticks 45 minutes apart printing one label is the same lie as a wrong
    /// time — worse, arguably, because it looks deliberate. The rule is that a
    /// label carries every field that changes between neighbouring ticks.
    func testTheWalkOffChartDoesNotPrintTheSameHourTwice() {
        // 15302915's own domain: 01:40Z-04:15Z, which is 9:40 PM - 12:15 AM in
        // the app's own timezone and therefore crosses a calendar day.
        var eastern = Calendar(identifier: .gregorian)
        eastern.timeZone = TimeZone(identifier: "America/New_York")!
        let range = date("2026-09-05T01:40:00Z")...date("2026-09-05T04:15:00Z")
        let plan = OddsChartView.xAxisPlan(
            for: range, plotWidth: phonePlotWidth, calendar: eastern)

        XCTAssertEqual(
            Set(labels(plan, over: range, calendar: eastern)).count,
            labels(plan, over: range, calendar: eastern).count,
            "the axis printed \(labels(plan, over: range, calendar: eastern))")
    }

    /// The property, over the whole continuum. A style that omits a field the
    /// stride changes is a bug at every span that reaches it, not just at the one
    /// somebody photographed.
    func testNoSpanEverPrintsTwoIdenticalLabels() {
        var eastern = Calendar(identifier: .gregorian)
        eastern.timeZone = TimeZone(identifier: "America/New_York")!
        // Start at 9:40 PM local so the sub-hour multi-day case is reached, not
        // just skirted (gotcha #44: offset first, then step).
        let start = date("2026-09-05T01:40:00Z")
        var span: TimeInterval = 600
        while span <= 3 * 365 * 86400 {
            let range = start...start.addingTimeInterval(span)
            let plan = OddsChartView.xAxisPlan(
                for: range, plotWidth: phonePlotWidth, calendar: eastern)
            let drawn = labels(plan, over: range, calendar: eastern)
            XCTAssertEqual(
                Set(drawn).count, drawn.count,
                "span \(Int(span))s (\(plan.labelStyle)) printed \(drawn)")
            span *= 1.25
        }
    }

    /// The labels the chart will actually draw, in tick order: the domain stepped
    /// by the plan's own stride and formatted by the plan's own format.
    private func labels(
        _ plan: OddsChartView.XAxisPlan, over range: ClosedRange<Date>, calendar: Calendar
    ) -> [String] {
        var format = plan.format
        format.locale = Locale(identifier: "en_US")
        format.timeZone = calendar.timeZone
        format.calendar = calendar

        var out: [String] = []
        var tick = range.lowerBound
        while tick <= range.upperBound && out.count < 40 {
            out.append(format.format(tick))
            tick = tick.addingTimeInterval(strideSeconds(plan))
        }
        return out
    }

    // MARK: - The pinned label widths are re-measured, not trusted

    #if canImport(UIKit)
    /// Every label each style can print, rendered with the axis's own font, must
    /// fit under the constant the fit rule divides by. A guessed budget is what
    /// put a wrong time on the axis; this one is measured on every run.
    ///
    /// Measured in `en_US`, which is what the app ships to today. A locale whose
    /// labels are wider would crowd the axis again rather than break it, so the
    /// widest of a small locale set is asserted too — if one of them ever exceeds
    /// the constant, this test says so before a reader does.
    func testPinnedLabelWidthsCoverEveryLabelTheStyleCanPrint() {
        let font = UIFont.systemFont(ofSize: 9)
        let locales = ["en_US", "en_GB", "de_DE", "fr_FR"].map(Locale.init(identifier:))

        for style in [OddsChartView.XAxisPlan.LabelStyle.timeOfDay, .hourOfDay,
                      .dayAndHour, .dayAndTime, .calendarDay, .monthAndYear] {
            var widest: (label: String, width: CGFloat) = ("", 0)
            for locale in locales {
                var format = OddsChartView.XAxisPlan(
                    component: .hour, count: 1, labelStyle: style).format
                format.locale = locale
                format.timeZone = TimeZone(identifier: "UTC")!
                format.calendar = utc
                for sample in Self.labelSamples {
                    let text = format.format(sample)
                    let width = (text as NSString)
                        .size(withAttributes: [.font: font]).width
                    if width > widest.width { widest = (text, width) }
                }
            }
            print("MEASURED \(style): \"\(widest.label)\" = \(widest.width)pt "
                    + "(pinned \(OddsChartView.xAxisLabelWidth(for: style))pt)")
            XCTAssertLessThanOrEqual(
                widest.width, OddsChartView.xAxisLabelWidth(for: style),
                "\(style): widest real label \"\(widest.label)\" measures "
                    + "\(widest.width)pt, pinned at "
                    + "\(OddsChartView.xAxisLabelWidth(for: style))pt")
            // …and not so generous that it coarsens the axis for nothing.
            XCTAssertGreaterThan(
                widest.width, OddsChartView.xAxisLabelWidth(for: style) - 8,
                "\(style): pinned width is \(OddsChartView.xAxisLabelWidth(for: style))pt "
                    + "for a \(widest.width)pt label — padding a fit rule is how "
                    + "an axis loses resolution it had room for")
        }
    }

    /// One sample per (weekday × month × hour × minute) corner the four formats
    /// can reach: every hour of a week's worth of days, at the widest minutes,
    /// across every month.
    private static let labelSamples: [Date] = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        var dates: [Date] = []
        for month in 1...12 {
            for day in [1, 8, 13, 20, 28] {
                for hour in 0...23 {
                    for minute in [0, 20, 30, 45, 58] {
                        if let d = cal.date(from: DateComponents(
                            year: 2026, month: month, day: day,
                            hour: hour, minute: minute)) {
                            dates.append(d)
                        }
                    }
                }
            }
        }
        return dates
    }()
    #endif
}
