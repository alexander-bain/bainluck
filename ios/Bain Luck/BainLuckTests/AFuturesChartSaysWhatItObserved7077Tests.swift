import XCTest
import SwiftUI
@testable import Bain_Luck

/// #7077 — THE FUTURES CHART DESCRIBED A WEEK IT HAD NOT WATCHED.
///
/// Photographed on Alex's phone, TestFlight 1.0 (15), 2026-09-18 ~17:00 PDT
/// (`artifacts/alex-phone-20260918-build15/game-awards-chart.png`, `meta-chart.png`)
/// and reproduced on the simulator at master in `artifacts/native-241/BEFORE-*.png`:
///
/// * **The Game Awards: Game of the Year** (58321581) — `7d` selected, and the
///   axis read **Sep 18 · Sep 18 · Sep 18 · Sep 18 · Sep 18 · Sep…**: six labels,
///   touching, the last one cut off, naming one day six times.
/// * **Meta announces a training pause by October 31?** (61122553) — two straight
///   lines crossing over **Sep 15 · Sep 16 · Sep 16 · Sep 17 · Sep 17 · …**, drawn
///   from exactly TWO observed prices 75 hours apart, and reading as a steady
///   three-day slide from 85% to 5%.
/// * Both carried a **Season** chip. Neither question has a season.
///
/// The common cause is one sentence: **the chart described the window the reader
/// ASKED for instead of the window it actually had.** `hours` and `actual_hours`
/// are both the window the route searched — live/399's producer half added
/// `coverage_hours` and `observation_times`, measured off the points really
/// served, and this suite is the consumer half's contract.
///
/// Every instant below was read from production on 2026-09-19 and is quoted
/// verbatim. The calendar is injected and pinned (gotcha #44) — the axis's
/// day-boundary arithmetic must not depend on where the test runs — and the
/// specimens are checked in BOTH UTC and the Pacific zone the defect was
/// photographed in.
final class AFuturesChartSaysWhatItObserved7077Tests: XCTestCase {

    // MARK: - The specimens, as production served them

    /// 58321581's nine observation times: 20.0 h of prices inside a 168 h request.
    private let gameAwards = [
        "2026-09-18T04:30:00Z", "2026-09-18T05:45:00Z", "2026-09-18T06:45:00Z",
        "2026-09-18T13:45:00Z", "2026-09-18T20:45:00Z", "2026-09-18T21:45:00Z",
        "2026-09-18T22:45:00Z", "2026-09-18T23:45:00Z", "2026-09-19T00:30:00Z",
    ].map { ISO8601DateFormatter().date(from: $0)! }

    /// 61122553's two observation times, 75.25 h apart inside the same request.
    private let metaTrainingPause = [
        "2026-09-15T09:15:00Z", "2026-09-18T12:30:00Z",
    ].map { ISO8601DateFormatter().date(from: $0)! }

    private let utc = TimeZone(identifier: "UTC")!
    private let pacific = TimeZone(identifier: "America/Los_Angeles")!

