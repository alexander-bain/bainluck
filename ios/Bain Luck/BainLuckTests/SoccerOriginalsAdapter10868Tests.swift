import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — "All props", part eight: the original catalogue and each
/// original's Details, on the RETAINED REAL `/game-markets` bodies
/// (`SoccerRetained10868`). Membership and order are the catalogue's own
/// (`QuestionCatalog9483.build`, through the accepted hockey originals adapter).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class SoccerOriginalsAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias O = SoccerOriginalsAdapter10868
    private typealias D = OriginalMarketDetails9483

    private func group(_ detail: String, _ markets: String, now: Date) throws -> SoccerEventPageOriginals10868 {
        O.originals(try F.detail(detail), markets: try F.markets(markets), host: F.propHost(now), tint: .blue)
    }

    private func original(_ group: SoccerEventPageOriginals10868, market: String, side: String) throws -> D.Original {
        try XCTUnwrap(group.catalogue?.originals.first {
            $0.identity == D.Identity(source: "polymarket", market: market, side: side)
        })
    }

    private func clock(_ stamp: String, _ now: Date) -> String {
        SoccerMatchPageAdapter10868.clockWords(stamp.asDate!, host: F.propHost(now).words)
    }

    func testEveryServedOriginalIsListedOnceUnderOneScopePerPhase() throws {
        let live = try group(F.liveDetail, F.liveMarkets, now: F.liveNow)
        let originals = try XCTUnwrap(live.catalogue?.originals)
        XCTAssertEqual(live.catalogue?.scope, "soccer:15325054:live:originals")
        XCTAssertEqual(Set(originals.map(\.identity)).count, originals.count)
        XCTAssertEqual(live.heading, O.Words.heading)
        XCTAssertEqual(live.context, O.Words.context(originals.count))
        XCTAssertTrue(originals.allSatisfy { $0.mode == .comparison(.current) })
    }

    /// The served O/U 4.5 Over reads 15% on a sibling-capped clock. During play
    /// it is never the current chance; it is kept as the dated historical quote.
    func testDuringPlayASiblingClockedTotalsQuoteIsHistoricalNeverCurrent() throws {
        let live = try group(F.liveDetail, F.liveMarkets, now: F.liveNow)
        let over = try original(live, market: "64353425", side: "242143187")

        XCTAssertEqual(over.later, D.Reading.missing(AllMarketsCatalogView9483.noRecentPrice))
        XCTAssertEqual(over.about.historicalQuote?.text, formatProbability(0.15))
        XCTAssertEqual(over.about.historicalQuote?.recorded,
                       "\(clock("2026-10-12T12:55:39.585325+00:00", F.liveNow)) · Polymarket")
        // Once started, its pre-match chance is the stored pin for the same outcome.
        XCTAssertEqual(over.pregame, .value(
            formatProbability(0.13), placement: 0.13,
            provenance: "\(O.Words.savedBeforeStart) \(clock("2026-10-12T11:47:12.057085+00:00", F.liveNow)) · Polymarket"))
    }

    func testDuringPlayAnOwnClockedRecentQuoteIsTheCurrentChanceBesideItsPin() throws {
        let live = try group(F.liveDetail, F.liveMarkets, now: F.liveNow)
        let yes = try original(live, market: "64353426", side: "242143189")

        XCTAssertEqual(yes.later, D.Reading.value(
            formatProbability(0.49), placement: 0.49,
            provenance: "\(O.Words.recorded) \(clock("2026-10-12T12:54:58.549918+00:00", F.liveNow)) · Polymarket"))
        XCTAssertNil(yes.about.historicalQuote)
        XCTAssertEqual(yes.pregame.placement, 0.55)
    }

    func testAfterTheFinalEachOriginalShowsItsOwnVenueGradeNeverAChance() throws {
        let final = try group(F.finalDetail, F.finalMarkets, now: F.finalNow)
        let no = try original(final, market: "64353426", side: "242143190")
        let yes = try original(final, market: "64353426", side: "242143189")

        XCTAssertEqual(no.mode, .result)
        XCTAssertNil(no.later)
        XCTAssertEqual(no.grade, D.Grade(words: OutcomeVerdict.won.label, provenance: "Settled by Polymarket"))
        XCTAssertEqual(yes.grade, D.Grade(words: OutcomeVerdict.lost.label, provenance: "Settled by Polymarket"))
        // The retained final body serves no stored pin.
        XCTAssertEqual(no.pregame, .missing(O.Words.preMatchNotRecorded))
    }

    func testBeforeKickoffOnlyARecentOwnClockedQuoteIsThePreMatchChance() throws {
        let hull = try group(F.hullDetail, F.hullMarkets, now: F.hullNow)
        XCTAssertEqual(hull.catalogue?.scope, "soccer:15311089:before:originals")
        let yes = try original(hull, market: "63390540", side: "238847205")
        XCTAssertEqual(yes.mode, .pregame)
        XCTAssertEqual(yes.pregame, .value(
            formatProbability(0.535), placement: 0.535,
            provenance: "\(O.Words.recorded) \(clock("2026-10-11T04:37:08.994633+00:00", F.hullNow)) · Polymarket"))
        // First team to score, observed 23:32 the night before.
        let everton = try original(hull, market: "62939466", side: "238846913")
        XCTAssertEqual(everton.pregame, .missing(AllMarketsCatalogView9483.noRecentPrice))
    }

    func testAHeldSelectionPassesThroughUnchanged() throws {
        let selection = D.Selection(scope: "soccer:15325054:live:originals",
                                    identity: D.Identity(source: "polymarket", market: "64353426", side: "242143189"))
        let live = O.originals(try F.detail(F.liveDetail), markets: try F.markets(F.liveMarkets),
                               host: F.propHost(F.liveNow), tint: .blue, selection: selection)
        XCTAssertEqual(live.selection, selection)
    }

    func testNoMarketsResponseIsNoCatalogueAndSaysSo() throws {
        let none = O.originals(try F.detail(F.liveDetail), markets: nil, host: F.propHost(F.liveNow), tint: .blue)
        XCTAssertNil(none.catalogue)
        XCTAssertNil(none.context)
        XCTAssertEqual(none.emptyWords, O.Words.emptyWords)
    }
}
