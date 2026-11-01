import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf tournament screen's "Explore props": the supplied originals
/// in compact typed groups, each card the shared catalogue's own original, the
/// held group's binding, the host's browse layers and the page-only entry, on
/// the retained bodies in `GolfFieldRetainedBodies10868`.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no Swift
/// parse, no XCTest).
///
/// RETAINED (decoded through the production models, `.convertFromSnakeCase`):
///   - DP World India Championship Winner / Top 5 / Top 10 / Top 20 / Make the
///     Cut (65391342–65391346, `status: open`, DataGolf) — SUBSETS of the served
///     bodies (4 of `outcome_count` 190 Winner rows, 3 of 190 per finish market);
///   - Baycurrent Classic Winner 64266833 (`status: resolved`, ungraded; 7 of
///     `outcome_count` 155 rows) and Michael Brennan's history.
///
/// CONSTRUCTED, and named again where used:
///   - the reader's calendar (Pacific, en_US) and every `now`;
///   - the host's per-golfer join (`Leg.outcomes`), required by `Leg.init` and
///     unused by browsing;
///   - single-key edits of a retained body (an outcome id, a market id, a
///     source, an empty outcome list), a market handed in under two roles, a
///     withdrawn market, and a held inspection on the India pass's evidence.
///
/// Mutation controls (each would fail a named test): reading a role from the
/// market name or position (roles, doubled market); dropping an unpriced, zero,
/// unattributed or duplicated row (supplied rows, duplicate, unattributed);
/// labelling a duplicated identity by last writer (duplicate); resolving a held
/// group by role or index alone (held key: replacement, source, role, phase);
/// holding while building a callback, or opening before the hold (callbacks);
/// Done skipping the group or the menu, or a dismissal resetting a choice
/// (layers); drawing the entry inside a reader (entry).
@MainActor
final class GolfFieldPropsBrowseAdapter10868Tests: XCTestCase {
    private typealias B = GolfFieldPropsBrowseAdapter10868
    private typealias O = GolfFieldOriginalsAdapter10868
    private typealias D = OriginalMarketDetails9483
    private typealias C = OriginalMarketCatalogue9483
    private typealias F = GolfFieldFinishAdapter10868
    private typealias I = GolfFieldHistoryInspectionAdapter10868
    private typealias Host = GolfFieldEventPageHost10868
    private typealias R = GolfFieldRetainedBodies10868

    /// CONSTRUCTED reader clocks.
    private static let indiaNow = "2026-10-12T23:28:52Z"
    private static let indiaRecordedNow = "2026-10-15T06:00:00Z"
    private static let finalNow = "2026-10-12T23:56:42Z"

    private static let beforeScope = "golf:65391342:before:originals"
    private static let recordedScope = "golf:65391342:recorded:originals"
    private static let finalScope = "golf:64266833:final:originals"

    /// CONSTRUCTED host join (unused by browsing; `Leg` requires one).
    private static let top5Join = [R.rory: 246352498, R.sharma: 246352530, R.noren: 245904764]
    private static let top10Join = [R.rory: 246352556, R.sharma: 246352588, R.noren: 245904896]
    private static let top20Join = [R.rory: 246352614, R.sharma: 246352646, R.noren: 245905028]
    private static let makeCutJoin = [R.rory: 246352672, R.sharma: 246352704, R.noren: 245905160]

    private func indiaLegs() throws -> F.Legs {
        try indiaLegs(top5: R.indiaTop5, top10: R.indiaTop10)
    }

    /// RETAINED finish markets; the Top 5 / Top 10 bodies from the caller, nil drops that market.
    private func indiaLegs(top5: String?, top10: String?) throws -> F.Legs {
        F.Legs(top5: try top5.map { F.Leg(market: try R.market($0), outcomes: Self.top5Join) },
               top10: try top10.map { F.Leg(market: try R.market($0), outcomes: Self.top10Join) },
               top20: F.Leg(market: try R.market(R.indiaTop20), outcomes: Self.top20Join),
               makeCut: F.Leg(market: try R.market(R.indiaMakeCut), outcomes: Self.makeCutJoin))
    }