    private func calendar(_ zone: TimeZone) -> Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = zone
        return cal
    }

    /// The label a style prints for one instant, with the reader's zone and a
    /// pinned locale so the assertion is about the FORMAT, not the runner.
    private func label(
        _ format: Date.FormatStyle, _ instant: Date, zone: TimeZone
    ) -> String {
        var style = format
        style.timeZone = zone
        return style.locale(Locale(identifier: "en_US")).format(instant)
    }

    /// Every tick the chart will draw for this domain, at the plan's own stride.
    private func tickLabels(
        _ plan: OddsChartView.XAxisPlan, over instants: [Date], zone: TimeZone
    ) -> [String] {
        let cal = calendar(zone)
        guard let lo = instants.min(), let hi = instants.max() else { return [] }
        var ticks: [Date] = []
        var cursor = lo
        while cursor <= hi, ticks.count < 64 {
            ticks.append(cursor)
            guard let next = cal.date(byAdding: plan.component, value: plan.count, to: cursor)
            else { break }
            cursor = next
        }
        return ticks.map { label(plan.format, $0, zone: zone) }
    }

    /// The rule this ship replaced: the format was chosen by the CHIP, and `7d`
    /// meant `month().day()` however little data came back.
    private let preFixWeekFormat = Date.FormatStyle.dateTime.month(.abbreviated).day()

    // MARK: - The axis

    func testTheGameAwardsAxisStopsNamingOneDaySixTimes() {
        for zone in [utc, pacific] {
            let plan = EvolutionChartView.axisPlan(
                for: gameAwards, plotWidth: 331, calendar: calendar(zone))
            let labels = tickLabels(plan, over: gameAwards, zone: zone)

            XCTAssertGreaterThanOrEqual(
                labels.count, 2, "\(zone.identifier): a 20-hour chart still needs an axis")
            XCTAssertEqual(
                Set(labels).count, labels.count,
                "\(zone.identifier): every tick must name a different instant — got \(labels)")
            XCTAssertLessThanOrEqual(
                labels.count, 6,
                "\(zone.identifier): six labels is what smeared on Alex's phone — \(labels)")
        }
    }

    /// ⚠️ THE CONTROL. Without it the assertion above is unfalsifiable: a plan that
    /// drew ONE tick would also have no duplicates. This asks the pre-fix rule for
    /// the six labels the reader was actually shown — `.automatic(desiredCount: 5)`
    /// drew six across this domain — and pins that they repeat.
    ///
    /// It is NOT stated as "both ends print the same day": in Pacific, where the
    /// defect was photographed, the domain does cross midnight, so the ends differ
    /// and only the FOUR ticks between them collide. Repetition is the defect;
    /// equality of the endpoints is an accident of the zone.
    func testThePreFixFormatRepeatedItselfAcrossTheGameAwardsChart() {
        for zone in [utc, pacific] {
            let sixTicks = evenlySpaced(count: 6, over: gameAwards)
            let before = sixTicks.map { label(preFixWeekFormat, $0, zone: zone) }
            XCTAssertLessThan(
                Set(before).count, before.count,
                "\(zone.identifier): the photographed axis — \(before)")

            let plan = EvolutionChartView.axisPlan(
                for: gameAwards, plotWidth: 331, calendar: calendar(zone))
            let after = sixTicks.map { label(plan.format, $0, zone: zone) }
            XCTAssertEqual(
                Set(after).count, after.count,
                "\(zone.identifier): the same six instants, told apart — \(after)")
        }
    }

    private func evenlySpaced(count: Int, over instants: [Date]) -> [Date] {
        guard let lo = instants.min(), let hi = instants.max(), count > 1 else { return instants }
        let step = hi.timeIntervalSince(lo) / Double(count - 1)
        return (0..<count).map { lo.addingTimeInterval(step * Double($0)) }
    }

    func testTheMetaChartsTwoObservationsGetTwoDifferentLabels() {
        for zone in [utc, pacific] {
            let plan = EvolutionChartView.axisPlan(
                for: metaTrainingPause, plotWidth: 331, calendar: calendar(zone))
            let labels = tickLabels(plan, over: metaTrainingPause, zone: zone)

            XCTAssertEqual(
                Set(labels).count, labels.count,
                "\(zone.identifier): `Sep 16 · Sep 16` and `Sep 17 · Sep 17` is the defect — \(labels)")
        }
    }

    /// A chart with no points must not crash the planner or ask it for a domain
    /// that runs backwards.
    func testAnEmptySeriesStillPlansAnAxis() {
        let plan = EvolutionChartView.axisPlan(for: [], plotWidth: 331, calendar: calendar(utc))
        XCTAssertGreaterThan(plan.count, 0)
    }

    // MARK: - Observation marks

    func testASparseSeriesIsDrawnWithItsObservationsOnIt() {
        XCTAssertTrue(
            EvolutionChartView.showsObservationMarks(distinctInstants: 2),
            "two prices 75 hours apart must not read as a continuous slide")
        XCTAssertTrue(EvolutionChartView.showsObservationMarks(distinctInstants: 9))
        XCTAssertTrue(
            EvolutionChartView.showsObservationMarks(
                distinctInstants: EvolutionChartView.sparseObservationLimit))
        XCTAssertFalse(
            EvolutionChartView.showsObservationMarks(
                distinctInstants: EvolutionChartView.sparseObservationLimit + 1),
            "past the limit the dots are texture, not information")
        XCTAssertFalse(
            EvolutionChartView.showsObservationMarks(distinctInstants: 0),
            "no points, no marks")
    }

    // MARK: - The coverage note

    func testTheGameAwardsSaysHowFarItsPricesGoBack() {
        XCTAssertEqual(
            EvolutionChartView.coverageNote(
                coverageHours: 20.0, observationTimes: 9, requestedHours: 168),
            "Prices only go back 20h")
    }

    func testTheMetaChartLeadsWithTheCountBecauseTwoPointsAreNotALine() {
        XCTAssertEqual(
            EvolutionChartView.coverageNote(
                coverageHours: 75.25, observationTimes: 2, requestedHours: 168),
            "Only 2 prices seen so far")
        XCTAssertEqual(
            EvolutionChartView.coverageNote(
                coverageHours: 0.0, observationTimes: 1, requestedHours: 168),
            "Only one price seen so far")
    }

    /// ⚠️ THE SECOND CONTROL. A note that always fires is a note nobody reads, and
    /// it would put diagnostic prose on every chart in the app (notice 34).
    func testAWellCoveredWindowSaysNothingAtAll() {
        XCTAssertNil(
            EvolutionChartView.coverageNote(
                coverageHours: 160.0, observationTimes: 600, requestedHours: 168),
            "a week of prices in a week-long window needs no caption")
        XCTAssertNil(
            EvolutionChartView.coverageNote(
                coverageHours: 20.0, observationTimes: 9, requestedHours: 24),
            "20 of 24 hours is covered — the note belongs to the wide windows")
        XCTAssertNil(
            EvolutionChartView.coverageNote(
                coverageHours: nil, observationTimes: nil, requestedHours: 168),
            "an older server sends neither key, and silence is the honest answer")
    }

    func testTheSpanIsSaidInAUnitAReaderCanHold() {
        XCTAssertEqual(EvolutionChartView.coverageSpanWord(0.4), "under an hour")
        XCTAssertEqual(EvolutionChartView.coverageSpanWord(20.0), "20h")
        XCTAssertEqual(EvolutionChartView.coverageSpanWord(47.6), "48h")
        XCTAssertEqual(EvolutionChartView.coverageSpanWord(75.25), "3d")
        XCTAssertEqual(EvolutionChartView.coverageSpanWord(600.0), "25d")
    }

    // MARK: - The word on the widest chip

    func testTheGameAwardsAndMetaDoNotHaveASeason() {
        for category in ["entertainment", "tech", "politics", "economics", "crypto", "weather"] {
            XCTAssertEqual(
                EvolutionRangeVocabulary.seasonWord(
                    sportCategory: category, hasTournamentDates: false),
                "6M",
                "\(category) markets were being labelled Season")
        }
        XCTAssertEqual(
            EvolutionRangeVocabulary.seasonWord(sportCategory: nil, hasTournamentDates: false),
            "6M",
            "an unknown category takes the honest generic, never the specific claim")
    }

    func testAMarketThatDoesHaveASeasonKeepsTheWord() {
        for category in ["football", "Basketball", " soccer ", "hockey", "baseball"] {
            XCTAssertEqual(
                EvolutionRangeVocabulary.seasonWord(
                    sportCategory: category, hasTournamentDates: false),
                "Season",
                "\(category) has a season and the chip should say so")
        }
        XCTAssertEqual(
            EvolutionRangeVocabulary.seasonWord(
                sportCategory: "golf", hasTournamentDates: true),
            "Season",
            "beside an `Event` chip, `Season` means the tour around it")
    }

    func testOnlyTheWidestChipTakesTheSubstitutedWord() {
        XCTAssertEqual(EvolutionTimeRange.season.label(seasonWord: "6M"), "6M")
        for range in [EvolutionTimeRange.week, .day, .today, .tournament] {
            XCTAssertEqual(
                range.label(seasonWord: "6M"), range.rawValue,
                "every other chip already names a real duration")
        }
    }

    /// The bar draws the substituted word on one line at the narrowest phone.
    /// `6M` is shorter than `Season`, so this cannot regress #4199's fix — it is
    /// here so that a future vocabulary change cannot quietly get longer.
    @MainActor
    func testTheSubstitutedChipStillFitsOnOnePhoneRow() {
        let ranges: [EvolutionTimeRange] = [.season, .week, .day, .today]
        let oneLine = barHeight(ranges, seasonWord: "6M", width: 1200)
        for width in [CGFloat(375), 402] {
            XCTAssertEqual(
                barHeight(ranges, seasonWord: "6M", width: width), oneLine, accuracy: 0.5,
                "the bar wrapped at \(width)pt")
        }
    }

    @MainActor
    private func barHeight(
        _ ranges: [EvolutionTimeRange], seasonWord: String, width: CGFloat
    ) -> CGFloat {
        let bar = EvolutionControlBar(
            availableRanges: ranges,
            selectedRange: .constant(.week),
            showCombinedProbability: .constant(false),
            topFilter: .constant(10),
            seasonWord: seasonWord
        )
        let host = hostForMeasurement(bar.frame(width: width), at: .large)
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
            in: CGSize(width: width, height: .greatestFiniteMagnitude)).height
    }

    // MARK: - The seam a pure suite cannot see

    /// ⚠️ EVERY ASSERTION ABOVE MEASURES A RULE, AND A RULE CAN BE PERFECT WHILE THE
    /// CHART IGNORES IT. The axis format lives inside `.chartXAxis`, the chip's word
    /// inside a `@ViewBuilder`, and neither is reachable from a test: a SwiftUI body
    /// returning an opaque type cannot be called, so a mutant that reverts either
    /// call site leaves this file green. That is the same shape as #4624 and the
    /// `TeamLogoView.initialsFallback` survivor, and the answer here is the one
    /// `ChartLegendPrintsTheBoardsNumber5949Tests` already uses — scan the call site
    /// itself, anchored on the line the reader's pixels come from.
    ///
    /// The comment strip is why the anchors cannot be satisfied by the prose in the
    /// file that explains them.
    func testTheChartActuallyASKSTheseRulesRatherThanDecidingForItself() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
        let chart = try code(
            at: root.appendingPathComponent("Bain Luck/Components/EvolutionChartView.swift"))

        // #4445 moved the planning into `axisLayout` (the drawn size picks the
        // stride, or the window's endpoints) — still fed the DRAWN points, and both
        // arms still print the plan's own format.
        XCTAssertTrue(
            chart.contains("let axis = Self.axisLayout(\n                for: entries.map(\\.date)"),
            "the axis must be planned from the points it DRAWS")
        XCTAssertEqual(
            chart.components(separatedBy: "AxisValueLabel(\n                        format: plan.format,").count - 1,
            2,
            "…and both axis arms must print the plan's own format")
        XCTAssertFalse(
            chart.contains(".automatic(desiredCount: 5)"),
            "the pre-fix tick rule: six labels across a 20-hour chart")
        XCTAssertFalse(
            chart.contains("selectedRange == .tournament"),
            "the pre-fix label rule keyed the format on the CHIP the reader pressed")

        XCTAssertTrue(
            chart.contains("Text(range.label(seasonWord: seasonWord))"),
            "the chip must print the word chosen for THIS market")
        XCTAssertFalse(
            chart.contains("Text(range.rawValue)"),
            "`Season` over The Game Awards is the reported defect")
        XCTAssertTrue(
            chart.contains("seasonWord: EvolutionRangeVocabulary.seasonWord("),
            "and the chart must be the one that chooses it, off the market's category")
        XCTAssertTrue(
            chart.contains("Self.coverageNote("),
            "the caption must come from the rule, not from a second copy in the body")
        XCTAssertTrue(
            chart.contains(".symbolSize(showsObservationMarks ? 14 : 0)"),
            "a sparse series must carry its observations")
    }

    private func code(at url: URL) throws -> String {
        let source = try String(contentsOf: url, encoding: .utf8)
        let stripped = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertTrue(
            stripped.contains("struct EvolutionChartView"),
            "the comment strip left nothing to scan in \(url.lastPathComponent)")
        return stripped
    }

    // MARK: - The payload half

    func testTheCoverageKeysAreDecodedAndTheirAbsenceIsNotAZero() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let served = """
        {"market_id": 58321581, "market_name": "The Game Awards: Game of the Year",
         "sport_category": "entertainment", "source": "polymarket",
         "hours": 168, "actual_hours": 168, "top": 50,
         "coverage_start": "2026-09-18T04:30:00+00:00",
         "coverage_end": "2026-09-19T00:30:00+00:00",
         "coverage_hours": 20.0, "observation_times": 9, "bucket_seconds": 900,
         "timeline": [], "outcomes": []}
        """.data(using: .utf8)!
        let payload = try decoder.decode(ProbabilityTimelineResponse.self, from: served)
        XCTAssertEqual(payload.coverageHours, 20.0)
        XCTAssertEqual(payload.observationTimes, 9)
        XCTAssertEqual(payload.hours, 168, "the requested window is untouched")
        XCTAssertEqual(payload.bucketSeconds, 900, "still non-optional, still read by shipped builds")

        // An older server, and an empty history, both send no coverage at all.
        let legacy = """
        {"market_id": 1, "market_name": "x", "sport_category": null, "source": null,
         "hours": 168, "top": 50, "bucket_seconds": 900, "timeline": [], "outcomes": []}
        """.data(using: .utf8)!
        let old = try decoder.decode(ProbabilityTimelineResponse.self, from: legacy)
        XCTAssertNil(old.coverageHours, "an absence must not arrive as 0 hours (gotcha #53)")
        XCTAssertNil(old.observationTimes)
    }
}
