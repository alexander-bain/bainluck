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
        let reading = Host.Reading(chosen: F.choice(F.carissaYip, in: market), full: true, displayed: .movement)
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
        XCTAssertEqual(Host.choice(france, in: rugby),
                       FieldEventPageAdapter10868.Choice(source: "kalshi", marketID: "60473053", outcomeID: String(F.france)))
        // CONSTRUCTED refs: another market, another source key, an unserved id.
        let otherMarket = FieldChooserOriginalRef10868(scope: france.scope, source: "kalshi", marketID: "62383719",
                                                       outcomeID: france.outcomeID)
        let otherSource = FieldChooserOriginalRef10868(scope: france.scope, source: "polymarket", marketID: "60473053",
                                                       outcomeID: france.outcomeID)
        let unserved = FieldChooserOriginalRef10868(scope: france.scope, source: "kalshi", marketID: "60473053",
                                                    outcomeID: "999")
        XCTAssertNil(Host.choice(otherMarket, in: rugby))
        XCTAssertNil(Host.choice(otherSource, in: rugby))
        XCTAssertNil(Host.choice(unserved, in: rugby))
    }

    // MARK: The held choice across refreshes

    func testAHeldChoiceSurvivesARefreshThatOmitsItAndIsRestoredWhenServedAgain() throws {
        let rugby = try F.market(F.rugbyBefore)
        let history = try F.history(F.rugbyHistory)
        let now = F.rugbyCapture.asDate!
        func build(_ field: FuturesMarketDetail, _ reading: Host.Reading) -> Host.Built {
            Host.build(field: field, history: history, now: now, reading: reading, calendar: F.pacific, locale: F.enUS)
        }
        // The reader chooses France through the REAL field card's own ref.
        let card = try XCTUnwrap(build(rugby, Host.Reading()).input.field)
        let france = try XCTUnwrap(card.displayed.first { $0.label == "France" }).ref
        let reading = Host.Reading(chosen: try XCTUnwrap(Host.choice(france, in: rugby)))

        // Present.
        let present = build(rugby, reading)
        XCTAssertEqual(present.input.headline.displayed.map(\.name), ["France", "Ireland", "South Africa"])
        XCTAssertEqual(present.input.headline.displayed.map(\.keyShape), [.circle, .diamond, .square])
        XCTAssertEqual(present.input.movement?.displayed.map(\.glyph), [.circle, .diamond, .square])
        let presentCard = FieldOutlookModel10868(try XCTUnwrap(present.input.field))
        XCTAssertEqual(presentCard.selectedOriginal?.name, "France")
        XCTAssertNil(presentCard.notice)

        // CONSTRUCTED refresh: the same REAL board with France's served row removed.
        let omittedBody = try F.market(F.omitting(F.rugbyBefore, outcome: F.france))
        XCTAssertEqual(omittedBody.outcomes.count, 23)
        let omitted = build(omittedBody, reading)
        // The choice keeps the first slot, unavailable; no other team is promoted into it,
        // and the served teams keep their own key shapes.
        let headline = omitted.input.headline
        XCTAssertEqual(headline.displayed.map(\.ref.outcomeID), [String(F.france), String(F.ireland), String(F.southAfrica)])
        XCTAssertEqual(headline.displayed.map(\.keyShape), [.circle, .diamond, .square])
        let competitors = FieldHeadlineModel10868(headline).competitors
        XCTAssertEqual(competitors.map(\.resolution.original?.name), [nil, "Ireland", "South Africa"])
        XCTAssertTrue(competitors[0].metrics.isEmpty)
        XCTAssertEqual(FieldHeadlineModel10868(headline).competitorSummary(competitors[0]),
                       "Chosen team unavailable in this update")
        // The field card hands the chooser the held identity; its own words say it is unavailable.
        let omittedField = try XCTUnwrap(omitted.input.field)
        XCTAssertEqual(omittedField.selected?.ref.outcomeID, String(F.france))
        let omittedCard = FieldOutlookModel10868(omittedField)
        XCTAssertNil(omittedCard.selectedOriginal)
        XCTAssertEqual(omittedCard.notice, "Chosen team unavailable in this update")
        XCTAssertFalse(omittedCard.bars.contains(where: omittedCard.isSelected))
        // No figure of France is kept: no bar, chance, line or movement row.
        XCTAssertFalse(omittedField.chances.contains { $0.ref.outcomeID == String(F.france) })
        XCTAssertEqual(omitted.input.history.series.map(\.name), ["Ireland", "South Africa"])
        XCTAssertEqual(omitted.input.history.series.map(\.shape), [.diamond, .square])
        XCTAssertEqual(omitted.input.movement?.displayed.map(\.name), ["Ireland", "South Africa"])
        XCTAssertEqual(omitted.input.movement?.displayed.map(\.glyph), [.diamond, .square])
        XCTAssertEqual(omitted.originals.catalogue?.originals.map(\.outcome), omittedBody.outcomes.map(\.name))

        // Served again: the same choice, restored exactly.
        let restored = build(rugby, reading)
        XCTAssertEqual(restored.input, present.input)
    }

    func testAChoiceIsNeverCarriedOntoAnotherMarketsCoincidentOutcomeID() throws {
        let rugby = try F.market(F.rugbyBefore)
        let card = try XCTUnwrap(FieldEventStoriesAdapter10868.field(rugby, host: F.host(F.rugbyCapture)))
        let france = try XCTUnwrap(card.displayed.first { $0.label == "France" }).ref
        let reading = Host.Reading(chosen: try XCTUnwrap(Host.choice(france, in: rugby)))
        // CONSTRUCTED: the REAL chess board (same venue) with Carissa Yip's served id
        // replaced by France's, so the held rugby choice's outcome id is served here.
        let chess = try F.market(F.replacing(F.chessBefore, "\"id\":\(F.carissaYip),", with: "\"id\":\(F.france),"))
        XCTAssertEqual(chess.outcomes.filter { $0.id == F.france }.map(\.name), ["Carissa Yip"])
        let history = try F.history(F.chessHistory)
        let now = F.chessCapture.asDate!
        let carried = Host.build(field: chess, history: history, now: now, reading: reading,
                                 calendar: F.pacific, locale: F.enUS)
        let fresh = Host.build(field: chess, history: history, now: now, calendar: F.pacific, locale: F.enUS)
        // Nothing of the rugby choice reaches the chess page: no selection, no held
        // slot, no notice — exactly the page with no choice.
        XCTAssertEqual(carried.input, fresh.input)
        XCTAssertNil(carried.input.field?.selected)
        XCTAssertEqual(carried.input.headline.displayed.map(\.name), ["Alice Lee", "Rachael Li", "Thalia Cervantes"])
        XCTAssertEqual(carried.input.headline.unavailableWords, "Player unavailable in this update")
        // Back on the rugby board, the choice is still that board's.
        XCTAssertEqual(Host.build(field: rugby, history: nil, now: F.rugbyCapture.asDate!, reading: reading,
                                  calendar: F.pacific, locale: F.enUS).input.headline.displayed.first?.name, "France")
    }
}