    /// One host pass: the page input, the originals and the groups from the same values.
    @MainActor
    private struct Built {
        let input: GolfEventPageInput10868
        let originals: O.Originals
        let groups: [B.Group]
        var finish: GolfFinishExpectationInput10868? { GolfEventPageModel10868(input).finish }

        func group(_ role: F.Kind) -> B.Group? { groups.first { $0.key.role == role } }
    }

    private func built(_ winnerJSON: String, history historyJSON: String? = nil, legs held: F.Legs? = nil,
                       selected: Int?, now: String) throws -> Built {
        let legs = held ?? F.Legs()
        let winner = try R.market(winnerJSON)
        let history = try historyJSON.map { try R.history($0) }
        let host = R.host(now)
        let input = Host.build(winner: winner, history: history, legs: legs,
                               cohort: selected.map { [$0] } ?? [], choice: Host.Choice(selected: selected),
                               now: host.now, calendar: host.calendar, locale: host.locale)
        let pass = try passOnly(winnerJSON, history: historyJSON, legs: legs, now: now)
        return Built(input: input, originals: pass.originals, groups: pass.groups)
    }

    /// The originals and groups alone, for bodies the page input is not asked about.
    private func passOnly(_ winnerJSON: String, history historyJSON: String? = nil, legs: F.Legs,
                          now: String) throws -> (originals: O.Originals, groups: [B.Group]) {
        let winner = try R.market(winnerJSON)
        let history = try historyJSON.map { try R.history($0) }
        let host = R.host(now)
        let originals = Host.originals(winner: winner, history: history, legs: legs,
                                       now: host.now, calendar: host.calendar, locale: host.locale)
        let groups = Host.propGroups(winner: winner, history: history, legs: legs, originals: originals, now: host.now)
        return (originals, groups)
    }

    private func cards(_ group: B.Group) -> [C.Card] {
        C.cards(catalogue: group.originals.catalogue, selection: group.originals.selection,
                labels: group.originals.labels, unavailableChoice: group.originals.unavailableChoice)
    }

    private func identity(_ market: Int, _ outcome: Int) -> D.Identity {
        D.Identity(source: "datagolf", market: String(market), side: String(outcome))
    }

    private func key(_ scope: String, _ market: Int, _ role: F.Kind, source: String = "datagolf") -> B.Key {
        B.Key(scope: scope, source: source, market: String(market), role: role)
    }

    // MARK: - Groups

    func testTheGroupsFollowTheTypedRolesAndHoldEveryOriginalExactlyOnce() throws {
        // RETAINED: the five India markets. CONSTRUCTED: the clock and the join.
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        XCTAssertEqual(b.groups.map(\.key), [
            key(Self.beforeScope, 65391342, .win), key(Self.beforeScope, 65391343, .top5),
            key(Self.beforeScope, 65391344, .top10), key(Self.beforeScope, 65391345, .top20),
            key(Self.beforeScope, 65391346, .makeCut),
        ], "the Winner market, then each held finish market once, each under its typed slot")
        XCTAssertEqual(b.groups.map(\.originals.heading), ["Win", "Top 5", "Top 10", "Top 20", "Make cut"])
        XCTAssertEqual(b.groups.map(\.count), [4, 3, 3, 3, 3])
        XCTAssertEqual(b.groups.map(\.originals.context),
                       ["4 original outcomes", "3 original outcomes", "3 original outcomes",
                        "3 original outcomes", "3 original outcomes"])
        XCTAssertEqual(b.groups.flatMap { $0.originals.catalogue?.originals.map(\.identity) ?? [] },
                       b.originals.catalogue.originals.map(\.identity),
                       "every held original sits in exactly one group, in served order")
        for group in b.groups {
            XCTAssertEqual(group.originals.catalogue?.scope, Self.beforeScope, "the shared catalogue's own scope")
            XCTAssertNil(group.originals.selection, "no golfer is marked or elected")
            XCTAssertEqual(group.originals.emptyWords, "No original outcomes for this field")
            XCTAssertEqual(group.originals.unavailableChoice, "Unnamed original")
        }
        XCTAssertEqual(B.spoken(try XCTUnwrap(b.group(.top5))), "Top 5, 3 original outcomes")
    }

