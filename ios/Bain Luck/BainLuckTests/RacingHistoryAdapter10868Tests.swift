import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the racing adapter, part two (the named-field win history), on a
/// REAL retained `/api/futures/{id}/history` body and its market detail decoded
/// as the app decodes them (`RacingAdapterFixtures10868`).
///
/// NOT A RACING BODY. No race market's `/history` is retained, so the rules are
/// proven on the Kalshi "Boston vs Minnesota: Total Goals" ladder: an
/// independent multi-outcome board (not mutually exclusive), resolved, one
/// settlement point per line — the shapes a race's driver lines take. The kept
/// points are each line's first six and last four (three prices and the
/// settlement point); the omitted 99 points are an omitted span the gap rule
/// must split, never join.
///
/// CONSTRUCTED here, and only here: the reader's calendar and `now`, and — named
/// in each test that does it — one served substring replaced (a line's
/// `outcome_id`, the response's `market_id`, or one point's `timestamp`).
@MainActor
final class RacingHistoryAdapter10868Tests: XCTestCase {
    private typealias A = RacingHistoryAdapter10868
    private typealias Page = RacingFieldPageAdapter10868
    private typealias F = RacingAdapterFixtures10868

    /// After every kept point, before nothing.
    private static let after = "2026-10-12T00:00:00Z"

    private func build(_ history: String = F.ladderHistory, now: String = after) throws -> FieldHistoryInput10868 {
        A.history(try F.history(history), market: try F.market(F.ladderDetail), host: F.host(now))
    }

    private func runSizes(_ series: FieldHistorySeries10868) -> [Int] {
        series.runs.map(\.points.count)
    }

    // MARK: Which lines

    func testEachDisplayedOutcomeDrawsItsOwnLineByServedIdInServedCohortOrder() throws {
        let input = try build()
        // The detail's served order: Over 2.5, Over 1.5, Over 4.5 — the chart's first three.
        XCTAssertEqual(input.series.map(\.name), ["Over 2.5 goals scored", "Over 1.5 goals scored", "Over 4.5 goals scored"])
        XCTAssertEqual(input.series.map(\.id), ["kalshi:63539066:239380537", "kalshi:63539066:239380538",
                                                "kalshi:63539066:239380540"])
        XCTAssertEqual(input.series.map(\.shape), [.circle, .diamond, .square])
        // Over 7.5 is served but not displayed: it draws nothing anywhere.
        XCTAssertFalse(input.series.contains { $0.name == "Over 7.5 goals scored" })
        // Values exactly as served, never normalized against the other lines.
        let first = try XCTUnwrap(input.series[0].runs.first?.points.map(\.probability))
        XCTAssertEqual(first, [0.96, 0.955, 0.96, 0.96, 0.96, 0.96])
        let overFour = try XCTUnwrap(input.series[2].runs.last?.points.map(\.probability))
        XCTAssertEqual(overFour, [0.765, 0.67, 0.995])
    }

    func testTheSettlementPointIsRemovedOutrightAndNoLineRunsToNow() throws {
        let input = try build()
        let settledAt = try XCTUnwrap("2026-10-06T00:00:00+00:00".asDate).timeIntervalSince1970
        let lastPrice = try XCTUnwrap("2026-10-04T02:46:43.395259+00:00".asDate).timeIntervalSince1970
        for series in input.series {
            let xs = series.runs.flatMap { $0.points.map(\.x) }
            XCTAssertFalse(xs.contains(settledAt), series.name)
            XCTAssertEqual(xs.count, 9, series.name)
        }
        // The frame ends at the last recorded price: never at the settlement, never at now.
        XCTAssertEqual(input.domain.upper, lastPrice)
        XCTAssertTrue(input.notes.contains(A.Words.settledNote))
    }

    func testTheOmittedSpanIsSplitByTheFuturesChartsOwnCadenceRule() throws {
        let input = try build()
        // Six points 25–64 minutes apart, then 68 hours of omitted points, then
        // three 4 minutes apart: `EvolutionSeriesGaps` breaks only the long step.
        XCTAssertEqual(input.series.map(runSizes), [[6, 3], [6, 3], [6, 3]])
        XCTAssertEqual(input.series[0].runs.map(\.id), ["kalshi:63539066:239380537#run-1",
                                                        "kalshi:63539066:239380537#run-2"])
    }

