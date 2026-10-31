import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game adapter, part two (the two-team win-probability
/// history), on the RETAINED REAL bodies in `BaseballRetainedAdapter10868Tests`:
/// the final `/history` subset and the live `/history` fixture of the same game.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The row rules are the accepted two-team history adapter's (H2,
/// `HockeyJourneyHistoryAdapter10868`), called, not copied; what is pinned here
/// is that the baseball screen gets exactly H2's history with only its expand
/// control's spoken words changed, and what that means on these bodies: the
/// settlement row and the pinned edge are never drawn, nothing is drawn past
/// the game's end or past now, and the away line is the blend's other side.
@MainActor
final class BaseballHistoryAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias A = BaseballHistoryAdapter10868
    private typealias H = HockeyJourneyHistoryAdapter10868

    private static let home = "blend:15321836:home"
    private static let away = "blend:15321836:away"

    private func points(_ input: FieldHistoryInput10868, _ id: String) -> [FieldHistoryPoint10868] {
        input.series.first { $0.id == id }?.runs.flatMap(\.points) ?? []
    }

    func testTheBaseballHistoryIsH2sHistoryWithOnlyItsExpandWordsChanged() throws {
        let event = try F.finalEvent()
        let response = try F.history(F.finalHistory)
        let host = F.historyHost(F.finalNow)
        let drawn = A.history(response, event: event, phase: .final, host: host)
        let shared = H.history(response, event: event, phase: .final, host: host)

        XCTAssertEqual(drawn.expand, H.action(H.expandActionID, "Full chart",
                                              spoken: "Expand baseball win probability history"))
        XCTAssertEqual(shared.expand?.spokenLabel, "Expand hockey probability history")
        XCTAssertEqual(drawn, A.withExpand(shared, drawn.expand), "every other field is H2's, unchanged")
        XCTAssertEqual(A.h2Phase(.before), .before)
        XCTAssertEqual(A.h2Phase(.live), .live)
        XCTAssertEqual(A.h2Phase(.final), .final)
    }

    func testAfterTheFinalTheJourneyEndsAtTheLastRealRowAndNeverDrawsTheSettlement() throws {
        let event = try F.finalEvent()
        let host = F.historyHost(F.finalNow)
        let drawn = A.history(try F.history(F.finalHistory), event: event, phase: .final, host: host)
        let homePoints = points(drawn, Self.home)

        XCTAssertEqual(drawn.title, "Win probability")
        XCTAssertEqual(drawn.caption, "Game history")
        XCTAssertEqual(drawn.series.map(\.id), [Self.home, Self.away])
        XCTAssertEqual(drawn.readout, .singleBefore(label: "Pregame"))

        // Opens on the last pregame blend row, drawn hollow.
        let first = try XCTUnwrap(homePoints.first)
        XCTAssertEqual(first.id, "\(Self.home)#2026-09-30T20:58:00+00:00")
        XCTAssertEqual(first.probability, 0.589)
        XCTAssertEqual(first.style, .hollow)
        guard case .observation(let pointID, _, let provenance) = drawn.series[0].before else {
            return XCTFail("the last pregame reading is a drawn observation")
        }
        XCTAssertEqual(pointID, first.id)
        XCTAssertEqual(provenance, "Last pregame · \(H.clockWords("2026-09-30T20:58:00+00:00".asDate!, host: host))")
        XCTAssertEqual(drawn.series[0].recorded, .absent(words: "Not recorded"))

        // Ends at 00:18:00Z, the last real row: the served settlement row (0.0,
        // served after the out-of-order 00:46Z row) and the 00:46Z row past the
        // game's end are never drawn.
        let last = try XCTUnwrap(homePoints.last)
        XCTAssertEqual(last.id, "\(Self.home)#2026-10-01T00:18:00+00:00")
        XCTAssertEqual(last.probability, 0.010558)
        XCTAssertFalse(homePoints.contains { $0.probability == 0 }, "settlement is never a chance")
        XCTAssertFalse((homePoints + points(drawn, Self.away)).contains { $0.id.hasSuffix("2026-10-01T00:46:00+00:00") })
        // Strictly advancing within each run; runs are never joined.
        for run in drawn.series[0].runs {
            XCTAssertEqual(run.points.map(\.x), run.points.map(\.x).sorted())
        }

        // The away line is the blend's other side, and the page says so.
        let awayPoints = points(drawn, Self.away)
        XCTAssertEqual(awayPoints.count, homePoints.count)
        XCTAssertEqual(awayPoints.first?.probability ?? 0, 1 - 0.589, accuracy: 1e-9)
        XCTAssertTrue(drawn.notes.contains(H.complementNote(away: event.awayTeam, home: event.homeTeam)))
        XCTAssertNil(drawn.inspect, "no inspection after the final")
        XCTAssertEqual(drawn.details?.isAvailable, false, "Details waits for its owner contract")
    }

    /// The live fixture keeps its served `blend_edge_pinned: true`: H2 removes
    /// that pinned last row (22:13:00Z) outright, so the latest drawn reading
    /// is 22:12:00Z. CONSTRUCTED: the event is `liveEvent`.
    func testDuringPlayThePinnedEdgeIsNeverDrawnAndTheLatestReadingKeepsItsOwnClock() throws {
        let event = try F.liveEvent()
        let host = F.historyHost(F.liveHistoryNow)
        let response = try F.liveHistory()
        XCTAssertEqual(response.blendEdgePinned, true)
        let drawn = A.history(response, event: event, phase: .live, host: host)
        let homePoints = points(drawn, Self.home)

        XCTAssertEqual(drawn.readout, .beforeAndRecorded(beforeLabel: "Pregame", recordedLabel: "Recorded"))
        XCTAssertEqual(homePoints.first?.id, "\(Self.home)#2026-09-30T20:59:00+00:00")
        XCTAssertEqual(homePoints.last?.id, "\(Self.home)#2026-09-30T22:12:00+00:00")
        XCTAssertFalse(homePoints.contains { $0.id.hasSuffix("2026-09-30T22:13:00+00:00") })
        XCTAssertFalse(homePoints.contains { $0.x > F.liveHistoryNow.timeIntervalSince1970 }, "nothing past now")
        guard case .observation(let pointID, _, let provenance) = drawn.series[0].recorded else {
            return XCTFail("the latest reading is a drawn observation")
        }
        XCTAssertEqual(pointID, "\(Self.home)#2026-09-30T22:12:00+00:00")
        XCTAssertEqual(provenance, "Recorded \(H.clockWords("2026-09-30T22:12:00+00:00".asDate!, host: host))")
        XCTAssertEqual(drawn.inspect?.isAvailable, false, "Inspect waits for its owner contract")
        XCTAssertEqual(drawn.expand?.spokenLabel, "Expand baseball win probability history")
    }

    /// CONSTRUCTED: `beforeEvent` read against the final subset at 20:59:00Z —
    /// a phase-safety check: before first pitch only rows at or before now and
    /// before the start are drawn.
    func testBeforeFirstPitchOnlyPregameRowsAtOrBeforeNowAreDrawn() throws {
        let drawn = A.history(try F.history(F.finalHistory), event: try F.beforeEvent(), phase: .before,
                              host: F.historyHost(F.beforeNow))
        let homePoints = points(drawn, Self.home)
        XCTAssertEqual(drawn.caption, "Before game")
        XCTAssertEqual(homePoints.last?.id, "\(Self.home)#2026-09-30T20:58:00+00:00")
        XCTAssertFalse(homePoints.contains { $0.x > F.beforeNow.timeIntervalSince1970 })
        XCTAssertTrue(drawn.guides.isEmpty, "no in-game guide before first pitch")
        XCTAssertNil(drawn.inspect)
    }

    func testWithoutAHistoryResponseOnlyTheChartSlotIsUnavailableAndOffersNoControl() throws {
        let event = try F.finalEvent()
        let missing = A.unavailable(event: event, phase: .final)
        XCTAssertEqual(missing, H.unavailable(event: event, phase: .final))
        XCTAssertEqual(missing.plotAbsence?.title, "History unavailable")
        XCTAssertNil(missing.expand)
        XCTAssertNil(missing.inspect)
        XCTAssertEqual(missing.details?.isAvailable, false)
        XCTAssertTrue(missing.series.allSatisfy { $0.runs.isEmpty })
    }
}