    func testOnlyMarketsTheHostHoldsBecomeGroupsAndNoRoleIsAdvertised() throws {
        // RETAINED: India Winner alone; CONSTRUCTED: no finish markets held.
        let alone = try built(R.indiaWin, selected: R.rory, now: Self.indiaNow)
        XCTAssertEqual(alone.groups.map(\.key), [key(Self.beforeScope, 65391342, .win)])
        XCTAssertEqual(alone.groups.map(\.count), [4])

        // CONSTRUCTED: no Top 5 market held. RETAINED otherwise.
        let noTop5 = try built(R.indiaWin, legs: try indiaLegs(top5: nil, top10: R.indiaTop10), selected: R.rory,
                               now: Self.indiaNow)
        XCTAssertEqual(noTop5.groups.map(\.key.role), [.win, .top10, .top20, .makeCut], "a missing market is not listed")
        XCTAssertFalse(noTop5.groups.contains { $0.key.market == "65391343" })

        // RETAINED: the resolved Baycurrent Winner with no finish markets.
        let final = try built(R.baycurrentWinner, history: R.brennanHistory, selected: R.brennan, now: Self.finalNow)
        XCTAssertEqual(final.groups.map(\.key), [key(Self.finalScope, 64266833, .win)])
        XCTAssertEqual(final.groups.map(\.count), [7], "every supplied row of the retained subset")
    }

    func testAMarketHandedInUnderTwoRolesIsOneGroupUnderItsFirstRole() throws {
        // CONSTRUCTED: the Winner body handed in as the Top 5 leg.
        let doubled = try passOnly(R.indiaWin, legs: F.Legs(top5: F.Leg(market: try R.market(R.indiaWin),
                                                                         outcomes: [R.rory: R.rory])),
                                   now: Self.indiaNow)
        XCTAssertEqual(doubled.groups.map(\.key), [key(Self.beforeScope, 65391342, .win)])
        XCTAssertEqual(doubled.groups.map(\.count), [4], "no row repeated under a second heading")

        // CONSTRUCTED: the Top 10 body handed in as both Top 10 and Top 20.
        let top10 = F.Leg(market: try R.market(R.indiaTop10), outcomes: Self.top10Join)
        let twice = try passOnly(R.indiaWin, legs: F.Legs(top10: top10, top20: top10), now: Self.indiaNow)
        XCTAssertEqual(twice.groups.map(\.key.role), [.win, .top10], "the first typed slot, as the originals resolve it")
        XCTAssertEqual(twice.groups.map(\.count).reduce(0, +), twice.originals.catalogue.originals.count)
        XCTAssertEqual(B.role(try R.market(R.indiaTop10), winner: try R.market(R.indiaWin),
                              legs: F.Legs(top10: top10, top20: top10)), .top10)
        XCTAssertNil(B.role(try R.market(R.indiaTop5), winner: try R.market(R.indiaWin), legs: F.Legs(top10: top10)),
                     "a market no slot holds has no role — never one read from its name")
    }

    func testAGroupWithNoRowsKeepsItsWordsAndExploreActsOnlyWhenARowIsSupplied() throws {
        // CONSTRUCTED: the Top 5 body served with no outcomes. RETAINED otherwise.
        let empty = try R.edited(R.indiaTop5, ["outcomes"], to: [Any]())
        let withEmpty = try passOnly(R.indiaWin, legs: F.Legs(top5: F.Leg(market: try R.market(empty), outcomes: [:])),
                                     now: Self.indiaNow)
        XCTAssertEqual(withEmpty.groups.map(\.key.role), [.win, .top5])
        let top5 = try XCTUnwrap(withEmpty.groups.last)
        XCTAssertNil(top5.originals.catalogue, "the catalogue's own empty words show")
        XCTAssertNil(top5.originals.context)
        XCTAssertEqual(top5.count, 0)
        XCTAssertTrue(B.offered(withEmpty.groups))

        // CONSTRUCTED: the Winner body served with no outcomes and nothing else held.
        let bare = try passOnly(try R.edited(R.indiaWin, ["outcomes"], to: [Any]()), legs: F.Legs(), now: Self.indiaNow)
        XCTAssertEqual(bare.groups.map(\.count), [0])
        XCTAssertFalse(B.offered(bare.groups))
        XCTAssertNil(B.entry(bare.groups, hold: nil, open: {}), "no entry that would show nothing")
    }

