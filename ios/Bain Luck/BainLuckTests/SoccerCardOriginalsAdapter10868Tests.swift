import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — a soccer story card's Details open that row's EXACT original and
/// return to the same card and chosen outcome
/// (`SoccerCardOriginalsAdapter10868`, wired by `SoccerEventPageHost10868`).
///
/// PILLARS: FORMATTING / TRUTH. SHIP: soccer story cards open their exact
/// original Details and return to the same card and chosen outcome.
///
/// Built through the host's pure `build` on RETAINED REAL bodies
/// (`SoccerRetained10868`, `SoccerExactRetained10868` — sources, hashes and
/// subset rules are in their own files), each at its own capture clock, under
/// the shared CONSTRUCTED owner admissions those files name
/// (`SoccerRetained10868.liveAdmission`, `SoccerExactRetained10868.hullBeforeAdmission`
/// and its descriptor `hullDescriptor`).
///
/// Labels, per test:
///   - RETAINED — those retained bodies, unedited, at their own clocks, under
///     those shared admissions and the host's existing route contexts.
///   - CONSTRUCTED — the test adds its own admission, descriptor, body edit,
///     reader choice or layer sequence; each is named CONSTRUCTED where made.
///     The constructed market id 99000001 names no served market.
///
/// Every C1 regression keeps BOTH the old and the replacement rows in the body:
/// the refusal comes from the held origin no longer matching, never from the
/// old row being gone (the old original is asserted still present in All props).
///
/// Not covered here (owed, not claimed): the full-size card's scroll position
/// and VoiceOver focus after Done; real phone, wide and accessibility-size
/// interaction; full-body and on-device performance (the per-pass lookups are
/// source-level reuse, not a measurement); a production owner of the story
/// admission and the exact-score descriptor.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class SoccerCardOriginalsAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias X = SoccerExactRetained10868
    private typealias R = SoccerPropReadingAdapter10868
    private typealias C = SoccerCardOriginalsAdapter10868
    private typealias D = OriginalMarketDetails9483
    private typealias E = SoccerExactScoreAdapter10868
    private typealias Host = SoccerEventPageHost10868
    private typealias Stream = StoryStreamPresentation10868

    private static let liveScope = "soccer:15325054:live:originals"
    private static let finalScope = "soccer:15325054:final:originals"
    private static let hullBeforeScope = "soccer:15311089:before:originals"
    private static let hullFinalScope = "soccer:15311089:final:originals"

    private final class Log {
        var lines: [String] = []
    }

    // MARK: - Fixtures

    private func built(detail: String = F.liveDetail, history: String? = F.liveHistory,
                       markets: String? = F.liveMarkets, admitted: R.Markets = F.liveAdmission,
                       now: Date = F.liveNow,
                       halvesAdmission: SoccerPageInputAdapter10868.HalvesAdmission = .routeDefault,
                       admittedCards: Set<SoccerEventPageCard10868> = [],
                       reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        let event = try F.detail(detail)
        return Host.build(event: event, history: try history.map { try F.history($0) },
                          markets: try markets.map { try F.markets($0) }, admitted: admitted,
                          halvesAdmission: halvesAdmission, admittedCards: admittedCards,
                          probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, now: now,
                          reading: reading, calendar: F.pacific, locale: F.locale)
    }

    /// The Valladolid–Albacete body after the final, at its own capture clock.
    private func finalPage(admitted: R.Markets = F.liveAdmission,
                           reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        try built(detail: F.finalDetail, history: F.finalHistory, markets: F.finalMarkets, admitted: admitted,
                  now: F.finalNow, reading: reading)
    }

    /// The Hull–Everton pregame body with every exact-score row, at its own capture clock.
    private func hull(markets: String = X.hullExactMarkets, admitted: R.Markets = X.hullBeforeAdmission,
                      reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        try built(detail: F.hullDetail, history: F.hullHistory, markets: markets, admitted: admitted,
                  now: F.hullNow, reading: reading)
    }

    private func selection(_ scope: String, _ market: String, _ side: String, source: String = "polymarket") -> D.Selection {
        D.Selection(scope: scope, identity: D.Identity(source: source, market: market, side: side))
    }

    private func ref(_ outcome: String, event: String = "15325054", market: String = "64353426") -> BothTeamsOutcomeRef10868 {
        BothTeamsOutcomeRef10868(eventID: event, marketID: market, outcomeID: outcome)
    }

    private func hold(_ opened: C.Opened) -> C.Hold? {
        if case .held(let hold) = opened { return hold }
        return nil
    }

    /// CONSTRUCTED: the descriptor with scope `id` rebound to `market` / `period`;
    /// every other scope and field unchanged.
    private func descriptor(_ base: E.Descriptor, rebinding id: String, market: Int, period: String?) -> E.Descriptor {
        E.Descriptor(eventID: base.eventID, scopes: base.scopes.map { (scope) -> E.Descriptor.Scope in
            guard scope.id == id else { return scope }
            return E.Descriptor.Scope(id: scope.id, label: scope.label, marketID: market, periodID: period,
                                      homeGoals: scope.homeGoals, awayGoals: scope.awayGoals,
                                      scaleUpper: scope.scaleUpper, originals: scope.originals)
        })
    }

    /// CONSTRUCTED: the descriptor with scope `id` listing the original whose
    /// outcome ids are exactly `[outcome]` a second time; everything else unchanged.
    private func descriptor(_ base: E.Descriptor, listingTwice outcome: Int, in id: String) throws -> E.Descriptor {
        let scopes = try base.scopes.map { (scope) throws -> E.Descriptor.Scope in
            guard scope.id == id else { return scope }
            let listed = try XCTUnwrap(scope.originals.first { $0.outcomeIDs == [outcome] })
            return E.Descriptor.Scope(id: scope.id, label: scope.label, marketID: scope.marketID,
                                      periodID: scope.periodID, homeGoals: scope.homeGoals,
                                      awayGoals: scope.awayGoals, scaleUpper: scope.scaleUpper,
                                      originals: scope.originals + [listed])
        }
        return E.Descriptor(eventID: base.eventID, scopes: scopes)
    }

    /// CONSTRUCTED: the served body with the ONE row of `array` whose
    /// `contributor_outcome_ids` is exactly `[outcomeID]` removed; every other
    /// row and key stays as served. A missing row fails.
    private func removingRow(_ json: String, array: String = "other", outcomeID: Int) throws -> String {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        var rows = try XCTUnwrap(object[array] as? [[String: Any]])
        let index = try XCTUnwrap(rows.firstIndex { ($0["contributor_outcome_ids"] as? [Int]) == [outcomeID] })
        rows.remove(at: index)
        object[array] = rows
        return String(decoding: try JSONSerialization.data(withJSONObject: object), as: UTF8.self)
    }

    /// The activation the real stream hands its displayed card `id`, logging
    /// the stream's hold.
    private func activation(_ input: SoccerEventPageInput10868, _ id: String, log: Log) -> StoryStreamCardActivation10868 {
        let stream = input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let card = Stream.CardRef(scope: stream.scope, id: id)
        return StoryStreamCardActivation10868(card: card, intents: stream.activationIntents(for: card, resolved: resolved)) { intent in
            if case .interaction(_, let card) = intent { log.lines.append("stream hold:\(card?.id ?? "-")") } else { log.lines.append("other") }
        }
    }

    // MARK: - Exact rows (RETAINED)

    /// RETAINED. During play every drawn goal milestone, both-teams outcome and
    /// first-team row opens its OWN row's original — that market and that
    /// contributor id — under the page's own catalogue scope, and the catalogue
    /// resolves exactly that original.
    func testLiveGoalBothAndFirstDetailsOpenEachRowsOwnOriginal() throws {
        let page = try built()
        let catalogue = try XCTUnwrap(page.originals.catalogue)
        XCTAssertEqual(catalogue.scope, Self.liveScope)
        XCTAssertEqual(page.input.goals?.milestones.map(\.id), ["242143183", "242143187", "242765587"])
        XCTAssertEqual(page.input.both?.outcomes.map(\.id), ["242143190", "242143189"])
        XCTAssertEqual(page.input.first?.overview.map(\.id), ["244237963", "244237965", "244237964"])

        for (id, market) in [("242143183", 64353423), ("242143187", 64353425), ("242765587", 64536538)] {
            let expected = selection(Self.liveScope, String(market), id)
            XCTAssertEqual(C.open(goal: id, in: page.pass),
                           .held(C.Hold(origin: .goal(market: market, id: id), selection: expected)), id)
            XCTAssertEqual(D.original(in: catalogue, selection: expected)?.identity, expected.identity, id)
            XCTAssertEqual(C.shown(.held(C.Hold(origin: .goal(market: market, id: id), selection: expected)),
                                   in: page.pass), expected, id)
        }
        for outcome in ["242143190", "242143189"] {
            let expected = selection(Self.liveScope, "64353426", outcome)
            XCTAssertEqual(C.open(both: ref(outcome), in: page.pass),
                           .held(C.Hold(origin: .both(market: 64353426, ref: ref(outcome)), selection: expected)), outcome)
            XCTAssertNotNil(D.original(in: catalogue, selection: expected), outcome)
        }
        for id in ["244237963", "244237965", "244237964"] {
            let expected = selection(Self.liveScope, "63178217", id)
            XCTAssertEqual(C.open(first: id, in: page.pass),
                           .held(C.Hold(origin: .first(market: 63178217, id: id), selection: expected)), id)
            XCTAssertNotNil(D.original(in: catalogue, selection: expected), id)
        }
    }

    /// RETAINED, under the journey/replay route's existing explicit half
    /// admission. Each cell opens its own half's original, compared with the
    /// id the real cell builder made; the bare leg id, or a composed id no
    /// builder made, names no cell.
    func testLiveHalfDetailsOpenEachCellsOwnOriginalAndNeverAComposedId() throws {
        let page = try built(halvesAdmission: .explicit)
        let cells = page.input.halves?.series.flatMap { $0.cells.map(\.id) } ?? []
        XCTAssertEqual(Set(cells), ["63178219:242338171", "63178218:246041831", "63178219:242338170",
                                    "63178218:245875499", "63178219:242338172", "63178218:245681743"])
        let expected: [(cell: String, market: Int, period: String, side: String)] = [
            ("63178219:242338171", 63178219, "first", "242338171"),
            ("63178219:242338170", 63178219, "first", "242338170"),
            ("63178219:242338172", 63178219, "first", "242338172"),
            ("63178218:246041831", 63178218, "second", "246041831"),
            ("63178218:245875499", 63178218, "second", "245875499"),
            ("63178218:245681743", 63178218, "second", "245681743"),
        ]
        for row in expected {
            XCTAssertEqual(C.open(half: row.cell, in: page.pass),
                           .held(C.Hold(origin: .half(market: row.market, period: row.period, id: row.cell),
                                        selection: selection(Self.liveScope, String(row.market), row.side))), row.cell)
        }
        XCTAssertEqual(C.open(half: "242338171", in: page.pass), .unresolved(.halves))
        XCTAssertEqual(C.open(half: "63178218:242338171", in: page.pass), .unresolved(.halves))
    }

    /// RETAINED. After the final the both-teams, first-team and half cards open
    /// their own settled originals under the final catalogue; no admitted goal
    /// market is served, so the goals card and its Details are absent.
    func testFinalBothFirstAndHalfDetailsOpenTheirOwnSettledOriginals() throws {
        let page = try finalPage()
        XCTAssertEqual(page.originals.catalogue?.scope, Self.finalScope)
        XCTAssertNil(page.input.goals)
        XCTAssertNil(C.goalDetails(in: page.pass, hold: nil, show: { _ in }))

        XCTAssertEqual(C.open(both: ref("242143189"), in: page.pass),
                       .held(C.Hold(origin: .both(market: 64353426, ref: ref("242143189")),
                                    selection: selection(Self.finalScope, "64353426", "242143189"))))
        XCTAssertEqual(C.open(first: "244237963", in: page.pass),
                       .held(C.Hold(origin: .first(market: 63178217, id: "244237963"),
                                    selection: selection(Self.finalScope, "63178217", "244237963"))))
        XCTAssertEqual(C.open(half: "63178219:242338171", in: page.pass),
                       .held(C.Hold(origin: .half(market: 63178219, period: "first", id: "63178219:242338171"),
                                    selection: selection(Self.finalScope, "63178219", "242338171"))))
        XCTAssertEqual(C.open(half: "63178218:246041831", in: page.pass),
                       .held(C.Hold(origin: .half(market: 63178218, period: "second", id: "63178218:246041831"),
                                    selection: selection(Self.finalScope, "63178218", "246041831"))))
        XCTAssertNotNil(C.bothDetails(in: page.pass, hold: nil, show: { _ in }))
        XCTAssertNotNil(C.firstDetails(in: page.pass, hold: nil, show: { _ in }))
        XCTAssertNotNil(C.halfDetails(in: page.pass, hold: nil, show: { _ in }))
    }

    /// RETAINED. Before kickoff the goal outlook's two Over milestones and the
    /// exact-score map's served originals open their own rows, scope by scope:
    /// the same score in the other scope is another original, and an id from
    /// one scope does not open in the other.
    func testHullBeforeGoalAndExactMapDetailsOpenServedOriginalsScopeByScope() throws {
        let page = try hull()
        XCTAssertEqual(page.originals.catalogue?.scope, Self.hullBeforeScope)
        XCTAssertEqual(page.input.goals?.milestones.map(\.id), ["238847193", "237512062"])
        for (id, market) in [("238847193", 63390534), ("237512062", 62958651)] {
            XCTAssertEqual(C.open(goal: id, in: page.pass),
                           .held(C.Hold(origin: .goal(market: market, id: id),
                                        selection: selection(Self.hullBeforeScope, String(market), id))), id)
        }

        let full = C.open(exactScope: "full", original: "238846934", in: page.pass)
        let first = C.open(exactScope: "first", original: "244588607", in: page.pass)
        XCTAssertEqual(full, .held(C.Hold(origin: .exact(scope: "full", market: 62939468, period: nil, original: "238846934"),
                                          selection: selection(Self.hullBeforeScope, "62939468", "238846934"))))
        XCTAssertEqual(first, .held(C.Hold(origin: .exact(scope: "first", market: 64002155, period: "first",
                                                          original: "244588607"),
                                           selection: selection(Self.hullBeforeScope, "64002155", "244588607"))))
        XCTAssertNotEqual(hold(full)?.selection, hold(first)?.selection)
        XCTAssertEqual(C.open(exactScope: "first", original: "238846934", in: page.pass), .unresolved(.exact))
        XCTAssertEqual(C.open(exactScope: "full", original: "244588607", in: page.pass), .unresolved(.exact))

        // Every served original of both scopes opens.
        for scope in page.input.exact?.scopes ?? [] {
            for original in scope.originals {
                XCTAssertNotNil(hold(C.open(exactScope: scope.id, original: original.id, in: page.pass)),
                                "\(scope.id) \(original.id)")
            }
        }
    }

    /// CONSTRUCTED owner context: `admittedCards: [.exact]` after the final.
    /// The completed body no longer serves any first-half exact-score row, so
    /// the map keeps the owner's nine held originals — and each of their
    /// Details stays unavailable; the full match's served 2–2 still opens.
    func testHullFinalFirstHalfOriginalsTheBodyNoLongerServesStayUnavailable() throws {
        let page = try built(detail: X.hullFinalDetail, history: nil, markets: X.hullFinalMarkets,
                             admitted: X.hullBeforeAdmission, now: X.finalNow, admittedCards: [.exact])
        XCTAssertEqual(page.input.exact?.phase, .final)
        let first = try XCTUnwrap(page.input.exact?.scopes.first { $0.id == "first" })
        XCTAssertEqual(first.originals.count, 9)
        for original in first.originals {
            XCTAssertEqual(C.open(exactScope: "first", original: original.id, in: page.pass), .unresolved(.exact), original.id)
        }
        XCTAssertEqual(C.open(exactScope: "full", original: "237459055", in: page.pass),
                       .held(C.Hold(origin: .exact(scope: "full", market: 62939468, period: nil, original: "237459055"),
                                    selection: selection(Self.hullFinalScope, "62939468", "237459055"))))
        XCTAssertNotNil(C.exactDetails(in: page.pass, hold: nil, show: { _ in }))
    }

    /// RETAINED. "Real Valladolid CF" names an outcome in three markets
    /// (first team, half time, second half): each card opens its own market's
    /// original — never another one with the same words.
    func testTheSameOutcomeNameInThreeMarketsOpensThreeDifferentOriginals() throws {
        let page = try built(halvesAdmission: .explicit)
        let picks = [
            hold(C.open(first: "244237963", in: page.pass))?.selection,
            hold(C.open(half: "63178219:242338171", in: page.pass))?.selection,
            hold(C.open(half: "63178218:246041831", in: page.pass))?.selection,
        ]
        XCTAssertEqual(picks, [selection(Self.liveScope, "63178217", "244237963"),
                               selection(Self.liveScope, "63178219", "242338171"),
                               selection(Self.liveScope, "63178218", "246041831")])
        // Draw in each half: two originals.
        XCTAssertNotEqual(hold(C.open(half: "63178219:242338170", in: page.pass))?.selection,
                          hold(C.open(half: "63178218:245875499", in: page.pass))?.selection)
    }

    // MARK: - C1: hold the origin, not just a selection (CONSTRUCTED)

    /// CONSTRUCTED admission change (C1 a). The owner moves the goals card from
    /// O/U 2.5 to O/U 5.5 and the both-teams card to another market; the body is
    /// unchanged, so the old AND replacement originals both stay in All props.
    /// The held origins refuse — their markets are no longer admitted — and the
    /// Details show the unavailable view, never the replacement. The reader's
    /// own choices are untouched.
    func testC1aACardMovedToAnotherMarketRefusesItsHeldOriginalWhileBothStayInAllProps() throws {
        let before = try built()
        let goal = try XCTUnwrap(hold(C.open(goal: "242143183", in: before.pass)))
        let both = try XCTUnwrap(hold(C.open(both: ref("242143189"), in: before.pass)))

        var moved = F.liveAdmission // CONSTRUCTED
        moved.goals = [64536538]
        moved.both = 64353427
        let after = try built(admitted: moved)
        let catalogue = after.originals.catalogue
        XCTAssertNotNil(D.original(in: catalogue, selection: goal.selection))
        XCTAssertNotNil(D.original(in: catalogue, selection: selection(Self.liveScope, "64536538", "242765587")))
        XCTAssertNotNil(D.original(in: catalogue, selection: both.selection))
        XCTAssertNotNil(D.original(in: catalogue, selection: selection(Self.liveScope, "64353427", "242143192")))
        XCTAssertEqual(after.input.goals?.milestones.map(\.id), ["242765587"])
        XCTAssertEqual(after.input.both?.marketID, "64353427")

        XCTAssertFalse(C.isAdmitted(goal.origin, in: after.pass))
        XCTAssertFalse(C.isAdmitted(both.origin, in: after.pass))
        XCTAssertNil(C.shown(.held(goal), in: after.pass))
        XCTAssertNil(C.shown(.held(both), in: after.pass))

        // Through the host: no selection — not the replacement — and no choice written.
        let reading = Host.Reading(story: .goals, goal: "242143183", both: "242143189", cardDetails: .held(goal))
        let shown = try built(admitted: moved, reading: reading)
        XCTAssertNil(shown.cardDetailsOriginals.selection)
        XCTAssertEqual(shown.cardDetailsOriginals.catalogue, catalogue)
        XCTAssertEqual(shown.input.goals?.selectedMilestoneID, "242143183")
        XCTAssertEqual(shown.input.both?.selectedOutcomeID, "242143189")
        XCTAssertNil(shown.originals.selection)
        // CONTROL: under the admission it was opened in, the same hold shows.
        XCTAssertEqual(try built(reading: reading).cardDetailsOriginals.selection, goal.selection)
    }

    /// CONSTRUCTED descriptors (C1 b). Scope "full" keeps its id but is rebound
    /// to the first-half market; scope "first" keeps its market but names
    /// another period. Every row stays served and in All props; the rebound
    /// "full" even still lists 238846934 (now as a held, unserved original) —
    /// and each held origin refuses on the admission, never a nearby original.
    func testC1bAnExactScopeReboundToAnotherMarketOrPeriodRefusesItsHeldOriginal() throws {
        let before = try hull()
        let full = try XCTUnwrap(hold(C.open(exactScope: "full", original: "238846934", in: before.pass)))
        let first = try XCTUnwrap(hold(C.open(exactScope: "first", original: "244588607", in: before.pass)))

        var rebound = X.hullBeforeAdmission // CONSTRUCTED
        rebound.exactScore = descriptor(X.hullDescriptor, rebinding: "full", market: 64002155, period: nil)
        let market = try hull(admitted: rebound)
        XCTAssertNotNil(D.original(in: market.originals.catalogue, selection: full.selection))
        XCTAssertTrue(C.isOffered(full.origin, in: market.pass))
        XCTAssertFalse(C.isAdmitted(full.origin, in: market.pass))
        XCTAssertNil(C.shown(.held(full), in: market.pass))
        XCTAssertEqual(C.open(exactScope: "full", original: "238846934", in: market.pass), .unresolved(.exact))

        var period = X.hullBeforeAdmission // CONSTRUCTED
        period.exactScore = descriptor(X.hullDescriptor, rebinding: "first", market: 64002155, period: "second")
        let moved = try hull(admitted: period)
        XCTAssertNotNil(D.original(in: moved.originals.catalogue, selection: first.selection))
        XCTAssertTrue(C.isOffered(first.origin, in: moved.pass))
        XCTAssertFalse(C.isAdmitted(first.origin, in: moved.pass))
        XCTAssertNil(C.shown(.held(first), in: moved.pass))

        // CONTROL: the unchanged descriptor keeps both.
        XCTAssertEqual(C.shown(.held(full), in: before.pass), full.selection)
        XCTAssertEqual(C.shown(.held(first), in: before.pass), first.selection)
    }

    /// CONSTRUCTED admissions (C1 c). Each origin's admission removed in turn —
    /// goals, both teams, first team, the halves, the half card's route context,
    /// the exact-score descriptor — with the body unchanged: every old original
    /// is still in All props and every held Details turns unavailable.
    func testC1cARemovedOriginOrAdmissionRefusesItsHeldOriginal() throws {
        let live = try built(halvesAdmission: .explicit)
        let goal = try XCTUnwrap(hold(C.open(goal: "242143183", in: live.pass)))
        let both = try XCTUnwrap(hold(C.open(both: ref("242143189"), in: live.pass)))
        let first = try XCTUnwrap(hold(C.open(first: "244237963", in: live.pass)))
        let half = try XCTUnwrap(hold(C.open(half: "63178219:242338171", in: live.pass)))

        var noGoals = F.liveAdmission
        noGoals.goals = []
        var noBoth = F.liveAdmission
        noBoth.both = nil
        var noFirst = F.liveAdmission
        noFirst.first = nil
        var noHalves = F.liveAdmission
        noHalves.halves = []
        for (admitted, held) in [(noGoals, goal), (noBoth, both), (noFirst, first), (noHalves, half)] {
            let after = try built(admitted: admitted, halvesAdmission: .explicit)
            XCTAssertNotNil(D.original(in: after.originals.catalogue, selection: held.selection), "\(held.origin)")
            XCTAssertNil(C.shown(.held(held), in: after.pass), "\(held.origin)")
        }

        // The half card leaves the page (the route default during play); its admission stays.
        let routed = try built()
        XCTAssertNil(routed.input.halves)
        XCTAssertTrue(C.isAdmitted(half.origin, in: routed.pass))
        XCTAssertNil(C.shown(.held(half), in: routed.pass))

        let hullBefore = try hull()
        let exact = try XCTUnwrap(hold(C.open(exactScope: "full", original: "238846934", in: hullBefore.pass)))
        var noDescriptor = X.hullBeforeAdmission
        noDescriptor.exactScore = nil
        let gone = try hull(admitted: noDescriptor)
        XCTAssertNil(gone.input.exact)
        XCTAssertNotNil(D.original(in: gone.originals.catalogue, selection: exact.selection))
        XCTAssertNil(C.shown(.held(exact), in: gone.pass))
    }

    /// CONSTRUCTED body edit + admissions (C1 d). Under the existing
    /// `_market_ids` contract, the O/U 2.5 Over row also names market 99000001
    /// (CONSTRUCTED id); its `_market_id` stays 64353423, so its catalogue
    /// identity is the same whichever market the card is admitted under. Moving
    /// the goals card from 64353423 to 99000001 draws the same milestone id and
    /// a fresh tap would open the same selection — but the HELD origin names
    /// 64353423 and refuses. Both markets admitted together draw the id twice:
    /// ambiguous, never resolved.
    func testC1dAMultiMarketAliasKeepsOneCatalogueIdentityButTheMovedOriginStillRefuses() throws {
        let body = try F.editedRow(F.liveMarkets, array: "totals", outcomeID: 242143183,
                                   setting: ["_market_ids": [64353423, 99000001]])
        var own = F.liveAdmission
        own.goals = [64353423]
        var alias = F.liveAdmission
        alias.goals = [99000001]
        let first = try built(markets: body, admitted: own)
        let second = try built(markets: body, admitted: alias)
        XCTAssertEqual(first.input.goals?.milestones.map(\.id), ["242143183"])
        XCTAssertEqual(second.input.goals?.milestones.map(\.id), ["242143183"])

        let held = try XCTUnwrap(hold(C.open(goal: "242143183", in: first.pass)))
        let reopened = try XCTUnwrap(hold(C.open(goal: "242143183", in: second.pass)))
        XCTAssertEqual(held.selection, selection(Self.liveScope, "64353423", "242143183"))
        XCTAssertEqual(reopened.selection, held.selection)
        XCTAssertEqual(reopened.origin, .goal(market: 99000001, id: "242143183"))
        XCTAssertNotEqual(reopened.origin, held.origin)

        XCTAssertTrue(C.isOffered(held.origin, in: second.pass))
        XCTAssertFalse(C.isAdmitted(held.origin, in: second.pass))
        XCTAssertNotNil(D.original(in: second.originals.catalogue, selection: held.selection))
        XCTAssertNil(C.shown(.held(held), in: second.pass))
        XCTAssertEqual(C.shown(.held(held), in: first.pass), held.selection)

        var together = F.liveAdmission
        together.goals = [64353423, 99000001]
        let twice = try built(markets: body, admitted: together)
        XCTAssertEqual(twice.input.goals?.milestones.map(\.id), ["242143183", "242143183"])
        XCTAssertEqual(C.open(goal: "242143183", in: twice.pass), .unresolved(.goals))
        // The held market is still admitted and still resolves alone; the
        // refusal is the card drawing that id twice.
        XCTAssertTrue(C.isAdmitted(held.origin, in: twice.pass))
        XCTAssertEqual(C.resolve(held.origin, in: twice.pass), held.selection)
        XCTAssertFalse(C.isOffered(held.origin, in: twice.pass))
        XCTAssertNil(C.shown(.held(held), in: twice.pass))
    }

    /// CONSTRUCTED body edits, admission and descriptor. For each card type, a
    /// Details held while its id was drawn ONCE refuses on the first pass the
    /// mounted card draws that id twice — every row still drawn, the held
    /// origin's market (and period / scope) still admitted, and the held
    /// original still in All props:
    ///   - goals: O/U 4.5's Over row re-served with O/U 2.5's contributor id;
    ///   - both teams: the No row re-served with the Yes row's contributor id;
    ///   - first team: Neither re-served with Valladolid's contributor id;
    ///   - halves: the half-time market also admitted under a second period id
    ///     (the cell id carries the market and leg, not the period);
    ///   - exact: the descriptor listing the 0–0 original twice in its scope.
    func testAHeldOriginRefusesOnceTheCardDrawsItsIdTwice() throws {
        let live = try built(halvesAdmission: .explicit)

        let goal = try XCTUnwrap(hold(C.open(goal: "242143183", in: live.pass)))
        let goals = try built(markets: try F.editedRow(F.liveMarkets, array: "totals", outcomeID: 242143187,
                                                       setting: ["contributor_outcome_ids": [242143183]]))
        XCTAssertEqual(goals.input.goals?.milestones.map(\.id), ["242143183", "242143183", "242765587"])
        XCTAssertTrue(C.isAdmitted(goal.origin, in: goals.pass))
        XCTAssertEqual(C.resolve(goal.origin, in: goals.pass), goal.selection)
        XCTAssertFalse(C.isOffered(goal.origin, in: goals.pass))
        XCTAssertNil(C.shown(.held(goal), in: goals.pass))
        XCTAssertNotNil(D.original(in: goals.originals.catalogue, selection: goal.selection))
        XCTAssertEqual(C.open(goal: "242143183", in: goals.pass), .unresolved(.goals))

        let both = try XCTUnwrap(hold(C.open(both: ref("242143189"), in: live.pass)))
        let twoYes = try built(markets: try F.editedRow(F.liveMarkets, outcomeID: 242143190,
                                                        setting: ["contributor_outcome_ids": [242143189]]))
        XCTAssertEqual(twoYes.input.both?.outcomes.map(\.id), ["242143189", "242143189"])
        XCTAssertTrue(C.isAdmitted(both.origin, in: twoYes.pass))
        XCTAssertFalse(C.isOffered(both.origin, in: twoYes.pass))
        XCTAssertNil(C.shown(.held(both), in: twoYes.pass))

        let first = try XCTUnwrap(hold(C.open(first: "244237963", in: live.pass)))
        let twoFirst = try built(markets: try F.editedRow(F.liveMarkets, outcomeID: 244237965,
                                                          setting: ["contributor_outcome_ids": [244237963]]))
        XCTAssertEqual(twoFirst.input.first?.overview.map(\.id), ["244237963", "244237963", "244237964"])
        XCTAssertTrue(C.isAdmitted(first.origin, in: twoFirst.pass))
        XCTAssertFalse(C.isOffered(first.origin, in: twoFirst.pass))
        XCTAssertNil(C.shown(.held(first), in: twoFirst.pass))
        XCTAssertNotNil(hold(C.open(first: "244237964", in: twoFirst.pass)))

        let half = try XCTUnwrap(hold(C.open(half: "63178219:242338171", in: live.pass)))
        var extra = F.liveAdmission // CONSTRUCTED: the half-time market under a second period id too
        extra.halves.append(.init(marketID: 63178219, periodID: "extra", label: "Extra"))
        let twoCells = try built(admitted: extra, halvesAdmission: .explicit)
        let cells = (twoCells.input.halves?.series ?? []).flatMap(\.cells).map(\.id)
        XCTAssertEqual(cells.filter { $0 == "63178219:242338171" }.count, 2)
        XCTAssertTrue(C.isAdmitted(half.origin, in: twoCells.pass))
        XCTAssertEqual(C.resolve(half.origin, in: twoCells.pass), half.selection)
        XCTAssertFalse(C.isOffered(half.origin, in: twoCells.pass))
        XCTAssertNil(C.shown(.held(half), in: twoCells.pass))
        XCTAssertNotNil(D.original(in: twoCells.originals.catalogue, selection: half.selection))

        let hullBefore = try hull()
        let exact = try XCTUnwrap(hold(C.open(exactScope: "full", original: "238846934", in: hullBefore.pass)))
        var listedTwice = X.hullBeforeAdmission // CONSTRUCTED
        listedTwice.exactScore = try descriptor(X.hullDescriptor, listingTwice: 238846934, in: "full")
        let twoScores = try hull(admitted: listedTwice)
        let full = try XCTUnwrap(twoScores.input.exact?.scopes.first { $0.id == "full" })
        XCTAssertEqual(full.originals.filter { $0.id == "238846934" }.count, 2)
        XCTAssertTrue(C.isAdmitted(exact.origin, in: twoScores.pass))
        XCTAssertEqual(C.resolve(exact.origin, in: twoScores.pass), exact.selection)
        XCTAssertFalse(C.isOffered(exact.origin, in: twoScores.pass))
        XCTAssertNil(C.shown(.held(exact), in: twoScores.pass))
        XCTAssertNotNil(D.original(in: twoScores.originals.catalogue, selection: exact.selection))
        // Another score in the same scope, still drawn once, still opens.
        XCTAssertNotNil(hold(C.open(exactScope: "full", original: "237459055", in: twoScores.pass)))
    }

    // MARK: - Refusals

    /// RETAINED (the live and final bodies, each at its own clock). The same
    /// cards and ids after the final resolve under the final catalogue, so the
    /// originals held during play turn unavailable rather than move over.
    func testAPhaseChangeNeverCarriesAHeldOriginalIntoTheNextCatalogue() throws {
        let live = try built(halvesAdmission: .explicit)
        let after = try finalPage()
        let holds = try [
            XCTUnwrap(hold(C.open(both: ref("242143189"), in: live.pass))),
            XCTUnwrap(hold(C.open(first: "244237963", in: live.pass))),
            XCTUnwrap(hold(C.open(half: "63178219:242338171", in: live.pass))),
        ]
        for held in holds {
            XCTAssertTrue(C.isOffered(held.origin, in: after.pass), "\(held.origin)")
            XCTAssertTrue(C.isAdmitted(held.origin, in: after.pass), "\(held.origin)")
            XCTAssertEqual(C.resolve(held.origin, in: after.pass)?.scope, Self.finalScope, "\(held.origin)")
            XCTAssertNil(C.shown(.held(held), in: after.pass), "\(held.origin)")
        }
    }

    /// CONSTRUCTED body edits. The held Yes row re-served under another venue
    /// is another identity; withdrawn, it is no longer drawn. Either way the
    /// held Details turn unavailable — a fresh tap on the re-sourced row opens
    /// the new identity, never the held one.
    func testASourceEditOrAWithdrawnRowRefusesTheHeldOriginal() throws {
        let live = try built()
        let held = try XCTUnwrap(hold(C.open(both: ref("242143189"), in: live.pass)))

        let resourced = try built(markets: try F.editedRow(F.liveMarkets, outcomeID: 242143189,
                                                           setting: ["source": "kalshi"]))
        XCTAssertNil(C.shown(.held(held), in: resourced.pass))
        XCTAssertEqual(hold(C.open(both: ref("242143189"), in: resourced.pass))?.selection,
                       selection(Self.liveScope, "64353426", "242143189", source: "kalshi"))

        let withdrawn = try built(markets: try removingRow(F.liveMarkets, outcomeID: 242143189))
        XCTAssertEqual(withdrawn.input.both?.outcomes.map(\.id), ["242143190"])
        XCTAssertFalse(C.isOffered(held.origin, in: withdrawn.pass))
        XCTAssertNil(C.shown(.held(held), in: withdrawn.pass))
        XCTAssertEqual(C.open(both: ref("242143189"), in: withdrawn.pass), .unresolved(.both))
        XCTAssertNotNil(hold(C.open(both: ref("242143190"), in: withdrawn.pass)))
    }

    /// CONSTRUCTED body edits. The No row re-served with the Yes row's
    /// contributor id makes that id two rows: ambiguous, so neither opens and
    /// the previously held Yes turns unavailable. When EVERY row a mounted card
    /// draws is ambiguous (both teams here; all three first-team rows below),
    /// the card offers no Details control at all.
    func testDuplicatedIdsAreAmbiguousAndAnAllUnresolvableCardOffersNoDetails() throws {
        let live = try built()
        let held = try XCTUnwrap(hold(C.open(both: ref("242143189"), in: live.pass)))
        let duplicated = try built(markets: try F.editedRow(F.liveMarkets, outcomeID: 242143190,
                                                            setting: ["contributor_outcome_ids": [242143189]]))
        XCTAssertEqual(duplicated.input.both?.outcomes.map(\.id), ["242143189", "242143189"])
        XCTAssertEqual(C.open(both: ref("242143189"), in: duplicated.pass), .unresolved(.both))
        XCTAssertNil(C.shown(.held(held), in: duplicated.pass))
        XCTAssertNil(C.bothDetails(in: duplicated.pass, hold: nil, show: { _ in }))
        XCTAssertNotNil(C.goalDetails(in: duplicated.pass, hold: nil, show: { _ in }))

        var body = F.liveMarkets
        for outcome in [244237965, 244237964] {
            body = try F.editedRow(body, outcomeID: outcome, setting: ["contributor_outcome_ids": [244237963]])
        }
        let first = try built(markets: body)
        XCTAssertEqual(first.input.first?.overview.map(\.id), ["244237963", "244237963", "244237963"])
        XCTAssertEqual(C.open(first: "244237963", in: first.pass), .unresolved(.first))
        XCTAssertNil(C.firstDetails(in: first.pass, hold: nil, show: { _ in }))
    }

    /// CONSTRUCTED refs, descriptor and ids. Another event's or another
    /// market's ref, another event's descriptor, an unknown id, an outcome
    /// name or a score label, and an unknown scope never open anything.
    func testForeignRefsDescriptorsUnknownIdsAndLabelsNeverResolve() throws {
        let live = try built()
        XCTAssertEqual(C.open(both: ref("242143189", event: "15311089"), in: live.pass), .unresolved(.both))
        XCTAssertEqual(C.open(both: ref("242143189", market: "64353427"), in: live.pass), .unresolved(.both))
        XCTAssertEqual(C.open(both: ref("Yes"), in: live.pass), .unresolved(.both))
        XCTAssertEqual(C.open(goal: "999", in: live.pass), .unresolved(.goals))
        XCTAssertEqual(C.open(first: "Real Valladolid CF", in: live.pass), .unresolved(.first))
        XCTAssertEqual(C.open(half: "63178219:242338171", in: live.pass), .unresolved(.halves)) // not mounted here
        XCTAssertEqual(C.open(exactScope: "full", original: "238846934", in: live.pass), .unresolved(.exact))

        let hullBefore = try hull()
        XCTAssertEqual(C.open(exactScope: "full", original: "Hull City AFC 0 - 0 Everton FC", in: hullBefore.pass),
                       .unresolved(.exact))
        XCTAssertEqual(C.open(exactScope: "missing", original: "238846934", in: hullBefore.pass), .unresolved(.exact))

        var foreign = X.hullBeforeAdmission // CONSTRUCTED
        foreign.exactScore = E.Descriptor(eventID: 15325054, scopes: X.hullDescriptor.scopes)
        let other = try hull(admitted: foreign)
        XCTAssertNil(other.input.exact)
        XCTAssertNil(other.pass.descriptor)
        XCTAssertEqual(C.open(exactScope: "full", original: "238846934", in: other.pass), .unresolved(.exact))
        XCTAssertNil(C.exactDetails(in: other.pass, hold: nil, show: { _ in }))
    }

    /// RETAINED. A tap that opened nothing stays the unavailable view on every
    /// later pass, even one on which the same id would resolve.
    func testAnUnresolvedTapStaysUnavailableOnEveryLaterPass() throws {
        let live = try built()
        XCTAssertNotNil(hold(C.open(both: ref("242143189"), in: live.pass)))
        XCTAssertNil(C.shown(.unresolved(.both), in: live.pass))
        let page = try built(reading: Host.Reading(cardDetails: .unresolved(.both)))
        XCTAssertNil(page.cardDetailsOriginals.selection)
        XCTAssertEqual(page.cardDetailsOriginals.catalogue, page.originals.catalogue)
    }

    // MARK: - Callbacks and the one hold (C2)

    /// RETAINED. Building every Details callback, resolving and revalidating
    /// call nothing. A tap asks the supplied hold once, then hands the host
    /// exactly what it opened.
    func testBuildingCallbacksResolvingAndRevalidatingCallNothing() throws {
        let log = Log()
        var opened: [C.Opened] = []
        let hold = { log.lines.append("hold") }
        let show: (C.Opened) -> Void = { log.lines.append("show"); opened.append($0) }
        let live = try built(halvesAdmission: .explicit)
        let goals = C.goalDetails(in: live.pass, hold: hold, show: show)
        let both = C.bothDetails(in: live.pass, hold: hold, show: show)
        let first = C.firstDetails(in: live.pass, hold: hold, show: show)
        let halves = C.halfDetails(in: live.pass, hold: hold, show: show)
        XCTAssertNil(C.exactDetails(in: live.pass, hold: hold, show: show)) // no map during play here
        let hullPage = try hull()
        let exact = C.exactDetails(in: hullPage.pass, hold: hold, show: show)
        let goal = C.open(goal: "242143183", in: live.pass)
        _ = C.shown(goal, in: live.pass)
        _ = C.offered(.both, in: live.pass)
        XCTAssertEqual(log.lines, [])
        XCTAssertEqual(opened, [])

        goals?("242143183")
        XCTAssertEqual(log.lines, ["hold", "show"])
        XCTAssertEqual(opened, [goal])
        both?(ref("242143190"))
        first?("244237964")
        halves?("63178218:245681743")
        exact?("first", "242337399")
        XCTAssertEqual(log.lines, Array(repeating: ["hold", "show"], count: 5).flatMap { $0 })
        XCTAssertEqual(opened.count, 5)
        XCTAssertTrue(opened.allSatisfy { self.hold($0) != nil })
    }

    /// RETAINED. On the page a card's Details sit in the story stream: the
    /// real stream's activation asks the stream's hold first, then the host's
    /// callback — built with no hold of its own (`detailsHold(.page, _)` is
    /// nil) — opens the Details. Exactly one hold, in that order, for each of
    /// the five cards.
    func testACompactCardDetailsTapAsksTheStreamHoldOnceAndTheHostAddsNone() throws {
        let log = Log()
        let hostHold = { log.lines.append("host hold") }
        XCTAssertNil(Host.detailsHold(.page, hostHold))
        let show: (C.Opened) -> Void = { opened in
            log.lines.append(self.hold(opened) == nil ? "open:unavailable" : "open:exact")
        }

        let liveCases: [(SoccerEventPageCard10868, String)] = [(.goals, "goals"), (.both, "both"), (.first, "first"),
                                                              (.halves, "halves")]
        for (card, id) in liveCases {
            log.lines = []
            let page = try built(halvesAdmission: .explicit, reading: Host.Reading(story: card))
            XCTAssertEqual(page.input.stream.primary?.id, id)
            let hold = Host.detailsHold(.page, hostHold)
            let view = SoccerEventPagePresentation10868(
                input: page.input,
                onGoalDetails: C.goalDetails(in: page.pass, hold: hold, show: show),
                onBothDetails: C.bothDetails(in: page.pass, hold: hold, show: show),
                onFirstDetails: C.firstDetails(in: page.pass, hold: hold, show: show),
                onHalfDetails: C.halfDetails(in: page.pass, hold: hold, show: show))
            let active = activation(page.input, id, log: log)
            XCTAssertEqual(active.intents, [.interaction(scope: page.input.stream.scope, card: active.card)])
            switch card {
            case .goals: try XCTUnwrap(view.goalsContent(activation: active)).onDetails?("242143183")
            case .both: try XCTUnwrap(view.bothContent(activation: active)).onDetails?(ref("242143189"))
            case .first: try XCTUnwrap(view.firstContent(activation: active)).onDetails?("244237963")
            default: try XCTUnwrap(view.halvesContent(activation: active)).onDetails?("63178219:242338171")
            }
            XCTAssertEqual(log.lines, ["stream hold:\(id)", "open:exact"], id)
        }

        log.lines = []
        let hullPage = try hull(reading: Host.Reading(story: .exact))
        XCTAssertEqual(hullPage.input.stream.primary?.id, "exact")
        let view = SoccerEventPagePresentation10868(
            input: hullPage.input,
            onExactDetails: C.exactDetails(in: hullPage.pass, hold: Host.detailsHold(.page, hostHold), show: show))
        let active = activation(hullPage.input, "exact", log: log)
        try XCTUnwrap(view.exactContent(activation: active)).onDetails?("full", "238846934")
        XCTAssertEqual(log.lines, ["stream hold:exact", "open:exact"])
    }

    /// RETAINED. In full-size content there is no activation: the host's
    /// callback asks the page's hold exactly once, before the Details open —
    /// for each of the five cards. The presenter's generic `open` is never
    /// involved.
    func testAFullSizeCardDetailsTapAsksThePageHoldExactlyOnceBeforeOpening() throws {
        let log = Log()
        let pageHold = { log.lines.append("hold") }
        let show: (C.Opened) -> Void = { _ in log.lines.append("open") }

        let live = try built(halvesAdmission: .explicit, reading: Host.Reading(readerOpen: true))
        for card in [SoccerEventPageCard10868.goals, .both, .first, .halves] {
            log.lines = []
            let mode = SoccerEventPageMode10868.reader(card)
            let hold = Host.detailsHold(mode, pageHold)
            XCTAssertNotNil(hold)
            let reader = SoccerEventPagePresentation10868(
                input: live.input, mode: mode,
                onGoalDetails: C.goalDetails(in: live.pass, hold: hold, show: show),
                onBothDetails: C.bothDetails(in: live.pass, hold: hold, show: show),
                onFirstDetails: C.firstDetails(in: live.pass, hold: hold, show: show),
                onHalfDetails: C.halfDetails(in: live.pass, hold: hold, show: show))
            switch card {
            case .goals: try XCTUnwrap(reader.goalsContent()).onDetails?("242143183")
            case .both: try XCTUnwrap(reader.bothContent()).onDetails?(ref("242143189"))
            case .first: try XCTUnwrap(reader.firstContent()).onDetails?("244237963")
            default: try XCTUnwrap(reader.halvesContent()).onDetails?("63178219:242338171")
            }
            XCTAssertEqual(log.lines, ["hold", "open"], "\(card)")
        }

        log.lines = []
        let hullPage = try hull(reading: Host.Reading(readerOpen: true))
        let mode = SoccerEventPageMode10868.reader(.exact)
        let reader = SoccerEventPagePresentation10868(
            input: hullPage.input, mode: mode,
            onExactDetails: C.exactDetails(in: hullPage.pass, hold: Host.detailsHold(mode, pageHold), show: show))
        try XCTUnwrap(reader.exactContent()).onDetails?("full", "238846934")
        XCTAssertEqual(log.lines, ["hold", "open"])
    }

    // MARK: - Layers and return

    /// CONSTRUCTED layer sequences. One sheet: Details over a full-size card
    /// keep that card's sheet identity and Done returns to the card; Details
    /// from the page return to the page; a swipe returns to the page; opening
    /// another mode replaces the Details.
    func testSessionKeepsOneSheetAndDoneReturnsToTheCardOrThePage() throws {
        let live = try built()
        let held = C.open(both: ref("242143189"), in: live.pass)
        XCTAssertNotNil(hold(held))

        var session = Host.Session()
        session.open(.reader(.both))
        XCTAssertEqual(session.presented?.id, "reader.both")
        session.openCardDetails(held)
        XCTAssertEqual(session.presented?.id, "reader.both")
        XCTAssertEqual(session.base, SoccerEventPageMode10868.reader(.both))
        session.close()
        XCTAssertEqual(session, Host.Session(base: .reader(.both), cardDetails: nil))
        XCTAssertEqual(session.presented?.id, "reader.both")
        session.close()
        XCTAssertNil(session.presented)

        session.openCardDetails(held)
        XCTAssertEqual(session.presented?.id, "page")
        session.close()
        XCTAssertEqual(session, Host.Session())
        XCTAssertNil(session.presented)

        session.open(.reader(.goals))
        session.openCardDetails(held)
        session.dismiss()
        XCTAssertEqual(session, Host.Session())

        session.open(.reader(.both))
        session.openCardDetails(held)
        session.open(.catalogue)
        XCTAssertEqual(session, Host.Session(base: .catalogue, cardDetails: nil))

        session.dismiss()
        session.open(.reader(.first))
        session.openCardDetails(.unresolved(.first))
        XCTAssertEqual(session.presented?.id, "reader.first")
        session.open(.page)
        XCTAssertEqual(session, Host.Session())
    }

    /// CONSTRUCTED reader choices. Opening a card's Details and closing them
    /// writes none of the story, outcome, milestone, first-team, exact-scope or
    /// score choices or the All props selection: the page input is identical
    /// before, during and after, and the Details show the held selection only
    /// while open. Under C1 (a)'s replacement the choices are still unchanged.
    func testOpeningAndClosingACardsDetailsKeepsTheReadersChoices() throws {
        let choices = Host.Reading(story: .both, goal: "242143187", both: "242143190", first: "244237964",
                                   readerOpen: true)
        let before = try built(reading: choices)
        let held = try XCTUnwrap(hold(C.open(both: ref("242143189"), in: before.pass)))

        var session = Host.Session()
        session.open(.reader(.both))
        session.openCardDetails(.held(held))
        var during = choices
        during.cardDetails = session.cardDetails
        let shown = try built(reading: during)
        XCTAssertEqual(shown.input, before.input)
        XCTAssertEqual(shown.cardDetailsOriginals.selection, held.selection)
        XCTAssertNil(shown.originals.selection)

        session.close()
        XCTAssertEqual(session.presented?.id, "reader.both")
        var after = choices
        after.cardDetails = session.cardDetails
        let back = try built(reading: after)
        XCTAssertEqual(back.input, before.input)
        XCTAssertEqual(back.input.stream.primary?.id, "both")
        XCTAssertEqual(back.input.both?.selectedOutcomeID, "242143190")
        XCTAssertEqual(back.input.goals?.selectedMilestoneID, "242143187")
        XCTAssertEqual(back.input.first?.selectedID, "244237964")
        XCTAssertNil(back.cardDetailsOriginals.selection)

        var moved = F.liveAdmission // CONSTRUCTED, as in C1 (a)
        moved.both = 64353427
        let replaced = try built(admitted: moved, reading: during)
        XCTAssertNil(replaced.cardDetailsOriginals.selection)
        XCTAssertEqual(replaced.input.both?.selectedOutcomeID, "242143190")
        XCTAssertEqual(replaced.input.stream.primary?.id, "both")

        let exactChoices = Host.Reading(story: .exact, exactScope: "first",
                                        exactOriginals: ["first": "242337399", "full": "237459055"], readerOpen: true)
        let map = try hull(reading: exactChoices)
        let exact = try XCTUnwrap(hold(C.open(exactScope: "full", original: "238846934", in: map.pass)))
        var exactOpen = exactChoices
        exactOpen.cardDetails = .held(exact)
        let mapOpen = try hull(reading: exactOpen)
        XCTAssertEqual(mapOpen.input, map.input)
        XCTAssertEqual(mapOpen.input.exact?.selectedScopeID, "first")
        XCTAssertEqual(mapOpen.input.exact?.selectedOriginalID, "242337399")
        XCTAssertEqual(mapOpen.cardDetailsOriginals.selection, exact.selection)
    }

    // MARK: - Per-pass lookups

    /// CONSTRUCTED edits and admission. Each pass builds its lookups once from
    /// its own inputs: the legs of exactly the admitted markets, each half's
    /// legs with their builder cell ids, and every served row by identity side
    /// — duplicates kept, so the ambiguity refusal still sees them. A pass
    /// with no admission reads no served rows; a fresh pass sees a changed body.
    func testEachPassBuildsItsLookupsOnceAndKeepsEveryDuplicate() throws {
        let live = try built(halvesAdmission: .explicit)
        XCTAssertEqual(Set(live.pass.legsByMarket.keys),
                       [64353423, 64353425, 64536538, 64353426, 63178217, 63178219, 63178218])
        XCTAssertEqual(live.pass.legs(64353426).map(\.id), ["242143190", "242143189"])
        XCTAssertEqual(live.pass.legs(63178228), [])
        XCTAssertEqual(live.pass.halfCells.map { $0.map(\.id) },
                       [["63178219:242338171", "63178219:242338172", "63178219:242338170"],
                        ["63178218:246041831", "63178218:245875499", "63178218:245681743"]])
        XCTAssertEqual(live.pass.servedBySide["242143189"]?.map(\.identity),
                       [D.Identity(source: "polymarket", market: "64353426", side: "242143189")])

        let duplicated = try built(markets: try F.editedRow(F.liveMarkets, outcomeID: 242143190,
                                                            setting: ["contributor_outcome_ids": [242143189]]))
        XCTAssertEqual(duplicated.pass.servedBySide["242143189"]?.count, 2)
        XCTAssertEqual(duplicated.pass.legs(64353426).map(\.id), ["242143189", "242143189"])

        let none = try built(admitted: R.Markets())
        XCTAssertTrue(none.pass.legsByMarket.isEmpty)
        XCTAssertTrue(none.pass.servedBySide.isEmpty)
        XCTAssertNil(C.goalDetails(in: none.pass, hold: nil, show: { _ in }))

        let resourced = try built(markets: try F.editedRow(F.liveMarkets, outcomeID: 242143189,
                                                           setting: ["source": "kalshi"]))
        XCTAssertEqual(resourced.pass.servedBySide["242143189"]?.map(\.identity.source), ["kalshi"])
    }
}
