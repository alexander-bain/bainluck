import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 tennis own markets — a tennis match lists and opens only ITS OWN
/// original props and results, and keeps the reader's held selection.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: a tennis match lists and opens only its
/// own original props and results, preserving the reader's held selection.
///
/// PREPARED, NOT RUN: written under a source-only hold (parse only; no build,
/// no XCTest, no simulator, no render).
///
/// What was exposed: the history, the dated reading and supplied story cards
/// already check this event's id (`TennisHistoryAdapter10868.admitted`,
/// `cards?.eventID`). `/game-markets` → host → `TennisOriginalsAdapter10868.originals`
/// did not: its catalogue AND its matrix read any body. Now the body is this
/// match's only when its `eventId` is exactly `event.id`
/// (`HockeyJourneyContributionAdapter10868.ownMarkets`, reused unchanged),
/// decided once in the host and checked again in `originals` before either is
/// read. Another match's body reads exactly as no body.
///
/// REAL retained bodies (unedited internal fixture strings, sha256 and subsets
/// written in their own files): the Fils–van de Zandschulp live match 15327807
/// (`TennisMatchPageAdapter10868Tests.liveDetail`, `TennisHistoryAdapter10868Tests.liveHistory`,
/// `TennisOriginalsAdapter10868Tests.liveMarkets`) and the Davidovich Fokina–Tiafoe
/// final 15327291 (`finalDetail`, `finalHistory`, `finalMarkets`). Each match's
/// real markets body is the other match's FOREIGN case.
///
/// CONSTRUCTED, named where used, no genuine-evidence credit: the before-the-start
/// state (the live detail with `status: scheduled` and `commence_time` 13:00Z,
/// exactly as `TennisOriginalsAdapter10868Tests` constructs it); a markets body
/// with only its `event_id` relabelled (the other match's id for the own bytes;
/// this match's id for the foreign bytes — the RELABEL CONTROL that must list
/// again); a held selection; and owner-supplied story cards with no routes.
@MainActor
final class TennisMarketsIdentity10868Tests: XCTestCase {
    private typealias O = TennisOriginalsAdapter10868
    private typealias Host = TennisEventPageHost10868
    private typealias Fixtures = TennisMatchPageAdapter10868Tests
    private typealias Markets = TennisOriginalsAdapter10868Tests
    private typealias Histories = TennisHistoryAdapter10868Tests
    private typealias Screen = TennisEventPagePresentation10868Tests
    private typealias Details = OriginalMarketDetails9483

    private static let liveID = 15327807
    private static let finalID = 15327291

