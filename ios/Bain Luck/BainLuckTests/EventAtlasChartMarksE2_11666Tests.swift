import XCTest
@testable import Bain_Luck

final class EventAtlasChartMarksE2_11666Tests: XCTestCase {

    private func makeDate(_ iso: String) -> Date {
        let formatter = ISO8601DateFormatter()
        return formatter.date(from: iso)!
    }

    func testMarkKeyShowsPregameOnlyWhenIncludesOpeningAndResultWordsOnlyWhenSettled() {
        let liveAllKey = EventAtlasChartMarkKeyModel11666(settledResult: nil, includesOpening: true)
        XCTAssertTrue(liveAllKey.showsOpening)
        XCTAssertEqual(liveAllKey.openingLabel, "Pregame")
        XCTAssertEqual(liveAllKey.recordedLabel, "Recorded reading")
        XCTAssertEqual(liveAllKey.changeLabel, "Change")
        XCTAssertFalse(liveAllKey.showsSettledResultWords)
        XCTAssertEqual(liveAllKey.tapHint, "Tap any reading for exact time (PT)")

        let liveSinceStartKey = EventAtlasChartMarkKeyModel11666(settledResult: nil, includesOpening: false)
        XCTAssertFalse(liveSinceStartKey.showsOpening)
        XCTAssertFalse(liveSinceStartKey.showsSettledResultWords)

        let settledKey = EventAtlasChartMarkKeyModel11666(settledResult: .won, includesOpening: true)
        XCTAssertTrue(settledKey.showsOpening)
        XCTAssertTrue(settledKey.showsSettledResultWords)
        XCTAssertEqual(settledKey.settledWonWord, "✓ Won")
        XCTAssertEqual(settledKey.settledLostWord, "✗ Lost")
        XCTAssertEqual(settledKey.settledExplanation, "Result as a word")
    }

    func testObservationRowsMarksFirstAsOpeningInAllRangeAndExcludesLiveEdge() {
        let t0 = makeDate("2026-11-06T20:00:00Z")
        let t1 = makeDate("2026-11-06T20:15:00Z")
        let t2 = makeDate("2026-11-06T20:30:00Z")
        let t3 = makeDate("2026-11-06T20:45:00Z")

        var edgePoint = ChartDataPoint(date: t3, probability: 0.72, source: "aggregate")
        edgePoint.isLiveEdge = true

        let points = [
            ChartDataPoint(date: t0, probability: 0.55, source: "aggregate"),
            ChartDataPoint(date: t1, probability: 0.55, source: "aggregate"), // unchanged intermediate reading dropped
            ChartDataPoint(date: t2, probability: 0.72, source: "aggregate"),
            edgePoint,
        ]

        let allRows = EventAtlasChartMarks11666.observationRows(
            dataPoints: points,
            includesOpening: true,
            selectedDate: t0
        )
        XCTAssertEqual(allRows.count, 2)
        XCTAssertTrue(allRows[0].isOpening)
        XCTAssertFalse(allRows[0].isVisibleSolid, "Opening mark is hollow, never solid")
        XCTAssertTrue(allRows[0].isSelected)
        XCTAssertFalse(allRows[1].isOpening)
        XCTAssertTrue(allRows[1].isVisibleSolid)

        let sinceStartRows = EventAtlasChartMarks11666.observationRows(
            dataPoints: points,
            includesOpening: false,
            selectedDate: t0
        )
        XCTAssertEqual(sinceStartRows.count, 2)
        XCTAssertFalse(sinceStartRows[0].isOpening, "Since Start range has no pregame opening mark")
        XCTAssertTrue(sinceStartRows[0].isVisibleSolid)
    }

