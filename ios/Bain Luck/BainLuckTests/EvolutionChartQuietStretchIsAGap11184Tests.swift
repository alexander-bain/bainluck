import XCTest
@testable import Bain_Luck

/// #11184 — a futures chart shows a quiet stretch as a gap, not as a smooth rise
/// or fall that nobody observed.
///
/// **The specimen.** 13795456 *Iran leadership change by December 31?* on Max,
/// served 2026-10-17 13:49Z (`/api/futures/13795456/probability-timeline?top=50
/// &hours=168&range=full`, the app's own query). The No leg reads 59.5% at
/// Apr 9 00:00:29Z and 71.5% at Apr 18 00:00:23Z with nothing between; both legs
/// go from Aug 10 00:00:20Z to Aug 26 with nothing between. The chart drew each
/// as one solid straight line — a steady nine-day rise and a sixteen-day slope
/// that were never observed.
///
/// **The rule is web's, with web's numbers** (`frontend/lib/chartSeriesPath.ts`
/// + `seriesGapThresholdMs`): per series, six of its own median gaps, floored at
/// two hours, and no split at all under four points.
///
/// The fixture is the served payload verbatim, decoded with the app's decoder, so
/// the medians these tests grade against are the ones the reader's chart computes.
final class EvolutionChartQuietStretchIsAGap11184Tests: XCTestCase {

    // MARK: - Harness

    private static let fixtureURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .appendingPathComponent("Fixtures")
        .appendingPathComponent("futures-13795456-timeline-full-11184.20261017T1349Z.json")

