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

    private func group(_ detail: String, _ markets: String, now: Date,
                       periods: Set<Int> = []) throws -> SoccerEventPageOriginals10868 {
        O.originals(try F.detail(detail), markets: try F.markets(markets), host: F.propHost(now), tint: .blue,
                    periodMarketIDs: periods)
    }

    /// The CONSTRUCTED owner admission's two half markets (63178219, 63178218).
    private var liveHalves: Set<Int> { Set(F.liveAdmission.halves.map(\.marketID)) }

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

    // MARK: - Half rows (Design, wave-1 review 2026-10-31)

    /// The REAL row: the first-half result, home (63178219 / 242338171), quoted
    /// 99.9% at 12:54:07 on its own clock after the half. Admitted as a half, it
    /// is never the current chance: the Details keep it only as the dated
    /// historical quote, and the later slot says the in-play chance is
    /// unavailable.
    func testDuringPlayAnAdmittedHalfsRecentQuoteIsADatedHistoricalQuoteNeverCurrent() throws {
        let live = try group(F.liveDetail, F.liveMarkets, now: F.liveNow, periods: liveHalves)
        let home = try original(live, market: "63178219", side: "242338171")

        XCTAssertEqual(home.mode, .comparison(.current))
        XCTAssertEqual(home.later, D.Reading.missing(O.Words.inPlayUnavailable))
        XCTAssertEqual(home.about.historicalQuote, D.HistoricalQuote(
            text: formatProbability(0.999),
            recorded: "\(clock("2026-10-12T12:54:07.360375+00:00", F.liveNow)) · Polymarket"))
        XCTAssertNil(home.grade)

        // The second half's rows (quoted 12:36–12:37) are held the same way.
        let secondHome = try original(live, market: "63178218", side: "246041831")
        XCTAssertEqual(secondHome.later, D.Reading.missing(O.Words.inPlayUnavailable))
        XCTAssertEqual(secondHome.about.historicalQuote?.text, formatProbability(0.3881))
    }

    /// Control, and the named dependency: which rows are about one half is the
    /// owner's admission, never the title. With no admission the same REAL row
    /// reads as a full-match quote — the reason the host passes its half
    /// markets to All props.
    func testWithoutTheOwnersHalfAdmissionTheRowIsNotKnownToBeAHalf() throws {
        let live = try group(F.liveDetail, F.liveMarkets, now: F.liveNow)
        let home = try original(live, market: "63178219", side: "242338171")
        XCTAssertEqual(home.later, D.Reading.value(
            formatProbability(0.999), placement: 0.999,
            provenance: "\(O.Words.recorded) \(clock("2026-10-12T12:54:07.360375+00:00", F.liveNow)) · Polymarket"))
        // A full-match row is unaffected by the half admission.
        let yes = try original(try group(F.liveDetail, F.liveMarkets, now: F.liveNow, periods: liveHalves),
                               market: "64353426", side: "242143189")
        XCTAssertEqual(yes.later?.placement, 0.49)
    }

    /// CONSTRUCTED: the first-half home row with only its `observed_at` set to
    /// null. A half's quote is shown only when dated, so none is kept.
    func testAnUndatedHalfQuoteKeepsNoHistoricalQuote() throws {
        let body = try F.editedRow(F.liveMarkets, outcomeID: 242338171, setting: ["observed_at": NSNull()])
        let live = try group(F.liveDetail, body, now: F.liveNow, periods: liveHalves)
        let home = try original(live, market: "63178219", side: "242338171")
        XCTAssertEqual(home.later, D.Reading.missing(AllMarketsCatalogView9483.noRecentPrice))
        XCTAssertNil(home.about.historicalQuote)
    }

    /// CONSTRUCTED: the first-half home row carrying the final body's grade.
    /// During play a graded half has no chance and keeps no quote; after the
    /// final (REAL final body) its grade is the venue's, admitted or not.
    func testAGradedHalfHasNoChanceAndAfterTheFinalShowsItsVenueGrade() throws {
        let graded = try F.graded(F.liveMarkets, [242338171: true])
        let live = try group(F.liveDetail, graded, now: F.liveNow, periods: liveHalves)
        let home = try original(live, market: "63178219", side: "242338171")
        XCTAssertEqual(home.later, D.Reading.missing(O.Words.settledNoChance))
        XCTAssertNil(home.about.historicalQuote)

        let final = try group(F.finalDetail, F.finalMarkets, now: F.finalNow, periods: liveHalves)
        let finalHome = try original(final, market: "63178219", side: "242338171")
        XCTAssertEqual(finalHome.grade, D.Grade(words: OutcomeVerdict.won.label, provenance: "Settled by Polymarket"))
    }

    func testAfterTheFinalEachOriginalShowsItsOwnVenueGradeNeverAChance() throws {
        let final = try group(F.finalDetail, F.finalMarkets, now: F.finalNow)
        let no = try original(final, market: "64353426", side: "242143190")
        let yes = try original(final, market: "64353426", side: "242143189")

        XCTAssertEqual(no.mode, .result)
        XCTAssertNil(no.later)
        XCTAssertEqual(no.grade, D.Grade(words: OutcomeVerdict.won.label, provenance: "Settled by Polymarket"))
        XCTAssertEqual(yes.grade, D.Grade(words: OutcomeVerdict.lost.label, provenance: "Settled by Polymarket"))
        // The retained final body serves no stored pin, and its comparison says
        // only `not_quoted` — not that none was recorded: unavailable.
        XCTAssertEqual(no.pregame, .missing(O.Words.preMatchUnavailable))
    }

    // MARK: - Baseline admission (Design, baseline-admission review 2026-10-31)

    /// CONSTRUCTED live variant: the Hull detail with only `status` changed to
    /// `live`. The first-team option's `no_pregame_pin` is the producer's own
    /// statement: "not recorded". The same option with only `comparison` served
    /// null: "unavailable".
    func testNotRecordedOnlyWhereTheProducerSaysNoPinWasRecorded() throws {
        let live = try F.edited(F.hullDetail, setting: ["status": "live"])
        let said = try original(try group(live, F.hullMarkets, now: F.hullNow), market: "62939466", side: "238846913")
        XCTAssertEqual(said.pregame, .missing(O.Words.preMatchNotRecorded))

        let silent = try F.editedOption(F.hullMarkets, question: "m:62939466", option: "o:238846913",
                                        setting: ["comparison": NSNull()])
        let unsaid = try original(try group(live, silent, now: F.hullNow), market: "62939466", side: "238846913")
        XCTAssertEqual(unsaid.pregame, .missing(O.Words.preMatchUnavailable))
    }

    /// CONSTRUCTED: the final No option with only a `pregame_reading` added —
    /// this outcome, basis `pregame_pin`, 0.45 at 11:50 — is the production
    /// helper's pin; the same reading naming the Yes outcome is never borrowed.
    func testDetailsReadThePinThroughTheProductionHelper() throws {
        func reading(_ outcome: Int) -> [String: Any] {
            ["state": "available", "reason": NSNull(), "probability": 0.45,
             "observed_at": "2026-10-12T11:50:00+00:00", "basis": "pregame_pin", "outcome_id": outcome]
        }
        let own = try F.editedOption(F.finalMarkets, question: "m:64353426", option: "o:242143190",
                                     setting: ["pregame_reading": reading(242143190)])
        let no = try original(try group(F.finalDetail, own, now: F.finalNow), market: "64353426", side: "242143190")
        XCTAssertEqual(no.pregame, .value(
            formatProbability(0.45), placement: 0.45,
            provenance: "\(O.Words.savedBeforeStart) \(clock("2026-10-12T11:50:00+00:00", F.finalNow)) · Polymarket"))

        let borrowed = try F.editedOption(F.finalMarkets, question: "m:64353426", option: "o:242143190",
                                          setting: ["pregame_reading": reading(242143189)])
        let refused = try original(try group(F.finalDetail, borrowed, now: F.finalNow), market: "64353426", side: "242143190")
        XCTAssertEqual(refused.pregame, .missing(O.Words.preMatchUnavailable))
    }

    /// CONTROLS, unknown contract and foreign scope: the live body with only
    /// the matrix `contract`, or only its `display_scope`, changed. No pin is
    /// read, and the whole catalogue is still listed — same identities, same
    /// order, same modes.
    func testAnUnsupportedMatrixReadsNoPinButEveryOriginalIsStillListed() throws {
        let real = try XCTUnwrap(try group(F.liveDetail, F.liveMarkets, now: F.liveNow).catalogue)
        for setting in [["contract": "10238.v2"], ["display_scope": "series"]] as [[String: Any]] {
            let body = try F.editedMatrix(F.liveMarkets, setting: setting)
            let unsupported = try group(F.liveDetail, body, now: F.liveNow)
            let catalogue = try XCTUnwrap(unsupported.catalogue)
            XCTAssertEqual(catalogue.originals.map(\.identity), real.originals.map(\.identity), "\(setting)")
            XCTAssertEqual(catalogue.originals.map(\.mode), real.originals.map(\.mode), "\(setting)")
            XCTAssertEqual(unsupported.context, O.Words.context(real.originals.count))
            let yes = try original(unsupported, market: "64353426", side: "242143189")
            XCTAssertEqual(yes.pregame, .missing(O.Words.preMatchUnavailable), "\(setting)")
            // The later reading is the catalogue's own, untouched by the matrix.
            XCTAssertEqual(yes.later?.placement, 0.49)
        }
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
