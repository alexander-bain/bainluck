import XCTest
import SwiftUI
import UIKit
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
        XCTAssertEqual(openingReadout?.badgeText, "Pregame")
        XCTAssertEqual(openingReadout?.probabilityText, "61%")
        XCTAssertEqual(openingReadout?.timestampTextPT, "Nov 6, 12:05:09 PM PT")
        XCTAssertEqual(openingReadout?.isOpening, true)

        let sinceStartReadout = EventAtlasChartMarks11666.selectedReading(
            rows: rowsAll,
            selectedDate: t0,
            outcomeName: "Celtics",
            includesOpening: false
        )
        XCTAssertEqual(sinceStartReadout?.badgeText, "Recorded", "Since Start range never badges a point as Pregame")
        XCTAssertEqual(sinceStartReadout?.isOpening, false)
    }

    func testObservationRowsChecksGameStartForOpeningAndBoundsSelectionSnapDistance() {
        let kickoff = makeDate("2026-11-06T20:00:00Z")
        let afterKickoff = makeDate("2026-11-06T20:15:00Z")
        let later = makeDate("2026-11-06T21:00:00Z")
        let farOutside = makeDate("2026-11-07T02:00:00Z")

        let points = [
            ChartDataPoint(date: afterKickoff, probability: 0.55, source: "aggregate"),
            ChartDataPoint(date: later, probability: 0.68, source: "aggregate"),
        ]

        // First observation is after kickoff -> not marked as a pregame opening dot.
        let rowsWithGameStart = EventAtlasChartMarks11666.observationRows(
            dataPoints: points,
            includesOpening: true,
            selectedDate: nil,
            gameStart: kickoff
        )
        XCTAssertEqual(rowsWithGameStart.count, 2)
        XCTAssertFalse(rowsWithGameStart[0].isOpening)
        XCTAssertTrue(rowsWithGameStart[0].isVisibleSolid)

        // Selection far outside the series span does not snap across a multi-hour gap.
        let farSelectionRows = EventAtlasChartMarks11666.observationRows(
            dataPoints: points,
            includesOpening: true,
            selectedDate: farOutside,
            gameStart: kickoff
        )
        XCTAssertFalse(farSelectionRows.contains(where: \.isSelected))
        XCTAssertNil(
            EventAtlasChartMarks11666.selectedReading(
                rows: rowsWithGameStart,
                selectedDate: farOutside,
                outcomeName: "Celtics",
                includesOpening: true
            )
        )
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
                sides: .homeAndAway,
                homeScoreOverride: 110,
                awayScoreOverride: 102
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
                sides: .homeAndAway,
                homeScoreOverride: 110,
                awayScoreOverride: 102
            )
        )
    }

    func testSettledResultReliesStrictlyOnEventOutcomeResolveAndWithholdsOnFinalUnresolvedOrMissingScoreboard() throws {
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

        // Without confirmed page scoreboard or servedSettledResult, settledResult returns nil (never falls back to history scores).
        XCTAssertNil(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: points,
                history: staleHistory,
                status: "completed",
                sides: .homeAndAway
            )
        )

        // On final_unresolved, settledResult returns nil even when scores are present (matching the hero's "Final").
        XCTAssertNil(
            EventAtlasChartMarks11666.settledResult(
                dataPoints: points,
                history: staleHistory,
                status: "final_unresolved",
                sides: .homeAndAway,
                homeScoreOverride: 24,
                awayScoreOverride: 28
            )
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
        XCTAssertTrue(source.contains("servedSettledResult: servedSettledResult,\n                            gameStart: kickoffDate"))
        XCTAssertTrue(source.contains("servedSettledResult: servedSettledResult,\n                        gameStart: kickoffDate,\n                        settledResult: atlasSettledResult"))
        XCTAssertTrue(source.contains("if let finishedEnd, atlasSettledResult == nil"))
    }

    @MainActor
    func testRendersE2ChartPolishStatesAt390Width() throws {
        let kickoff = makeDate("2026-11-06T20:00:00Z")
        let t0 = makeDate("2026-11-06T19:00:00Z")
        let t1 = makeDate("2026-11-06T20:35:00Z")
        let t2 = makeDate("2026-11-06T21:15:00Z")
        let t3 = makeDate("2026-11-06T22:00:00Z")
        let points = [
            ChartDataPoint(date: t0, probability: 0.56, source: "aggregate"),
            ChartDataPoint(date: t1, probability: 0.64, source: "aggregate"),
            ChartDataPoint(date: t2, probability: 0.78, source: "aggregate"),
            ChartDataPoint(date: t3, probability: 0.99, source: "aggregate"),
        ]

        let restSelection = OddsChartSelection()
        let atRestView = VStack(alignment: .leading, spacing: 12) {
            Text("Live chart header at rest (All tab)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            EventAtlasChartHeaderView11666(
                selection: restSelection,
                dataPoints: points,
                checkpoints: nil,
                history: nil,
                status: "live",
                sides: .homeAndAway,
                includesOpening: true,
                homeName: "Celtics",
                primaryColor: .blue,
                gameStart: kickoff
            )
            Divider()
            Text("Settled chart header at rest")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            EventAtlasChartHeaderView11666(
                selection: restSelection,
                dataPoints: points,
                checkpoints: nil,
                history: nil,
                status: "completed",
                sides: .homeAndAway,
                includesOpening: true,
                homeName: "Celtics",
                primaryColor: .blue,
                homeScore: 112,
                awayScore: 104,
                servedSettledResult: "home",
                gameStart: kickoff
            )
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let scrubOpeningSelection = OddsChartSelection()
        scrubOpeningSelection.hold(date: t0)
        let scrubMidSelection = OddsChartSelection()
        scrubMidSelection.hold(date: t2)

        let scrubView = VStack(alignment: .leading, spacing: 12) {
            Text("Scrubbing pregame opening mark (t <= kickoffDate)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            EventAtlasChartHeaderView11666(
                selection: scrubOpeningSelection,
                dataPoints: points,
                checkpoints: nil,
                history: nil,
                status: "live",
                sides: .homeAndAway,
                includesOpening: true,
                homeName: "Celtics",
                primaryColor: .blue,
                gameStart: kickoff
            )
            Divider()
            Text("Scrubbing with a long outcome name (ViewThatFits two-line wrap)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            EventAtlasChartHeaderView11666(
                selection: scrubMidSelection,
                dataPoints: points,
                checkpoints: nil,
                history: nil,
                status: "live",
                sides: .homeAndAway,
                includesOpening: true,
                homeName: "Minnesota Timberwolves",
                primaryColor: .blue,
                gameStart: kickoff
            )
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let settledTerminalView = VStack(alignment: .leading, spacing: 10) {
            EventAtlasChartHeaderView11666(
                selection: restSelection,
                dataPoints: points,
                checkpoints: nil,
                history: nil,
                status: "completed",
                sides: .homeAndAway,
                includesOpening: true,
                homeName: "Celtics",
                primaryColor: .blue,
                homeScore: 112,
                awayScore: 104,
                servedSettledResult: "home",
                gameStart: kickoff
            )
            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.secondary.opacity(0.05))
                    .frame(width: 358, height: 140)
                Path { path in
                    path.move(to: CGPoint(x: 24, y: 82))
                    path.addLine(to: CGPoint(x: 120, y: 66))
                    path.addLine(to: CGPoint(x: 220, y: 42))
                    path.addLine(to: CGPoint(x: 296, y: 18))
                }
                .stroke(Color.blue, lineWidth: 2)
                Circle()
                    .fill(Color(.systemBackground))
                    .overlay(Circle().stroke(Color.blue, lineWidth: 2))
                    .frame(width: 8, height: 8)
                    .position(x: 24, y: 82)
                Circle().fill(Color.blue).frame(width: 6, height: 6).position(x: 120, y: 66)
                Circle().fill(Color.blue).frame(width: 6, height: 6).position(x: 220, y: 42)
                Circle().fill(Color.blue).frame(width: 6, height: 6).position(x: 296, y: 18)
                let placement = EventAtlasChartMarks11666.resultWordPlacement(
                    result: .won,
                    dotX: 296,
                    dotY: 18,
                    plotWidth: 358
                )
                Text(placement.word)
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Color.green)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1.5)
                    .background(Color(.systemBackground).opacity(0.88), in: RoundedRectangle(cornerRadius: 3))
                    .position(x: placement.labelX, y: placement.labelY)
            }
            .frame(width: 358, height: 140)
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let r1 = rendererForMeasurement(atRestView)
        r1.scale = 2.0
        let img1 = try XCTUnwrap(r1.uiImage)
        XCTAssertEqual(Int(img1.size.width), 390)

        let r2 = rendererForMeasurement(scrubView)
        r2.scale = 2.0
        let img2 = try XCTUnwrap(r2.uiImage)
        XCTAssertEqual(Int(img2.size.width), 390)

        let r3 = rendererForMeasurement(settledTerminalView)
        r3.scale = 2.0
        let img3 = try XCTUnwrap(r3.uiImage)
        XCTAssertEqual(Int(img3.size.width), 390)

        if let outDir = ProcessInfo.processInfo.environment["ATLAS_E2_CHART_SCREENSHOT_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try XCTUnwrap(img1.pngData()).write(to: dirURL.appendingPathComponent("e2-chart-header-at-rest-390px.png"))
            try XCTUnwrap(img2.pngData()).write(to: dirURL.appendingPathComponent("e2-chart-header-scrub-wrapping-390px.png"))
            try XCTUnwrap(img3.pngData()).write(to: dirURL.appendingPathComponent("e2-chart-settled-won-no-100pct-390px.png"))
        }
    }
}
