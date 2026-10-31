import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the soccer history adapter, part two, on the RETAINED REAL bodies
/// (`SoccerRetained10868`). Only the home win chance is drawn; Draw and the
/// away win are key entries with no runs and their own words.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The retained `/history` bodies are REDUCED VERBATIM SUBSETS (rows kept are
/// listed in `SoccerRetainedAdapter10868Tests`), so every run counted here is a
/// run OF THE SUBSET: an in-game interval across left-out rows is wider than
/// served, and a break the subset shows may be narrower in the full body.
@MainActor
final class SoccerHistoryAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias S = SoccerHistoryAdapter10868
    private typealias A = SoccerMatchPageAdapter10868

    private func built(_ detail: String, _ history: String, phase: SoccerEventPagePhase10868,
                       now: Date) throws -> (FieldHistoryInput10868, EventDetail) {
        let event = try F.detail(detail)
        return (S.history(try F.history(history), event: event, phase: phase, host: F.historyHost(now)), event)
    }

    private func pointIDs(_ series: FieldHistorySeries10868) -> [[String]] {
        series.runs.map { $0.points.map(\.id) }
    }

    // MARK: - Three named entries, one line

    func testDuringPlayOnlyTheHomeWinIsDrawnAndDrawAndAwayKeepTheirWords() throws {
        let (input, event) = try built(F.liveDetail, F.liveHistory, phase: .live, now: F.liveNow)
        let names = A.names(event)

        XCTAssertEqual(input.series.map(\.id),
                       ["blend:15325054:home", "blend:15325054:draw", "blend:15325054:away"])
        XCTAssertEqual(input.series.map(\.name), [A.Words.outcome(names.home), "Draw", A.Words.outcome(names.away)])
        XCTAssertEqual(input.series.map(\.shape), [.circle, .diamond, .square])

        // The served blend's draw-priced rows carry home only; the away side is
        // never the complement, and Draw has no served history at all.
        XCTAssertTrue(input.series[1].runs.isEmpty)
        XCTAssertEqual(input.series[1].absentWords, S.Words.drawHistoryUnavailable)
        XCTAssertEqual(input.series[1].before, .absent(words: S.Words.drawHistoryUnavailable))
        XCTAssertTrue(input.series[2].runs.isEmpty)
        XCTAssertEqual(input.series[2].absentWords, S.Words.awayHistoryUnavailable)
        XCTAssertTrue(input.notes.contains(S.Words.drawAndAwayNote(away: names.away)))
        XCTAssertTrue(input.summary.hasSuffix(S.Words.drawAndAwayNote(away: names.away)))
    }

    /// The last pre-match minute, then the match — split where the subset's
    /// rows leave a 43-minute in-game hole (12:09 → 12:52), never joined across it.
    func testDuringPlayTheLineStartsAtTheLastPreMatchReadingAndBreaksAcrossTheUnrecordedSpan() throws {
        let (input, _) = try built(F.liveDetail, F.liveHistory, phase: .live, now: F.liveNow)
        let runs = pointIDs(input.series[0])
        let id = "blend:15325054:home#"

        XCTAssertEqual(runs.count, 2)
        XCTAssertEqual(runs.first?.first, id + "2026-10-12T11:59:00+00:00")
        XCTAssertEqual(runs.first?.last, id + "2026-10-12T12:09:00+00:00")
        XCTAssertEqual(runs.last?.first, id + "2026-10-12T12:52:00+00:00")
        // The pinned edge (12:56:02.476915) and the carried-forward 12:56 minute
        // (the venue's `live_edge` re-serve) are not readings, so neither is drawn.
        XCTAssertEqual(runs.last?.last, id + "2026-10-12T12:55:00+00:00")
        XCTAssertFalse(runs.joined().contains(id + "2026-10-12T12:56:02.476915+00:00"))
        XCTAssertFalse(runs.joined().contains(id + "2026-10-12T12:56:00+00:00"))
        XCTAssertEqual(input.series[0].runs.first?.points.first?.style, .hollow)
    }

    func testDuringPlayTheReadoutPairsTheLastPreMatchReadingWithTheLatestRecordedOne() throws {
        let (input, _) = try built(F.liveDetail, F.liveHistory, phase: .live, now: F.liveNow)
        let host = F.historyHost(F.liveNow)
        let home = input.series[0]
        let id = "blend:15325054:home#"

        XCTAssertEqual(input.caption, S.Words.gameCaption)
        XCTAssertEqual(input.readout, .beforeAndRecorded(beforeLabel: S.Words.preMatch, recordedLabel: S.Words.recorded))
        XCTAssertEqual(home.before, .observation(
            pointID: id + "2026-10-12T11:59:00+00:00", figure: formatProbability(0.4892),
            provenance: "\(S.Words.lastPreMatch) · \(HockeyJourneyHistoryAdapter10868.clockWords("2026-10-12T11:59:00+00:00".asDate!, host: host))"))
        XCTAssertEqual(home.recorded, .observation(
            pointID: id + "2026-10-12T12:55:00+00:00", figure: formatProbability(0.951805),
            provenance: "\(S.Words.recorded) \(HockeyJourneyHistoryAdapter10868.clockWords("2026-10-12T12:55:00+00:00".asDate!, host: host))"))
        XCTAssertEqual(input.inspect?.isAvailable, false)
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertEqual(input.expand?.isAvailable, true)
        XCTAssertEqual(input.expand?.id, HockeyJourneyHistoryAdapter10868.expandActionID)
        XCTAssertNil(input.plotAbsence)
    }

    // MARK: - Before kickoff and after the final

    func testBeforeKickoffTheLineEndsAtTheLastPreMatchReadingAndOmitsThePinnedEdge() throws {
        let (input, _) = try built(F.hullDetail, F.hullHistory, phase: .before, now: F.hullNow)
        let id = "blend:15311089:home#"

        XCTAssertEqual(input.caption, S.Words.beforeCaption)
        XCTAssertEqual(input.readout, .singleBefore(label: S.Words.preMatch))
        // The day ending at the last pre-match reading (04:56) is the window, not the
        // day before kickoff (13:00): the 10 October rows are inside it. The pinned
        // 04:57 edge is not a reading.
        XCTAssertEqual(pointIDs(input.series[0]), [[id + "2026-10-10T04:57:00+00:00",
                                                     id + "2026-10-10T05:03:00+00:00",
                                                     id + "2026-10-10T05:07:00+00:00",
                                                     id + "2026-10-11T04:53:00+00:00",
                                                     id + "2026-10-11T04:54:00+00:00",
                                                     id + "2026-10-11T04:56:00+00:00"]])
        // UNCHANGED gap authority, flagged rather than fixed here: pre-match intervals are never
        // judged, so 05:07 → 04:53 (23 h 46 min with no reading) stays inside ONE run. The points
        // keep their own clocks; nothing is observed between them.
        let drawn = input.series[0].runs.flatMap(\.points).map(\.x)
        XCTAssertEqual(input.series[0].runs.count, 1)
        guard drawn.count == 6 else { return XCTFail("six pre-match readings") }
        XCTAssertEqual(drawn[3] - drawn[2], 23 * 3_600 + 46 * 60)
        XCTAssertTrue(input.guides.isEmpty)
        XCTAssertNil(input.inspect)
        XCTAssertTrue(input.series[1].runs.isEmpty)
        XCTAssertTrue(input.series[2].runs.isEmpty)
    }

    func testAfterTheFinalTheSettlementRowIsNotDrawnAsAChance() throws {
        let (input, _) = try built(F.finalDetail, F.finalHistory, phase: .final, now: F.finalNow)
        let points = input.series[0].runs.flatMap(\.points)

        XCTAssertEqual(input.readout, .singleBefore(label: S.Words.preMatch))
        XCTAssertFalse(points.contains { $0.probability == 1.0 })
        XCTAssertEqual(points.last?.probability, 0.9995)
        // Subset runs: 11:59–12:09, 12:25–12:29, 13:47–13:57.
        XCTAssertEqual(input.series[0].runs.count, 3)
        XCTAssertTrue(input.series[1].runs.isEmpty)
        XCTAssertTrue(input.series[2].runs.isEmpty)
    }

    // MARK: - Absences

    /// CONSTRUCTED: the live history with only `aggregate_line` removed, so the
    /// consensus is the line. Its rows serve an away figure on every priced row;
    /// none is drawn.
    func testOnTheConsensusTheServedAwayFigureIsStillNeverDrawn() throws {
        let (input, _) = try built(F.liveDetail, try F.edited(F.liveHistory, removing: ["aggregate_line"]),
                                   phase: .live, now: F.liveNow)
        XCTAssertEqual(input.series[0].id, "consensus:15325054:home")
        XCTAssertFalse(input.series[0].runs.isEmpty)
        XCTAssertTrue(input.series[2].runs.isEmpty)
        XCTAssertEqual(input.series[2].absentWords, S.Words.awayHistoryUnavailable)
        XCTAssertEqual(input.notes.first, HockeyJourneyHistoryAdapter10868.sourceWords(.consensus))
    }

    /// CONSTRUCTED: the live subset with only `event_id` changed to a different
    /// event's id. None of it is drawn: the chart reads exactly as with no response.
    func testAnotherEventsHistoryDrawsNothingAndReadsAsUnavailable() throws {
        let event = try F.detail(F.liveDetail)
        let foreign = try F.history(try F.edited(F.liveHistory, setting: ["event_id": 15325055]))
        let input = S.history(foreign, event: event, phase: .live, host: F.historyHost(F.liveNow))
        XCTAssertEqual(input, S.unavailable(event: event, phase: .live))
        XCTAssertTrue(input.series.allSatisfy { $0.runs.isEmpty })
        XCTAssertNil(input.expand)
        XCTAssertNil(input.inspect)
    }

    func testWithNoHistoryResponseOnlyTheChartSlotSaysSo() throws {
        let event = try F.detail(F.liveDetail)
        let input = S.unavailable(event: event, phase: .live)

        XCTAssertEqual(input.plotAbsence, FieldHistoryPlotAbsence10868(title: S.Words.historyUnavailable, words: nil))
        XCTAssertEqual(input.series.count, 3)
        XCTAssertTrue(input.series.allSatisfy { $0.runs.isEmpty && $0.absentWords == S.Words.historyUnavailable })
        XCTAssertNil(input.expand)
        XCTAssertNil(input.inspect)
    }
}