    // MARK: - Cards are the shared originals

    func testEachCardIsTheSharedOriginalLabelledWithItsServedGolferAndOpensItsExactDetails() throws {
        // RETAINED: the five India markets. CONSTRUCTED: the clock and the join.
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        for group in b.groups {
            let members = try XCTUnwrap(group.originals.catalogue).originals
            let shown = cards(group)
            XCTAssertEqual(shown.count, members.count, group.originals.heading)
            for (card, original) in zip(shown, members) {
                XCTAssertEqual(card.choice.label, original.outcome, "the served golfer name, verbatim")
                let selection = try XCTUnwrap(card.choice.selection, original.outcome)
                XCTAssertEqual(selection, D.Selection(scope: Self.beforeScope, identity: original.identity))
                let details = try XCTUnwrap(D.content(catalogue: b.originals.catalogue, selection: selection))
                XCTAssertEqual(card.content, details, "the card is the shared Details content")
                XCTAssertEqual(details.title, original.title, "the Details keep the market's own title")
            }
        }
        // Rory's Top 5 card is the finish card's own selection for that original.
        let finish = try XCTUnwrap(b.finish)
        let roryTop5 = try XCTUnwrap(cards(try XCTUnwrap(b.group(.top5))).first?.choice.selection)
        XCTAssertEqual(O.selection(finishID: finish.top5.selection, in: b.originals), roryTop5)
        XCTAssertEqual(O.shown(.original(roryTop5), finish: finish, originals: b.originals), .original(roryTop5))
    }

    func testUnpricedAndZeroRowsStayAsCardsWithTheirOwnWords() throws {
        // RETAINED: Noren unpriced (an untimed opening beside it); Jaglan a real 0.
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        let win = cards(try XCTUnwrap(b.group(.win)))
        XCTAssertEqual(win.map(\.choice.label), ["Rory McIlroy", "Shubhankar Sharma", "Shubham Jaglan", "Alex Noren"])
        let noren = try XCTUnwrap(win.last?.content)
        XCTAssertEqual(noren.readings.map(\.text), ["Before-start chance not recorded"])
        XCTAssertEqual(noren.readings.map(\.isValue), [false])
        let jaglan = try XCTUnwrap(win[2].content)
        XCTAssertEqual(jaglan.readings.map(\.text), [formatProbability(0)])
        XCTAssertEqual(jaglan.readings.map(\.isValue), [true], "a real 0 is a value")
        for group in b.groups.dropFirst() {
            XCTAssertEqual(cards(group).last?.content?.readings.map(\.text), ["Before-start chance not recorded"],
                           "Noren's \(group.originals.heading) row stays")
        }
    }

    func testADuplicatedIdentityKeepsBothRowsUnavailableAndNeitherBorrowsTheOthersGolfer() throws {
        // CONSTRUCTED: Sharma's Top 10 row served with Rory's Top 10 id — two rows,
        // one identity, two different outcome names. RETAINED otherwise.
        let twinTop10 = try R.edited(R.indiaTop10, ["outcomes", 1, "id"], to: 246352556)
        let b = try built(R.indiaWin, legs: try indiaLegs(top5: R.indiaTop5, top10: twinTop10), selected: R.rory,
                          now: Self.indiaNow)
        let top10 = try XCTUnwrap(b.group(.top10))
        let members = try XCTUnwrap(top10.originals.catalogue).originals
        let twin = identity(65391344, 246352556)
        XCTAssertEqual(members.map(\.outcome), ["Rory McIlroy", "Shubhankar Sharma", "Alex Noren"], "both rows stay")
        XCTAssertEqual(members.filter { $0.identity == twin }.count, 2)
        XCTAssertNil(top10.originals.labels[twin], "no override for an ambiguous identity — no last writer wins")
        XCTAssertNil(B.labels(Array(members.reversed()))[twin], "in either order")

        let shown = cards(top10)
        XCTAssertEqual(shown.count, 3)
        for card in shown.prefix(2) {
            XCTAssertNil(card.choice.selection, "the shared refusal: neither opens")
            XCTAssertNil(card.content)
            XCTAssertEqual(card.choice.status, "Unavailable")
            XCTAssertEqual(card.choice.label, "DP World India Championship - Top 10 Finish", "its own title, verbatim")
            XCTAssertNotEqual(card.choice.label, "Rory McIlroy")
            XCTAssertNotEqual(card.choice.label, "Shubhankar Sharma")
        }
        XCTAssertEqual(shown[2].choice.label, "Alex Noren")
        XCTAssertNotNil(shown[2].choice.selection, "its sibling stays exact")
        XCTAssertNil(D.content(catalogue: b.originals.catalogue,
                               selection: D.Selection(scope: Self.beforeScope, identity: twin)))
    }

