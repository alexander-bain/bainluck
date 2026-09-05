import XCTest
@testable import Bain_Luck

/// #2911 — the RACE primitive's contract, pinned.
///
/// Every rule here has a counterpart in `frontend/lib/contenderChart.ts`, which
/// is the contract of record; where the two disagree the web is right and this
/// file has caught a port bug, which is exactly what it is for. SwiftUI bodies
/// are not rendered in tests, so these pin `RaceChart`'s pure statics and the
/// decode that feeds them.
final class RaceChartTests: XCTestCase {

    // MARK: - Fixtures

    private func row(_ json: String) throws -> TournamentHubBoardRow {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(TournamentHubBoardRow.self, from: Data(json.utf8))
    }

    private func rows(_ json: String) throws -> [TournamentHubBoardRow] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode([TournamentHubBoardRow].self, from: Data(json.utf8))
    }

    private func results(_ json: String) throws -> [TournamentHubResult] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode([TournamentHubResult].self, from: Data(json.utf8))
    }

    /// A series whose points are given as `(day, probability)` on August 2026.
    private func series(_ key: String, _ points: [(Int, Double)], current: Double? = nil, index: Int = 0) -> RaceChartSeries {
        RaceChartSeries(
            entityKey: key,
            displayName: key.capitalized,
            colorIndex: index,
            probability: current,
            points: points.map { RaceChartPoint(date: String(format: "2026-08-%02d", $0.0), probability: $0.1) }
        )
    }

    private let noStarts = RaceChartWindowStarts.undated

    // MARK: - Decode

    func testTrendDecodesOffThePayloadShape() throws {
        let decoded = try row("""
        {"entity_key":"carlos-alcaraz","display_name":"Carlos Alcaraz","probability":0.445,
         "trend":[{"date":"2026-08-05","probability":0.103182},{"date":"2026-08-06","probability":0.110625}]}
        """)
        XCTAssertEqual(decoded.trend?.count, 2)
        XCTAssertEqual(decoded.trend?.first?.date, "2026-08-05")
        XCTAssertEqual(decoded.trend?.first?.probability ?? 0, 0.103182, accuracy: 1e-9)
    }

    /// A row with no `trend` is a row, not a decode failure — the board still
    /// has to print its name and its price.
    func testRowWithoutTrendStillDecodes() throws {
        let decoded = try row("""
        {"entity_key":"x","display_name":"X","probability":0.2}
        """)
        XCTAssertNil(decoded.trend)
        XCTAssertEqual(decoded.probability, 0.2)
    }

    /// The tolerant decode: a malformed `trend` costs the CHART, never the row.
    func testMalformedTrendDoesNotCostTheRow() throws {
        let decoded = try row("""
        {"entity_key":"x","display_name":"X","probability":0.2,"trend":"not-an-array"}
        """)
        XCTAssertNil(decoded.trend)
        XCTAssertEqual(decoded.displayName, "X")
        XCTAssertEqual(decoded.probability, 0.2)
    }

    // MARK: - Series building

    func testSeriesTakesTheTopThreePricedRowsInBoardOrder() throws {
        let board = try rows("""
        [{"entity_key":"a","display_name":"A","probability":0.4},
         {"entity_key":"b","display_name":"B","probability":0.3},
         {"entity_key":"c","display_name":"C","probability":0.2},
         {"entity_key":"d","display_name":"D","probability":0.1}]
        """)
        let built = RaceChart.series(from: board)
        XCTAssertEqual(built.map(\.entityKey), ["a", "b", "c"])
        XCTAssertEqual(built.map(\.colorIndex), [0, 1, 2])
    }

    /// A result is not a standing: a row with no probability has no live line
    /// and must not consume one of the three slots.
    func testUnpricedRowsAreSkippedNotDrawnEmpty() throws {
        let board = try rows("""
        [{"entity_key":"a","display_name":"A","probability":null},
         {"entity_key":"b","display_name":"B","probability":0.3},
         {"entity_key":"c","display_name":"C","probability":0.2},
         {"entity_key":"d","display_name":"D","probability":0.1}]
        """)
        XCTAssertEqual(RaceChart.series(from: board).map(\.entityKey), ["b", "c", "d"])
    }

    /// A point with no date, or a non-finite probability, is dropped — but its
    /// siblings are drawn. One bad reading must never cost a whole line.
    func testUndatedPointsAreDroppedAndSiblingsSurvive() throws {
        let board = try rows("""
        [{"entity_key":"a","display_name":"A","probability":0.4,
          "trend":[{"date":"2026-08-05","probability":0.1},
                   {"date":null,"probability":0.2},
                   {"date":"2026-08-07","probability":0.3}]}]
        """)
        let points = RaceChart.series(from: board).first?.points ?? []
        XCTAssertEqual(points.map(\.date), ["2026-08-05", "2026-08-07"])
    }

    // MARK: - The ceiling ladder (#2451)

    /// Zero stays; only the top moves, and only onto 10/25/50/100.
    func testCeilingClimbsTheLadderWithHeadroom() {
        // (the field's peak, the step 1.15 × it must land on)
        let ladder: [(Double, Double)] = [
            (0.05, 0.10),   // 5.75%  -> 10
            (0.086, 0.10),  // 9.89%  -> 10, the last value the 10 step holds
            (0.09, 0.25),   // 10.35% -> 25
            (0.20, 0.25),   // 23%    -> 25
            (0.22, 0.50),   // 25.3%  -> 50
            (0.345, 0.50),  // 39.7%  -> 50; Alex's men's board in #2451
            (0.44, 1.00),   // 50.6%  -> 100
            (0.90, 1.00),   // 103.5% -> 100 by the fallback, never above 1
        ]
        for (peak, expected) in ladder {
            let ceiling = RaceChart.ceiling(
                [series("a", [(1, peak * 0.5), (2, peak)])], range: .all, starts: noStarts
            )
            XCTAssertEqual(ceiling, expected, "peak \(peak) landed on \(ceiling), expected \(expected)")
        }
    }

    /// The exact case in #2451: a runaway favourite at 34.5% must not be drawn
    /// against a hard 0–100 axis, where the whole title race lives in the
    /// bottom third.
    func testCeilingForAlexsMensBoard() {
        let field = [
            series("alcaraz", [(1, 0.30), (2, 0.345)], current: 0.345, index: 0),
            series("zverev", [(1, 0.22), (2, 0.235)], current: 0.235, index: 1),
            series("shelton", [(1, 0.10), (2, 0.093)], current: 0.093, index: 2),
        ]
        XCTAssertEqual(RaceChart.ceiling(field, range: .all, starts: noStarts), 0.5)
    }

    /// The board's CURRENT number counts too. A contender whose history is one
    /// reading draws no line, but its legend value is on screen and the axis
    /// must be able to contain it.
    func testCeilingContainsTheCurrentNumberEvenWithNoLine() {
        let field = [series("a", [(1, 0.05)], current: 0.42)]
        XCTAssertEqual(RaceChart.ceiling(field, range: .all, starts: noStarts), 0.5)
    }

    func testCeilingIsAlwaysAnchoredAtZeroWithThreeLabels() {
        let labels = RaceChart.yLabels(ceiling: 0.5)
        XCTAssertEqual(labels.map(\.label), ["50%", "25%", "0%"])
        XCTAssertEqual(labels.last?.probability, 0)
        XCTAssertEqual(labels.count, 3)
    }

    /// The 25 step's midpoint is 12.5% and rounds — correct, and the only place
    /// the rounding is visible is a rule the reader uses to place a line.
    func testQuarterCeilingMidLabelRounds() {
        XCTAssertEqual(RaceChart.yLabels(ceiling: 0.25).map(\.label), ["25%", "13%", "0%"])
    }

    // MARK: - Windows and timeframes

    /// A duration is measured back from the SERIES' LAST READING, not from
    /// `now`. A field dark for three weeks must still draw its last week.
    func testTimeframeIsMeasuredFromTheLastReadingNotToday() {
        let entry = series("a", [(1, 0.1), (5, 0.2), (10, 0.3), (11, 0.4)])
        let week = RaceChart.points(entry.points, in: .week, starts: noStarts)
        XCTAssertEqual(week.map(\.date), ["2026-08-05", "2026-08-10", "2026-08-11"])
    }

    func testMonthWindowIsThirtyDaysInclusiveOfTheLastReading() {
        // Last reading 31 Aug; a 30-day window reaches back to 2 Aug, so the
        // 1 Aug point falls out and the 2 Aug one is the boundary that stays.
        let entry = series("a", [(1, 0.1), (2, 0.2), (31, 0.3)])
        XCTAssertEqual(RaceChart.points(entry.points, in: .month, starts: noStarts).map(\.date),
                       ["2026-08-02", "2026-08-31"])
    }

    func testWindowFiltersByDateNotByDuration() {
        let entry = series("a", [(1, 0.1), (5, 0.2), (9, 0.3)])
        let starts = RaceChartWindowStarts(draw: "2026-08-05", qual: "2026-08-01")
        XCTAssertEqual(RaceChart.points(entry.points, in: .draw, starts: starts).map(\.date),
                       ["2026-08-05", "2026-08-09"])
        XCTAssertEqual(RaceChart.points(entry.points, in: .qual, starts: starts).count, 3)
    }

    /// A single point is not a line. Joining it to an assumed origin would draw
    /// a movement that never happened.
    func testOnePointIsNotDrawable() {
        XCTAssertFalse(RaceChart.isDrawable([series("a", [(1, 0.1)])], range: .all, starts: noStarts))
        XCTAssertTrue(RaceChart.isDrawable([series("a", [(1, 0.1), (2, 0.2)])], range: .all, starts: noStarts))
    }

    /// A daily series can never fill a 1D window with two readings — the chip
    /// is therefore offered disabled, not drawn empty.
    func testOneDayIsNotDrawableOnADailySeries() {
        let entry = [series("a", [(1, 0.1), (2, 0.2), (3, 0.3)])]
        XCTAssertFalse(RaceChart.isDrawable(entry, range: .day, starts: noStarts))
    }

    // MARK: - Ranges offered and chosen

    /// An option that cannot be honoured is worse than an absent one: a window
    /// with no start is not offered at all.
    func testUndatedWindowsAreNotOffered() {
        XCTAssertEqual(RaceChart.availableRanges(starts: .undated), [.day, .week, .month, .all])
        XCTAssertEqual(
            RaceChart.availableRanges(starts: RaceChartWindowStarts(draw: "2026-08-30", qual: nil)),
            [.draw, .day, .week, .month, .all]
        )
    }

    func testDefaultIsTheDrawWhenItCanBeDrawn() {
        let entry = [series("a", [(29, 0.1), (30, 0.2), (31, 0.3)])]
        let starts = RaceChartWindowStarts(draw: "2026-08-30", qual: nil)
        XCTAssertEqual(RaceChart.defaultRange(series: entry, starts: starts), .draw)
    }

    /// On the morning of day one the tournament window has one reading in it,
    /// so it has not earned the default — a chart that opens blank on a market
    /// with a month of history is the worse failure.
    func testDefaultFallsBackToAllWhenTheDrawHasOneReading() {
        let entry = [series("a", [(1, 0.1), (15, 0.2), (30, 0.3)])]
        let starts = RaceChartWindowStarts(draw: "2026-08-30", qual: nil)
        XCTAssertEqual(RaceChart.defaultRange(series: entry, starts: starts), .all)
    }

    // MARK: - Window starts come off the payload, never from a constant

    func testDrawStartIsTheLocalDayOfThePublishedTimestamp() {
        // `2026-08-30T11:00:00-04:00` is 30 August on the ticket. A UTC
        // conversion of an evening session would give the day after.
        let starts = RaceChart.windowStarts(mainDrawStartsAt: "2026-08-30T11:00:00-04:00", results: [])
        XCTAssertEqual(starts.draw, "2026-08-30")
        XCTAssertNil(starts.qual)
    }

    func testQualifyingStartIsTheEarliestObservedQualifyingResult() throws {
        let finished = try results("""
        [{"matchup_key":"m1","round":"Round 1","completed_at":"2026-08-31T18:00:00+00:00"},
         {"matchup_key":"m2","source_round":"Qualifying 2nd Round","completed_at":"2026-08-27T18:00:00+00:00"},
         {"matchup_key":"m3","round":"Qualifying 1st Round","completed_at":"2026-08-25T18:00:00+00:00"}]
        """)
        let starts = RaceChart.windowStarts(mainDrawStartsAt: "2026-08-30T11:00:00-04:00", results: finished)
        XCTAssertEqual(starts.qual, "2026-08-25")
    }

    /// Two chips that draw the same window are one chip and a puzzle.
    func testQualifyingIsDroppedWhenItIsNotEarlierThanTheDraw() throws {
        let finished = try results("""
        [{"matchup_key":"m1","round":"Qualifying 1st Round","completed_at":"2026-08-31T18:00:00+00:00"}]
        """)
        let starts = RaceChart.windowStarts(mainDrawStartsAt: "2026-08-30T11:00:00-04:00", results: finished)
        XCTAssertNil(starts.qual)
    }

    func testTournamentWithNoQualifyingOffersNoQualsChip() {
        let starts = RaceChart.windowStarts(mainDrawStartsAt: "2026-08-30T11:00:00-04:00", results: [])
        XCTAssertFalse(RaceChart.availableRanges(starts: starts).contains(.qual))
    }

    // MARK: - Day arithmetic (timezone- and clock-free)

    func testDayNumberIsCivilArithmeticNotCalendar() {
        XCTAssertEqual(RaceChart.dayNumber("1970-01-01"), 0)
        XCTAssertEqual(RaceChart.dayNumber("1970-01-02"), 1)
        XCTAssertEqual(RaceChart.dayNumber("2026-09-04"), 20_700)
        // Across a leap day, and across a year boundary.
        let feb28 = RaceChart.dayNumber("2024-02-28")!
        XCTAssertEqual(RaceChart.dayNumber("2024-03-01")! - feb28, 2)
        XCTAssertEqual(RaceChart.dayNumber("2026-01-01")! - RaceChart.dayNumber("2025-12-31")!, 1)
    }

    func testIsoDayRejectsThingsThatAreNotDays() {
        XCTAssertNil(RaceChart.isoDay(nil))
        XCTAssertNil(RaceChart.isoDay(""))
        XCTAssertNil(RaceChart.isoDay("2026-8-4"))
        XCTAssertNil(RaceChart.isoDay("not-a-date"))
        XCTAssertEqual(RaceChart.isoDay("2026-09-04T11:50:05.220001+00:00"), "2026-09-04")
    }

    // MARK: - The domain and the footer read the same thing

    func testDomainIsTheSortedUnionSoLinesLineUpInTime() {
        let field = [
            series("a", [(1, 0.1), (3, 0.2)]),
            series("b", [(2, 0.3), (3, 0.4)], index: 1),
        ]
        XCTAssertEqual(RaceChart.domain(field, range: .all, starts: noStarts),
                       ["2026-08-01", "2026-08-02", "2026-08-03"])
        XCTAssertEqual(RaceChart.spanDays(field, range: .all, starts: noStarts), 2)
    }

    func testSpanIsNilWhenThereIsNothingToSpan() {
        XCTAssertNil(RaceChart.spanDays([series("a", [(1, 0.1)])], range: .all, starts: noStarts))
    }

    // MARK: - Labels

    func testShortDateLabelIsDayFirst() {
        XCTAssertEqual(RaceChart.shortDateLabel("2026-08-26"), "26 Aug")
        XCTAssertEqual(RaceChart.shortDateLabel("2026-09-04"), "4 Sep")
        XCTAssertEqual(RaceChart.shortDateLabel("garbage"), "garbage")
    }

    func testLegendNameInitialisesTheGivenName() {
        XCTAssertEqual(RaceChart.legendName("Aryna Sabalenka"), "A. Sabalenka")
        XCTAssertEqual(RaceChart.legendName("Carlos Alcaraz"), "C. Alcaraz")
        XCTAssertEqual(RaceChart.legendName("Jan-Lennard Struff"), "J. Struff")
        // A one-word name has no given name to shorten.
        XCTAssertEqual(RaceChart.legendName("Nadal"), "Nadal")
    }

    // MARK: - The presentation builds a chart for every board

    func testPresentationBuildsAChartAndSaysWhyWhenItCannot() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let payload = """
        {"title":"US Open","main_draw_starts_at":"2026-08-30T11:00:00-04:00",
         "boards":[
           {"draw":"mens-singles","label":"Men's Singles","rows":[
             {"entity_key":"a","display_name":"Carlos Alcaraz","state":"live","rank":1,"probability":0.44,
              "trend":[{"date":"2026-08-30","probability":0.30},{"date":"2026-09-01","probability":0.44}]},
             {"entity_key":"b","display_name":"Alexander Zverev","state":"live","rank":2,"probability":0.12,
              "trend":[{"date":"2026-08-30","probability":0.10},{"date":"2026-09-01","probability":0.12}]}]},
           {"draw":"womens-singles","label":"Women's Singles","rows":[
             {"entity_key":"c","display_name":"Aryna Sabalenka","state":"live","rank":1,"probability":0.5,
              "trend":[{"date":"2026-09-01","probability":0.5}]}]}],
         "bracket":{}}
        """
        let response = try decoder.decode(TournamentHubResponse.self, from: Data(payload.utf8))
        let presentation = TournamentHubPresentation(response: response)

        XCTAssertEqual(presentation.boards.count, 2)

        let mens = presentation.boards[0]
        XCTAssertNil(mens.chart.emptyNote)
        XCTAssertEqual(mens.chart.series.map(\.displayName), ["Carlos Alcaraz", "Alexander Zverev"])
        XCTAssertEqual(mens.chart.initialRange, .draw, "two readings inside the draw earn the default")
        XCTAssertEqual(mens.chart.starts.draw, "2026-08-30")

        // One reading is a state, and it gets its OWN sentence — not the one
        // that means "nobody is priced".
        let womens = presentation.boards[1]
        XCTAssertEqual(womens.chart.emptyNote, "Only one reading so far — there is no line to draw yet.")
    }

    func testBoardWithNoPricedContenderSaysSo() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let payload = """
        {"title":"US Open","boards":[{"draw":"d","label":"D","rows":[
          {"entity_key":"a","display_name":"A","state":"live","probability":null}]}],"bracket":{}}
        """
        let response = try decoder.decode(TournamentHubResponse.self, from: Data(payload.utf8))
        let board = try XCTUnwrap(TournamentHubPresentation(response: response).boards.first)
        XCTAssertEqual(board.chart.emptyNote, "No contender on this board has a price to chart.")
        XCTAssertTrue(board.chart.series.isEmpty)
    }

    // MARK: - The view's day↔instant round trip

    /// The plotted x-value must name the day the payload named, in every
    /// device timezone — which is why the instant is pinned to UTC noon.
    func testDayRoundTripsThroughTheInstantTheChartPlots() {
        for iso in ["2026-01-01", "2026-08-05", "2026-12-31", "2024-02-29"] {
            XCTAssertEqual(RaceChartView.isoDay(RaceChartView.date(iso)), iso)
        }
    }
}
