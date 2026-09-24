import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4445 + #8429 — THE EVOLUTION CARD AT THE LARGEST TEXT, ON ALEX'S OWN PHONE.
///
/// TestFlight 1.0.1 (20), iPhone 18 Pro Max (440pt: the simulator profile for the
/// same model, `iPhone19,3`, is 1320×2868 px at @3x), Larger Accessibility Sizes at
/// maximum, NFL Super Bowl Winner (86832). Two failures in one frame:
///
///   * #4445 — the dates on the time axis stayed at a fixed 9pt while the y-axis
///     percentages and the controls grew around them. Minuscule, not overprinted;
///     the Sept 21 fit stopped the overprint by pinning the size, and a date nobody
///     can read is not a fixed axis.
///   * #8429 — the leaderboard read **Los… 11% · Buf… 10% · Sea… 7%**: the name was
///     one line beside its record, so it got whatever the record and the
///     probability left over.
///
/// The acceptance is at 375pt (the narrowest phone the app ships to) AND the
/// larger phones, across accessibility 1–5 — so every test here sweeps both.
@MainActor
final class EvolutionMaximumTextDatesAndNames4445And8429Tests: XCTestCase {

    private let narrowPhone: CGFloat = 375
    private let alexsPhone: CGFloat = 440
    private let accessibilitySizes: [DynamicTypeSize] = [
        .accessibility1, .accessibility2, .accessibility3, .accessibility4, .accessibility5,
    ]