    func testAnUnattributedMarketKeepsItsGroupAndItsRowsAsUnavailableCards() throws {
        // CONSTRUCTED: `source` null on the Top 5 body. RETAINED otherwise.
        let unattributed = try R.edited(R.indiaTop5, ["source"], to: NSNull())
        let b = try built(R.indiaWin, legs: try indiaLegs(top5: unattributed, top10: R.indiaTop10), selected: R.rory,
                          now: Self.indiaNow)
        let top5 = try XCTUnwrap(b.group(.top5))
        XCTAssertEqual(top5.key, key(Self.beforeScope, 65391343, .top5, source: ""))
        let shown = cards(top5)
        XCTAssertEqual(shown.map(\.choice.label), ["Rory McIlroy", "Shubhankar Sharma", "Alex Noren"])
        XCTAssertEqual(shown.map { $0.choice.selection == nil }, [true, true, true], "a blank source is never an identity")
        XCTAssertEqual(shown.map(\.choice.status), ["Unavailable", "Unavailable", "Unavailable"])
        XCTAssertNotNil(cards(try XCTUnwrap(b.group(.win))).first?.choice.selection, "other groups keep opening")
    }

    func testRecordedAndFinalCardsReadEachOriginalsOwnDatedContent() throws {
        // CONSTRUCTED clock after the listed start over RETAINED pre-start captures.
        let during = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaRecordedNow)
        let top5 = try XCTUnwrap(during.group(.top5))
        XCTAssertEqual(top5.key.scope, Self.recordedScope)
        let rory = try XCTUnwrap(cards(top5).first?.content)
        XCTAssertEqual(rory.readings.map(\.label), ["Before start", "Recorded chance"])
        XCTAssertEqual(rory.readings.map(\.text), ["35%", "Chance since the start not recorded"])

