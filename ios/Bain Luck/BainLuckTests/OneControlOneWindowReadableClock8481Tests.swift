import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #8481 + #1833 — the two stacked event-page charts share ONE All / Since Start
/// control, ONE time window, and a clock whose last two labels do not run
/// together.
///
/// SPECIMEN: Alex's installed TestFlight 1.0.1(20) recording, iPhone 18 Pro Max
/// (iOS 27, 440pt), Brewers @ Phillies 15318131, 2026-09-24 3:50–3:51 PM PDT —
/// 45 minutes after the 3:05 scheduled start. Frames 036/040/044 of
/// `artifacts/chart-sprint-coordinator/device-review-1833-20260924/`:
///   * 00:40, All: the green line runs LEFT of the plot through the y-axis to
///     the screen edge while the axis still opens at 3:05 PM;
///   * 00:36/00:44, Since Start: contained, but `3:35 PM3:45 PM` run together
///     on BOTH charts.
///
/// FIXTURE: `Fixtures/history-15318131-early.20260924T2251Z.json` is the served
/// `GET /api/events/15318131/history?hours=168`, fetched 2026-09-24 23:13Z while
/// the game was still live, cut back to the instant of the recording (every
/// point after 22:51:00Z dropped) and thinned 1-in-12 before 20:00Z so it stays
/// small. The 20:00Z–22:51Z window — everything either range draws — is whole.
///
/// RUN ON iOS 27 for the rendered-label arm: the collision is the iOS 27 chart
/// framework's placement, and an iOS 26 simulator drew the OLD code cleanly
/// (native/328 reproduced it on both). The window, containment and pure arms
/// bite on either.
@MainActor
final class OneControlOneWindowReadableClock8481Tests: XCTestCase {

    // MARK: - Harness

    private static var testsDir: URL { URL(fileURLWithPath: #filePath).deletingLastPathComponent() }
    private static let commence = "2026-09-24T22:05:00+00:00"
    /// The phone's clock at 00:40 of the recording.
    private static let recordedAt = "2026-09-24T22:51:00Z".asDate!

    private static func specimen() throws -> EventHistoryResponse {
        let url = testsDir.appendingPathComponent(
            "Fixtures/history-15318131-early.20260924T2251Z.json")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(contentsOf: url))
    }

    private static func window(_ range: OddsTimeRange) throws -> ClosedRange<Date> {
        try XCTUnwrap(SharedChartWindow.domain(
            status: "live", commenceTime: commence, history: try specimen(),
            range: range, now: recordedAt))
    }

    private static var pacific: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return cal
    }

    /// The narrowest inline plot on a 440pt phone (#1833's width table).
    private static let phonePlot: CGFloat = 340

    private func probabilityChart(
        range: OddsTimeRange, window: ClosedRange<Date>?
    ) throws -> some View {
        OddsChartView(
            eventId: 15318131, teamColors: (away: .blue, home: .red),
            commenceTime: Self.commence, status: "live",
            homeTeamName: "Philadelphia Phillies", awayTeamName: "Milwaukee Brewers",
            homeTeamAbbrev: "PHI", awayTeamAbbrev: "MIL", sportKey: "baseball_mlb",
            forcedDomain: window, pageAxisPlotWidth: Self.phonePlot,
            selectedRange: .constant(range), preloadedHistory: try Self.specimen())
            .frame(width: 440)
            .background(Color.white)
    }

    private func scoreChart(
        range: OddsTimeRange, window: ClosedRange<Date>?
    ) throws -> some View {
        ScoreDifferentialChartView(
            history: try Self.specimen(), homeTeam: "Philadelphia Phillies",
            awayTeam: "Milwaukee Brewers", sportKey: "baseball_mlb",
            commenceTime: Self.commence, eventStatus: "live",
            homeTeamColor: .red, awayTeamColor: .blue,
            homeTeamAbbrev: "PHI", awayTeamAbbrev: "MIL",
            forcedDomain: window, pageAxisPlotWidth: Self.phonePlot, range: range)
            .padding(.horizontal, 16)
            .frame(width: 440)
            .background(Color.white)
    }

