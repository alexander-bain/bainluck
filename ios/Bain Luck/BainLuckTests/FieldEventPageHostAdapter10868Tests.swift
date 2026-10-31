import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the field screen's host glue (`FieldEventPageHost10868`): which
/// served markets it would serve, and the pure `build` every body pass runs, on
/// the retained REAL bodies (`FieldEventAdapterFixtures10868`). The proposed
/// mount is NOT applied; nothing here renders. PREPARED / NOT RUN.
@MainActor
final class FieldEventPageHostAdapter10868Tests: XCTestCase {
    private typealias Host = FieldEventPageHost10868
    private typealias F = FieldEventAdapterFixtures10868

    // MARK: Which markets

    func testItAppliesToTheFourProvenWinnerFieldsOnly() throws {
        for body in [F.cricketBefore, F.rugbyBefore, F.dartsBefore, F.chessBefore] {
            XCTAssertTrue(Host.applies(try F.market(body)))
        }
        // Served with category "basketball": not claimed.
        XCTAssertFalse(Host.applies(try F.market(F.volleyballBefore)))
        // Each country qualifies independently: not a winner field.
        XCTAssertFalse(Host.applies(try F.market(F.lacrosseQualification)))
        // An exact-score board of an unproven category.
        XCTAssertFalse(Host.applies(try F.market(F.seriesFinal)))
        // CONSTRUCTED: the rugby board with only `mutually_exclusive` flipped.
        let independent = F.replacing(F.rugbyBefore, "\"mutually_exclusive\":true", with: "\"mutually_exclusive\":false")
        XCTAssertFalse(Host.applies(try F.market(independent)))
        // CONSTRUCTED: the rugby board with only its market `category` changed.
        let award = F.replacing(F.rugbyBefore, "\"category\":\"championship\"", with: "\"category\":\"award\"")
        XCTAssertFalse(Host.applies(try F.market(award)))
    }

    // MARK: Build

    func testBuildComposesTheWholeChessPageFromThePassedValues() throws {
        let market = try F.market(F.chessBefore)
        let built = Host.build(field: market, history: try F.history(F.chessHistory), now: F.chessCapture.asDate!,
                               calendar: F.pacific, locale: F.enUS)
        XCTAssertEqual(built.input.phase, .before)
        XCTAssertEqual(built.input.history.ceiling, 0.8)
        XCTAssertEqual(built.input.stories.map(\.card), [.field, .movement])
        XCTAssertEqual(built.originals.catalogue?.originals.count, 12)
        XCTAssertEqual(built.input.copy.allPropsLabel, "All 12 original outcomes")
        XCTAssertNil(built.originals.selection)
        // Pure: the same values build the same page.
        let again = Host.build(field: market, history: try F.history(F.chessHistory), now: F.chessCapture.asDate!,
                               calendar: F.pacific, locale: F.enUS)
        XCTAssertEqual(again.input, built.input)
    }

    func testTheReadersScaleChoiceAndChosenContenderReachEveryPart() throws {
        let market = try F.market(F.chessBefore)
        let reading = Host.Reading(chosen: F.carissaYip, full: true, displayed: .movement)
        let built = Host.build(field: market, history: try F.history(F.chessHistory), now: F.chessCapture.asDate!,
                               reading: reading, calendar: F.pacific, locale: F.enUS)
        XCTAssertEqual(built.input.history.ceiling, 1)
        XCTAssertEqual(built.input.history.scale?.label, "Full scale · 0–100%")
        XCTAssertEqual(built.input.headline.displayed.map(\.name), ["Carissa Yip", "Alice Lee", "Rachael Li"])
        XCTAssertEqual(built.input.history.series.map(\.name), ["Carissa Yip", "Alice Lee", "Rachael Li"])
        XCTAssertEqual(built.input.movement?.displayed.map(\.name), ["Carissa Yip", "Alice Lee", "Rachael Li"])
        XCTAssertEqual(built.input.field?.selected?.ref.outcomeID, String(F.carissaYip))
        XCTAssertEqual(built.input.stream.primary?.id, "movement")
    }

    func testAForeignOrMissingHistoryLeavesOnlyTheChartUnavailable() throws {
        let rugby = try F.market(F.rugbyBefore)
        let now = F.rugbyCapture.asDate!
        // REAL foreign body: the chess board's history handed to the rugby page.
        let foreign = Host.build(field: rugby, history: try F.history(F.chessHistory), now: now,
                                 calendar: F.pacific, locale: F.enUS)
        XCTAssertEqual(foreign.input.history.plotAbsence?.title, "History unavailable")
        XCTAssertNil(foreign.input.movement)
        XCTAssertEqual(foreign.input.stories.map(\.card), [.field])
        XCTAssertEqual(foreign.input.headline.displayed.map(\.name), ["Ireland", "South Africa", "France"])
        XCTAssertEqual(foreign.originals.catalogue?.originals.count, 24)
        let missing = Host.build(field: rugby, history: nil, now: now, calendar: F.pacific, locale: F.enUS)
        XCTAssertEqual(missing.input, foreign.input)
        let own = Host.build(field: rugby, history: try F.history(F.rugbyHistory), now: now,
                             calendar: F.pacific, locale: F.enUS)
        XCTAssertNil(own.input.history.plotAbsence)
        XCTAssertEqual(own.input.stories.map(\.card), [.field, .movement])
    }

    func testTheFinalPageShowsResultsAndNoFieldCard() throws {
        let market = try F.market(F.seriesFinal)
        let built = Host.build(field: market, history: try F.history(F.seriesHistory), now: F.seriesCapture.asDate!,
                               calendar: F.pacific, locale: F.enUS)
        XCTAssertEqual(built.input.phase, .final)
        XCTAssertNil(built.input.field)
        XCTAssertEqual(built.input.stories.map(\.card), [.movement])
        XCTAssertEqual(built.input.history.series.map { $0.keyContext?.words }, ["Won", "Lost", "Lost"])
        XCTAssertEqual(built.input.reader.state, "Settled market")
    }

    // MARK: Choosing

    func testOnlyAnExactRefOfThisBoardChoosesAContender() throws {
        let rugby = try F.market(F.rugbyBefore)
        let card = try XCTUnwrap(FieldEventStoriesAdapter10868.field(rugby, host: F.host(F.rugbyCapture)))
        let france = try XCTUnwrap(card.displayed.first { $0.label == "France" }).ref
        XCTAssertEqual(Host.chosenID(france, in: rugby), F.france)
        // CONSTRUCTED refs: another market, another source key, an unserved id.
        let otherMarket = FieldChooserOriginalRef10868(scope: france.scope, source: "kalshi", marketID: "62383719",
                                                       outcomeID: france.outcomeID)
        let otherSource = FieldChooserOriginalRef10868(scope: france.scope, source: "polymarket", marketID: "60473053",
                                                       outcomeID: france.outcomeID)
        let unserved = FieldChooserOriginalRef10868(scope: france.scope, source: "kalshi", marketID: "60473053",
                                                    outcomeID: "999")
        XCTAssertNil(Host.chosenID(otherMarket, in: rugby))
        XCTAssertNil(Host.chosenID(otherSource, in: rugby))
        XCTAssertNil(Host.chosenID(unserved, in: rugby))
    }
}