    func testAnUnreadablePointBreaksTheRunWhereItSits() throws {
        // CONSTRUCTED: Over 1.5's third served point given an unreadable time.
        let variant = F.replacing(F.ladderHistory,
                                  #"{"timestamp":"2026-10-01T04:41:22.673271+00:00","probability":0.98,"#,
                                  with: #"{"timestamp":"unrecorded","probability":0.98,"#)
        let input = try build(variant)
        XCTAssertEqual(runSizes(input.series[1]), [2, 3, 3])
        // Its neighbours keep their own lines.
        XCTAssertEqual(runSizes(input.series[0]), [6, 3])
    }

    func testALineIsMatchedOnlyByItsServedId() throws {
        // CONSTRUCTED: Over 2.5's line served without an outcome id.
        let variant = F.replacing(F.ladderHistory, #"{"outcome_id":239380537,"#, with: #"{"outcome_id":null,"#)
        let input = try build(variant)
        XCTAssertEqual(input.series[0].runs, [])
        XCTAssertEqual(input.series[0].before, .absent(words: A.Words.noHistory))
        XCTAssertTrue(input.summary.hasSuffix("No recorded history for Over 2.5 goals scored."))
        XCTAssertEqual(runSizes(input.series[1]), [6, 3])
    }

    func testAResponseForAnotherMarketDrawsNothing() throws {
        // CONSTRUCTED: the response names another market.
        let variant = F.replacing(F.ladderHistory, #""market_id":63539066,"#, with: #""market_id":1,"#)
        let input = try build(variant)
        XCTAssertEqual(input.plotAbsence, FieldHistoryPlotAbsence10868(title: A.Words.noHistory, words: nil))
        XCTAssertEqual(input.series.flatMap(\.runs), [])
        XCTAssertEqual(input.xTicks, [])
        XCTAssertNil(input.expand)
    }

    func testPointsAfterTheReadersClockAreNotDrawn() throws {
        // CONSTRUCTED reader clock between the third and fourth kept points.
        let input = try build(now: "2026-10-01T05:00:00Z")
        XCTAssertEqual(input.series.map(runSizes), [[3], [3], [3]])
        XCTAssertEqual(input.domain.upper, try XCTUnwrap("2026-10-01T04:41:22.673271+00:00".asDate).timeIntervalSince1970)
    }

    // MARK: Readout, words and controls

    func testTheReadoutIsTheLastRecordedPointBoundToItsOwnId() throws {
        let input = try build()
        let host = F.host(Self.after)
        let stamp = "2026-10-04T02:46:43.395259+00:00"
        XCTAssertEqual(input.readout, .singleBefore(label: "Last recorded"))
        XCTAssertEqual(input.series[1].before, .observation(
            pointID: "kalshi:63539066:239380538#\(stamp)", figure: ">99%",
            provenance: "Recorded \(Page.clockWords(stamp.asDate!, host: host)) · Kalshi"))
        XCTAssertEqual(input.series[1].recorded, .absent(words: "Not recorded"))
        let ids = input.series[1].runs.flatMap { $0.points.map(\.id) }
        XCTAssertTrue(ids.contains("kalshi:63539066:239380538#\(stamp)"))
        let styles = input.series.flatMap { $0.runs.flatMap { $0.points.map(\.style) } }
        XCTAssertTrue(styles.allSatisfy { $0 == .filled })
    }

    func testNoStartClockMeansNoSplitNoGuideAndTheReasonIsSaid() throws {
        let input = try build()
        XCTAssertEqual(input.guides, [])
        XCTAssertEqual(input.breaks, [])
        XCTAssertEqual(input.markKey, FieldHistoryMarkKey10868(hollow: nil, filled: nil))
        XCTAssertEqual(input.caption, "Recorded history · race start time unavailable")
        XCTAssertEqual(input.notes, ["Source: Kalshi", A.Words.independent, A.Words.startUnavailable,
                                     A.Words.gapsNote, A.Words.settledNote])
        XCTAssertEqual(input.selection, .none)
        XCTAssertNil(input.plotAbsence)
        XCTAssertFalse(input.xTicks.isEmpty)
    }

    func testOnlyFullChartActsDetailsAndInspectionAreUnavailable() throws {
        let input = try build()
        XCTAssertEqual(input.expand, FieldHistoryAction10868(id: "history.expand", label: "Full chart",
                                                             spokenLabel: "Expand race probability chart", isAvailable: true))
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertNil(input.inspect)
        XCTAssertNil(input.inspection)
    }

    func testNoHistoryResponseLeavesOnlyTheChartSlotUnavailable() throws {
        let input = A.unavailable(try F.market(F.ladderDetail), host: F.host(Self.after))
        XCTAssertEqual(input.plotAbsence, FieldHistoryPlotAbsence10868(title: "History unavailable", words: nil))
        XCTAssertEqual(input.series.map(\.name), ["Over 2.5 goals scored", "Over 1.5 goals scored", "Over 4.5 goals scored"])
        XCTAssertEqual(input.notes, [])
        XCTAssertNil(input.expand)
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertEqual(input.summary, "History unavailable")
    }
}
