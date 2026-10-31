import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the racing host glue's pure `build`, on the REAL retained Singapore
/// Grand Prix bodies (`RacingAdapterFixtures10868`). Only the builder is read:
/// no view is hosted or rendered here.
///
/// CONSTRUCTED here, and only here: the reader's calendar and `now`, the held
/// reading state, and — named in the one test that does it — one served
/// `probability` changed.
@MainActor
final class RacingEventPageHostAdapter10868Tests: XCTestCase {
    private typealias Host = RacingEventPageHost10868
    private typealias F = RacingAdapterFixtures10868

    private func build(_ json: String = F.winnerBefore, history: FuturesHistoryResponse? = nil,
                       markets: [FuturesMarketDetail] = [], reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        Host.build(race: try F.market(json), history: history, markets: markets, now: F.beforeCapture.asDate!,
                   reading: reading, calendar: F.pacific, locale: Locale(identifier: "en_US"))
    }

    private func figures(_ built: Host.Built) -> [[String?]] {
        FieldHeadlineModel10868(built.input.headline).competitors.map { $0.metrics.map(FieldChaseModel10868.figure) }
    }

    func testWithoutAHistoryResponseOnlyTheChartSlotIsUnavailable() throws {
        let built = try build(markets: [try F.market(F.podiumBefore)])
        XCTAssertEqual(built.input.history.plotAbsence, FieldHistoryPlotAbsence10868(title: "History unavailable", words: nil))
        XCTAssertNil(built.input.history.expand)
        // The headline and All props compose from their own inputs.
        XCTAssertEqual(figures(built), [["62%"], ["14%"], ["13%"]])
        XCTAssertEqual(built.originals.catalogue?.originals.count, 7)
        XCTAssertEqual(built.input.copy.allPropsLabel, "All 7 original outcomes")
    }

    func testAChangedPriceReachesTheBuiltInputOnTheNextPass() throws {
        let first = try build()
        // CONSTRUCTED: Verstappen's served price moved, every other byte equal.
        let moved = F.replacing(F.winnerBefore, #""probability":0.6162,"#, with: #""probability":0.6299,"#)
        let second = try build(moved)
        XCTAssertEqual(figures(first).first, ["62%"])
        XCTAssertEqual(figures(second).first, ["63%"])
        XCTAssertEqual(figures(second).dropFirst().map { $0 }, [["14%"], ["13%"]])
    }

    func testTheHeldSelectionAndReaderStateReachTheInputs() throws {
        let identity = OriginalMarketDetails9483.Identity(source: "polymarket", market: "63989371", side: "241675151")
        let selection = OriginalMarketDetails9483.Selection(scope: "racing:63989371:before:originals", identity: identity)
        let built = try build(reading: Host.Reading(selection: selection, readerOpen: true, wide: true))
        XCTAssertEqual(built.originals.selection, selection)
        XCTAssertEqual(OriginalMarketDetails9483.original(in: built.originals.catalogue, selection: selection)?.outcome,
                       "Max Verstappen")
        XCTAssertTrue(built.input.stream.readerOpen)
        XCTAssertTrue(built.input.stream.wide)
    }

    func testAppliesToMotorsportFieldWinnerBoardsOnly() throws {
        XCTAssertTrue(Host.applies(try F.market(F.winnerBefore)))
        XCTAssertTrue(Host.applies(try F.market(F.winnerFinal)))
        // The podium board is not one partition of the field.
        XCTAssertFalse(Host.applies(try F.market(F.podiumBefore)))
        XCTAssertFalse(Host.applies(try F.market(F.ladderDetail)))
    }
}
