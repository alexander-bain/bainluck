import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — part two (`FieldEventHistoryAdapter10868`): the named-field win
/// history on Design's Auto / Full scale, proven on the retained REAL rugby,
/// chess and resolved series `/history` bodies (`FieldEventAdapterFixtures10868`,
/// reduced verbatim subsets: the kept points of each line are its first and
/// last served points, so an omitted middle can open a new run — every expected
/// run below is the production cadence rule applied to the KEPT points, as
/// `/tmp/cli-10868-field/make_field_subsets.py` prints it). PREPARED / NOT RUN.
@MainActor
final class FieldEventHistoryAdapter10868Tests: XCTestCase {
    private typealias H = FieldEventHistoryAdapter10868
    private typealias A = FieldEventPageAdapter10868
    private typealias F = FieldEventAdapterFixtures10868

    private func stamps(_ series: FieldHistorySeries10868) -> [[String]] {
        series.runs.map { run in run.points.map { String($0.id.split(separator: "#").last ?? "") } }
    }

    private func values(_ series: FieldHistorySeries10868) -> [[Double]] {
        series.runs.map { run in run.points.map(\.probability) }
    }

    // MARK: Rugby

    func testEachDisplayedTeamDrawsOnlyItsOwnServedLineInItsOwnRuns() throws {
        let market = try F.market(F.rugbyBefore)
        let host = F.host(F.rugbyCapture)
        let input = H.history(try F.history(F.rugbyHistory), market: market, host: host)
        XCTAssertNil(input.plotAbsence)
        XCTAssertEqual(input.series.map(\.name), ["Ireland", "South Africa", "France"])
        XCTAssertEqual(input.series.map(\.id), ["kalshi:60473053:225917124", "kalshi:60473053:225917112",
                                                "kalshi:60473053:225917111"])
        // New Zealand has a served line but is not in the chart: it is not drawn.
        XCTAssertFalse(input.series.contains { $0.name == "New Zealand" })
        XCTAssertEqual(input.series.map(\.shape), [.circle, .diamond, .square])
        XCTAssertEqual(stamps(input.series[0]), [
            ["2026-10-01T08:07:08.891195+00:00", "2026-10-02T21:18:50.422968+00:00", "2026-10-03T04:20:39.302962+00:00"],
            ["2026-10-07T13:01:09.953967+00:00", "2026-10-08T05:21:17.891245+00:00", "2026-10-08T12:47:34.213639+00:00"],
        ])
        XCTAssertEqual(values(input.series[0]), [[0.97, 0.03, 0.03], [0.03, 0.03, 0.03]])
        XCTAssertEqual(values(input.series[1]), [[0.09, 0.09, 0.09], [0.8, 0.8, 0.69]])
        XCTAssertEqual(values(input.series[2]), [[0.97, 0.97, 0.97], [0.03, 0.03, 0.03]])
        XCTAssertTrue(input.series.allSatisfy { $0.runs.allSatisfy { $0.points.allSatisfy { $0.style == .filled } } })
        // The readout is the last recorded point, bound by id, with its own clock.
        let clock = A.clockWords("2026-10-07T13:01:09.953967+00:00".asDate!, host: host)
        XCTAssertEqual(input.series[1].before, .observation(
            pointID: "kalshi:60473053:225917112#2026-10-07T13:01:09.953967+00:00", figure: "69%",
            provenance: "Recorded \(clock) · Kalshi"))
        XCTAssertEqual(input.readout, .singleBefore(label: "Last recorded"))
        XCTAssertEqual(input.series.map(\.keyContext), [nil, nil, nil])
        // The highest plotted point is 97%: Auto opens on the full axis, never clipping it.
        XCTAssertEqual(input.ceiling, 1)
        XCTAssertEqual(input.scale?.label, "Auto scale · 0–100%")
        XCTAssertEqual(input.notes, [
            "Source: Kalshi",
            "Each line is that team’s own chance, recorded at its own times. The lines are not adjusted to add up to 100%.",
            "Start times are unavailable here, so readings are not split into before and during play.",
            "Gaps remain blank.",
        ])
        XCTAssertEqual(input.expand?.id, H.expandActionID)
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertEqual(input.domain.lower, "2026-09-16T01:51:29.915951+00:00".asDate!.timeIntervalSince1970)
        XCTAssertEqual(input.domain.upper, "2026-10-08T12:47:34.213639+00:00".asDate!.timeIntervalSince1970)
        XCTAssertEqual(input.guides, [])
        XCTAssertEqual(input.markKey, FieldHistoryMarkKey10868(hollow: nil, filled: nil))
    }

    func testAServedTeamWithNoLineSaysNoReadingsInThisHistory() throws {
        // Scotland is served on the board and has no line in the REAL response at all.
        let market = try F.market(F.rugbyBefore)
        let input = H.history(try F.history(F.rugbyHistory), market: market,
                              host: F.host(F.rugbyCapture, chosen: F.scotland))
        XCTAssertEqual(input.series.map(\.name), ["Scotland", "Ireland", "South Africa"])
        XCTAssertEqual(input.series[0].runs, [])
        XCTAssertEqual(input.series[0].before, .absent(words: "No readings in this history"))
        XCTAssertEqual(input.summary, "Recorded win probability for Ireland, South Africa, each line that team’s own chance. No readings in this history for Scotland.")
    }

    // MARK: Identity

