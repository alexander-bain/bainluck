import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the tennis match screen's adapter, part three (the dated reading
/// beside the history), on the same REAL served bodies part two reads:
/// `TennisHistoryAdapter10868Tests.liveHistory` / `.finalHistory` (reduced
/// verbatim subsets; sources, sha256 and kept rows are listed there) and part
/// one's `liveDetail` / `finalDetail` (byte for byte, sha256 in
/// `TennisMatchPageAdapter10868Tests`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED here, each named where used: the reader's `now`; held values
/// (a tap position, a reading of the pinned edge); an unconfirmed start
/// (`start_is_tbd: true` in the DETAIL body) and a before variant (`status:
/// scheduled`, `commence_time` 13:00Z), neither editing the history. Two
/// LABELLED history controls do edit named served rows (`finalWithCertainty`,
/// `liveWithBarriers`); they are constructed shapes, not observations of
/// these matches — the retained final's last genuine reading is 0.891273 and
/// never reaches the certainty edge.
///
/// Every series is compared with the history's OWN drawn home trace for the
/// same body, event and clock (`TennisHistoryAdapter10868.history`): the same
/// vertices in the same runs, and the same inspection inside a run and inside
/// each break — never only equal counts.
@MainActor
final class TennisReadingAdapter10868Tests: XCTestCase {
    private typealias R = TennisReadingAdapter10868
    private typealias Fixtures = TennisMatchPageAdapter10868Tests
    private typealias Histories = TennisHistoryAdapter10868Tests
    private typealias H = TennisHistoryAdapter10868
    private typealias Series = TennisChartReading9483.Series

    private func at(_ stamp: String) -> Date { stamp.asDate! }

    private func liveSeries() throws -> TennisChartReading9483.Series {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        return try XCTUnwrap(R.series(try Histories.live(), event: event, now: at(Fixtures.liveReadAt)))
    }

    private func finalSeries() throws -> TennisChartReading9483.Series {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        return try XCTUnwrap(R.series(try Histories.finished(), event: event, now: at(Fixtures.finalReadAt)))
    }

    // MARK: - The chart's own trace

    /// The history's drawn home trace for the same body, event and clock, run
    /// by run, as (time, value) — the chart beside the reading.
    private func chartRuns(_ history: EventHistoryResponse, _ event: EventDetail, now: Date) -> [[[Double]]] {
        let phase = TennisMatchPageAdapter10868.phase(event, now: now)
        let input = H.history(history, event: event, phase: phase,
                              host: H.Host(now: now, calendar: Fixtures.pacific, locale: Fixtures.locale))
        return input.series[0].runs.map { run in run.points.map { [$0.x, $0.probability] } }
    }

    private func readerRuns(_ series: Series) -> [[[Double]]] {
        series.segments.map { run in run.map { [$0.date.timeIntervalSince1970, $0.probability] } }
    }

    /// Exact membership — the same vertices in the same runs, and the same
    /// flat points — and the same inspection: a tap a quarter of the way to
    /// the next vertex of a run holds that vertex, and a tap inside each of
    /// the chart's breaks holds the break.
    private func assertReadsTheChart(_ series: Series, _ chart: [[[Double]]],
                                     file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertFalse(chart.isEmpty, "the chart draws something", file: file, line: line)
        XCTAssertEqual(readerRuns(series), chart, "vertex for vertex, run for run", file: file, line: line)
        XCTAssertEqual(series.points.map { [$0.date.timeIntervalSince1970, $0.probability] }, chart.flatMap { $0 },
                       file: file, line: line)
        for (number, run) in chart.enumerated() {
            for (vertex, next) in zip(run, run.dropFirst()) {
                let tap = Date(timeIntervalSince1970: vertex[0] + (next[0] - vertex[0]) / 4)
                guard case .reading(let held)? = series.inspect(at: tap) else {
                    XCTFail("a tap inside a drawn run holds a reading", file: file, line: line)
                    continue
                }
                XCTAssertEqual([held.date.timeIntervalSince1970, held.home], vertex, file: file, line: line)
            }
            guard number + 1 < chart.count, let end = run.last, let start = chart[number + 1].first else { continue }
            let inside = Date(timeIntervalSince1970: (end[0] + start[0]) / 2)
            XCTAssertEqual(series.inspect(at: inside), TennisChartReading9483.Held.gap(inside),
                           "inside the chart's break: the break, never a neighbour", file: file, line: line)
        }
    }