    private var utc: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return cal
    }

    // MARK: - #4445: the dates grow with the reader's text

    /// THE SHIP, axis half: from the default size up, the dates are drawn larger as
    /// the reader's text is larger, and at every accessibility size they are at
    /// least three-quarters larger than the 9pt build 20 drew.
    func testTheDatesGrowWithTheReadersTextSize() {
        XCTAssertEqual(
            EvolutionChartView.axisLabelPointSize(at: .large), 9, accuracy: 0.01,
            "the default size must draw exactly what every reader sees today")

        var previous: CGFloat = 0
        for size in DynamicTypeSize.allCases {
            let points = EvolutionChartView.axisLabelPointSize(at: size)
            print("AXIS \(size): \(points)pt")
            XCTAssertGreaterThanOrEqual(points, previous, "\(size) drew smaller dates than the size below it")
            previous = points
        }
        for size in accessibilitySizes {
            XCTAssertGreaterThanOrEqual(
                EvolutionChartView.axisLabelPointSize(at: size), 9 * 1.75,
                "\(size): dates still near build 20's fixed 9pt")
        }
    }

    /// The planner charges each label its GROWN width. This is the measurement the
    /// fit stands on: the pinned widths were measured at 9pt, and SF gets slightly
    /// TIGHTER per point as it grows, so scaling them must never under-charge a real
    /// label at the size it is drawn. Same samples, same locales as the 9pt test.
    func testThePinnedWidthsScaledToTheDrawnSizeStillCoverEveryLabel() {
        let locales = ["en_US", "en_GB", "de_DE", "fr_FR"].map(Locale.init(identifier:))
        let points = EvolutionChartView.axisLabelPointSize(at: .accessibility5)
        let scale = points / EvolutionChartView.axisLabelBasePointSize
        let font = UIFont.systemFont(ofSize: points)

        for style in [OddsChartView.XAxisPlan.LabelStyle.timeOfDay, .hourOfDay,
                      .dayAndHour, .dayAndTime, .calendarDay, .monthAndYear] {
            var widest: (label: String, width: CGFloat) = ("", 0)
            for locale in locales {
                var format = OddsChartView.XAxisPlan(
                    component: .hour, count: 1, labelStyle: style).format
                format.locale = locale
                format.timeZone = utc.timeZone
                format.calendar = utc
                for sample in Self.labelSamples {
                    let text = format.format(sample)
                    let width = (text as NSString).size(withAttributes: [.font: font]).width
                    if width > widest.width { widest = (text, width) }
                }
            }
            let charged = OddsChartView.xAxisLabelWidth(for: style) * scale
            XCTAssertLessThanOrEqual(
                widest.width, charged,
                "\(style) at \(points)pt: \"\(widest.label)\" is \(widest.width)pt, charged \(charged)pt")
        }
    }

    /// Plot widths the card actually leaves at .accessibility5 once the y-axis has
    /// grown too (rendered on the simulator: ~250pt at 375, ~315pt at 440). Taken
    /// low so the test is the conservative side of the render.
    private let plotWidths: [CGFloat] = [230, 300]

    /// THE SHIP, fit half: at the grown size, no span the card can show — a Today
    /// window to a whole season — draws two dates touching.
    func testNoWindowDrawsTouchingDatesAtTheLargestText() {
        let points = EvolutionChartView.axisLabelPointSize(at: .accessibility5)
        let scale = points / EvolutionChartView.axisLabelBasePointSize
        let start = utc.date(from: DateComponents(year: 2026, month: 9, day: 5))!

        for plotWidth in plotWidths {
            var span: TimeInterval = 3600
            while span <= 365 * 86400 {
                let plan = EvolutionChartView.axisPlan(
                    for: [start, start.addingTimeInterval(span)], plotWidth: plotWidth,
                    calendar: utc, labelScale: scale)
                let intervals = span / Self.strideSeconds(plan)
                if intervals >= 1 {
                    let spacing = plotWidth / CGFloat(intervals)
                    let labelWidth = OddsChartView.xAxisLabelWidth(for: plan.labelStyle) * scale
                    // Charged at the dearest count the stride could draw.
                    let required = 2 * labelWidth + OddsChartView.xAxisLabelMinGap
                    let interior = 1.5 * labelWidth + OddsChartView.xAxisLabelMinGap
                    XCTAssertGreaterThanOrEqual(
                        spacing, intervals < 3 ? required : interior,
                        "plot \(plotWidth)pt span \(Int(span))s: \(plan.labelStyle) \(spacing)pt apart")
                }
                span *= 1.25
            }
        }
    }

    /// …and the axis still NAMES the window, legibly. Every window from an hour to a
    /// season, on both plot widths: either a stride with two whole strides inside the
    /// window (two ticks, whatever the alignment), or the window's two endpoints —
    /// and either way the labels clear each other and are drawn at the reader's size,
    /// never stepped back toward build 20's 9pt. The 375pt 7d case (232pt of plot)
    /// is the one that stepped to 9.5pt under the previous rule.
    func testTheLargestTextStillDrawsTwoLegibleDatesForEveryWindow() {
        let maxSize = EvolutionChartView.axisLabelPointSize(at: .accessibility5)
        let start = utc.date(from: DateComponents(year: 2026, month: 9, day: 5))!
        for plotWidth in plotWidths + [232, 297] {
            var span: TimeInterval = 3600
            while span <= 365 * 86400 {
                let layout = EvolutionChartView.axisLayout(
                    for: [start, start.addingTimeInterval(span)], plotWidth: plotWidth,
                    maxPointSize: maxSize, calendar: utc)
                let scale = layout.pointSize / EvolutionChartView.axisLabelBasePointSize
                let label = "plot \(plotWidth)pt, \(Int(span))s"
                if let ends = layout.endpoints {
                    XCTAssertEqual(ends.count, 2, label)
                    XCTAssertGreaterThanOrEqual(
                        plotWidth,
                        OddsChartView.xAxisRequiredSpacing(
                            labelWidth: OddsChartView.xAxisLabelWidth(for: layout.plan.labelStyle) * scale,
                            labelCount: 2),
                        "\(label): the two endpoint labels touch")
                } else {
                    let intervals = span / EvolutionChartView.nominalSeconds(of: layout.plan)
                    XCTAssertGreaterThanOrEqual(intervals, 2, "\(label): fewer than two strides — ticks can vanish")
                    XCTAssertTrue(
                        OddsChartView.xAxisFits(
                            intervals: intervals, plotWidth: plotWidth,
                            style: layout.plan.labelStyle, labelScale: scale),
                        "\(label): drawn size collides")
                }
                XCTAssertGreaterThanOrEqual(
                    layout.pointSize, 14, "\(label): dates stepped back to \(layout.pointSize)pt")
                span *= 1.25
            }
        }
    }

    /// Endpoint labels must never print the same text twice (#3269's rule).
    func testEndpointLabelsAreDistinct() {
        let start = utc.date(from: DateComponents(year: 2026, month: 9, day: 5, hour: 13, minute: 30))!
        // 23h45m crosses midnight and ends in the SAME clock hour it began: an
        // hour-only label would print "1 PM" twice (mutation M5, native/326).
        for span: TimeInterval in [3600, 5 * 3600, 20 * 3600, 23.75 * 3600, 86400, 7 * 86400, 200 * 86400] {
            let hi = start.addingTimeInterval(span)
            var format = OddsChartView.XAxisPlan(
                component: .day, count: 1,
                labelStyle: EvolutionChartView.endpointStyle(from: start, to: hi, calendar: utc)).format
            format.locale = Locale(identifier: "en_US")
            format.timeZone = utc.timeZone
            format.calendar = utc
            XCTAssertNotEqual(format.format(start), format.format(hi), "span \(Int(span))s")
        }
    }

    /// CONTROL for the above: the reader's size alone, unstepped, is exactly the
    /// plan that emptied the 7d axis.
    func testTheUnsteppedSizeIsTheOneThatEmptiedTheAxis() {
        let maxSize = EvolutionChartView.axisLabelPointSize(at: .accessibility5)
        let start = utc.date(from: DateComponents(year: 2026, month: 9, day: 5))!
        let dates = [start, start.addingTimeInterval(7 * 86400)]
        let unstepped = EvolutionChartView.axisPlan(
            for: dates, plotWidth: 297, calendar: utc,
            labelScale: maxSize / EvolutionChartView.axisLabelBasePointSize)
        XCTAssertLessThan(
            7 * 86400 / EvolutionChartView.nominalSeconds(of: unstepped), 2,
            "the control no longer reproduces the emptied axis")
    }

    /// The default size is untouched: at 9pt the layout IS the plan every reader had.
    func testTheDefaultSizeLayoutIsTheOldPlan() {
        let start = utc.date(from: DateComponents(year: 2026, month: 9, day: 5))!
        for span: TimeInterval in [3600, 86400, 7 * 86400, 90 * 86400] {
            let dates = [start, start.addingTimeInterval(span)]
            let layout = EvolutionChartView.axisLayout(
                for: dates, plotWidth: 330, maxPointSize: 9, calendar: utc)
            XCTAssertEqual(layout.pointSize, 9)
            XCTAssertNil(layout.endpoints)
            XCTAssertEqual(layout.plan, EvolutionChartView.axisPlan(for: dates, plotWidth: 330, calendar: utc))
        }
    }

    /// CONTROL: across the same windows, the 9pt plan drawn at the grown size would
    /// COLLIDE on some of them, and on every one of those the grown plan chose a
    /// coarser stride. Without this the fit test above could pass because the
    /// stride never needed to change.
    func testTheNinePointPlanWouldCollideAtTheGrownSize() {
        let scale = EvolutionChartView.axisLabelPointSize(at: .accessibility5)
            / EvolutionChartView.axisLabelBasePointSize
        let start = utc.date(from: DateComponents(year: 2026, month: 9, day: 5))!
        var collisions = 0
        for plotWidth in plotWidths {
            var span: TimeInterval = 3600
            while span <= 365 * 86400 {
                let dates = [start, start.addingTimeInterval(span)]
                let old = EvolutionChartView.axisPlan(
                    for: dates, plotWidth: plotWidth, calendar: utc)
                let new = EvolutionChartView.axisPlan(
                    for: dates, plotWidth: plotWidth, calendar: utc, labelScale: scale)
                let oldFitsGrown = OddsChartView.xAxisFits(
                    intervals: span / Self.strideSeconds(old), plotWidth: plotWidth,
                    style: old.labelStyle, labelScale: scale)
                if !oldFitsGrown {
                    collisions += 1
                    XCTAssertGreaterThan(
                        Self.strideSeconds(new), Self.strideSeconds(old),
                        "plot \(plotWidth)pt span \(Int(span))s: grown labels kept the 9pt stride")
                }
                span *= 1.25
            }
        }
        XCTAssertGreaterThan(collisions, 10, "the grown size never needed a coarser stride")
    }

    /// Every game chart keeps its 9pt rule: the default `labelScale` is 1 and a
    /// scale below 1 is never used to squeeze more ticks in.
    func testGameChartsAreUnchanged() {
        let start = utc.date(from: DateComponents(year: 2026, month: 9, day: 5, hour: 17))!
        for span: TimeInterval in [2700, 9300, 86400, 7 * 86400] {
            let range = start...start.addingTimeInterval(span)
            XCTAssertEqual(
                OddsChartView.xAxisPlan(for: range, plotWidth: 302, calendar: utc),
                OddsChartView.xAxisPlan(for: range, plotWidth: 302, calendar: utc, labelScale: 1))
            XCTAssertEqual(
                OddsChartView.xAxisPlan(for: range, plotWidth: 302, calendar: utc, labelScale: 0.5),
                OddsChartView.xAxisPlan(for: range, plotWidth: 302, calendar: utc, labelScale: 1))
        }
    }

    // MARK: - #8429: the board names every participant

    private func outcome(name: String, prob: Double, record: String?) -> TimelineOutcomeMeta {
        var json: [String: Any] = ["name": name, "current_probability": prob]
        if let record { json["record"] = record }
        let data = try! JSONSerialization.data(withJSONObject: json)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(TimelineOutcomeMeta.self, from: data)
    }

    /// The five rows the recording showed as fragments, plus the pair a city alone
    /// cannot tell apart.
    private var board: [TimelineOutcomeMeta] {
        [
            outcome(name: "Los Angeles Rams", prob: 0.11, record: "2-1"),
            outcome(name: "Los Angeles Chargers", prob: 0.06, record: "2-1"),
            outcome(name: "Buffalo Bills", prob: 0.10, record: "3-0"),
            outcome(name: "Seattle Seahawks", prob: 0.07, record: "2-1"),
            outcome(name: "Baltimore Ravens", prob: 0.07, record: "1-2"),
            outcome(name: "San Francisco 49ers", prob: 0.07, record: "2-1"),
            outcome(name: "Philadelphia Eagles", prob: 1.0, record: "3-0"),
        ]
    }

    func testTheParticipantStacksExactlyAtAccessibilitySizes() {
        for size in DynamicTypeSize.allCases {
            XCTAssertEqual(
                EvolutionLeaderboardRow.stacksParticipant(at: size), size.isAccessibilitySize,
                "\(size)")
        }
    }

    private func hostedRow(
        _ outcome: TimelineOutcomeMeta, width: CGFloat, at size: DynamicTypeSize
    ) -> CGSize {
        let columns = EvolutionLeaderboardGeometry.columns(
            for: board, at: size, renderedPercents: [])
        let row = EvolutionLeaderboardRow(
            position: 1, outcome: outcome, color: .blue, isSelected: true,
            isHighlighted: true, columns: columns, renderedPercent: nil)
        let host = hostForMeasurement(row, at: size)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 2000))
        window.rootViewController = host
        window.isHidden = false
        host.view.frame = window.bounds
        for _ in 0..<3 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        return host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
    }

    /// The width the name actually has in a stacked row: the phone, less the row's
    /// padding, the position cell and the logo, each with its spacing.
    private func nameColumn(width: CGFloat) -> CGFloat {
        // Padding, rank cell + spacing, 18pt logo + spacing. The numbers are on the
        // second line, so they take nothing from the name.
        return width - 32 - (24 + 6) - (18 + 6)
    }

    /// THE SHIP, board half: every WORD of every name fits the name's column at every
    /// accessibility size on both phones — so the name wraps between words and is
    /// never cut to a city fragment or split inside one.
    func testEveryWordOfEveryNameFitsItsColumn() {
        for width in [narrowPhone, alexsPhone] {
            for size in accessibilitySizes {
                let font = UIFont.preferredFont(
                    forTextStyle: .subheadline,
                    compatibleWith: UITraitCollection(
                        preferredContentSizeCategory:
                            CalibrationSourceTableGeometry.CellFont.contentSizeCategory(size)))
                let bold = UIFont.systemFont(ofSize: font.pointSize, weight: .semibold)
                let column = nameColumn(width: width)
                for outcome in board {
                    for word in outcome.name.split(separator: " ") {
                        let w = (String(word) as NSString).size(withAttributes: [.font: bold]).width
                        XCTAssertLessThanOrEqual(
                            w, column,
                            "\(width)pt at \(size): \"\(word)\" of \(outcome.name) is \(w)pt in a \(column)pt column")
                    }
                }
            }
        }
    }

    /// The rendered row, hosted: no wider than the phone, and at every accessibility
    /// size at least two lines tall — the name on its own line, the numbers under it.
    func testTheRowWrapsInsteadOfTruncating() {
        let longest = board[1] // "Los Angeles Chargers"
        func lineHeight(_ size: DynamicTypeSize) -> CGFloat {
            UIFont.preferredFont(
                forTextStyle: .subheadline,
                compatibleWith: UITraitCollection(
                    preferredContentSizeCategory:
                        CalibrationSourceTableGeometry.CellFont.contentSizeCategory(size))
            ).lineHeight
        }
        for width in [narrowPhone, alexsPhone] {
            let atLarge = hostedRow(longest, width: width, at: .large).height
            for size in accessibilitySizes {
                let hosted = hostedRow(longest, width: width, at: size)
                XCTAssertLessThanOrEqual(hosted.width, width + 0.5, "\(width)pt at \(size)")
                // What a ONE-line row would measure at this size: the .large row
                // with its line grown to this size's line.
                let oneLine = atLarge + lineHeight(size) - lineHeight(.large)
                XCTAssertGreaterThan(
                    hosted.height, oneLine + 0.8 * lineHeight(size),
                    "\(width)pt at \(size): the row is still one line — the name is sharing it with the numbers")
            }
        }
    }

    /// CONTROL: below accessibility sizes the row is still the one-line row #4373
    /// measured — nothing about the default board moves.
    func testTheDefaultBoardIsOneLine() {
        for width in [narrowPhone, alexsPhone] {
            let a = hostedRow(board[1], width: width, at: .large)
            let b = hostedRow(board[2], width: width, at: .large)
            XCTAssertEqual(a.height, b.height, accuracy: 0.5, "long and short names differ in height at .large")
        }
    }

    // MARK: - Helpers

    private static func strideSeconds(_ plan: OddsChartView.XAxisPlan) -> TimeInterval {
        switch plan.component {
        case .minute: return TimeInterval(plan.count) * 60
        case .hour: return TimeInterval(plan.count) * 3600
        default: return TimeInterval(plan.count) * 86400
        }
    }

    private static let labelSamples: [Date] = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        var dates: [Date] = []
        for month in 1...12 {
            for day in [1, 8, 13, 20, 28] {
                for hour in [0, 9, 10, 11, 12, 23] {
                    for minute in [0, 58] {
                        if let d = cal.date(from: DateComponents(
                            year: 2026, month: month, day: day, hour: hour, minute: minute)) {
                            dates.append(d)
                        }
                    }
                }
            }
        }
        return dates
    }()
}