    /// RGBA8 raster at 3x, plus a copy in the lane's evidence directory.
    private struct Raster {
        let width: Int, height: Int, bytes: [UInt8]
        func rgb(_ x: Int, _ y: Int) -> (Int, Int, Int) {
            let i = (y * width + x) * 4
            return (Int(bytes[i]), Int(bytes[i + 1]), Int(bytes[i + 2]))
        }
    }

    private func raster<V: View>(_ view: V, name: String) throws -> Raster {
        let renderer = rendererForMeasurement(view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.cgImage, "\(name) produced no raster")
        let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["BL_ARTIFACTS"]
            ?? FileManager.default.temporaryDirectory.path)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let os = ProcessInfo.processInfo.operatingSystemVersion.majorVersion
        try? UIImage(cgImage: image).pngData()?
            .write(to: dir.appendingPathComponent("8481-\(name)-ios\(os).png"))

        let w = image.width, h = image.height
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = try XCTUnwrap(CGContext(
            data: &bytes, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        return Raster(width: w, height: h, bytes: bytes)
    }

    /// Coloured ink (a series stroke — the green blend, the orange projection,
    /// the teal score) inside a column band. Axis text and gridlines are grey.
    private func colouredInk(in r: Raster, xPoints: ClosedRange<CGFloat>,
                             yPoints: ClosedRange<CGFloat>) -> Int {
        var count = 0
        for y in Int(yPoints.lowerBound * 3)..<min(r.height, Int(yPoints.upperBound * 3)) {
            for x in Int(xPoints.lowerBound * 3)..<Int(xPoints.upperBound * 3) {
                let (red, green, blue) = r.rgb(x, y)
                if max(red, green, blue) - min(red, green, blue) > 60 { count += 1 }
            }
        }
        return count
    }

    /// How many label-sized clusters of GREY ink the time-axis row holds, right
    /// of `fromX`. A label is one cluster (its inner space is ~2.5pt, under the
    /// 4pt split); two labels whose ink touches are ONE cluster too wide to be a
    /// label — which is exactly the defect.
    ///
    /// The axis row is the FIRST text row below the chart's midline. The band
    /// that first finds it holds only the TOPS of the glyphs, where a merged
    /// pair can still split into label-sized pieces (native/328's own mutant
    /// read 5 there against a rendered `3:35 PM3:45 PM`), so the verdict is the
    /// fewest clusters over the bands 5–8pt lower, which hold whole glyphs. The
    /// legend below ("Projected Spread · Actual Score Diff") is never reached.
    private func labelClusters(in r: Raster, fromX: CGFloat) -> Int {
        let bandRows = 30, split = 12
        let labelWidths = 45...150  // px at 3x: "1:05 PM" ≈ 90, "12:45 PM" ≈ 120
        func clusters(at y: Int) -> Int {
            var inkColumns = [Bool](repeating: false, count: r.width)
            for x in Int(fromX * 3)..<r.width {
                for row in y..<min(r.height, y + bandRows) {
                    let (red, green, blue) = r.rgb(x, row)
                    let grey = abs(red - green) < 14 && abs(green - blue) < 14
                    if grey && (red + green + blue) / 3 < 200 { inkColumns[x] = true; break }
                }
            }
            var count = 0, runStart: Int?, gap = 0
            for x in 0...r.width {
                let ink = x < r.width && inkColumns[x]
                if ink {
                    if runStart == nil { runStart = x }
                    gap = 0
                } else if let start = runStart {
                    gap += 1
                    if gap >= split || x == r.width {
                        if labelWidths.contains(x - gap + 1 - start) { count += 1 }
                        runStart = nil
                        gap = 0
                    }
                }
            }
            return count
        }
        guard let top = stride(from: r.height / 2, to: r.height - bandRows, by: 3)
            .first(where: { clusters(at: $0) >= 2 }) else { return 0 }
        return stride(from: top + 15, through: top + 24, by: 3).map(clusters(at:)).min() ?? 0
    }

    // MARK: - One window, read from the one control

    /// Since Start is today's window: first pitch to the live edge.
    func testSinceStartIsTheGamesOwnWindow() throws {
        let window = try Self.window(.sinceStart)
        XCTAssertEqual(window.lowerBound, "2026-09-24T22:05:00Z".asDate)
        XCTAssertEqual(window.upperBound, "2026-09-24T22:52:00Z".asDate)
    }

    /// All widens the SAME window back over the run-up — to the first reading,
    /// but never more than the pre-start margin (the web's L2-163 rule). The
    /// specimen's readings go back two days, so the margin binds.
    func testAllWidensTheSharedWindowOverTheRunUp() throws {
        let all = try Self.window(.all)
        let since = try Self.window(.sinceStart)
        XCTAssertEqual(all.lowerBound, "2026-09-24T20:05:00Z".asDate,
                       "All must open at the margin, not at first pitch (#8481) nor two days back")
        XCTAssertEqual(all.upperBound, since.upperBound, "the choice moves the start, never the live edge")
    }

    /// A market that opened inside the margin opens All where its first reading
    /// is — All shows what exists, it does not invent flat run-up.
    func testAllOpensAtAFirstReadingInsideTheMargin() throws {
        let json = """
        {"event_id": 1, "home_team": "H", "away_team": "A", "status": "live",
         "history": [{"timestamp": "2026-09-24T21:35:00Z", "home_probability": 0.5},
                     {"timestamp": "2026-09-24T22:30:00Z", "home_probability": 0.6}]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let history = try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
        let all = try XCTUnwrap(SharedChartWindow.domain(
            status: "live", commenceTime: Self.commence, history: history,
            range: .all, now: Self.recordedAt))
        XCTAssertEqual(all.lowerBound, "2026-09-24T21:35:00Z".asDate)
    }

    /// All is a superset of Since Start on every phase of the game, and never
    /// an inverted range.
    func testAllIsNeverNarrowerThanSinceStart() throws {
        let history = try Self.specimen()
        for status in ["live", "completed", "final"] {
            let since = SharedChartWindow.domain(
                status: status, commenceTime: Self.commence, history: history,
                range: .sinceStart, now: Self.recordedAt)
            let all = SharedChartWindow.domain(
                status: status, commenceTime: Self.commence, history: history,
                range: .all, now: Self.recordedAt)
            XCTAssertEqual(since == nil, all == nil, status)
            if let since, let all {
                XCTAssertLessThanOrEqual(all.lowerBound, since.lowerBound, status)
                XCTAssertEqual(all.upperBound, since.upperBound, status)
            }
        }
    }

    /// The page owns the choice: the picker above Win Probability writes it,
    /// the window reads it, and the score chart is handed it. There is no
    /// second control (Alex, 2026-09-24).
    func testThePageHoldsOneChoiceAndHandsItToBothCharts() throws {
        let appDir = Self.testsDir.deletingLastPathComponent().appendingPathComponent("Bain Luck")
        func code(_ path: String) throws -> String {
            try String(contentsOf: appDir.appendingPathComponent(path), encoding: .utf8)
                .filter { !$0.isWhitespace }
        }
        let page = try code("Views/EventDetailView.swift")
        XCTAssertTrue(page.contains("@StateprivatevarchartRange:OddsTimeRange"))
        XCTAssertTrue(page.contains("range:chartRange)"), "the shared window ignores the choice")
        XCTAssertTrue(page.contains("selectedRange:$chartRange,"), "the picker no longer writes the page's choice")
        XCTAssertTrue(page.contains("pageAxisPlotWidth:pageAxisPlotWidth,range:chartRange"),
                      "the score chart is not handed the choice")

        let score = try code("Components/ScoreDifferentialChartView.swift")
        XCTAssertFalse(score.contains("OddsTimeRange.allCases"), "a second All / Since Start control")
        let probability = try code("Components/OddsChartView.swift")
        XCTAssertFalse(probability.contains("@PublishedvarselectedRange"),
                       "the range is private to the probability chart again")
    }

    /// The score chart's projection runs over the run-up in All, and from first
    /// pitch in Since Start.
    func testTheScoreChartsProjectionFollowsTheChoice() throws {
        let start = try XCTUnwrap(Self.commence.asDate)
        let all = try Self.window(.all)
        XCTAssertEqual(ScoreDifferentialChartView.projectionStart(
            range: .all, gameStart: start, window: all), all.lowerBound)
        XCTAssertEqual(ScoreDifferentialChartView.projectionStart(
            range: .sinceStart, gameStart: start, window: all), start)
        XCTAssertEqual(ScoreDifferentialChartView.projectionStart(
            range: .all, gameStart: start, window: nil), start)
    }

    // MARK: - Nothing drawn outside the window

    /// The recording's 00:40 frame, rebuilt: All selected, and a window that
    /// opened at first pitch — exactly what the page handed the chart before
    /// the window read the choice. No stroke may reach the y-axis gutter.
    func testNoLineIsDrawnThroughTheAxisWhenTheWindowIsNarrowerThanTheData() throws {
        let r = try raster(try probabilityChart(range: .all, window: try Self.window(.sinceStart)),
                           name: "all-in-first-pitch-window")
        // 16 card padding + 24 team gutter = 40pt; the plot opens ~69pt.
        let gutterInk = colouredInk(in: r, xPoints: 42...64, yPoints: 45...290)
        XCTAssertEqual(gutterInk, 0, "the probability line is drawn through the y-axis gutter (#8481)")

        let plotInk = colouredInk(in: r, xPoints: 80...420, yPoints: 45...290)
        XCTAssertGreaterThan(plotInk, 500, "control: the chart drew no line at all")
    }

    /// The same on the score chart, whose window can be narrower than its points.
    func testTheScoreChartDrawsNothingOutsideItsWindow() throws {
        let narrow = "2026-09-24T22:20:00Z".asDate!..."2026-09-24T22:52:00Z".asDate!
        let r = try raster(try scoreChart(range: .sinceStart, window: narrow), name: "score-narrow-window")
        // 16 padding + 22 gutter = 38pt, and the rotated team name's ink reaches
        // ~47pt; the plot opens ~70pt.
        let gutterInk = colouredInk(in: r, xPoints: 49...64, yPoints: 40...200)
        XCTAssertEqual(gutterInk, 0, "the score chart draws through its y-axis gutter")

        let plotInk = colouredInk(in: r, xPoints: 80...420, yPoints: 40...200)
        XCTAssertGreaterThan(plotInk, 300, "control: the score chart drew nothing")
    }

    // MARK: - A readable clock

    /// The accepted sequence (#1833, 00:36/00:44): owning the ticks moved none.
    func testTheSpecimenTicksTheAcceptedSequence() throws {
        let window = try Self.window(.sinceStart)
        let plan = OddsChartView.xAxisPlan(for: window, plotWidth: Self.phonePlot, calendar: Self.pacific)
        let ticks = OddsChartView.xAxisTicks(for: window, plan: plan, calendar: Self.pacific)
        var format = plan.format
        format.timeZone = Self.pacific.timeZone
        format.locale = Locale(identifier: "en_US")
        // The formatter puts a narrow no-break space before "PM".
        XCTAssertEqual(ticks.map { $0.formatted(format).replacingOccurrences(of: "\u{202F}", with: " ") },
                       ["3:05 PM", "3:15 PM", "3:25 PM", "3:35 PM", "3:45 PM"])
    }

    /// Ticks open on the domain's first whole component, so an hourly axis
    /// reads on the hour and a label never names a time its tick is not at.
    func testHourlyTicksLandOnTheHour() {
        let domain = "2026-09-24T02:05:00Z".asDate!..."2026-09-24T05:40:00Z".asDate!
        let plan = OddsChartView.XAxisPlan(component: .hour, count: 1, labelStyle: .hourOfDay)
        XCTAssertEqual(OddsChartView.xAxisTicks(for: domain, plan: plan, calendar: Self.pacific),
                       ["2026-09-24T03:00:00Z", "2026-09-24T04:00:00Z", "2026-09-24T05:00:00Z"]
                        .map { $0.asDate! })
    }

    /// The planner and the renderer share one model of the row: whatever stride
    /// the planner accepts, the labels the renderer places clear each other and
    /// stay inside the plot — across every phone and iPad plot width and every
    /// domain from twenty minutes to a month.
    func testEveryPlannedAxisPlacesLabelsThatClearAndStayInside() {
        let start = "2026-09-24T22:05:00Z".asDate!
        var checked = 0
        for width in stride(from: 240.0, through: 720.0, by: 20.0) {
            for minutes in [20, 30, 47, 60, 75, 90, 110, 150, 167, 200, 300, 480, 900, 1440, 3000, 10080, 43200] {
                for offset in [0.0, 37.0, 290.0] {
                    let lower = start.addingTimeInterval(offset)
                    let domain = lower...lower.addingTimeInterval(Double(minutes) * 60)
                    let plan = OddsChartView.xAxisPlan(
                        for: domain, plotWidth: CGFloat(width), calendar: Self.pacific)
                    let ticks = OddsChartView.xAxisTicks(for: domain, plan: plan, calendar: Self.pacific)
                    let span = domain.upperBound.timeIntervalSince(domain.lowerBound)
                    let xs = ticks.map { CGFloat($0.timeIntervalSince(domain.lowerBound) / span) * CGFloat(width) }
                    let labelWidth = OddsChartView.xAxisLabelWidth(for: plan.labelStyle)
                    let centers = OddsChartView.xAxisLabelCenters(
                        tickPositions: xs, plotWidth: CGFloat(width), labelWidth: labelWidth)
                    let label = "width \(width) · \(minutes) min · +\(offset)s · \(plan)"
                    XCTAssertTrue(OddsChartView.xAxisLabelsClear(centers: centers, labelWidth: labelWidth),
                                  "labels collide: \(label)")
                    for c in centers {
                        XCTAssertGreaterThanOrEqual(c - labelWidth / 2, -0.001, "overhangs left: \(label)")
                        XCTAssertLessThanOrEqual(c + labelWidth / 2, CGFloat(width) + 0.001,
                                                 "overhangs right: \(label)")
                    }
                    checked += 1
                }
            }
        }
        XCTAssertEqual(checked, 25 * 17 * 3)
    }

    /// A label with room is exactly on its tick; only an edge label moves, and
    /// only as far as the edge requires.
    func testLabelsCentreOnTheirTicksAndMoveOnlyAtTheEdge() {
        XCTAssertEqual(OddsChartView.xAxisLabelCenters(
            tickPositions: [0, 72, 144, 216, 288, 330], plotWidth: 340, labelWidth: 41),
            [20.5, 72, 144, 216, 288, 319.5])
    }

    /// RENDERED, both charts, both ranges: every tick's label is its own cluster
    /// of ink. On iOS 27 the framework-placed labels merged the last pair into
    /// one over-wide cluster (`3:35 PM3:45 PM`), so this count came out one short.
    func testEveryTimeLabelRendersSeparatelyOnBothCharts() throws {
        for range in OddsTimeRange.allCases {
            let window = try Self.window(range)
            let plan = OddsChartView.xAxisPlan(for: window, plotWidth: Self.phonePlot)
            let expected = OddsChartView.xAxisTicks(for: window, plan: plan).count
            XCTAssertGreaterThanOrEqual(expected, 4, "control: the specimen axis has too few ticks to test")

            let probability = try raster(try probabilityChart(range: range, window: window),
                                         name: "probability-\(range.rawValue)")
            XCTAssertEqual(labelClusters(in: probability, fromX: 66), expected,
                           "Win Probability, \(range.label): a time label runs into its neighbour")

            let score = try raster(try scoreChart(range: range, window: window),
                                   name: "score-\(range.rawValue)")
            XCTAssertEqual(labelClusters(in: score, fromX: 66), expected,
                           "Score Differential, \(range.label): a time label runs into its neighbour")
        }
    }
}
