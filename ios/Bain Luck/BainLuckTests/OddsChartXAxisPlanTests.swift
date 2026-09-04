import XCTest
@testable import Bain_Luck

/// native/001 finding 4 — the win-probability chart's TIME axis must stay
/// readable at every span the app actually serves.
///
/// The old rule was one line: stride 15/30/**60** minutes by duration, label
/// `hour().minute()`, always. That is fine for a three-hour game and unreadable
/// for anything else. Alex opened the upcoming Shelton–Shapovalov match, whose
/// history is 24 + 47 points over a **17-hour** span (measured 2026-09-03,
/// 01:33–18:40Z for a match two days out), and got ~18 labels of the form
/// "11:18 PM" overprinting each other into a smear. Worse, the label named no
/// day, so a domain crossing midnight labelled two different days identically.
///
/// Two properties are pinned for every span: the tick count fits the label, and
/// a multi-day domain says which day. `Calendar` is injected and pinned to UTC so
/// the day-boundary arithmetic cannot depend on where the test runs (gotcha #44).
final class OddsChartXAxisPlanTests: XCTestCase {

    private var utc: Calendar = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return cal
    }()

    private func date(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

    private func domain(_ from: String, _ to: String) -> ClosedRange<Date> {
        date(from)...date(to)
    }

    /// Nominal seconds per tick for a plan, so a test can count labels the way
    /// the chart will draw them.
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

    private func tickCount(_ range: ClosedRange<Date>) -> Double {
        let plan = OddsChartView.xAxisPlan(for: range, calendar: utc)
        return range.upperBound.timeIntervalSince(range.lowerBound) / strideSeconds(plan)
    }

    // MARK: - The reported defect

    /// Alex's chart. The old rule gave 60-minute ticks and a bare clock label:
    /// ~17 labels, no day. Both halves are fixed here.
    func testUpcomingMatchSeventeenHourSpanIsReadable() {
        let range = domain("2026-09-03T01:33:00Z", "2026-09-03T18:40:00Z")
        let plan = OddsChartView.xAxisPlan(for: range, calendar: utc)

        XCTAssertLessThanOrEqual(
            tickCount(range), 6,
            "a 17-hour span must not draw ~17 labels across a phone-width chart")
        XCTAssertGreaterThanOrEqual(
            tickCount(range), 2, "…and must still draw an axis")
        XCTAssertNotEqual(
            strideSeconds(plan), 3600,
            "the old hard-coded 60-minute stride is exactly what smeared")
        XCTAssertEqual(
            plan.labelStyle, .hourOfDay,
            "within one calendar day the hour alone reads cleanly")
    }

    /// The same match's real span in Pacific time, where it straddles midnight:
    /// the label must name the day or "12 AM" appears twice meaning two days.
    func testDomainCrossingMidnightNamesTheDay() {
        let range = domain("2026-09-02T18:33:00Z", "2026-09-03T11:40:00Z")
        let plan = OddsChartView.xAxisPlan(for: range, calendar: utc)
        XCTAssertEqual(plan.labelStyle, .dayAndHour)
        XCTAssertLessThanOrEqual(tickCount(range), 5, "day+hour labels are wider")
    }

    // MARK: - Every span the app serves

    func testLiveGameShortSpanKeepsMinutePrecision() {
        // A first-quarter chart: 40 minutes of play.
        let range = domain("2026-09-03T19:00:00Z", "2026-09-03T19:40:00Z")
        let plan = OddsChartView.xAxisPlan(for: range, calendar: utc)
        XCTAssertEqual(plan.labelStyle, .timeOfDay, "minutes still matter at this span")
        XCTAssertLessThanOrEqual(tickCount(range), 6)
    }

    func testFullGameThreeHourSpan() {
        let range = domain("2026-09-03T17:00:00Z", "2026-09-03T20:00:00Z")
        XCTAssertLessThanOrEqual(tickCount(range), 6)
    }

    func testMultiDayFuturesSpanLabelsCalendarDays() {
        let range = domain("2026-08-20T00:00:00Z", "2026-09-03T00:00:00Z")
        let plan = OddsChartView.xAxisPlan(for: range, calendar: utc)
        XCTAssertEqual(plan.labelStyle, .calendarDay)
        XCTAssertEqual(plan.component, .day)
        XCTAssertLessThanOrEqual(tickCount(range), 6)
    }

    func testSeasonLongSpanStillGetsAnAxis() {
        let range = domain("2026-01-01T00:00:00Z", "2026-09-03T00:00:00Z")
        let plan = OddsChartView.xAxisPlan(for: range, calendar: utc)
        XCTAssertEqual(plan.labelStyle, .calendarDay)
        XCTAssertGreaterThan(plan.count, 0, "an unlabelled axis is not an improvement")
    }

    /// The label budget holds across the whole continuum, not just at the spans
    /// someone thought to write a case for. This is the property the old rule
    /// violated: it was correct at 3 hours and wrong everywhere above it.
    func testNoSpanFromTenMinutesToAYearOverdrawsItsLabelBudget() {
        let start = date("2026-09-03T00:00:00Z")
        var span: TimeInterval = 600
        while span <= 365 * 86400 {
            let range = start...start.addingTimeInterval(span)
            let plan = OddsChartView.xAxisPlan(for: range, calendar: utc)
            let ticks = span / strideSeconds(plan)
            XCTAssertLessThanOrEqual(
                ticks, 6,
                "span \(Int(span))s drew \(ticks) ticks with style \(plan.labelStyle)")
            span *= 1.25
        }
    }

    /// Degenerate domains (one snapshot, or none) must not crash or divide by a
    /// zero stride.
    func testZeroWidthDomainIsSafe() {
        let instant = date("2026-09-03T12:00:00Z")
        let plan = OddsChartView.xAxisPlan(for: instant...instant, calendar: utc)
        XCTAssertEqual(plan.component, .minute)
        XCTAssertEqual(plan.count, 5)
        XCTAssertEqual(plan.labelStyle, .timeOfDay)
    }

    // MARK: - Label formats say what the style claims

    func testFormatsCarryTheFieldsTheirStyleNames() {
        // 2026-09-03T18:40Z — a Thursday, 6:40 PM UTC.
        let sample = date("2026-09-03T18:40:00Z")

        func rendered(_ style: OddsChartView.XAxisPlan.LabelStyle) -> String {
            let plan = OddsChartView.XAxisPlan(component: .hour, count: 1, labelStyle: style)
            var format = plan.format
            format.locale = Locale(identifier: "en_US_POSIX")
            format.timeZone = TimeZone(identifier: "UTC")!
            format.calendar = utc
            return format.format(sample)
        }

        XCTAssertTrue(rendered(.timeOfDay).contains("40"), rendered(.timeOfDay))
        XCTAssertFalse(rendered(.hourOfDay).contains("40"),
                       "the hour style must not smuggle minutes back in")
        XCTAssertTrue(rendered(.dayAndHour).contains("Thu"), rendered(.dayAndHour))
        XCTAssertTrue(rendered(.calendarDay).contains("Sep"), rendered(.calendarDay))
        XCTAssertTrue(rendered(.calendarDay).contains("3"), rendered(.calendarDay))
    }
}
