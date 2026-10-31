import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the soccer screen's host glue: the pure `build` the host view runs
/// on every body pass, on the RETAINED REAL bodies (`SoccerRetained10868`) and
/// the CONSTRUCTED owner admission.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class SoccerEventPageHostAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias Host = SoccerEventPageHost10868

    private func built(history: String?, markets: String?, admitted: SoccerPropReadingAdapter10868.Markets,
                       reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        let event = try F.detail(F.liveDetail)
        return Host.build(event: event, history: try history.map { try F.history($0) },
                          markets: try markets.map { try F.markets($0) }, admitted: admitted,
                          probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, now: F.liveNow,
                          reading: reading, calendar: F.pacific, locale: F.locale)
    }

    func testTheScreenAppliesToSoccerAlone() throws {
        XCTAssertTrue(Host.applies(try F.detail(F.liveDetail)))
        XCTAssertTrue(Host.applies(try F.detail(F.hullDetail)))
        // CONSTRUCTED: the live body with only `sport` changed.
        XCTAssertFalse(Host.applies(try F.detail(try F.edited(F.liveDetail, setting: ["sport": "icehockey_nhl"]))))
    }

    func testTheBuiltPageComposesEveryPartFromThePassedValues() throws {
        let page = try built(history: F.liveHistory, markets: F.liveMarkets, admitted: F.liveAdmission)
        let count = try XCTUnwrap(page.originals.catalogue?.originals.count)

        XCTAssertEqual(page.input.phase, .live)
        XCTAssertEqual(page.input.headline.home.primary, formatProbability(0.995))
        XCTAssertFalse(page.input.history.series[0].runs.isEmpty)
        XCTAssertEqual(page.input.stream.cards.map(\.id), ["goals", "both", "first", "halves"])
        XCTAssertEqual(page.input.copy.allPropsLabel, "\(SoccerPageInputAdapter10868.Words.allProps) · \(count)")
        XCTAssertEqual(page.originals.catalogue?.scope, "soccer:15325054:live:originals")
    }

    /// No history response: only the chart slot says so; the outcomes, stories
    /// and All props still compose.
    func testWithNoHistoryOnlyTheChartSlotIsUnavailable() throws {
        let page = try built(history: nil, markets: F.liveMarkets, admitted: F.liveAdmission)
        XCTAssertEqual(page.input.history.plotAbsence?.title, SoccerHistoryAdapter10868.Words.historyUnavailable)
        XCTAssertEqual(page.input.headline.home.primary, formatProbability(0.995))
        XCTAssertEqual(page.input.stream.cards.count, 4)
        XCTAssertNotNil(page.originals.catalogue)
        // The first-team card keeps its rows and drops only the checkpoints.
        XCTAssertNil(page.input.first?.scorePath)
    }

    func testWithNoMarketsResponseThePageStillHasItsHeadlineAndHistory() throws {
        let page = try built(history: F.liveHistory, markets: nil, admitted: F.liveAdmission)
        XCTAssertTrue(page.input.stream.cards.isEmpty)
        XCTAssertNil(page.originals.catalogue)
        XCTAssertNil(page.input.copy.allPropsLabel)
        XCTAssertEqual(page.input.headline.home.primary, formatProbability(0.995))
    }

    func testTheReadingStateReachesTheBuiltPageUnchanged() throws {
        let selection = OriginalMarketDetails9483.Selection(
            scope: "soccer:15325054:live:originals",
            identity: OriginalMarketDetails9483.Identity(source: "polymarket", market: "64353426", side: "242143189"))
        let page = try built(history: F.liveHistory, markets: F.liveMarkets, admitted: F.liveAdmission,
                             reading: Host.Reading(story: .halves, goal: "242143187", both: "242143190",
                                                   first: "244237965", half: "draw", selection: selection,
                                                   readerOpen: true, wide: true))
        XCTAssertEqual(page.input.stream.primary?.id, "halves")
        XCTAssertTrue(page.input.stream.readerOpen)
        XCTAssertEqual(page.input.goals?.selectedMilestoneID, "242143187")
        XCTAssertEqual(page.input.both?.selectedOutcomeID, "242143190")
        XCTAssertEqual(page.input.first?.selectedID, "244237965")
        XCTAssertEqual(page.input.halves?.selectedSeriesID, "draw")
        XCTAssertEqual(page.originals.selection, selection)
    }

    func testEachPresentedModeHasItsOwnIdentity() {
        XCTAssertEqual(Host.Presented(mode: .catalogue).id, "catalogue")
        XCTAssertEqual(Host.Presented(mode: .original).id, "original")
        XCTAssertEqual(Host.Presented(mode: .reader(.history)).id, "reader.history")
        XCTAssertEqual(Host.Presented(mode: .reader(.halves)).id, "reader.halves")
    }
}
