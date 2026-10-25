import XCTest
@testable import Bain_Luck

/// #683 — a Kalshi price recovered from Kalshi's own record is drawn on the
/// Evolution chart as what it is: a recorded interval, labelled under the chart and
/// in the scrub readout, never a live reading.
///
/// The archive shapes below are DETERMINISTIC FIXTURES of calibration's unpublished
/// contract (PR #11083, head `c3a9b8ae3a`), produced by that head's own serializers
/// `kalshi_archive_reader.history_point` / `timeline_mark` over hand-built rows, not
/// read from production: the store is empty until the attended import runs.
@MainActor
final class EvolutionArchiveProvenance683Tests: XCTestCase {
    private typealias P = EvolutionArchiveProvenance
    private typealias T = VerifiedTitleConsumer9387Tests
    private typealias F = VerifiedTitle9387Fixtures

    private static let thunder = "Oklahoma City Thunder"
    private static let celtics = "Boston Celtics"

    private static func mark(_ start: String, _ basis: String?, period: Int? = 60,
                             provenance: String? = P.kalshiArchive) -> TimelineArchiveMark {
        TimelineArchiveMark(provenance: provenance, intervalStart: start,
                            periodMinutes: period, priceBasis: basis)
    }

    private func note(_ json: String = archiveTimeline, cutoff: Date? = nil,
                      names: Set<String> = [thunder, celtics]) throws -> String? {
        let drawn = P.drawnMarks(in: try T.timeline(json).timeline, names: names, cutoff: cutoff)
        return P.note(marks: drawn.marks, drawnValues: drawn.values)
    }

    // MARK: - Decoding the contract

    func testTheArchiveTimelineDecodesEachValuesMarkAndLeavesLiveEntriesUnmarked() throws {
        let response = try T.timeline(Self.archiveTimeline)
        XCTAssertEqual(response.timeline.count, 4)
        let first = response.timeline[0]
        XCTAssertEqual(first.outcomes[Self.thunder], 0.41)
        XCTAssertEqual(first.archive?[Self.thunder],
                       Self.mark("2026-04-01T13:00:00+00:00", P.tradedInterval))
        XCTAssertEqual(response.timeline[1].archive?[Self.thunder]?.priceBasis, P.quoteOnly)
        XCTAssertNil(response.timeline[1].archive?[Self.celtics],
                     "a value without a mark at an archive instant is not archived")
        XCTAssertNil(response.timeline[2].archive, "live capture: no mark")
        XCTAssertNil(response.timeline[3].archive, "live capture: no mark")
    }

    func testALiveOnlyTimelineDecodesAsBeforeAndCarriesNoLine() throws {
        let response = try T.timeline(F.timelineVerified)
        XCTAssertEqual(response.timeline.count, 3)
        XCTAssertTrue(response.timeline.allSatisfy { $0.archive == nil })
        XCTAssertNil(try note(F.timelineVerified, names: Set(response.outcomes.map(\.name))))
    }