    func testAnotherMarketsHistoryIsNeverDrawnAsThisField() throws {
        let rugby = try F.market(F.rugbyBefore)
        // REAL foreign body: the chess board's own history, handed to the rugby page.
        let foreign = H.history(try F.history(F.chessHistory), market: rugby, host: F.host(F.rugbyCapture))
        XCTAssertEqual(foreign.plotAbsence, FieldHistoryPlotAbsence10868(title: "History unavailable", words: nil))
        XCTAssertEqual(foreign.series.map(\.name), ["Ireland", "South Africa", "France"])
        XCTAssertTrue(foreign.series.allSatisfy { $0.runs.isEmpty })
        XCTAssertEqual(foreign.notes, [])
        XCTAssertNil(foreign.scale)
        XCTAssertNil(foreign.expand)
        // CONSTRUCTED: the rugby history with only its `market_id` changed — same outcome ids.
        let renamed = F.replacing(F.rugbyHistory, "\"market_id\":60473053", with: "\"market_id\":62383719")
        let relabelled = H.history(try F.history(renamed), market: rugby, host: F.host(F.rugbyCapture))
        XCTAssertEqual(relabelled, foreign)
        // Never claims this field has no recorded history.
        XCTAssertFalse(relabelled.summary.contains("No readings"))
        XCTAssertEqual(H.unavailable(rugby, host: F.host(F.rugbyCapture)), foreign)
    }

    // MARK: The Auto / Full scale

    func testAutoKeepsEveryPlottedChessPointInsideAndFullIsZeroToOneHundred() throws {
        let market = try F.market(F.chessBefore)
        let history = try F.history(F.chessHistory)
        let auto = H.history(history, market: market, host: F.host(F.chessCapture))
        XCTAssertEqual(auto.series.map(\.name), ["Alice Lee", "Rachael Li", "Thalia Cervantes"])
        XCTAssertEqual(values(auto.series[0]), [[0.325, 0.33, 0.325], [0.38], [0.635, 0.685]])
        XCTAssertEqual(values(auto.series[2]), [[0.06, 0.05]])
        // Peak 68.5% plus 4% headroom is 71.2%: the first approved rung at or above it is 80%.
        XCTAssertEqual(auto.ceiling, 0.8)
        XCTAssertEqual(auto.yTicks.map(\.value), [0, 0.4, 0.8])
        XCTAssertEqual(auto.scale, FieldHistoryAction10868(id: GolfFieldHistoryAdapter10868.scaleActionID,
                                                            label: "Auto scale · 0–80%",
                                                            spokenLabel: "Show full zero to 100 percent scale",
                                                            isAvailable: true))
        let plotted = auto.series.flatMap { $0.runs.flatMap { $0.points.map(\.probability) } }
        XCTAssertTrue(plotted.allSatisfy { $0 <= auto.ceiling })
        let full = H.history(history, market: market, full: true, host: F.host(F.chessCapture))
        XCTAssertEqual(full.ceiling, 1)
        XCTAssertEqual(full.scale?.label, "Full scale · 0–100%")
        XCTAssertEqual(full.scale?.spokenLabel, "Use automatic probability scale")
        // The scale changes nothing else: same series, points, readouts and domain.
        XCTAssertEqual(full.series, auto.series)
        XCTAssertEqual(full.domain, auto.domain)
        XCTAssertEqual(H.scaleActionID, GolfFieldHistoryAdapter10868.scaleActionID)
    }

    // MARK: Final

    func testASettlementPointIsNeverDrawnAndTheResultSitsInTheKey() throws {
        let market = try F.market(F.seriesFinal)
        let input = H.history(try F.history(F.seriesHistory), market: market, host: F.host(F.seriesCapture))
        XCTAssertEqual(input.series.map(\.name), ["CWS wins 2-0", "HOU wins 2-0", "HOU wins 2-1"])
        XCTAssertEqual(values(input.series[0]), [[0.215, 0.215, 0.7798]])
        XCTAssertEqual(values(input.series[1]), [[0.325, 0.325, 0.03]])
        // The served 1.0 settlement at 23:52:24 is not a point, an axis bound or a readout.
        XCTAssertFalse(input.series.contains { $0.runs.contains { $0.points.contains { $0.probability == 1 || $0.probability == 0 } } })
        XCTAssertEqual(input.domain.upper, "2026-09-30T23:52:23.670292+00:00".asDate!.timeIntervalSince1970)
        guard case .observation(_, let figure, _) = input.series[0].before else { return XCTFail("no readout") }
        XCTAssertEqual(figure, "78%")
        XCTAssertEqual(input.series.map { $0.keyContext?.words }, ["Won", "Lost", "Lost"])
        XCTAssertEqual(input.series[0].keyContext, FieldHistoryKeyContext10868(label: "Result", words: "Won",
                                                                               spoken: "Final result: Won"))
        XCTAssertEqual(input.notes.last, "A settled result is not a chance, so no 0% or 100% point is shown.")
        XCTAssertTrue(input.notes.contains("Each line is that contender’s own chance, recorded at its own times. The lines are not adjusted to add up to 100%."))
    }

    // MARK: Absence

    func testNoResponseIsHistoryUnavailableAndTheRestOfTheInputStands() throws {
        let market = try F.market(F.chessBefore)
        let input = H.unavailable(market, host: F.host(F.chessCapture))
        XCTAssertEqual(input.plotAbsence?.title, "History unavailable")
        XCTAssertEqual(input.series.map(\.name), ["Alice Lee", "Rachael Li", "Thalia Cervantes"])
        XCTAssertEqual(input.series.map(\.before),
                       [FieldHistoryReading10868](repeating: .absent(words: "History unavailable"), count: 3))
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertNil(input.expand)
        XCTAssertNil(input.scale)
    }
}
