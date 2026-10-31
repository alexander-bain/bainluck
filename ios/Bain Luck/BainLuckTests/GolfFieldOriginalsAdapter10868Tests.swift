import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf tournament adapter, part six (the originals behind the
/// finish and contenders cards and their Details) and the host glue's Details
/// routing and return context, on the retained bodies in
/// `GolfFieldRetainedBodies10868`.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no Swift
/// parse, no XCTest).
///
/// RETAINED (decoded through the production models, `.convertFromSnakeCase`):
///   - DP World India Championship Winner / Top 5 / Top 10 / Top 20 / Make the
///     Cut (65391342–65391346, `status: open`, captured Oct 12 before the Oct 15
///     listed start, DataGolf, `bookmakers: ["datagolf_model"]`);
///   - Baycurrent Classic Winner 64266833 (`status: resolved`, no grade on any
///     row), its three-golfer history and Michael Brennan's history.
///
/// CONSTRUCTED, and named again where used:
///   - the reader's calendar (Pacific, en_US) and every `now`;
///   - THE HOST'S JOIN from each Winner outcome to its finish outcomes (no
///     production owner serves it; the ids are the ones the retained markets
///     serve for that golfer, as in the finish tests);
///   - the recorded-phase clock: India read after its listed start, over the
///     retained pre-start captures. No live specimen exists, so nothing here
///     credits live delivery or a real recorded estimate;
///   - single-key edits of a retained body (a grade, a settlement contract, an
///     id, a source, a `market_id`, `bookmakers`), and a missing finish market.
///
/// Mutation controls (each would fail a named test): reading the untimed
/// `opening_probability` (Noren); reading `Field.later` or a comparison before
/// the start (the before catalogue); the superseded all-slot gate (missing Top 5);
/// passing a placement (D1 asserts); choosing the first of two equal identities
/// (duplicates); parsing an unavailable slot id into a market (missing Top 5);
/// Done returning to the page from a card's Details, or a dismissal resetting
/// the golfer or finish (return context); re-scoping a held selection to the new
/// phase (phase change); opening Details before, or without, the hold (hold order).
@MainActor
final class GolfFieldOriginalsAdapter10868Tests: XCTestCase {
    private typealias O = GolfFieldOriginalsAdapter10868
    private typealias D = OriginalMarketDetails9483
    private typealias F = GolfFieldFinishAdapter10868
    private typealias A = GolfFieldPageAdapter10868
    private typealias Host = GolfFieldEventPageHost10868
    private typealias R = GolfFieldRetainedBodies10868

    /// CONSTRUCTED reader clocks.
    private static let indiaNow = "2026-10-12T23:28:52Z"
    private static let indiaRecordedNow = "2026-10-15T06:00:00Z"
    private static let finalNow = "2026-10-12T23:56:42Z"

    private static let beforeScope = "golf:65391342:before:originals"
    private static let recordedScope = "golf:65391342:recorded:originals"
    private static let finalScope = "golf:64266833:final:originals"

    /// CONSTRUCTED host join: Winner outcome id → that market's outcome id.
    private static let top5Join = [R.rory: 246352498, R.sharma: 246352530, R.noren: 245904764]
    private static let top10Join = [R.rory: 246352556, R.sharma: 246352588, R.noren: 245904896]
    private static let top20Join = [R.rory: 246352614, R.sharma: 246352646, R.noren: 245905028]
    private static let makeCutJoin = [R.rory: 246352672, R.sharma: 246352704, R.noren: 245905160]

    /// RETAINED finish markets with the CONSTRUCTED join.
    private func indiaLegs() throws -> F.Legs {
        try indiaLegs(top5: R.indiaTop5, top10: R.indiaTop10)
    }

    /// The same, with the Top 5 / Top 10 body supplied by the caller; nil drops that market.
    private func indiaLegs(top5: String?, top10: String?) throws -> F.Legs {
        F.Legs(top5: try top5.map { F.Leg(market: try R.market($0), outcomes: Self.top5Join) },
               top10: try top10.map { F.Leg(market: try R.market($0), outcomes: Self.top10Join) },
               top20: F.Leg(market: try R.market(R.indiaTop20), outcomes: Self.top20Join),
               makeCut: F.Leg(market: try R.market(R.indiaMakeCut), outcomes: Self.makeCutJoin))
    }

    /// One host pass: the page input and the originals from the same values.
    @MainActor
    private struct Built {
        let input: GolfEventPageInput10868
        let originals: O.Originals
        /// The finish the page actually mounts.
        var finish: GolfFinishExpectationInput10868? { GolfEventPageModel10868(input).finish }
    }

    private func built(_ winnerJSON: String, history historyJSON: String? = nil, legs held: F.Legs? = nil, selected: Int?,
                       selectedFinish: String? = nil, now: String) throws -> Built {
        let legs = held ?? F.Legs()
        let winner = try R.market(winnerJSON)
        let history = try historyJSON.map { try R.history($0) }
        let host = R.host(now)
        let input = Host.build(winner: winner, history: history, legs: legs,
                               cohort: selected.map { [$0] } ?? [],
                               choice: Host.Choice(selected: selected, selectedFinish: selectedFinish),
                               now: host.now, calendar: host.calendar, locale: host.locale)
        let originals = Host.originals(winner: winner, history: history, legs: legs,
                                       now: host.now, calendar: host.calendar, locale: host.locale)
        return Built(input: input, originals: originals)
    }

    private func content(_ built: Built, _ selection: D.Selection?) -> D.Content? {
        D.content(catalogue: built.originals.catalogue, selection: selection)
    }

    private func identity(_ market: Int, _ outcome: Int) -> D.Identity {
        D.Identity(source: "datagolf", market: String(market), side: String(outcome))
    }

    private func updated(_ stamp: String, _ now: String) -> String {
        "Updated \(A.clockWords(stamp.asDate!, host: R.host(now))) · DataGolf"
    }

    private func recorded(_ stamp: String, _ now: String) -> String {
        "Recorded \(A.clockWords(stamp.asDate!, host: R.host(now))) · DataGolf"
    }

    // MARK: - Before the start

    func testTheBeforeCatalogueHoldsEveryOriginalOnceWithItsExactServedIdentity() throws {
        // RETAINED: the five India markets. CONSTRUCTED: the clock and the join.
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        let catalogue = b.originals.catalogue
        XCTAssertEqual(catalogue.scope, Self.beforeScope)
        let expected: [D.Identity] = [
            identity(65391342, R.rory), identity(65391342, R.sharma),
            identity(65391342, R.jaglan), identity(65391342, R.noren),
            identity(65391343, 246352498), identity(65391343, 246352530), identity(65391343, 245904764),
            identity(65391344, 246352556), identity(65391344, 246352588), identity(65391344, 245904896),
            identity(65391345, 246352614), identity(65391345, 246352646), identity(65391345, 245905028),
            identity(65391346, 246352672), identity(65391346, 246352704), identity(65391346, 245905160),
        ]
        XCTAssertEqual(catalogue.originals.map(\.identity), expected,
                       "the Winner in served order, then each finish market once, in served order")
        XCTAssertEqual(b.originals.keys.map(\.identity), expected, "keys and originals line up one to one")
        XCTAssertEqual(b.originals.keys.first?.finishID, "datagolf|65391342|246352440")
        XCTAssertEqual(b.originals.keys.compactMap(\.ref).map(\.outcomeID),
                       [R.rory, R.sharma, R.jaglan, R.noren].map { String($0) },
                       "contenders refs exist for Winner originals only")
        for original in catalogue.originals {
            XCTAssertEqual(original.mode, .pregame, original.outcome)
            XCTAssertNil(original.later, "nothing recorded since the start is read before it")
            XCTAssertNil(original.grade, original.outcome)
            XCTAssertNil(original.pregame.placement, "no 0–100% Details rail (D1)")
            XCTAssertNil(original.about.historicalQuote, original.outcome)
            XCTAssertEqual(original.beforeLabel, "Before start")
        }
    }

    func testRorysFiveFinishSlotsAndHisContenderRefOpenTheirOwnOriginals() throws {
        // RETAINED: the five India markets. CONSTRUCTED: the clock and the join.
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        let finish = try XCTUnwrap(b.finish)
        let markets = [65391342, 65391343, 65391344, 65391345, 65391346]
        let outcomes = [R.rory, 246352498, 246352556, 246352614, 246352672]
        let titles = ["DP World India Championship - Winner", "DP World India Championship - Top 5 Finish",
                      "DP World India Championship - Top 10 Finish", "DP World India Championship - Top 20 Finish",
                      "DP World India Championship - Make the Cut"]
        let figures = ["13%", "35%", "50%", "67%", "90%"]
        let stamps = ["2026-10-12T23:11:05.501054+00:00", "2026-10-12T23:11:06.747890+00:00",
                      "2026-10-12T23:11:07.952964+00:00", "2026-10-12T23:11:09.073291+00:00",
                      "2026-10-12T23:11:10.724619+00:00"]
        XCTAssertEqual(finish.slots.count, 5)
        XCTAssertTrue(O.finishDetailsOffered(finish, originals: b.originals))
        for (index, slot) in finish.slots.enumerated() {
            let expected = D.Selection(scope: Self.beforeScope, identity: identity(markets[index], outcomes[index]))
            XCTAssertEqual(O.destination(finishID: slot.selection, finish: finish, originals: b.originals),
                           .original(expected), slot.name)
            let shown = try XCTUnwrap(content(b, expected), slot.name)
            XCTAssertEqual(shown.title, titles[index])
            XCTAssertEqual(shown.outcome, "Rory McIlroy")
            XCTAssertEqual(shown.readings.map(\.label), ["Before start"])
            XCTAssertEqual(shown.readings.map(\.text), [figures[index]])
            XCTAssertEqual(shown.readings.map(\.provenance), [updated(stamps[index], Self.indiaNow)],
                           "each original keeps its own stamp")
            XCTAssertEqual(shown.readings.first?.text, slot.before?.text, "the card and its Details read alike")
            XCTAssertEqual(shown.readings.first?.provenance, slot.before?.accessibilityDetail)
            XCTAssertNil(shown.result, "no result before the start")
            XCTAssertTrue(shown.marks.isEmpty, "no rail mark (D1)")
        }

        // The contenders card's Details: Rory's exact Winner original.
        let contenders = try XCTUnwrap(GolfEventPageModel10868(b.input).contenders)
        let ref = try XCTUnwrap(FieldOutlookModel10868(contenders).detailsRef(canOpen: true))
        XCTAssertEqual(ref, FieldChooserOriginalRef10868(scope: "golf:65391342:before", source: "datagolf",
                                                          marketID: "65391342", outcomeID: String(R.rory)))
        XCTAssertTrue(O.contendersDetailsOffered(contenders, originals: b.originals))
        XCTAssertEqual(O.destination(ref: ref, originals: b.originals),
                       .original(D.Selection(scope: Self.beforeScope, identity: identity(65391342, R.rory))))
    }

    func testAMissingPriceIsNeverTheOpeningAndARealZeroIsAValue() throws {
        // RETAINED: Noren is served with no price (an untimed opening 0.0283 beside
        // it); Jaglan's Winner price is a real 0. CONSTRUCTED: the clock and the join.
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.noren, now: Self.indiaNow)
        let noren = try XCTUnwrap(content(b, D.Selection(scope: Self.beforeScope, identity: identity(65391342, R.noren))))
        XCTAssertEqual(noren.readings.map(\.text), ["Before-start chance not recorded"])
        XCTAssertEqual(noren.readings.map(\.isValue), [false])
        XCTAssertEqual(noren.readings.map(\.provenance), [nil], "a missing reading has no clock")

        let jaglan = try XCTUnwrap(content(b, D.Selection(scope: Self.beforeScope, identity: identity(65391342, R.jaglan))))
        XCTAssertEqual(jaglan.readings.map(\.text), [formatProbability(0)])
        XCTAssertEqual(jaglan.readings.map(\.isValue), [true], "a real 0 is a value, never the missing words")
        XCTAssertEqual(jaglan.readings.map(\.provenance), [updated("2026-10-12T23:11:05.501054+00:00", Self.indiaNow)])

        // Every held market serves Noren, so each finish opens his own original — all missing.
        let finish = try XCTUnwrap(b.finish)
        XCTAssertEqual(finish.slots.count, 5)
        for slot in finish.slots {
            guard case .original(let selection) = O.destination(finishID: slot.selection, finish: finish,
                                                                originals: b.originals) else {
                return XCTFail("\(slot.name) must open its own original")
            }
            XCTAssertEqual(content(b, selection)?.readings.map(\.text), ["Before-start chance not recorded"], slot.name)
        }
    }

    func testDetailsNameTheDataGolfModelAndTheServedIds() throws {
        // RETAINED: the India Top 5 body. CONSTRUCTED: the clock and the join.
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        let selection = D.Selection(scope: Self.beforeScope, identity: identity(65391343, 246352498))
        let shown = try XCTUnwrap(content(b, selection))
        XCTAssertEqual(shown.about, [
            D.Row(label: "Market", value: "DP World India Championship - Top 5 Finish"),
            D.Row(label: "Outcome", value: "Rory McIlroy"),
            D.Row(label: "Source", value: "Probabilities from the DataGolf model"),
            D.Row(label: "Market ID", value: "65391343"),
            D.Row(label: "Outcome ID", value: "246352498"),
        ], "a model estimate is named as one (D2)")
        XCTAssertEqual(shown.rules, .unavailable("Rules unavailable"))
        XCTAssertEqual(shown.readings.first?.provenance, updated("2026-10-12T23:11:06.747890+00:00", Self.indiaNow))

        // CONSTRUCTED: the same Top 5 body served with no contributors — the market's own source name.
        let bare = try R.edited(R.indiaTop5, ["bookmakers"], to: [String]())
        let unnamed = try built(R.indiaWin, legs: try indiaLegs(top5: bare, top10: R.indiaTop10), selected: R.rory, now: Self.indiaNow)
        XCTAssertEqual(content(unnamed, selection)?.about.first(where: { $0.label == "Source" })?.value, "DataGolf")
    }

    // MARK: - During play

    func testDuringPlayDetailsCompareTheBeforeReadingWithTheRecordedChanceAndNeverPromoteAPreStartQuote() throws {
        // CONSTRUCTED clock after the listed start, over RETAINED pre-start captures:
        // no live delivery is credited, and no recorded estimate exists to show.
        let top5 = "datagolf|65391343|246352498"
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, selectedFinish: top5,
                          now: Self.indiaRecordedNow)
        let finish = try XCTUnwrap(b.finish)
        XCTAssertEqual(finish.phase, .recorded)
        XCTAssertEqual(finish.sourceAction(canOpenDetails: true), .details(top5), "the selected finish's time & source")
        XCTAssertTrue(O.finishDetailsOffered(finish, originals: b.originals))
        let selection = D.Selection(scope: Self.recordedScope, identity: identity(65391343, 246352498))
        XCTAssertEqual(O.destination(finishID: top5, finish: finish, originals: b.originals), .original(selection))
        let shown = try XCTUnwrap(content(b, selection))
        XCTAssertEqual(shown.readings.map(\.label), ["Before start", "Recorded chance"])
        XCTAssertEqual(shown.readings.map(\.text), ["35%", "Chance since the start not recorded"])
        XCTAssertEqual(shown.readings.map(\.isValue), [true, false])
        XCTAssertEqual(shown.readings.map(\.provenance),
                       [updated("2026-10-12T23:11:06.747890+00:00", Self.indiaRecordedNow), nil])
        XCTAssertNil(shown.result)
        XCTAssertNil(GolfEventPageModel10868(b.input).contenders, "the contenders card is before the start only")
        XCTAssertFalse(O.contendersDetailsOffered(GolfEventPageModel10868(b.input).contenders, originals: b.originals))
    }

    // MARK: - Final

    func testAtTheFinalAnUngradedRowIsResultUnavailableNeverLostAndTheBeforeReadingKeepsItsOwnClock() throws {
        // RETAINED: the resolved Baycurrent Winner (no grade on any row) and Brennan's history.
        let b = try built(R.baycurrentWinner, history: R.brennanHistory, selected: R.brennan, now: Self.finalNow)
        XCTAssertEqual(b.originals.catalogue.scope, Self.finalScope)
        let brennan = D.Selection(scope: Self.finalScope, identity: identity(64266833, R.brennan))
        let original = try XCTUnwrap(D.original(in: b.originals.catalogue, selection: brennan))
        XCTAssertEqual(original.mode, .result)
        XCTAssertNil(original.grade, "resolved, but no grade is served")
        let shown = try XCTUnwrap(content(b, brennan))
        XCTAssertEqual(shown.readings.map(\.label), ["Before start"])
        XCTAssertEqual(shown.readings.map(\.text), ["3%"],
                       "his last observation before the listed start — never the 06:41Z 1.0 or the 22:08Z re-served row")
        XCTAssertEqual(shown.readings.map(\.provenance),
                       [recorded("2026-10-06T13:08:40.644152+00:00", Self.finalNow)])
        XCTAssertEqual(shown.result, D.ShownResult(words: "Result unavailable", provenance: nil))

        // RETAINED: Fishburn has no price and no line here — missing, and unavailable, never 0% or Lost.
        let fishburn = try XCTUnwrap(content(b, D.Selection(scope: Self.finalScope, identity: identity(64266833, R.fishburn))))
        XCTAssertEqual(fishburn.readings.map(\.text), ["Before-start chance not recorded"])
        XCTAssertEqual(fishburn.readings.map(\.isValue), [false])
        XCTAssertEqual(fishburn.result?.words, "Result unavailable")

        // CONSTRUCTED: Brennan's row graded won (`is_winner` + `resolution_source`).
        var won = try R.edited(R.baycurrentWinner, ["outcomes", 3, "is_winner"], to: true)
        won = try R.edited(won, ["outcomes", 3, "resolution_source"], to: "datagolf_settlement")
        let graded = try built(won, history: R.brennanHistory, selected: R.brennan, now: Self.finalNow)
        XCTAssertEqual(content(graded, brennan)?.result,
                       D.ShownResult(words: "Won", provenance: "Settlement time unknown"))
        XCTAssertEqual(content(graded, brennan)?.readings, shown.readings, "a grade never replaces the before reading")

        // CONSTRUCTED: Schauffele's row graded lost (the same two keys).
        var lost = try R.edited(R.baycurrentWinner, ["outcomes", 0, "is_winner"], to: false)
        lost = try R.edited(lost, ["outcomes", 0, "resolution_source"], to: "datagolf_settlement")
        let lostBuilt = try built(lost, history: R.baycurrentHistory, selected: R.schauffele, now: "2026-10-12T23:55:18Z")
        let schauffele = D.Selection(scope: Self.finalScope, identity: identity(64266833, R.schauffele))
        XCTAssertEqual(content(lostBuilt, schauffele)?.result?.words, "Lost")

        // CONSTRUCTED: Brennan's row served an unknown settlement contract — "Result
        // unknown", distinct from Lost and from "Result unavailable".
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(R.baycurrentWinner.utf8)) as? [String: Any])
        var rows = try XCTUnwrap(object["outcomes"] as? [[String: Any]])
        rows[3]["settlement_display"] = ["verdict": "unknown", "basis": "nonterminal_stored_price"]
        let unknown = try built(try R.edited(R.baycurrentWinner, ["outcomes"], to: rows), history: R.brennanHistory,
                                selected: R.brennan, now: Self.finalNow)
        XCTAssertEqual(content(unknown, brennan)?.result,
                       D.ShownResult(words: "Result unknown", provenance: "Settlement time unknown"))
    }

    // MARK: - D3: one absent finish

    func testAMissingTop5KeepsEveryOtherFinishOpenAndNamesItsOwnAbsence() throws {
        // CONSTRUCTED: the host holds no Top 5 market. RETAINED: Winner, Top 10, Top 20, Make the Cut.
        let b = try built(R.indiaWin, legs: try indiaLegs(top5: nil, top10: R.indiaTop10), selected: R.rory, now: Self.indiaNow)
        let finish = try XCTUnwrap(b.finish)
        XCTAssertEqual(finish.top5.selection, "golf.finish.top5.unavailable")
        XCTAssertTrue(O.finishDetailsOffered(finish, originals: b.originals), "one absent finish never closes the others (D3)")
        XCTAssertNotNil(Host.finishDetails(b.input, originals: b.originals, hold: nil, open: { _ in }))
        XCTAssertEqual(O.destination(finishID: finish.win.selection, finish: finish, originals: b.originals),
                       .original(D.Selection(scope: Self.beforeScope, identity: identity(65391342, R.rory))))
        XCTAssertEqual(O.destination(finishID: finish.top10.selection, finish: finish, originals: b.originals),
                       .original(D.Selection(scope: Self.beforeScope, identity: identity(65391344, 246352556))))

        XCTAssertEqual(finish.action(for: finish.top5, canSelect: true, canOpenDetails: true),
                       .details("golf.finish.top5.unavailable"), "the card still draws the Top 5 tap")
        let top5 = O.destination(finishID: "golf.finish.top5.unavailable", finish: finish, originals: b.originals)
        XCTAssertEqual(top5, .notSupplied(finish: "Top 5", slot: "golf.finish.top5.unavailable", scope: Self.beforeScope))
        XCTAssertEqual(O.shown(top5, finish: finish, originals: b.originals), .notSupplied("Top 5 original not supplied"))
        XCTAssertNil(O.selection(finishID: "golf.finish.top5.unavailable", in: b.originals),
                     "an unavailable slot id is never parsed into a selection")
        XCTAssertFalse(b.originals.catalogue.originals.contains { $0.identity.market == "65391343" },
                       "no Top 5 original is manufactured")
        XCTAssertEqual(b.originals.catalogue.originals.count, 13)

        // After play, the same rule. RETAINED: Baycurrent, no finish markets held.
        let after = try built(R.baycurrentWinner, history: R.brennanHistory, selected: R.brennan, now: Self.finalNow)
        let afterFinish = try XCTUnwrap(after.finish)
        XCTAssertNil(afterFinish.makeCut, "no fifth slot is invented")
        XCTAssertTrue(O.finishDetailsOffered(afterFinish, originals: after.originals))
        let top20 = O.destination(finishID: afterFinish.top20.selection, finish: afterFinish, originals: after.originals)
        XCTAssertEqual(O.shown(top20, finish: afterFinish, originals: after.originals),
                       .notSupplied("Top 20 original not supplied"))
        XCTAssertEqual(O.destination(finishID: afterFinish.win.selection, finish: afterFinish, originals: after.originals),
                       .original(D.Selection(scope: Self.finalScope, identity: identity(64266833, R.brennan))))
    }

    // MARK: - Return context and the hold

    func testDoneReturnsToThePageOrTheCardItWasOpenedOverAndDismissalKeepsTheChoices() {
        // CONSTRUCTED: the reader's choices and destinations.
        let top10 = "datagolf|65391344|246352556"
        let selection = D.Selection(scope: Self.recordedScope, identity: identity(65391344, 246352556))

        // Details from the page: Done returns to the page.
        var session = Host.Session()
        session.choose(R.rory)
        session.selectFinish(top10)
        session.openDetails(.original(selection))
        XCTAssertNil(session.mode)
        XCTAssertEqual(session.presented?.id, "page", "Details over the page")
        session.close()
        XCTAssertNil(session.presented, "Done: back to the page")
        XCTAssertEqual(session.selected(initial: nil), R.rory)
        XCTAssertEqual(session.selectedFinish, top10)

        // Details from the full-size finish card: Done returns to that card.
        session.open(.reader(.finish))
        session.openDetails(.notSupplied(finish: "Top 5", slot: "golf.finish.top5.unavailable", scope: Self.recordedScope))
        XCTAssertEqual(session.presented?.id, "reader.finish", "the card's sheet is kept under Details, not re-presented")
        session.close()
        XCTAssertEqual(session.mode, .reader(.finish), "Done: back to the same card")
        XCTAssertNil(session.details)
        XCTAssertEqual(session.selectedFinish, top10)
        session.close()
        XCTAssertNil(session.presented, "Done again: the page")

        // An interactive dismissal over a card's Details: the page, golfer and finish kept.
        session.open(.reader(.finish))
        session.openDetails(.original(selection))
        session.dismiss()
        XCTAssertNil(session.presented)
        XCTAssertNil(session.details)
        XCTAssertEqual(session.selected(initial: R.sharma), R.rory, "the reader's choice outlives the sheet")
        XCTAssertEqual(session.selectedFinish, top10)

        // The page is never a sheet of its own.
        session.open(.page)
        XCTAssertNil(session.presented)
    }

    func testOneHoldComesBeforeEveryDetailsAndNothingIsOfferedThatWouldDoNothing() throws {
        // RETAINED: Winner, Top 10, Top 20, Make the Cut. CONSTRUCTED: no Top 5 market, clocks, join.
        let b = try built(R.indiaWin, legs: try indiaLegs(top5: nil, top10: R.indiaTop10), selected: R.rory, now: Self.indiaNow)
        var events: [String] = []
        var opened: [O.Destination] = []
        let hold = { events.append("hold") }
        let open: (O.Destination) -> Void = { events.append("open"); opened.append($0) }

        let finishDetails = try XCTUnwrap(Host.finishDetails(b.input, originals: b.originals, hold: hold, open: open))
        XCTAssertEqual(events, [], "building the callback calls nothing")
        finishDetails("golf.finish.top5.unavailable")
        XCTAssertEqual(events, ["hold", "open"])
        XCTAssertEqual(opened, [.notSupplied(finish: "Top 5", slot: "golf.finish.top5.unavailable", scope: Self.beforeScope)])
        finishDetails("datagolf|65391343|246352498")
        XCTAssertEqual(events, ["hold", "open", "hold", "open"], "a stale id still holds once and opens, never a silent no-op")
        XCTAssertEqual(opened.last, .unavailable, "it names no current slot: never a neighbour")

        let openOriginal = try XCTUnwrap(Host.openOriginal(b.input, originals: b.originals, hold: hold, open: open))
        openOriginal(FieldChooserOriginalRef10868(scope: "golf:65391342:before", source: "datagolf",
                                                  marketID: "65391342", outcomeID: String(R.rory)))
        XCTAssertEqual(events, ["hold", "open", "hold", "open", "hold", "open"])
        XCTAssertEqual(opened.last, .original(D.Selection(scope: Self.beforeScope, identity: identity(65391342, R.rory))))

        // No golfer chosen: no finish card, no contenders, so neither callback.
        let none = try built(R.indiaWin, legs: try indiaLegs(), selected: nil, now: Self.indiaNow)
        XCTAssertNil(Host.finishDetails(none.input, originals: none.originals, hold: nil, open: { _ in }))
        XCTAssertNil(Host.openOriginal(none.input, originals: none.originals, hold: nil, open: { _ in }))
        // After the start: the contenders card is not mounted, so no original callback.
        let during = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaRecordedNow)
        XCTAssertNil(Host.openOriginal(during.input, originals: during.originals, hold: nil, open: { _ in }))
        XCTAssertNotNil(Host.finishDetails(during.input, originals: during.originals, hold: nil, open: { _ in }))
    }

    // MARK: - Never a neighbour

    func testPhaseWithdrawalWrongMarketAndDuplicateIdentityNeverChooseANeighbour() throws {
        // RETAINED: the five India markets. CONSTRUCTED: clocks, join and the edits named below.
        let before = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        let held = D.Selection(scope: Self.beforeScope, identity: identity(65391343, 246352498))
        XCTAssertNotNil(content(before, held))

        // Phase: the same values read after the listed start (CONSTRUCTED clock).
        let during = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaRecordedNow)
        XCTAssertNil(content(during, held), "a before-phase selection resolves to nothing after the start")
        XCTAssertEqual(O.shown(.original(held), finish: during.finish, originals: during.originals), .original(held),
                       "handed to the Details unchanged, never re-scoped to the new phase")

        // Withdrawal: the Top 5 market is no longer held (CONSTRUCTED).
        let withdrawn = try built(R.indiaWin, legs: try indiaLegs(top5: nil, top10: R.indiaTop10), selected: R.rory, now: Self.indiaNow)
        XCTAssertNil(content(withdrawn, held), "not Win, not Top 10")
        let named = O.Destination.notSupplied(finish: "Top 5", slot: "golf.finish.top5.unavailable", scope: Self.beforeScope)
        XCTAssertEqual(O.shown(named, finish: withdrawn.finish, originals: withdrawn.originals),
                       .notSupplied("Top 5 original not supplied"))
        XCTAssertEqual(O.shown(named, finish: before.finish, originals: before.originals), .unavailable,
                       "once the Top 5 market is held the claim is withdrawn — never upgraded to an original")
        let duringWithdrawn = try built(R.indiaWin, legs: try indiaLegs(top5: nil, top10: R.indiaTop10), selected: R.rory,
                                        now: Self.indiaRecordedNow)
        XCTAssertEqual(O.shown(named, finish: duringWithdrawn.finish, originals: duringWithdrawn.originals), .unavailable,
                       "another phase")

        // Stale ids name no current slot.
        XCTAssertEqual(O.destination(finishID: "datagolf|65391343|246352498", finish: withdrawn.finish,
                                     originals: withdrawn.originals), .unavailable)
        XCTAssertEqual(O.destination(finishID: "golf.finish.top5.unavailable", finish: before.finish,
                                     originals: before.originals), .unavailable, "that slot is no longer unavailable")
        XCTAssertEqual(O.destination(finishID: "datagolf|65391343|246352498", finish: nil, originals: before.originals),
                       .unavailable, "no finish card: no slot to name")

        // Wrong market: a /history body for another market is never this market's (CONSTRUCTED `market_id`).
        let foreign = try R.edited(R.brennanHistory, ["market_id"], to: 65391342)
        let wrong = try built(R.baycurrentWinner, history: foreign, selected: R.brennan, now: Self.finalNow)
        let brennan = D.Selection(scope: Self.finalScope, identity: identity(64266833, R.brennan))
        XCTAssertEqual(content(wrong, brennan)?.readings.map(\.text), ["Before-start chance not recorded"],
                       "not his 3%, and never the 1.0")

        // Refs whose market, source or phase differ name no original.
        let rory = FieldChooserOriginalRef10868(scope: "golf:65391342:before", source: "datagolf",
                                                marketID: "65391342", outcomeID: String(R.rory))
        XCTAssertEqual(O.destination(ref: FieldChooserOriginalRef10868(scope: rory.scope, source: rory.source,
                                                                        marketID: "65391343", outcomeID: "246352498"),
                                     originals: before.originals), .unavailable, "a finish market's outcome is no contenders ref")
        XCTAssertEqual(O.destination(ref: FieldChooserOriginalRef10868(scope: rory.scope, source: "kalshi",
                                                                        marketID: rory.marketID, outcomeID: rory.outcomeID),
                                     originals: before.originals), .unavailable)
        XCTAssertEqual(O.destination(ref: FieldChooserOriginalRef10868(scope: "golf:65391342:recorded", source: rory.source,
                                                                        marketID: rory.marketID, outcomeID: rory.outcomeID),
                                     originals: before.originals), .unavailable, "another phase's ref")

        // Duplicate identity: Sharma's Top 10 row served with Rory's Top 10 id (CONSTRUCTED).
        let twinTop10 = try R.edited(R.indiaTop10, ["outcomes", 1, "id"], to: 246352556)
        let duplicated = try built(R.indiaWin, legs: try indiaLegs(top5: R.indiaTop5, top10: twinTop10), selected: R.rory, now: Self.indiaNow)
        let duplicatedFinish = try XCTUnwrap(duplicated.finish)
        XCTAssertEqual(duplicatedFinish.top10.selection, "golf.finish.top10.unavailable")
        XCTAssertNil(O.selection(finishID: "datagolf|65391344|246352556", in: duplicated.originals),
                     "two originals carry it: neither is chosen")
        XCTAssertNil(content(duplicated, D.Selection(scope: Self.beforeScope, identity: identity(65391344, 246352556))))
        XCTAssertEqual(O.destination(finishID: duplicatedFinish.top10.selection, finish: duplicatedFinish,
                                     originals: duplicated.originals),
                       .notSupplied(finish: "Top 10", slot: "golf.finish.top10.unavailable", scope: Self.beforeScope))
        XCTAssertEqual(O.destination(finishID: duplicatedFinish.top5.selection, finish: duplicatedFinish,
                                     originals: duplicated.originals),
                       .original(D.Selection(scope: Self.beforeScope, identity: identity(65391343, 246352498))),
                       "its siblings stay exact")

        // Duplicate Winner identity: Sharma served with Rory's id (CONSTRUCTED). No callback is offered.
        let twinWinner = try R.edited(R.indiaWin, ["outcomes", 1, "id"], to: R.rory)
        let twins = try built(twinWinner, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        XCTAssertNil(Host.openOriginal(twins.input, originals: twins.originals, hold: nil, open: { _ in }))
        XCTAssertNil(Host.finishDetails(twins.input, originals: twins.originals, hold: nil, open: { _ in }))

        // The same market handed in twice is one set of originals (CONSTRUCTED: the Winner body as the Top 5 leg).
        let doubled = F.Legs(top5: F.Leg(market: try R.market(R.indiaWin), outcomes: [R.rory: R.rory]))
        let doubledBuilt = try built(R.indiaWin, legs: doubled, selected: R.rory, now: Self.indiaNow)
        XCTAssertEqual(doubledBuilt.originals.catalogue.originals.count, 4)
    }

    func testAnUnattributedMarketOffersNoDetailsRatherThanAControlThatDoesNothing() throws {
        // CONSTRUCTED: `source` null on the Winner and the Top 5 body (RETAINED otherwise).
        let winner = try R.edited(R.indiaWin, ["source"], to: NSNull())
        let top5 = try R.edited(R.indiaTop5, ["source"], to: NSNull())
        let legs = F.Legs(top5: F.Leg(market: try R.market(top5), outcomes: Self.top5Join))
        let b = try built(winner, legs: legs, selected: R.rory, now: Self.indiaNow)
        let finish = try XCTUnwrap(b.finish)
        XCTAssertEqual(finish.win.selection, "|65391342|246352440", "golf's own key: empty, never \"unattributed\"")
        XCTAssertEqual(b.originals.catalogue.originals.count, 7)
        XCTAssertFalse(O.finishDetailsOffered(finish, originals: b.originals), "a blank source is never an identity")
        XCTAssertNil(Host.finishDetails(b.input, originals: b.originals, hold: nil, open: { _ in }))
        XCTAssertNil(Host.openOriginal(b.input, originals: b.originals, hold: nil, open: { _ in }))
    }
}