    func testAMarkPresentButUnreadableStillLabelsItsValueAsRecorded() throws {
        let json = Self.archiveTimeline.replacingOccurrences(
            of: #""archive":{"Oklahoma City Thunder":{"provenance":"kalshi_archive","interval_start":"2026-04-01T13:00:00+00:00","period_minutes":60,"price_basis":"traded_interval"}"#,
            with: #""archive":{"Oklahoma City Thunder":{"provenance":7,"period_minutes":"sixty"}"#)
        XCTAssertNotEqual(json, Self.archiveTimeline, "the edit must land")
        let response = try T.timeline(json)
        let mark = try XCTUnwrap(response.timeline[0].archive?[Self.thunder])
        XCTAssertNil(mark.provenance)
        XCTAssertNil(mark.periodMinutes)
        XCTAssertEqual(
            P.note(marks: [mark], drawnValues: 3),
            "Some prices here are from the market's record, not live readings.")
    }

    func testAnArchiveBlockThatIsNotAnObjectCostsTheChartNoLines() throws {
        let json = try T.edited(Self.archiveTimeline) { object in
            var timeline = object["timeline"] as! [[String: Any]]
            timeline[0]["archive"] = "unreadable"
            object["timeline"] = timeline
        }
        let response = try T.timeline(json)
        XCTAssertNil(response.timeline[0].archive)
        XCTAssertEqual(response.timeline[0].outcomes[Self.thunder], 0.41)
        XCTAssertEqual(response.timeline.count, 4)
    }

    // MARK: - The line under the chart

    func testTheChartSaysWhichPricesAreKalshisHourlyRecord() throws {
        XCTAssertEqual(try note(),
                       "Some prices here are from Kalshi's hourly record of trades and quotes, not live readings.")
    }

    func testAWindowHoldingOnlyLiveCapturesSaysNothing() throws {
        let afterArchive = try XCTUnwrap("2026-04-01T16:00:00+00:00".asDate)
        XCTAssertNil(try note(cutoff: afterArchive))
    }

    func testOnlyTheDrawnLinesAreCounted() throws {
        // From 15:00 the Celtics' values are all live (their one mark is the 14:00
        // traded hour); the Thunder's 15:00 quoted hour is in the window but not drawn.
        let fromThree = try XCTUnwrap("2026-04-01T15:00:00+00:00".asDate)
        XCTAssertNotNil(try note(cutoff: fromThree, names: [Self.thunder]),
                        "control: the Thunder's mark is inside this window")
        XCTAssertNil(try note(cutoff: fromThree, names: [Self.celtics]),
                     "the Celtics' values here are all live; the Thunder's marks are not on screen")
        XCTAssertNil(try note(names: []))
    }

    func testWhenEveryDrawnPriceIsRecordedTheLineSaysSo() {
        let marks = [Self.mark("2026-04-01T13:00:00+00:00", P.tradedInterval),
                     Self.mark("2026-04-01T14:00:00+00:00", P.tradedInterval)]
        XCTAssertEqual(P.note(marks: marks, drawnValues: 2),
                       "These prices are from Kalshi's hourly record of trades, not live readings.")
    }

    func testTheBasisAndGrainWordsAreOnlyTheOnesEveryMarkSupports() {
        let quote = Self.mark("a", P.quoteOnly)
        XCTAssertEqual(P.note(marks: [quote], drawnValues: 5),
                       "Some prices here are from Kalshi's hourly record of quotes (no trades), not live readings.")
        let minute = Self.mark("a", P.tradedInterval, period: 1)
        XCTAssertEqual(P.note(marks: [minute], drawnValues: 5),
                       "Some prices here are from Kalshi's minute-by-minute record of trades, not live readings.")
        XCTAssertEqual(P.note(marks: [minute, Self.mark("a", P.tradedInterval)], drawnValues: 5),
                       "Some prices here are from Kalshi's record of trades, not live readings.",
                       "mixed grains drop the grain word")
        XCTAssertEqual(P.note(marks: [Self.mark("a", "something_new")], drawnValues: 5),
                       "Some prices here are from Kalshi's hourly record, not live readings.",
                       "an unknown basis claims neither trades nor quotes")
        XCTAssertNil(P.note(marks: [], drawnValues: 5))
    }

    func testTheCopyNeverPrintsARawFieldString() throws {
        let copies = [try note(),
                      P.readoutLine(marks: [Self.mark("a", P.tradedInterval)]),
                      P.readoutLine(marks: [Self.mark("a", P.quoteOnly)])].compactMap { $0 }
        XCTAssertEqual(copies.count, 3)
        for copy in copies {
            for raw in ["kalshi_archive", "traded_interval", "quote_only", "_", "period", "provenance"] {
                XCTAssertFalse(copy.contains(raw), "\(copy) prints \(raw)")
            }
        }
    }

    // MARK: - The scrub readout

    func testTheReadoutNamesTheRecordAndItsBasis() {
        XCTAssertEqual(P.readoutLine(marks: [Self.mark("a", P.tradedInterval)]), "From Kalshi's record · traded")
        XCTAssertEqual(P.readoutLine(marks: [Self.mark("a", P.quoteOnly)]), "From Kalshi's record · quote, no trades")
        XCTAssertEqual(P.readoutLine(marks: [Self.mark("a", P.quoteOnly), Self.mark("a", P.tradedInterval)]),
                       "From Kalshi's record")
        XCTAssertNil(P.readoutLine(marks: []))
    }

    func testTheReadoutPrintsTheIntervalOnlyWhenEveryMarkAgreesOnItsStart() throws {
        let close = try XCTUnwrap("2026-04-01T14:00:00+00:00".asDate)
        let start = try XCTUnwrap("2026-04-01T13:00:00+00:00".asDate)
        let hour = Self.mark("2026-04-01T13:00:00+00:00", P.tradedInterval)
        XCTAssertEqual(P.interval(closingAt: close, marks: [hour, hour]), start...close)
        XCTAssertNil(P.interval(closingAt: close, marks: [hour, Self.mark("2026-04-01T13:59:00+00:00", nil)]))
        XCTAssertNil(P.interval(closingAt: close, marks: [Self.mark("not a date", nil)]))
        XCTAssertNil(P.interval(closingAt: start, marks: [hour]), "a start at or after the close is no interval")
        XCTAssertNil(P.interval(closingAt: close, marks: []))
    }

    // MARK: - `/history` (the verified chart's lines) carries the same marks

    func testHistoryPointsKeepTheirMarksOnTheLinesTheyJoin() throws {
        let history = try VerifiedTitleHistory10244Tests.history(Self.archiveHistory)
        let points = try XCTUnwrap(history.outcomes.first?.history)
        XCTAssertEqual(points[0].archiveMark, Self.mark("2026-04-01T13:00:00+00:00", P.tradedInterval))
        XCTAssertNil(points[2].archiveMark, "a consensus point is live")

        let drawn = VerifiedTitleHistory.drawing(history, over: try T.timeline(Self.archiveTimeline))
        XCTAssertEqual(drawn.timeline.map(\.timestamp), [
            "2026-04-01T14:00:00+00:00", "2026-04-01T15:00:00+00:00", "2026-04-01T16:30:00+00:00",
        ])
        XCTAssertEqual(drawn.timeline[0].archive?[Self.thunder]?.priceBasis, P.tradedInterval)
        XCTAssertEqual(drawn.timeline[1].archive?[Self.thunder]?.priceBasis, P.quoteOnly)
        XCTAssertNil(drawn.timeline[2].archive)
        let marks = P.drawnMarks(in: drawn.timeline, names: [Self.thunder], cutoff: nil)
        XCTAssertEqual(marks.marks.count, 2)
        XCTAssertEqual(marks.values, 3)
    }

    func testAHistoryPointWithoutTheArchiveProvenanceIsNotMarked() throws {
        let json = Self.archiveHistory.replacingOccurrences(
            of: #""bookmaker":"kalshi_archive","provenance":"kalshi_archive""#,
            with: #""bookmaker":"kalshi_archive","provenance":"venue_history""#)
        XCTAssertNotEqual(json, Self.archiveHistory, "the edit must land")
        let history = try VerifiedTitleHistory10244Tests.history(json)
        XCTAssertTrue(history.outcomes[0].history.allSatisfy { $0.archiveMark == nil })
    }

    // MARK: - Fixtures (PR #11083 `c3a9b8ae3a` shapes)

    /// `/probability-timeline` for a settled Kalshi board: two archive closes (one
    /// traded hour, one quoted-only hour) before two live captures, plus the
    /// additive `archive_history` block, which the client does not read.
    static let archiveTimeline = #"""
{"market_id":59165001,"market_name":"NBA Champion 2026","sport_category":"basketball","source":"kalshi",
 "hours":4320,"top":50,"bucket_seconds":3600,"coverage_hours":3.5,"observation_times":4,
 "outcomes":[
  {"id":1,"name":"Oklahoma City Thunder","current_probability":0.47,"rank":1},
  {"id":2,"name":"Boston Celtics","current_probability":0.53,"rank":2}
 ],
 "timeline":[
  {"timestamp":"2026-04-01T14:00:00+00:00","outcomes":{"Oklahoma City Thunder":0.41,"Boston Celtics":0.59},"archive":{"Oklahoma City Thunder":{"provenance":"kalshi_archive","interval_start":"2026-04-01T13:00:00+00:00","period_minutes":60,"price_basis":"traded_interval"},"Boston Celtics":{"provenance":"kalshi_archive","interval_start":"2026-04-01T13:00:00+00:00","period_minutes":60,"price_basis":"traded_interval"}}},
  {"timestamp":"2026-04-01T15:00:00+00:00","outcomes":{"Oklahoma City Thunder":0.43,"Boston Celtics":0.58},"archive":{"Oklahoma City Thunder":{"provenance":"kalshi_archive","interval_start":"2026-04-01T14:00:00+00:00","period_minutes":60,"price_basis":"quote_only"}}},
  {"timestamp":"2026-04-01T16:30:00+00:00","outcomes":{"Oklahoma City Thunder":0.45,"Boston Celtics":0.55}},
  {"timestamp":"2026-04-01T17:30:00+00:00","outcomes":{"Oklahoma City Thunder":0.47,"Boston Celtics":0.53}}
 ],
 "archive_history":{"state":"served","provenance":"kalshi_archive","points_served":3,"outcomes_served":2,"observed_from":"2026-04-01T14:00:00+00:00","observed_through":"2026-04-01T15:00:00+00:00","periods_minutes":[60],"price_basis":{"traded_interval":2,"quote_only":1},"withheld_overlapping_live":0}}
"""#

    /// `/history` for the same board: two archive points, then a live consensus point.
    static let archiveHistory = #"""
{"market_id":59165001,"coverage_hours":2.5,"observation_times":3,
 "outcomes":[
  {"outcome_id":1,"name":"Oklahoma City Thunder","history":[
   {"timestamp":"2026-04-01T14:00:00+00:00","probability":0.41,"american_odds":null,"bookmaker":"kalshi_archive","provenance":"kalshi_archive","interval_start":"2026-04-01T13:00:00+00:00","period_minutes":60,"price_basis":"traded_interval"},
   {"timestamp":"2026-04-01T15:00:00+00:00","probability":0.43,"american_odds":null,"bookmaker":"kalshi_archive","provenance":"kalshi_archive","interval_start":"2026-04-01T14:00:00+00:00","period_minutes":60,"price_basis":"quote_only"},
   {"timestamp":"2026-04-01T16:30:00+00:00","probability":0.45,"american_odds":-122,"bookmaker":"consensus"}
  ]}
 ],
 "archive_history":{"state":"served","provenance":"kalshi_archive","points_served":2}}
"""#
}