        // RETAINED: the resolved, ungraded Baycurrent Winner.
        let final = try built(R.baycurrentWinner, history: R.brennanHistory, selected: R.brennan, now: Self.finalNow)
        let win = cards(try XCTUnwrap(final.group(.win)))
        let brennan = try XCTUnwrap(win.first { $0.choice.label == "Michael Brennan" }?.content)
        XCTAssertEqual(brennan.result?.words, "Result unavailable", "unknown is never Lost")
        XCTAssertEqual(brennan.readings.map(\.text), ["3%"])
        let fishburn = try XCTUnwrap(win.first { $0.choice.label == "Patrick Fishburn" }?.content)
        XCTAssertEqual(fishburn.readings.map(\.text), ["Before-start chance not recorded"])
    }

    // MARK: - The held group

    func testAHeldGroupBindsScopeMarketSourceAndRoleAndNeverResolvesToAnotherGroup() throws {
        // RETAINED: the five India markets. CONSTRUCTED: the clocks, the join and the edits below.
        let before = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        let held = key(Self.beforeScope, 65391343, .top5)
        XCTAssertEqual(B.group(held, in: before.groups)?.count, 3)

        // A different market under the same role (CONSTRUCTED Top 5 id): never substituted.
        let replacedBody = try R.edited(R.indiaTop5, ["id"], to: 65391399)
        let replaced = try passOnly(R.indiaWin, legs: try indiaLegs(top5: replacedBody, top10: R.indiaTop10),
                                    now: Self.indiaNow)
        XCTAssertNotNil(replaced.groups.first { $0.key.role == .top5 }, "a Top 5 group exists on this pass")
        XCTAssertNil(B.group(held, in: replaced.groups), "but it is another market: the held group is unavailable")
        XCTAssertNotNil(B.group(key(Self.beforeScope, 65391399, .top5), in: replaced.groups))

        // Another source for the same market id (CONSTRUCTED).
        let resourced = try R.edited(R.indiaTop5, ["source"], to: "kalshi")
        let moved = try passOnly(R.indiaWin, legs: try indiaLegs(top5: resourced, top10: R.indiaTop10), now: Self.indiaNow)
        XCTAssertNil(B.group(held, in: moved.groups))

        // The same market under another role is not this key.
        XCTAssertNil(B.group(key(Self.beforeScope, 65391343, .top10), in: before.groups))

        // Withdrawn (CONSTRUCTED: no Top 5 market held).
        let withdrawn = try passOnly(R.indiaWin, legs: try indiaLegs(top5: nil, top10: R.indiaTop10), now: Self.indiaNow)
        XCTAssertNil(B.group(held, in: withdrawn.groups), "never the Win or Top 10 group")

        // Phase: the same values read after the listed start (CONSTRUCTED clock) — another scope.
        let during = try passOnly(R.indiaWin, legs: try indiaLegs(), now: Self.indiaRecordedNow)
        XCTAssertNil(B.group(held, in: during.groups))
        XCTAssertEqual(B.group(key(Self.recordedScope, 65391343, .top5), in: during.groups)?.count, 3)
    }

    // MARK: - Callbacks and layers

    func testBuildingTheCallbacksCallsNothingAndEachOpenHoldsOnceFirst() throws {
        // RETAINED: the five India markets. CONSTRUCTED: the clock and the join.
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        var events: [String] = []
        var opened: [O.Destination] = []
        let entry = try XCTUnwrap(B.entry(b.groups, hold: { events.append("hold") }, open: { events.append("menu") }))
        let select = B.select(hold: { events.append("hold") },
                              open: { events.append("details"); opened.append($0) })
        XCTAssertEqual(events, [], "building either callback calls nothing")

        entry()
        XCTAssertEqual(events, ["hold", "menu"])
        let selection = try XCTUnwrap(cards(try XCTUnwrap(b.group(.top5))).first?.choice.selection)
        select(selection)
        XCTAssertEqual(events, ["hold", "menu", "hold", "details"])
        XCTAssertEqual(opened, [.original(selection)], "the exact selection, unchanged")

        var opens = 0
        try XCTUnwrap(B.entry(b.groups, hold: nil, open: { opens += 1 }))()
        XCTAssertEqual(opens, 1, "no hold to ask for: it still opens")
    }

    func testDoneUnwindsDetailsGroupMenuPageAndADismissalKeepsEveryChoice() throws {
        // RETAINED: the five India markets. CONSTRUCTED: the choices, the selection
        // and a held inspection on the India pass's own evidence.
        let b = try built(R.indiaWin, legs: try indiaLegs(), selected: R.rory, now: Self.indiaNow)
        let top5 = try XCTUnwrap(b.group(.top5)).key
        let selection = D.Selection(scope: Self.beforeScope, identity: identity(65391343, 246352498))
        let host = R.host(Self.indiaNow)
        let snapshot = Host.inspectionSnapshot(winner: try R.market(R.indiaWin), history: nil, cohort: [R.rory],
                                               selected: R.rory, held: nil, now: host.now,
                                               calendar: host.calendar, locale: host.locale)
        let inspection = I.Held(evidence: snapshot.pass.evidence, at: .moment("constructed"))
        let finishID = "datagolf|65391343|246352498"

        var session = Host.Session()
        session.choose(R.rory)
        session.selectFinish(finishID)
        session.inspect(inspection)
        func assertChoicesKept(_ line: UInt = #line) {
            XCTAssertEqual(session.selected(initial: R.sharma), R.rory, line: line)
            XCTAssertEqual(session.selectedFinish, finishID, line: line)
            XCTAssertEqual(session.inspection, inspection, line: line)
        }

        session.openBrowse()
        XCTAssertEqual(session.browse, .menu)
        XCTAssertNil(session.mode)
        XCTAssertEqual(session.presented?.id, "browse")
        session.openGroup(top5)
        XCTAssertEqual(session.browse, .group(top5))
        session.openDetails(.original(selection))
        XCTAssertEqual(session.presented?.id, "browse", "Details over the group keep the sheet, never re-presented")

        session.close()
        XCTAssertNil(session.details)
        XCTAssertEqual(session.browse, .group(top5), "Done: back to the same group")
        session.close()
        XCTAssertEqual(session.browse, .menu, "Done: back to the menu")
        session.close()
        XCTAssertNil(session.browse)
        XCTAssertNil(session.presented, "Done: the page")
        assertChoicesKept()

        // A swipe-down over Details over a group: the page, every choice kept.
        session.openBrowse()
        session.openGroup(top5)
        session.openDetails(.original(selection))
        session.dismiss()
        XCTAssertNil(session.presented)
        XCTAssertNil(session.browse)
        XCTAssertNil(session.details)
        assertChoicesKept()

        // A card and the browse layer never stack.
        session.openBrowse()
        session.open(.reader(.finish))
        XCTAssertNil(session.browse)
        XCTAssertEqual(session.presented?.id, "reader.finish")
        session.openBrowse()
        XCTAssertNil(session.mode)
        XCTAssertEqual(session.presented?.id, "browse")
        session.dismiss()

        // Regression: the existing layers are unchanged.
        session.openDetails(.original(selection))
        XCTAssertEqual(session.presented?.id, "page")
        session.close()
        XCTAssertNil(session.presented)
        session.open(.reader(.finish))
        session.openDetails(.original(selection))
        XCTAssertEqual(session.presented?.id, "reader.finish")
        session.close()
        XCTAssertEqual(session.mode, .reader(.finish))
        session.close()
        XCTAssertNil(session.presented)
        assertChoicesKept()
    }

    // MARK: - The page entry

    func testExplorePropsIsOnePageOnlyEntryWithTheOwnersWordsAndTheHostsCallback() throws {
        // RETAINED: the India Winner. CONSTRUCTED: the clock.
        let b = try built(R.indiaWin, selected: R.rory, now: Self.indiaNow)
        XCTAssertEqual(b.input.copy.exploreLabel, "Explore props")
        let model = GolfEventPageModel10868(b.input)
        XCTAssertTrue(model.exploreAvailable(canOpen: true))
        XCTAssertFalse(model.exploreAvailable(canOpen: false), "no callback: no entry")

        var calls = 0
        GolfEventPagePresentation10868(input: b.input, onExploreProps: { calls += 1 }).exploreProps()
        XCTAssertEqual(calls, 1)
        for mode: GolfEventPageMode10868 in [.reader(.history), .reader(.finish), .chooser] {
            GolfEventPagePresentation10868(input: b.input, mode: mode, onExploreProps: { calls += 1 }).exploreProps()
        }
        XCTAssertEqual(calls, 1, "never from a reader or the chooser")
        _ = GolfEventPagePresentation10868(input: b.input, onExploreProps: { calls += 1 })
        XCTAssertEqual(calls, 1, "building the page calls nothing")

        // Blank words, or a copy without them: no entry and no call.
        let c = b.input.copy
        for words: String? in ["  ", nil] {
            let copy = GolfEventPageCopy10868(eyebrow: c.eyebrow, title: c.title, context: c.context,
                                              aboutLabel: c.aboutLabel, storiesLabel: c.storiesLabel,
                                              finishUnavailable: c.finishUnavailable, exploreLabel: words)
            let input = GolfEventPageInput10868(
                phase: b.input.phase, copy: copy, status: b.input.status, history: b.input.history,
                finish: b.input.finish, finishFrame: b.input.finishFrame, contenders: b.input.contenders,
                contendersFrame: b.input.contendersFrame, movement: b.input.movement,
                movementFrame: b.input.movementFrame, chooser: b.input.chooser)
            XCTAssertFalse(GolfEventPageModel10868(input).exploreAvailable(canOpen: true))
            GolfEventPagePresentation10868(input: input, onExploreProps: { calls += 1 }).exploreProps()
        }
        XCTAssertEqual(calls, 1)
        XCTAssertNil(GolfEventPageCopy10868(eyebrow: nil, title: "t", context: nil, aboutLabel: nil,
                                            storiesLabel: "s", finishUnavailable: "f").exploreLabel,
                     "an owner that supplies no words draws no entry")
    }
}