    func testEverySeriesIsTheChartsOwnTraceOnTheGenuineAndConstructedStartBodies() throws {
        let live = try Fixtures.detail(Fixtures.liveDetail)
        let finished = try Fixtures.detail(Fixtures.finalDetail)
        // CONSTRUCTED details only (the history is never edited): a before variant and an unconfirmed start.
        let before = try Fixtures.edited(Fixtures.liveDetail, ["status": "scheduled",
                                                               "commence_time": "2026-10-12T13:00:00+00:00"])
        let unconfirmed = try Fixtures.edited(Fixtures.liveDetail, ["start_is_tbd": true])
        let liveHistory = try Histories.live()
        let finalHistory = try Histories.finished()
        let cases: [(EventDetail, EventHistoryResponse, Date, Int, Int)] = [
            (live, liveHistory, at(Fixtures.liveReadAt), 89, 1),
            (finished, finalHistory, at(Fixtures.finalReadAt), 20, 2),
            (before, liveHistory, at(Fixtures.liveReadAt), 101, 1),
            (unconfirmed, liveHistory, at(Fixtures.liveReadAt), 104, 1),
        ]
        for (event, history, now, count, runs) in cases {
            let series = try XCTUnwrap(R.series(history, event: event, now: now))
            let chart = chartRuns(history, event, now: now)
            assertReadsTheChart(series, chart)
            XCTAssertEqual(series.points.count, count)
            XCTAssertEqual(series.segments.count, runs)
            XCTAssertEqual(R.points(history, event: event, now: now).map(\.date), series.points.map(\.date))
        }
    }

    // MARK: - The series is the history's readings

    func testTheLiveSeriesReadsTheBlendRowsTheHistoryDrawsAndNoCarriedOrPinnedRow() throws {
        let series = try liveSeries()
        XCTAssertEqual(series.eventId, 15327807)
        XCTAssertEqual(series.source, "aggregate")
        XCTAssertEqual(series.points.count, 89, "rows 510–598: the last reading before the scheduled start, then the match")
        XCTAssertEqual(series.points.first?.date, at("2026-10-12T10:54:00+00:00"))
        XCTAssertFalse(series.points.contains { $0.date == at("2026-10-12T12:24:00+00:00") },
                       "the carried-forward minute is not a recorded chance")
        XCTAssertFalse(series.points.contains { $0.date == at("2026-10-12T12:24:06.030278+00:00") },
                       "the pinned hero edge is not a recorded chance")
        XCTAssertEqual(series.scheduledStart, at("2026-10-12T10:55:00+00:00"))
        XCTAssertEqual(series.baseline, TennisChartReading9483.Reading(
            eventId: 15327807, source: "aggregate", date: at("2026-10-12T10:54:00+00:00"), home: 0.795, away: nil))
        XCTAssertEqual(series.latest, TennisChartReading9483.Reading(
            eventId: 15327807, source: "aggregate", date: at("2026-10-12T12:23:00+00:00"), home: 0.203605, away: nil),
            "the blend's away side is its complement, printed and never looked up")
        XCTAssertEqual(series.segments.count, 1)
    }

    func testTheFinalSeriesStopsAtTheMatchEndAndHoldsNoSettlement() throws {
        let series = try finalSeries()
        XCTAssertEqual(series.points.count, 20, "rows 714–725 and 878–885: from the last reading before the scheduled start")
        XCTAssertEqual(series.points.first?.date, at("2026-10-11T12:49:00+00:00"))
        XCTAssertFalse(series.points.contains { $0.probability == 1 || $0.probability == 0 })
        XCTAssertEqual(series.latest?.date, at("2026-10-11T15:40:00+00:00"))
        XCTAssertEqual(series.latest?.home, 0.891273)
        XCTAssertEqual(series.baseline?.date, at("2026-10-11T12:49:00+00:00"))
        XCTAssertEqual(series.baseline?.home, 0.46)
        XCTAssertEqual(series.segments.count, 2, "the subset leaves out rows 726–877; the line breaks there")
    }

    func testAnUnconfirmedStartHasNoBaseline() throws {
        // CONSTRUCTED: the detail's `start_is_tbd: true`.
        let event = try Fixtures.edited(Fixtures.liveDetail, ["start_is_tbd": true])
        let series = try XCTUnwrap(R.series(try Histories.live(), event: event, now: at(Fixtures.liveReadAt)))
        XCTAssertNil(series.scheduledStart)
        XCTAssertNil(series.baseline, "no reading is called before an unconfirmed start")
        XCTAssertNotNil(series.latest)
    }