    private static func payload() throws -> ProbabilityTimelineResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            ProbabilityTimelineResponse.self, from: Data(contentsOf: fixtureURL))
    }

    /// One leg on its own clock: the instants the timeline serves THAT outcome at,
    /// in the timeline's order — what `EvolutionChartView.splitAtGaps` hands the rule.
    private static func leg(_ name: String, in payload: ProbabilityTimelineResponse) -> [Date] {
        payload.timeline.compactMap { entry in
            entry.outcomes[name] == nil ? nil : entry.timestamp.asDate
        }
    }

    private static func instant(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

    /// Asserts the step from `from` to `to` is the boundary between two runs, and
    /// that they are consecutive observations of the leg — the bridge spans
    /// exactly these two real points and nothing is invented between them.
    private func assertGap(
        _ name: String, from: String, to: String,
        instants: [Date], runs: [Int],
        file: StaticString = #filePath, line: UInt = #line
    ) {
        guard let i = instants.firstIndex(of: Self.instant(from)) else {
            return XCTFail("\(name) has no observation at \(from)", file: file, line: line)
        }
        XCTAssertLessThan(i + 1, instants.count, file: file, line: line)
        guard i + 1 < instants.count else { return }
        XCTAssertEqual(instants[i + 1], Self.instant(to),
                       "\(name): \(from) and \(to) must be consecutive observations",
                       file: file, line: line)
        XCTAssertEqual(runs[i + 1], runs[i] + 1,
                       "\(name) \(from) → \(to) must be drawn as a gap, not a solid line",
                       file: file, line: line)
    }

    // MARK: - The specimen

    func testTheNineAndSixteenDayStretchesAreGapsOnBothLegs() throws {
        let payload = try Self.payload()
        let no = Self.leg("No", in: payload)
        let yes = Self.leg("Yes", in: payload)
        XCTAssertEqual(no.count, 998, "fixture drifted — the served No leg")
        XCTAssertEqual(yes.count, 1985, "fixture drifted — the served Yes leg")

        let noRuns = EvolutionSeriesGaps.runs(no)
        let yesRuns = EvolutionSeriesGaps.runs(yes)

        // Each leg on its OWN clock: the seconds differ (00:00:29 vs 00:00:32),
        // so a chart-wide clock would have missed one of them.
        assertGap("No", from: "2026-04-09T00:00:29Z", to: "2026-04-18T00:00:23Z",
                  instants: no, runs: noRuns)
        assertGap("Yes", from: "2026-04-09T00:00:32Z", to: "2026-04-18T00:00:27Z",
                  instants: yes, runs: yesRuns)
        assertGap("No", from: "2026-08-10T00:00:20Z", to: "2026-08-26T00:00:25Z",
                  instants: no, runs: noRuns)
        assertGap("Yes", from: "2026-08-10T00:00:20Z", to: "2026-08-26T00:00:26Z",
                  instants: yes, runs: yesRuns)
    }

    func testEachLegIsGradedAgainstItsOwnMedianWithWebsConstants() throws {
        let payload = try Self.payload()
        // Both legs' served median step is one hour, so six medians is six hours
        // (above web's two-hour floor) — the same number `seriesGapThresholdMs`
        // gives these instants.
        XCTAssertEqual(EvolutionSeriesGaps.threshold(Self.leg("No", in: payload)), 6 * 3600)
        XCTAssertEqual(EvolutionSeriesGaps.threshold(Self.leg("Yes", in: payload)), 6 * 3600)
        XCTAssertEqual(EvolutionSeriesGaps.minPointsForCadence, 4)
        XCTAssertEqual(EvolutionSeriesGaps.gapCadenceMultiple, 6)
        XCTAssertEqual(EvolutionSeriesGaps.gapFloor, 2 * 3600)
    }

    /// The solid stroke touches only real observations, and every one of them:
    /// a run boundary falls exactly where a step exceeds the threshold, never
    /// elsewhere, and no point is added or dropped.
    func testRunsBreakExactlyAtStepsOverTheThresholdAndKeepEveryPoint() throws {
        let payload = try Self.payload()
        for name in ["No", "Yes"] {
            let instants = Self.leg(name, in: payload)
            let runs = EvolutionSeriesGaps.runs(instants)
            let threshold = try XCTUnwrap(EvolutionSeriesGaps.threshold(instants))
            XCTAssertEqual(runs.count, instants.count, "\(name): no synthetic or dropped points")
            XCTAssertEqual(runs.first, 0)
            for i in 1..<instants.count {
                let step = instants[i].timeIntervalSince(instants[i - 1])
                XCTAssertEqual(runs[i] - runs[i - 1], step > threshold ? 1 : 0,
                               "\(name) step \(i) (\(step)s vs \(threshold)s)")
            }
        }
    }

    // MARK: - Controls: what must NOT break

    /// A healthy series — the one nearly every chart plots nearly all of the time —
    /// stays one solid run.
    func testAnUnbrokenHourlySeriesStaysOneRun() {
        let start = Self.instant("2026-10-10T00:00:00Z")
        let hourly = (0..<48).map { start.addingTimeInterval(Double($0) * 3600) }
        XCTAssertEqual(Set(EvolutionSeriesGaps.runs(hourly)), [0])
    }

    /// A skipped beat is normal operation: a step of five medians stays solid,
    /// seven medians breaks — the multiple is six, not "any step longer than usual".
    func testTheMultipleIsSixMediansNotAnyLongerStep() {
        let start = Self.instant("2026-10-10T00:00:00Z")
        var instants = (0..<20).map { start.addingTimeInterval(Double($0) * 3600) }
        let fiveLater = instants.last!.addingTimeInterval(5 * 3600)
        instants.append(fiveLater)
        instants.append(contentsOf: (1...5).map { fiveLater.addingTimeInterval(Double($0) * 3600) })
        let sevenLater = instants.last!.addingTimeInterval(7 * 3600)
        instants.append(sevenLater)
        instants.append(contentsOf: (1...5).map { sevenLater.addingTimeInterval(Double($0) * 3600) })

        let runs = EvolutionSeriesGaps.runs(instants)
        XCTAssertEqual(runs[20], 0, "five medians is a skipped beat, drawn solid")
        XCTAssertEqual(runs[26], 1, "seven medians is a gap")
    }

    /// A fast series is not broken for a trivially small lapse: at a two-minute
    /// cadence six medians is twelve minutes, and the two-hour floor holds.
    func testTheTwoHourFloorHoldsForAFastSeries() {
        let start = Self.instant("2026-10-10T00:00:00Z")
        var instants = (0..<30).map { start.addingTimeInterval(Double($0) * 120) }
        instants.append(instants.last!.addingTimeInterval(90 * 60))
        XCTAssertEqual(Set(EvolutionSeriesGaps.runs(instants)), [0])
    }

    /// Under four points there is no cadence to grade against, so nothing is split
    /// and the line draws exactly as it did before — web returns its one run too.
    func testThreePointsHaveNoCadenceAndAreNotSplit() {
        let instants = ["2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z", "2026-05-01T00:00:00Z"]
            .map(Self.instant)
        XCTAssertNil(EvolutionSeriesGaps.threshold(instants))
        XCTAssertEqual(EvolutionSeriesGaps.runs(instants), [0, 0, 0])
    }

    // MARK: - The chart draws the rule

    /// The pure rule is only half: the chart must key its solid line on the run,
    /// draw the bridge dotted and faint, and mark a point standing alone. Read off
    /// the view's own source, comments stripped.
    func testTheChartKeysItsSolidLineOnTheRunAndDrawsBridgesDotted() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/EvolutionChartView.swift")
        // Comment lines dropped, so a pin can only be met by code.
        let source = try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertTrue(source.contains("return Self.splitAtGaps(points)"),
                      "chartEntries must number its points into runs")
        XCTAssertTrue(source.contains("series: .value(\"Series\", \"\\(point.name)#\\(point.run)\")"),
                      "the solid line must be one series per run, or it crosses the gap")
        XCTAssertTrue(source.contains("series: .value(\"Series\", bridge.id)"),
                      "each bridge must be its own series")
        XCTAssertTrue(source.contains("dash: Self.gapBridgeDash"))
        XCTAssertTrue(source.contains("isCombined: false) * 0.3)"),
                      "a bridge is a third of its line's opacity, never as loud as data")
        XCTAssertTrue(source.contains("showsObservationMarks || point.standsAlone ? 14 : 0"),
                      "a point alone in its run must still be visible")
        XCTAssertEqual(EvolutionChartView.gapBridgeDash, [1, 5])
    }
}
