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

    private func built(detail: String = F.liveDetail, history: String?, markets: String?,
                       admitted: SoccerPropReadingAdapter10868.Markets, now: Date = F.liveNow,
                       halvesAdmission: SoccerPageInputAdapter10868.HalvesAdmission = .routeDefault,
                       reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        let event = try F.detail(detail)
        return Host.build(event: event, history: try history.map { try F.history($0) },
                          markets: try markets.map { try F.markets($0) }, admitted: admitted,
                          halvesAdmission: halvesAdmission,
                          probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, now: now,
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
        // The live route carries no half-by-half card by default.
        XCTAssertEqual(page.input.stream.cards.map(\.id), ["goals", "both", "first"])
        XCTAssertEqual(page.input.copy.allPropsLabel, "\(SoccerPageInputAdapter10868.Words.allProps) · \(count)")
        XCTAssertEqual(page.originals.catalogue?.scope, "soccer:15325054:live:originals")
    }

    /// No history response: only the chart slot says so; the outcomes, stories
    /// and All props still compose.
    func testWithNoHistoryOnlyTheChartSlotIsUnavailable() throws {
        let page = try built(history: nil, markets: F.liveMarkets, admitted: F.liveAdmission)
        XCTAssertEqual(page.input.history.plotAbsence?.title, SoccerHistoryAdapter10868.Words.historyUnavailable)
        XCTAssertEqual(page.input.headline.home.primary, formatProbability(0.995))
        XCTAssertEqual(page.input.stream.cards.count, 3)
        XCTAssertNotNil(page.originals.catalogue)
        // The first-team card keeps its rows and drops only the checkpoints.
        XCTAssertNil(page.input.first?.scorePath)
    }

    /// CONSTRUCTED: the live history and markets with only `event_id` changed to
    /// a different event's id. Neither the chart, the score path, the stories nor
    /// All props read them; the match's own headline still composes.
    func testAnotherEventsHistoryAndMarketsNeverReachThisMatch() throws {
        let foreignHistory = try F.edited(F.liveHistory, setting: ["event_id": 15325055])
        let foreignMarkets = try F.edited(F.liveMarkets, setting: ["event_id": 15325055])
        let page = try built(history: foreignHistory, markets: foreignMarkets, admitted: F.liveAdmission)
        let event = try F.detail(F.liveDetail)
        XCTAssertEqual(page.input.history, SoccerHistoryAdapter10868.unavailable(event: event, phase: .live))
        XCTAssertTrue(page.input.stream.cards.isEmpty)
        XCTAssertNil(page.originals.catalogue)
        XCTAssertNil(page.input.copy.allPropsLabel)
        XCTAssertNil(page.input.first?.scorePath)
        XCTAssertEqual(page.input.headline.home.primary, formatProbability(0.995))
        // Own history beside foreign markets: the chart stays, the market parts go.
        let mixed = try built(history: F.liveHistory, markets: foreignMarkets, admitted: F.liveAdmission)
        XCTAssertFalse(mixed.input.history.series[0].runs.isEmpty)
        XCTAssertNil(mixed.originals.catalogue)
    }

    func testWithNoMarketsResponseThePageStillHasItsHeadlineAndHistory() throws {
        let page = try built(history: F.liveHistory, markets: nil, admitted: F.liveAdmission)
        XCTAssertTrue(page.input.stream.cards.isEmpty)
        XCTAssertNil(page.originals.catalogue)
        XCTAssertNil(page.input.copy.allPropsLabel)
        XCTAssertEqual(page.input.headline.home.primary, formatProbability(0.995))
    }

    /// A journey/replay-style host admits the half-by-half card explicitly, so
    /// the held half selection has a card to reach.
    func testTheReadingStateReachesTheBuiltPageUnchanged() throws {
        let selection = OriginalMarketDetails9483.Selection(
            scope: "soccer:15325054:live:originals",
            identity: OriginalMarketDetails9483.Identity(source: "polymarket", market: "64353426", side: "242143189"))
        let page = try built(history: F.liveHistory, markets: F.liveMarkets, admitted: F.liveAdmission,
                             halvesAdmission: .explicit,
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

    // MARK: - The half-by-half card's route-phase membership (Design, wave-1 review)

    /// By default the host follows the approved membership: no half-by-half card
    /// during play, the card after the final; a held half story falls back to
    /// the first offered card. An explicit admission is the host's own context.
    func testTheHostOffersTheHalvesCardAfterTheFinalByDefaultAndOtherwiseOnlyWhenAdmitted() throws {
        let live = try built(history: F.liveHistory, markets: F.liveMarkets, admitted: F.liveAdmission,
                             reading: Host.Reading(story: .halves))
        XCTAssertNil(live.input.halves)
        XCTAssertEqual(live.input.stream.primary?.id, "goals")

        let final = try built(detail: F.finalDetail, history: F.finalHistory, markets: F.finalMarkets,
                              admitted: F.liveAdmission, now: F.finalNow)
        XCTAssertNotNil(final.input.halves)
        XCTAssertTrue(final.input.stream.cards.map(\.id).contains("halves"))

        let admitted = try built(history: F.liveHistory, markets: F.liveMarkets, admitted: F.liveAdmission,
                                 halvesAdmission: .explicit)
        XCTAssertEqual(admitted.input.stream.cards.map(\.id), ["goals", "both", "first", "halves"])
    }

    /// The host tells All props which markets are halves (its admission), so
    /// the REAL first-half result row at 99.9% (63178219 / 242338171) is kept
    /// only as a dated historical quote during play — never a current chance.
    func testTheHostPassesItsHalfMarketsToAllProps() throws {
        let page = try built(history: F.liveHistory, markets: F.liveMarkets, admitted: F.liveAdmission)
        let home = try XCTUnwrap(page.originals.catalogue?.originals.first {
            $0.identity == OriginalMarketDetails9483.Identity(source: "polymarket", market: "63178219", side: "242338171")
        })
        XCTAssertEqual(home.later, OriginalMarketDetails9483.Reading.missing(SoccerOriginalsAdapter10868.Words.inPlayUnavailable))
        XCTAssertEqual(home.about.historicalQuote?.text, formatProbability(0.999))
    }

    func testEachPresentedModeHasItsOwnIdentity() {
        XCTAssertEqual(Host.Presented(mode: .catalogue).id, "catalogue")
        XCTAssertEqual(Host.Presented(mode: .original).id, "original")
        XCTAssertEqual(Host.Presented(mode: .reader(.history)).id, "reader.history")
        XCTAssertEqual(Host.Presented(mode: .reader(.halves)).id, "reader.halves")
    }
}