    func testAForeignHistoryYieldsNoPointsNoSeriesAndSoNoReading() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let now = at(Fixtures.liveReadAt)
        // CONSTRUCTED: the live subset with only its `event_id` changed (`Histories.foreign`).
        let foreign = try Histories.foreign()
        XCTAssertTrue(R.points(foreign, event: event, now: now).isEmpty)
        XCTAssertNil(R.series(foreign, event: event, now: now), "no foreign baseline, held or latest reading")
        XCTAssertEqual(R.points(try Histories.live(), event: event, now: now).count, 89, "this event's own body is unchanged")
        XCTAssertTrue(R.runs(foreign, event: event, now: now).isEmpty)
        XCTAssertNil(R.drawn(foreign, event: event, now: now))
    }

    // MARK: - Holding

    func testWithNothingHeldThePageShowsNoReadingAndTheReaderShowsTheLatest() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let series = try liveSeries()
        let reading = R.reading(series, held: nil, event: event, now: at(Fixtures.liveReadAt))
        XCTAssertEqual(reading.shown, .reading(try XCTUnwrap(series.latest), held: false))
        XCTAssertFalse(reading.isHeld, "the hero already prints the current chance (#9517)")
        XCTAssertFalse(reading.offersLatest)
        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        XCTAssertEqual([reading.homeName, reading.awayName], [names.home, names.away])
        XCTAssertEqual(reading.baseline, series.baseline)
        XCTAssertEqual(reading.scheduledStart, series.scheduledStart)
    }

    func testATapHoldsTheNearestReadingInItsRunAndOffersTheLatest() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let series = try liveSeries()
        // CONSTRUCTED: a tap at 11:30:20Z.
        let held = R.inspect(at("2026-10-12T11:30:20Z").timeIntervalSince1970, in: series)
        guard case .reading(let wanted)? = held else { return XCTFail("a tap inside the line holds a reading") }
        XCTAssertEqual(wanted.date, at("2026-10-12T11:30:00+00:00"))
        let reading = R.reading(series, held: held, event: event, now: at(Fixtures.liveReadAt))
        XCTAssertEqual(reading.shown, .reading(wanted, held: true))
        XCTAssertTrue(reading.isHeld)
        XCTAssertTrue(reading.offersLatest)

        // "Show latest recorded chance" holds the newest observation; the offer goes.
        let latest = R.latest(in: series)
        XCTAssertEqual(latest, TennisChartReading9483.Held.reading(try XCTUnwrap(series.latest)))
        XCTAssertFalse(R.offersLatest(latest, in: series))
    }

    func testATapInsideABreakHoldsTheBreakAndBorrowsNoNeighbour() throws {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        let series = try finalSeries()
        // CONSTRUCTED: a tap at 14:00Z, inside the break the subset leaves.
        let date = at("2026-10-11T14:00:00Z")
        let held = R.inspect(date.timeIntervalSince1970, in: series)
        XCTAssertEqual(held, TennisChartReading9483.Held.gap(date))
        let reading = R.reading(series, held: held, event: event, now: at(Fixtures.finalReadAt))
        XCTAssertEqual(reading.shown, .gap(date))
        XCTAssertTrue(reading.isHeld)
        XCTAssertTrue(reading.offersLatest)
    }

    func testAHeldPointThatIsNotARecordedReadingIsUnavailableNeverANeighbour() throws {
        let series = try liveSeries()
        // CONSTRUCTED: the pinned edge held as a reading (today's production panel offers it).
        let pinned = TennisChartReading9483.Held.reading(TennisChartReading9483.Reading(
            eventId: 15327807, source: "aggregate", date: at("2026-10-12T12:24:06.030278+00:00"),
            home: 0.205895, away: nil))
        XCTAssertEqual(series.resolve(pinned), TennisChartReading9483.Shown.unavailable)
        XCTAssertTrue(R.offersLatest(pinned, in: series))
    }

    func testOpeningTheFullSizeHistoryHoldsWhatItShowsAndKeepsAHeldValue() throws {
        let series = try liveSeries()
        XCTAssertEqual(R.opening(nil, in: series), TennisChartReading9483.Held.reading(try XCTUnwrap(series.latest)))
        let gap = TennisChartReading9483.Held.gap(at("2026-10-12T11:00:00Z"))
        XCTAssertEqual(R.opening(gap, in: series), gap)
    }

    // MARK: - LABELLED constructed controls

    /// CONSTRUCTED control (not an observation of 15327291): the retained final
    /// with ONE served value changed — its 15:40 blend row (0.891273) set to
    /// `certainty` — so a genuine certainty observation precedes the one
    /// appended result row (15:40, 1.0, served last). The retained match reads
    /// 0.891273 there and never reaches this edge.
    private func finalWithCertainty(_ certainty: String) throws -> EventHistoryResponse {
        let genuine = #"{"timestamp":"2026-10-11T15:40:00+00:00","home_probability":0.891273}"#
        XCTAssertEqual(Histories.finalHistory.components(separatedBy: genuine).count, 2, "exactly one such served row")
        let body = Histories.finalHistory.replacingOccurrences(
            of: genuine, with: #"{"timestamp":"2026-10-11T15:40:00+00:00","home_probability":\#(certainty)}"#)
        return try Fixtures.decoder().decode(EventHistoryResponse.self, from: Data(body.utf8))
    }

    func testAGenuineCertaintyBeforeTheOneResultRowIsReadExactlyAsTheChartDrawsIt() throws {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        let now = at(Fixtures.finalReadAt)
        for (served, certainty) in [("1.0", 1.0), ("0.0", 0.0)] {
            let history = try finalWithCertainty(served)
            let series = try XCTUnwrap(R.series(history, event: event, now: now))
            assertReadsTheChart(series, chartRuns(history, event, now: now))
            XCTAssertEqual(series.points.count, 20, "only the appended result row is gone (\(served))")
            XCTAssertEqual(series.latest, TennisChartReading9483.Reading(
                eventId: 15327291, source: "aggregate", date: at("2026-10-11T15:40:00+00:00"), home: certainty, away: nil),
                "the genuine certainty is the latest reading, as the chart's last vertex")
            let held = R.latest(in: series)
            XCTAssertEqual(series.resolve(held), .reading(try XCTUnwrap(series.latest), held: true))
            XCTAssertEqual(series.baseline?.date, at("2026-10-11T12:49:00+00:00"), "the baseline is unchanged")

            // The production series' own result-row rule, applied a second time
            // over rows the settlement rule already cleaned, would drop it.
            let twice = try XCTUnwrap(TennisChartReading9483.series(
                eventId: history.eventId, points: series.points, source: series.source,
                scheduledStart: series.scheduledStart, gameStart: event.commenceTime?.asDate, finished: true,
                history: history))
            XCTAssertEqual(twice.points.count, 19)
            XCTAssertEqual(twice.latest?.home, 0.891273, "filtering twice loses the chart's last vertex")
        }
    }

    /// CONSTRUCTED control (not an observation of 15327807): the live subset with
    /// three served blend rows changed, each a barrier the chart keeps although
    /// it sits inside the 60 s in-play rhythm, far under the elapsed-time floor:
    /// 11:01 served at 1.5 (no readable value), 11:10 served at 11:09 (its time
    /// does not advance) and 11:21 served with a time that cannot be read.
    private func liveWithBarriers() throws -> EventHistoryResponse {
        var body = Histories.liveHistory
        let edits = [
            (#"{"timestamp":"2026-10-12T11:01:00+00:00","home_probability":0.776974}"#,
             #"{"timestamp":"2026-10-12T11:01:00+00:00","home_probability":1.5}"#),
            (#"{"timestamp":"2026-10-12T11:10:00+00:00","home_probability":0.789711}"#,
             #"{"timestamp":"2026-10-12T11:09:00+00:00","home_probability":0.789711}"#),
            (#"{"timestamp":"2026-10-12T11:21:00+00:00","home_probability":0.794579}"#,
             #"{"timestamp":"not a time","home_probability":0.794579}"#),
        ]
        for (row, barrier) in edits {
            XCTAssertEqual(body.components(separatedBy: row).count, 2, "exactly one such served row")
            body = body.replacingOccurrences(of: row, with: barrier)
        }
        return try Fixtures.decoder().decode(EventHistoryResponse.self, from: Data(body.utf8))
    }

    func testInvalidNonAdvancingAndUnreadableRowsBreakTheReaderExactlyWhereTheChartBreaks() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let now = at(Fixtures.liveReadAt)
        let history = try liveWithBarriers()
        let series = try XCTUnwrap(R.series(history, event: event, now: now))
        let chart = chartRuns(history, event, now: now)
        XCTAssertEqual(chart.count, 4, "the chart keeps all three barriers")
        assertReadsTheChart(series, chart)
        XCTAssertEqual(series.points.count, 86, "the 89 drawn rows less the three barriers")
        XCTAssertEqual(chart.compactMap { $0.last?[0] },
                       ["11:00", "11:09", "11:20", "12:23"].map { at("2026-10-12T\($0):00+00:00").timeIntervalSince1970 },
                       "each run ends just before its barrier")

        // None of these is an elapsed-time break: that rule alone joins the readings.
        XCTAssertEqual(OddsChartView.observationSegments(series.points, gameStart: event.commenceTime?.asDate).count, 1)

        // A tap at each barrier holds the break, on the page and in the full-size reader.
        for minute in ["11:01", "11:10", "11:21"] {
            let date = at("2026-10-12T\(minute):00+00:00")
            let held = R.inspect(date.timeIntervalSince1970, in: series)
            XCTAssertEqual(held, TennisChartReading9483.Held.gap(date), minute)
            let reading = R.reading(series, held: held, event: event, now: now)
            XCTAssertEqual(reading.shown, .gap(date), minute)
            XCTAssertTrue(reading.offersLatest, minute)
        }
        XCTAssertEqual(series.baseline?.date, at("2026-10-12T10:54:00+00:00"), "the baseline is unchanged")
        XCTAssertEqual(series.latest?.date, at("2026-10-12T12:23:00+00:00"), "the latest is unchanged")
    }
}