    /// CONSTRUCTED: the same served bytes with only `event_id` changed.
    private func relabelled(_ json: String, eventId: Int) throws -> GameMarketsResponse {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        object["event_id"] = eventId
        return try Fixtures.decoder().decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private func reader(_ now: String) throws -> O.Host {
        O.Host(now: try XCTUnwrap(now.asDate), calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    private struct Case {
        let label: String
        let event: EventDetail
        let history: EventHistoryResponse
        let ownJSON: String
        let foreignJSON: String
        let otherID: Int
        let now: String
        let phase: String
        /// The count the existing suites pin for the real state; nil for the CONSTRUCTED state.
        let count: Int?
    }

    private func cases() throws -> [Case] {
        [
            Case(label: "before (CONSTRUCTED scheduled 15327807)",
                 event: try Fixtures.edited(Fixtures.liveDetail, ["status": "scheduled",
                                                                  "commence_time": "2026-10-12T13:00:00+00:00"]),
                 history: try Histories.live(), ownJSON: Markets.liveMarkets, foreignJSON: Markets.finalMarkets,
                 otherID: Self.finalID, now: Fixtures.liveReadAt, phase: "before", count: nil),
            Case(label: "during (real 15327807)", event: try Fixtures.detail(Fixtures.liveDetail),
                 history: try Histories.live(), ownJSON: Markets.liveMarkets, foreignJSON: Markets.finalMarkets,
                 otherID: Self.finalID, now: Fixtures.liveReadAt, phase: "during", count: 12),
            Case(label: "final (real 15327291)", event: try Fixtures.detail(Fixtures.finalDetail),
                 history: try Histories.finished(), ownJSON: Markets.finalMarkets, foreignJSON: Markets.liveMarkets,
                 otherID: Self.liveID, now: Fixtures.finalReadAt, phase: "final", count: 18),
        ]
    }

    private func decoded(_ json: String) throws -> GameMarketsResponse {
        try Fixtures.decoder().decode(GameMarketsResponse.self, from: Data(json.utf8))
    }

    /// Every field of the originals group a reader can see or open.
    private func assertSameOriginals(_ a: TennisEventPageOriginals10868, _ b: TennisEventPageOriginals10868,
                                     _ message: String, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(a.catalogue, b.catalogue, message, file: file, line: line)
        XCTAssertEqual(a.selection, b.selection, message, file: file, line: line)
        XCTAssertEqual(a.recorded, b.recorded, message, file: file, line: line)
        XCTAssertEqual(a.labels, b.labels, message, file: file, line: line)
        XCTAssertEqual(a.context, b.context, message, file: file, line: line)
        XCTAssertEqual(a.heading, b.heading, message, file: file, line: line)
        XCTAssertEqual(a.emptyWords, b.emptyWords, message, file: file, line: line)
        XCTAssertEqual(a.unavailableChoice, b.unavailableChoice, message, file: file, line: line)
    }

    func testOwnershipIsTheExactServedIdThroughTheReusedHelper() throws {
        let live = try Fixtures.detail(Fixtures.liveDetail)
        let own = try Markets.live()
        let foreign = try Markets.finished()
        XCTAssertEqual(own.eventId, Self.liveID)
        XCTAssertEqual(foreign.eventId, Self.finalID)
        XCTAssertEqual(HockeyJourneyContributionAdapter10868.ownMarkets(own, for: live), own)
        XCTAssertNil(HockeyJourneyContributionAdapter10868.ownMarkets(foreign, for: live))
        XCTAssertNil(HockeyJourneyContributionAdapter10868.ownMarkets(nil, for: live))
    }

    /// Real own bodies (and the CONSTRUCTED before state): every original still lists, in the
    /// counts and scopes the existing suites pin, and the host's originals are the direct reader's.
    func testThisMatchsOwnBodyStillListsEveryOriginal() throws {
        for c in try cases() {
            let direct = O.originals(c.event, markets: try decoded(c.ownJSON), host: try reader(c.now), tint: .blue)
            let catalogue = try XCTUnwrap(direct.catalogue, c.label)
            XCTAssertFalse(catalogue.originals.isEmpty, c.label)
            if let count = c.count {
                XCTAssertEqual(catalogue.originals.count, count, c.label)
                XCTAssertEqual(direct.context, O.Words.context(count), c.label)
            }
            XCTAssertEqual(catalogue.scope, "tennis:\(c.event.id):\(c.phase):originals", c.label)
            let hosted = Host.build(event: c.event, history: c.history, markets: try decoded(c.ownJSON),
                                    probabilityObservedAt: c.event.heroProbabilityObservedAt?.asDate,
                                    now: try XCTUnwrap(c.now.asDate), calendar: Fixtures.pacific, locale: Fixtures.locale)
            XCTAssertEqual(hosted.originals.catalogue, direct.catalogue, c.label)
            XCTAssertEqual(hosted.originals.labels, direct.labels, c.label)
            // The same bytes relabelled to this match's own id are this match's body (CONSTRUCTED).
            let same = O.originals(c.event, markets: try relabelled(c.ownJSON, eventId: c.event.id),
                                   host: try reader(c.now), tint: .blue)
            assertSameOriginals(same, direct, c.label)
        }
    }

    /// The direct reader: a real other match's body, and this match's own bytes under another
    /// match's id (CONSTRUCTED), each list exactly what no body lists — the held selection kept.
    func testAnotherMatchsBodyListsNothingAtTheDirectReader() throws {
        for c in try cases() {
            let host = try reader(c.now)
            let held = Details.Selection(scope: O.scope(c.event, phase: TennisMatchPageAdapter10868.phase(c.event, now: host.now)),
                                         identity: Details.Identity(source: "polymarket", market: "1", side: "1"))
            let missing = O.originals(c.event, markets: nil, host: host, tint: .blue, selection: held)
            for body in [try decoded(c.foreignJSON), try relabelled(c.ownJSON, eventId: c.otherID)] {
                let read = O.originals(c.event, markets: body, host: host, tint: .blue, selection: held)
                XCTAssertNil(read.catalogue, c.label)
                XCTAssertTrue(read.labels.isEmpty, c.label)
                XCTAssertNil(read.context, c.label)
                XCTAssertEqual(read.selection, held, "the reader's own held selection is kept")
                assertSameOriginals(read, missing, c.label)
            }
            // RELABEL CONTROL: the foreign bytes under this match's id list again (CONSTRUCTED).
            let control = O.originals(c.event, markets: try relabelled(c.foreignJSON, eventId: c.event.id),
                                      host: host, tint: .blue)
            XCTAssertNotNil(control.catalogue, c.label)
        }
    }

    /// The event-less matrix primitive still describes the body it is given; only the
    /// event-aware entry refuses another match's body.
    func testTheMatrixPrimitiveDescribesTheBodyItIsGiven() throws {
        let final = try Fixtures.detail(Fixtures.finalDetail)
        let foreign = try Markets.live()
        XCTAssertEqual(O.matrix(foreign)?.questions.count, 7)
        XCTAssertNil(O.originals(final, markets: foreign, host: try reader(Fixtures.finalReadAt), tint: .blue).catalogue)
    }

    /// The host: another match's body builds exactly the no-markets page. The own headline,
    /// history, dated reading, held selection and admitted story cards stand.
    func testTheHostBuildsTheNoMarketsPageFromAnotherMatchsBody() throws {
        for c in try cases() {
            let now = try XCTUnwrap(c.now.asDate)
            let held = Details.Selection(scope: O.scope(c.event, phase: TennisMatchPageAdapter10868.phase(c.event, now: now)),
                                         identity: Details.Identity(source: "polymarket", market: "1", side: "1"))
            func build(_ body: GameMarketsResponse?) -> Host.Built {
                Host.build(event: c.event, history: c.history, markets: body,
                           probabilityObservedAt: c.event.heroProbabilityObservedAt?.asDate, now: now,
                           reading: Host.Reading(selection: held), calendar: Fixtures.pacific, locale: Fixtures.locale)
            }
            let missing = build(nil)
            let own = build(try decoded(c.ownJSON))
            for body in [try decoded(c.foreignJSON), try relabelled(c.ownJSON, eventId: c.otherID)] {
                let page = build(body)
                XCTAssertEqual(page.input, missing.input, c.label)
                assertSameOriginals(page.originals, missing.originals, c.label)
                XCTAssertNil(page.originals.catalogue, c.label)
                XCTAssertNil(page.input.copy.allPropsLabel, c.label)
                XCTAssertEqual(page.originals.selection, held, "the reader's own held selection is kept")
                XCTAssertEqual(page.input.headline, own.input.headline, "the own headline stands")
                XCTAssertEqual(page.input.history, own.input.history, "the own history stands")
                XCTAssertEqual(page.input.reading, own.input.reading, "the own dated reading stands")
            }
            XCTAssertNotNil(own.originals.catalogue, c.label)
            XCTAssertNotNil(own.input.copy.allPropsLabel, c.label)
        }
    }

    /// CONSTRUCTED owner cards for the final, with no routes: admitted by their own event id
    /// whatever markets body is held, so the typed-card channel is independent of All props.
    func testAdmittedStoryCardsStandBesideAnotherMatchsBody() throws {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        let cards = TennisCardsAdapter10868.Supplied(eventID: Self.finalID, sets: Screen.sets(.final),
                                                     totals: Screen.totals(.final), exact: Screen.exact(.final))
        func build(_ body: GameMarketsResponse?) throws -> Host.Built {
            Host.build(event: event, history: try Histories.finished(), markets: body, probabilityObservedAt: nil,
                       now: try XCTUnwrap(Fixtures.finalReadAt.asDate), cards: cards,
                       calendar: Fixtures.pacific, locale: Fixtures.locale)
        }
        let own = try build(try Markets.finished())
        let foreign = try build(try Markets.live())
        let missing = try build(nil)
        XCTAssertEqual(foreign.input, missing.input)
        XCTAssertEqual(foreign.cards, cards)
        XCTAssertEqual(own.cards, cards)
        // No routes: no Details is offered in either, so the cards themselves are the same.
        XCTAssertEqual(foreign.input.sets, own.input.sets)
        XCTAssertEqual(foreign.input.totals, own.input.totals)
        XCTAssertEqual(foreign.input.exact, own.input.exact)
        XCTAssertNil(foreign.originals.catalogue)
        XCTAssertNotNil(own.originals.catalogue)
    }
}
