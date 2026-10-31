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
/// (`start_is_tbd: true` in the DETAIL body; the history is never edited).
@MainActor
final class TennisReadingAdapter10868Tests: XCTestCase {
    private typealias R = TennisReadingAdapter10868
    private typealias Fixtures = TennisMatchPageAdapter10868Tests
    private typealias Histories = TennisHistoryAdapter10868Tests

    private func at(_ stamp: String) -> Date { stamp.asDate! }

    private func liveSeries() throws -> TennisChartReading9483.Series {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        return try XCTUnwrap(R.series(try Histories.live(), event: event, now: at(Fixtures.liveReadAt)))
    }

    private func finalSeries() throws -> TennisChartReading9483.Series {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        return try XCTUnwrap(R.series(try Histories.finished(), event: event, now: at(Fixtures.finalReadAt)))
    }

    // MARK: - The series is the history's readings

    func testTheLiveSeriesReadsTheBlendRowsTheHistoryDrawsAndNoCarriedOrPinnedRow() throws {
        let series = try liveSeries()
        XCTAssertEqual(series.eventId, 15327807)
        XCTAssertEqual(series.source, "aggregate")
        XCTAssertEqual(series.points.count, 104, "rows 0, 1, 19, 20, 21 and 500–598")
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
        XCTAssertEqual(series.points.count, 30, "rows 0, 705–725 and 878–885")
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
        XCTAssertEqual(R.points(try Histories.live(), event: event, now: now).count, 104, "this event's own body is unchanged")
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
}