    func testSolidMarkStrideThinsDenseSeriesWhileKeepingLastAndSelectedVisible() {
        XCTAssertEqual(EventAtlasChartMarks11666.solidMarkStride(pointCount: 10), 1)
        XCTAssertEqual(EventAtlasChartMarks11666.solidMarkStride(pointCount: 36), 1)
        XCTAssertEqual(EventAtlasChartMarks11666.solidMarkStride(pointCount: 56), 2)

        let base = makeDate("2026-11-06T18:00:00Z")
        let points: [ChartDataPoint] = (0..<50).map { i in
            ChartDataPoint(
                date: base.addingTimeInterval(Double(i * 60)),
                probability: 0.30 + Double(i) * 0.01,
                source: "aggregate"
            )
        }
        // Index 3 is odd (not divisible by stride=2), so it is only visible when selected.
        let unselectedRows = EventAtlasChartMarks11666.observationRows(
            dataPoints: points,
            includesOpening: true,
            selectedDate: nil
        )
        XCTAssertEqual(unselectedRows.count, 50)
        XCTAssertTrue(unselectedRows[0].isOpening)
        XCTAssertFalse(unselectedRows[3].isVisibleSolid)
        XCTAssertTrue(unselectedRows[49].isVisibleSolid, "Last observation is always visible")

        let selectedRows = EventAtlasChartMarks11666.observationRows(
            dataPoints: points,
            includesOpening: true,
            selectedDate: points[3].date
        )
        XCTAssertTrue(selectedRows[3].isSelected)
        XCTAssertTrue(selectedRows[3].isVisibleSolid, "Selected observation is always visible even when off-stride")
    }

    func testSelectedReadingFormatsWholePercentAndExactTimeInPT() {
        let t0 = makeDate("2026-11-06T20:05:09Z") // 12:05:09 PM PST
        let t1 = makeDate("2026-11-06T21:30:45Z") // 1:30:45 PM PST
        let points = [
            ChartDataPoint(date: t0, probability: 0.614, source: "aggregate"),
            ChartDataPoint(date: t1, probability: 0.786, source: "aggregate"),
        ]
        let rowsAll = EventAtlasChartMarks11666.observationRows(
            dataPoints: points,
            includesOpening: true,
            selectedDate: t0
        )
        let openingReadout = EventAtlasChartMarks11666.selectedReading(
            rows: rowsAll,
            selectedDate: t0,
            outcomeName: "Celtics",
            includesOpening: true
        )
        XCTAssertEqual(openingReadout?.outcomeName, "Celtics")
        XCTAssertEqual(openingReadout?.badgeText, "Opening")
        XCTAssertEqual(openingReadout?.probabilityText, "61%")
        XCTAssertEqual(openingReadout?.timestampTextPT, "Nov 6, 12:05:09 PM PT")
        XCTAssertEqual(openingReadout?.isOpening, true)

        let sinceStartReadout = EventAtlasChartMarks11666.selectedReading(
            rows: rowsAll,
            selectedDate: t0,
            outcomeName: "Celtics",
            includesOpening: false
        )
        XCTAssertEqual(sinceStartReadout?.badgeText, "Recorded", "Since Start range never badges a point as Opening")
        XCTAssertEqual(sinceStartReadout?.isOpening, false)
    }

    func testSettledResultComputesWonOrLostForEndingSideWithoutInventing100PercentSpike() {
        let t0 = makeDate("2026-11-06T20:00:00Z")
        let t1 = makeDate("2026-11-06T22:00:00Z")

        var endHomeFavored = ChartDataPoint(date: t1, probability: 0.88, source: "aggregate")
        endHomeFavored.homeScore = 110
        endHomeFavored.awayScore = 102
        let homeWonPoints = [
            ChartDataPoint(date: t0, probability: 0.55, source: "aggregate"),
            endHomeFavored,
        ]

        // Home side ended at 88% (>= 50%) and won 110-102 -> .won ("✓ Won")
        XCTAssertEqual(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: homeWonPoints,
                status: "completed",
                sides: .homeAndAway
            ),
            .won
        )

