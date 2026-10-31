import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — part three (`FieldEventStoriesAdapter10868`): the field card and the
/// movement card, on the retained REAL rugby, chess, darts, series and
/// volleyball bodies (`FieldEventAdapterFixtures10868`), read through the
/// accepted leaves' own models (`FieldOutlookModel10868`,
/// `PreEventShiftModel10868`) so what is asserted is what the cards show.
/// PREPARED / NOT RUN.
@MainActor
final class FieldEventStoriesAdapter10868Tests: XCTestCase {
    private typealias S = FieldEventStoriesAdapter10868
    private typealias A = FieldEventPageAdapter10868
    private typealias F = FieldEventAdapterFixtures10868

    private func figures(_ input: FieldOutlookInput10868) -> [String?] {
        let model = FieldOutlookModel10868(input)
        return model.bars.map(model.figure)
    }

    private func sides(_ input: PreEventShiftInput10868) -> [[String?]] {
        PreEventShiftModel10868(input).rows.map { row in
            [row.first, row.latest].map { side in side.flatMap { FieldChaseModel10868.figure($0.endpoint) ?? FieldChaseModel10868.words($0.endpoint) } }
        }
    }

    // MARK: The field card

    func testTheFieldCardShowsEveryRecentRugbyChanceInServedOrder() throws {
        let market = try F.market(F.rugbyBefore)
        let input = try XCTUnwrap(S.field(market, host: F.host(F.rugbyCapture)))
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.scope, A.scope(market, phase: .before))
        XCTAssertEqual(input.displayed.map(\.label), ["Ireland", "South Africa", "France", "New Zealand", "England"])
        XCTAssertEqual(input.displayed.map(\.shortLabel), input.displayed.map(\.label))
        XCTAssertEqual(input.traversal, input.displayed.map(\.ref))
        XCTAssertEqual(input.chances.map(\.probability), [0.59, 0.4, 0.06, 0.01, 0.01])
        XCTAssertEqual(figures(input), ["59%", "40%", "6%", "1%", "1%"])
        let model = FieldOutlookModel10868(input)
        XCTAssertEqual(model.bars.map(\.chance.fraction), [0.59, 0.4, 0.06, 0.01, 0.01])
        XCTAssertEqual(input.copy.note, "5 of 24 teams with a recent win chance · in the market’s order, not a ranking")
        XCTAssertEqual(input.scale.ceiling, 1)
        XCTAssertEqual(input.scale.ticks.map(\.label), ["0%", "25%", "50%", "75%", "100%"])
        XCTAssertEqual(input.scale.words, "0–100% win chance · each team’s own chance, never added up")
        XCTAssertEqual(input.chooseHint, "Shows this team in the chart")
        XCTAssertNil(input.selected)
        // The catalogue is the headline's: the card cannot print a team two ways.
        XCTAssertEqual(input.catalogue, A.headline(market, host: F.host(F.rugbyCapture)).catalogue)
    }

    func testTheFieldCardLeavesOutStaleAndUnpricedChessRows() throws {
        let market = try F.market(F.chessBefore)
        let input = try XCTUnwrap(S.field(market, host: F.host(F.chessCapture)))
        XCTAssertEqual(input.displayed.map(\.label),
                       ["Alice Lee", "Rachael Li", "Thalia Cervantes", "Megan Paragua", "Irina Krush", "Carissa Yip"])
        XCTAssertFalse(input.displayed.contains { $0.label == "Tatev Abrahamyan" }, "11 h old: not a recent chance")
        XCTAssertEqual(figures(input), ["86%", "11%", "10%", "10%", "6%", "1%"])
        XCTAssertEqual(input.copy.note, "6 of 12 players with a recent win chance · in the market’s order, not a ranking")
        XCTAssertEqual(input.copy.previousLabel, "Previous player")
    }

    func testNoRecentChanceIsNoFieldCardAndAResolvedBoardHasNone() throws {
        // Every darts value is 17 h 36 m old at the capture.
        XCTAssertNil(S.field(try F.market(F.dartsBefore), host: F.host(F.dartsCapture)))
        // CONSTRUCTED reader clock ten minutes after the served write: all 18 are recent.
        let recent = try XCTUnwrap(S.field(try F.market(F.dartsBefore), host: F.host(F.dartsRecentClock)))
        XCTAssertEqual(recent.displayed.count, 18)
        XCTAssertEqual(figures(recent).suffix(3), ["<1%", "<1%", "<1%"])
        XCTAssertNil(S.field(try F.market(F.seriesFinal), host: F.host(F.seriesCapture)))
    }

    func testTheChosenContenderIsTheFieldCardsSelection() throws {
        let market = try F.market(F.rugbyBefore)
        let input = try XCTUnwrap(S.field(market, host: F.host(F.rugbyCapture, chosen: F.choice(F.france, in: market))))
        XCTAssertEqual(input.selected?.ref.outcomeID, String(F.france))
        XCTAssertEqual(input.selected?.words, "In your chart")
        let model = FieldOutlookModel10868(input)
        XCTAssertEqual(model.selectedOriginal?.name, "France")
        XCTAssertEqual(model.neighbour(.previous)?.name, "South Africa")
        XCTAssertEqual(model.neighbour(.next)?.name, "New Zealand")
        // The chosen team leads the chart, so its bar carries the chart's first colour.
        XCTAssertEqual(model.selectedOriginal?.accent, A.tint(0))
        XCTAssertNil(input.catalogue.first { $0.name == "New Zealand" }?.accent)
        // CONSTRUCTED: this board's identity with an id it does not serve is still the
        // choice — handed over by its identity, so the chooser's own words say it is
        // unavailable, and nothing else is selected in its place.
        let missing = try XCTUnwrap(S.field(market, host: F.host(F.rugbyCapture, chosen: F.choice(999, in: market))))
        XCTAssertEqual(missing.selected?.ref.outcomeID, "999")
        let unresolved = FieldOutlookModel10868(missing)
        XCTAssertNil(unresolved.selectedOriginal)
        XCTAssertEqual(unresolved.notice, "Chosen team unavailable in this update")
        XCTAssertFalse(unresolved.bars.contains(where: unresolved.isSelected))
        // CONSTRUCTED: another market's choice with an outcome id this board serves selects nothing.
        let foreign = A.Choice(source: "kalshi", marketID: "62383719", outcomeID: String(F.france))
        let other = try XCTUnwrap(S.field(market, host: F.host(F.rugbyCapture, chosen: foreign)))
        XCTAssertNil(other.selected)
        XCTAssertNil(FieldOutlookModel10868(other).notice)
    }

    // MARK: The movement card

    func testEachChartedPlayerShowsItsEarliestAndLatestRecordedReading() throws {
        let market = try F.market(F.chessBefore)
        let host = F.host(F.chessCapture)
        let input = try XCTUnwrap(S.movement(try F.history(F.chessHistory), market: market, host: host))
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.displayed.map(\.name), ["Alice Lee", "Rachael Li", "Thalia Cervantes"])
        // The third contender's square: the same mark as its headline key and chart line.
        XCTAssertEqual(input.displayed.map(\.glyph), [.circle, .diamond, .square])
        XCTAssertEqual(sides(input), [["33%", "69%"], ["5%", "5%"], ["6%", "5%"]])
        let alice = try XCTUnwrap(PreEventShiftModel10868(input).rows.first)
        XCTAssertEqual(alice.first?.chance, .value(probability: 0.325, fraction: 0.325))
        XCTAssertEqual(alice.latest?.chance, .value(probability: 0.685, fraction: 0.685))
        // Each key is the chart's own point id, so an open lands on that exact point.
        XCTAssertEqual(alice.first?.key, "kalshi:62383719:235705516#2026-09-25T20:49:31.505270+00:00")
        XCTAssertEqual(alice.latest?.key, "kalshi:62383719:235705516#2026-10-12T17:40:20.327811+00:00")
        let clock = A.clockWords("2026-10-12T17:40:20.327811+00:00".asDate!, host: host)
        XCTAssertEqual(FieldChaseModel10868.detail(try XCTUnwrap(alice.latest?.endpoint)), "Recorded \(clock) · Kalshi")
        XCTAssertEqual(input.copy.firstLabel, "Earliest in this history")
        XCTAssertEqual(input.copy.latestLabel, "Latest recorded")
        XCTAssertEqual(input.copy.phaseKey, "Each mark is a recorded reading with its own time")
        XCTAssertEqual(input.scale.ceiling, 1)
        XCTAssertEqual(input.catalogue, A.headline(market, host: host).catalogue)
    }

    func testOneReadingIsTheLatestAndTheEarliestSaysSo() throws {
        // Texas A&M has exactly one served point in the REAL volleyball history.
        let market = try F.market(F.volleyballBefore)
        let input = try XCTUnwrap(S.movement(try F.history(F.volleyballHistory), market: market,
                                             host: F.host(F.volleyballCapture, chosen: F.choice(F.texasAM, in: market))))
        XCTAssertEqual(input.displayed.map(\.name), ["Texas A&M", "Nebraska", "Pittsburgh"])
        XCTAssertEqual(sides(input), [["Only one reading in this history", "1%"], ["63%", "45%"], ["74%", "32%"]])
        XCTAssertEqual(PreEventShiftModel10868(input).rows.first?.first?.key, nil)
    }

    func testTheMovementCardNeverReadsAnotherMarketsHistoryOrNone() throws {
        let rugby = try F.market(F.rugbyBefore)
        XCTAssertNil(S.movement(try F.history(F.chessHistory), market: rugby, host: F.host(F.rugbyCapture)))
        XCTAssertNil(S.movement(nil, market: rugby, host: F.host(F.rugbyCapture)))
    }

    func testAtTheFinalTheLatestReadingIsTheLastValueNeverTheSettlement() throws {
        let market = try F.market(F.seriesFinal)
        let input = try XCTUnwrap(S.movement(try F.history(F.seriesHistory), market: market, host: F.host(F.seriesCapture)))
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(sides(input), [["22%", "78%"], ["33%", "3%"], ["28%", "8%"]])
        XCTAssertTrue(PreEventShiftModel10868(input).isShown)
    }
}