        // Home side ended at 88% (>= 50%) but lost 98-102 -> .lost ("✗ Lost")
        XCTAssertEqual(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: homeWonPoints,
                status: "completed",
                sides: .homeAndAway,
                homeScoreOverride: 98,
                awayScoreOverride: 102
            ),
            .lost
        )

        // Two-outcome axis ending below 50% (away side favored at 82%, homeProb = 0.18) and away won 95-104 -> .won ("✓ Won")
        let awayEndPoints = [
            ChartDataPoint(date: t0, probability: 0.45, source: "aggregate"),
            ChartDataPoint(date: t1, probability: 0.18, source: "aggregate"),
        ]
        XCTAssertEqual(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: awayEndPoints,
                status: "completed",
                sides: .homeAndAway,
                homeScoreOverride: 95,
                awayScoreOverride: 104
            ),
            .won
        )

        // Unfinished game -> nil
        XCTAssertNil(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: homeWonPoints,
                status: "live",
                sides: .homeAndAway
            )
        )
    }

    func testSettledResultPrefersPageScoreboardAndServedResultOverStaleHistoryAndTennisGames() throws {
        let t0 = makeDate("2026-11-06T20:00:00Z")
        let t1 = makeDate("2026-11-06T22:00:00Z")

        // Mid-game history snapshot has home leading 24-21, while final scoreboard is 24-28 (away won).
        var midGamePoint = ChartDataPoint(date: t1, probability: 0.76, source: "aggregate")
        midGamePoint.homeScore = 24
        midGamePoint.awayScore = 21
        let points = [
            ChartDataPoint(date: t0, probability: 0.52, source: "aggregate"),
            midGamePoint,
        ]
        let staleHistoryJSON = """
        {
          "event_id": 1,
          "home_team": "Bears",
          "away_team": "Eagles",
          "commence_time": "2026-11-06T20:00:00Z",
          "status": "completed",
          "history": [],
          "espn_history": [
            {"timestamp": "2026-11-06T21:45:00Z", "home_win_prob": 0.76, "home_score": 24, "away_score": 21}
          ]
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let staleHistory = try decoder.decode(EventHistoryResponse.self, from: staleHistoryJSON)

        // Without scoreboard override, fallback reads history (home 24 > away 21 -> .won).
        XCTAssertEqual(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: points,
                history: staleHistory,
                status: "completed",
                sides: .homeAndAway
            ),
            .won
        )

        // With the page's authoritative scoreboard (24-28), the scoreboard wins (.lost for home-favored ending point).
        XCTAssertEqual(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: points,
                history: staleHistory,
                status: "completed",
                sides: .homeAndAway,
                homeScoreOverride: 24,
                awayScoreOverride: 28
            ),
            .lost
        )

        // Tennis sets case: history holds last-set games (4-6), while the page scoreboard holds sets (2-1) and servedSettledResult = "home".
        let tennisHistoryJSON = """
        {
          "event_id": 2,
          "home_team": "Sabalenka",
          "away_team": "Gauff",
          "commence_time": "2026-11-06T20:00:00Z",
          "status": "completed",
          "history": [],
          "espn_history": [
            {"timestamp": "2026-11-06T21:55:00Z", "home_win_prob": 0.68, "home_score": 4, "away_score": 6}
          ]
        }
        """.data(using: .utf8)!
        let tennisHistory = try decoder.decode(EventHistoryResponse.self, from: tennisHistoryJSON)

        XCTAssertEqual(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: points,
                history: tennisHistory,
                status: "completed",
                sides: .homeAndAway,
                homeScoreOverride: 2,
                awayScoreOverride: 1,
                servedSettledResult: "home"
            ),
            .won
        )

        // Draw on settled game -> nil (neither ✓ Won nor ✗ Lost).
        XCTAssertNil(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: points,
                history: staleHistory,
                status: "completed",
                sides: .homeOnly,
                homeScoreOverride: 1,
                awayScoreOverride: 1,
                servedSettledResult: "draw"
            )
        )
    }

    func testResultWordPlacementFlipsLeftNearPlotRightEdge() {
        let midPlot = EventAtlasChartMarks11666.resultWordPlacement(
            result: .won,
            dotX: 180,
            dotY: 40,
            plotWidth: 320
        )
        XCTAssertEqual(midPlot.word, "✓ Won")
        XCTAssertFalse(midPlot.placesLeftOfDot)
        XCTAssertGreaterThan(midPlot.labelX, midPlot.dotX)

        let rightEdge = EventAtlasChartMarks11666.resultWordPlacement(
            result: .lost,
            dotX: 300,
            dotY: 40,
            plotWidth: 320
        )
        XCTAssertEqual(rightEdge.word, "✗ Lost")
        XCTAssertTrue(rightEdge.placesLeftOfDot)
        XCTAssertLessThan(rightEdge.labelX, rightEdge.dotX)
    }

    func testOddsChartViewGatesE2HeaderAndOverlayBehindEventPageAtlasEnabled() throws {
        let chartURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/OddsChartView.swift")
        let source = try String(contentsOf: chartURL, encoding: .utf8)
        XCTAssertTrue(source.contains("if ReleaseSurfaces.isEventPageAtlasEnabled() {\n                        EventAtlasChartHeaderView11666("))
        XCTAssertTrue(source.contains("if ReleaseSurfaces.isEventPageAtlasEnabled() {\n                    EventAtlasChartOverlay11666("))
        XCTAssertTrue(source.contains("homeScore: homeScore,\n                            awayScore: awayScore"))
        XCTAssertTrue(source.contains("homeScore: homeScore,\n                        awayScore: awayScore"))
    }
}
