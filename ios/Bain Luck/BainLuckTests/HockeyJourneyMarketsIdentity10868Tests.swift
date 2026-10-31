import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 F1b — a hockey page's points and assists cards and its "All props"
/// come only from ITS OWN `/game-markets` body.
///
/// PILLARS: TRUTH / FORMATTING / DISCOVER. SHIP: hockey props, grades and All
/// props counts stay attached to the game the reader opened.
///
/// PREPARED, NOT RUN: written under a source-only hold (parse only; no build,
/// no XCTest, no render).
///
/// The rule: the body is this game's only when its `eventId` is exactly
/// `event.id` (`HockeyJourneyContributionAdapter10868.ownMarkets`). Another
/// game's body reads exactly as no body. The host decides this once; `ladders`
/// and `originals` check it again themselves. `matched` / `sources` are
/// unchanged and describe the body they are given.
///
/// REAL retained bodies: the internal fixtures of
/// `HockeyJourneyContributionAdapter10868Tests` — wildBruins 15169793 (final),
/// islandersWild 15338034 (final), devilsKnights 15338496 (scheduled), each a
/// detail and its markets. Each game's real markets body is another game's
/// FOREIGN case.
///
/// CONSTRUCTED, named where used: a decoded `status` set to `live` (no live NHL
/// body is retained); the SAME-MATCHUP STAND-IN — a game's own markets with only
/// `event_id` relabelled to another game's id, the discriminating case for the
/// cards (a real other game's body already deals no card, because
/// `PlayerPropsStatLabel.display` keeps a matchup prefix that does not name both
/// of the page's teams; no real rematch leak is claimed); and the RELABEL
/// CONTROL — a foreign body relabelled to this game's id, which must list again.
@MainActor
final class HockeyJourneyMarketsIdentity10868Tests: XCTestCase {
    private typealias C = HockeyJourneyContributionAdapter10868
    private typealias O = HockeyJourneyOriginalsAdapter10868
    private typealias Host = HockeyJourneyEventPageHost10868
    private typealias Fixtures = HockeyJourneyContributionAdapter10868Tests

    private static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()
    private static let locale = Locale(identifier: "en_US")

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func detail(_ json: String, status: String? = nil) throws -> EventDetail {
        var event = try decoder().decode(EventDetail.self, from: Data(json.utf8))
        if let status { event.status = status } // CONSTRUCTED where passed: the decoded status only
        return event
    }

    private func markets(_ json: String) throws -> GameMarketsResponse {
        try decoder().decode(GameMarketsResponse.self, from: Data(json.utf8))
    }

    /// CONSTRUCTED: the same served bytes with only `event_id` changed.
    private func relabelled(_ json: String, eventId: Int) throws -> GameMarketsResponse {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        object["event_id"] = eventId
        return try decoder().decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private func people(_ now: String) throws -> C.Host {
        C.Host(boxScore: nil, now: try XCTUnwrap(now.asDate), calendar: Self.pacific, locale: Self.locale)
    }

    private func catalogueHost(_ now: String) throws -> O.Host {
        O.Host(now: try XCTUnwrap(now.asDate), calendar: Self.pacific, locale: Self.locale)
    }

    private struct Case {
        let label: String
        let event: EventDetail
        let ownJSON: String
        let foreignJSON: String
        let otherID: Int
        let now: String
    }

    /// Before, during (CONSTRUCTED live replays) and after the final.
    private func cases() throws -> [Case] {
        [
            Case(label: "before, 15338496", event: try detail(Fixtures.devilsKnightsDetail),
                 ownJSON: Fixtures.devilsKnightsMarkets, foreignJSON: Fixtures.wildBruinsMarkets,
                 otherID: 15169793, now: "2026-10-30T20:13:55Z"),
            Case(label: "during, 15338496 (CONSTRUCTED live)", event: try detail(Fixtures.devilsKnightsDetail, status: "live"),
                 ownJSON: Fixtures.devilsKnightsMarkets, foreignJSON: Fixtures.wildBruinsMarkets,
                 otherID: 15169793, now: "2026-10-30T22:30:00Z"),
            Case(label: "during, 15169793 (CONSTRUCTED live)", event: try detail(Fixtures.wildBruinsDetail, status: "live"),
                 ownJSON: Fixtures.wildBruinsMarkets, foreignJSON: Fixtures.devilsKnightsMarkets,
                 otherID: 15338496, now: "2026-10-04T02:00:00Z"),
            Case(label: "final, 15169793", event: try detail(Fixtures.wildBruinsDetail),
                 ownJSON: Fixtures.wildBruinsMarkets, foreignJSON: Fixtures.devilsKnightsMarkets,
                 otherID: 15338496, now: "2026-10-11T04:56:41Z"),
            Case(label: "final, 15338034", event: try detail(Fixtures.islandersWildDetail),
                 ownJSON: Fixtures.islandersWildMarkets, foreignJSON: Fixtures.wildBruinsMarkets,
                 otherID: 15169793, now: "2026-10-30T20:13:55Z"),
        ]
    }

    /// Every field of the originals group that a reader can see.
    private func assertSameOriginals(_ a: HockeyJourneyPageOriginals10868, _ b: HockeyJourneyPageOriginals10868,
                                     _ message: String, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(a.catalogue, b.catalogue, message, file: file, line: line)
        XCTAssertEqual(a.selection, b.selection, message, file: file, line: line)
        XCTAssertEqual(a.labels, b.labels, message, file: file, line: line)
        XCTAssertEqual(a.context, b.context, message, file: file, line: line)
        XCTAssertEqual(a.heading, b.heading, message, file: file, line: line)
        XCTAssertEqual(a.emptyWords, b.emptyWords, message, file: file, line: line)
    }

    func testOwnershipIsTheExactServedId() throws {
        let event = try detail(Fixtures.wildBruinsDetail)
        let own = try markets(Fixtures.wildBruinsMarkets)
        let foreign = try markets(Fixtures.devilsKnightsMarkets)
        XCTAssertEqual(own.eventId, 15169793)
        XCTAssertEqual(foreign.eventId, 15338496)
        XCTAssertEqual(C.ownMarkets(own, for: event), own)
        XCTAssertNil(C.ownMarkets(foreign, for: event))
        XCTAssertNil(C.ownMarkets(nil, for: event))
        XCTAssertEqual(C.ownMarkets(try relabelled(Fixtures.devilsKnightsMarkets, eventId: event.id), for: event)?.eventId,
                       event.id, "the id alone decides (CONSTRUCTED relabel)")
    }

    func testThisGamesOwnBodyStillDealsBothCardsAndListsItsOriginals() throws {
        for c in try cases() {
            let own = try markets(c.ownJSON)
            XCTAssertNotNil(C.points(c.event, markets: own, host: try people(c.now)), c.label)
            XCTAssertNotNil(C.assists(c.event, markets: own, host: try people(c.now)), c.label)
            XCTAssertFalse(C.ladders(.points, event: c.event, markets: own).isEmpty, c.label)
            XCTAssertNotNil(O.originals(c.event, markets: own, host: try catalogueHost(c.now), tint: .blue).catalogue, c.label)
        }
    }

    /// The discriminating card case: this matchup's own rows under another game's id (CONSTRUCTED).
    func testCardsReadThisMatchupsRowsUnderAnotherGamesIdAsNoBody() throws {
        for c in try cases() {
            let sameMatchup = try relabelled(c.ownJSON, eventId: c.otherID)
            XCTAssertEqual(C.ladders(.points, event: c.event, markets: sameMatchup), [], c.label)
            XCTAssertEqual(C.ladders(.assists, event: c.event, markets: sameMatchup), [], c.label)
            XCTAssertNil(C.points(c.event, markets: sameMatchup, host: try people(c.now)), c.label)
            XCTAssertNil(C.assists(c.event, markets: sameMatchup, host: try people(c.now)), c.label)
        }
    }

    /// Already empty today through the team filter; kept as the semantic case, not the guard's proof.
    func testCardsReadARealOtherGamesBodyAsNoBody() throws {
        for c in try cases() {
            let foreign = try markets(c.foreignJSON)
            XCTAssertNil(C.points(c.event, markets: foreign, host: try people(c.now)), c.label)
            XCTAssertNil(C.assists(c.event, markets: foreign, host: try people(c.now)), c.label)
        }
    }

    func testAllPropsReadAnotherGamesBodyAsNoBody() throws {
        for c in try cases() {
            let host = try catalogueHost(c.now)
            let missing = O.originals(c.event, markets: nil, host: host, tint: .blue)
            let foreign = O.originals(c.event, markets: try markets(c.foreignJSON), host: host, tint: .blue)
            XCTAssertNil(foreign.catalogue, c.label)
            XCTAssertTrue(foreign.labels.isEmpty, c.label)
            XCTAssertNil(foreign.context, c.label)
            assertSameOriginals(foreign, missing, c.label)
            let sameMatchup = O.originals(c.event, markets: try relabelled(c.ownJSON, eventId: c.otherID),
                                          host: host, tint: .blue)
            assertSameOriginals(sameMatchup, missing, c.label + " (CONSTRUCTED same-matchup)")
            // RELABEL CONTROL: the foreign bytes under this game's id list again.
            let control = O.originals(c.event, markets: try relabelled(c.foreignJSON, eventId: c.event.id),
                                      host: host, tint: .blue)
            XCTAssertNotNil(control.catalogue, c.label + " (CONSTRUCTED relabel control)")
        }
    }

    /// The host builds the no-markets page from another game's body; the reader's held
    /// selection and choices pass through exactly as with no body.
    func testTheHostBuildsTheNoMarketsPageFromAnotherGamesBody() throws {
        for c in try cases() {
            let now = try XCTUnwrap(c.now.asDate)
            let held = OriginalMarketDetails9483.Selection(
                scope: O.scope(c.event, phase: HockeyJourneyPageAdapter10868.phase(c.event, now: now)),
                identity: OriginalMarketDetails9483.Identity(source: "kalshi", market: "1", side: "1"))
            let reading = Host.Reading(pointsPlayer: "player:quinn hughes", selection: held)
            func build(_ body: GameMarketsResponse?) -> Host.Built {
                Host.build(event: c.event, history: nil, markets: body, boxScore: nil,
                           probabilityObservedAt: c.event.heroProbabilityObservedAt?.asDate,
                           now: now, reading: reading, calendar: Self.pacific, locale: Self.locale)
            }
            let missing = build(nil)
            let own = build(try markets(c.ownJSON))
            for body in [try markets(c.foreignJSON), try relabelled(c.ownJSON, eventId: c.otherID)] {
                let page = build(body)
                XCTAssertEqual(page.input, missing.input, c.label)
                XCTAssertNil(page.input.points, c.label)
                XCTAssertNil(page.input.assists, c.label)
                XCTAssertEqual(page.input.stories, [], c.label)
                XCTAssertNil(page.input.copy.allPropsLabel, c.label)
                assertSameOriginals(page.originals, missing.originals, c.label)
                XCTAssertEqual(page.originals.selection, held, "the reader's own held selection is kept")
                XCTAssertEqual(page.input.headline, own.input.headline, "the own chance stands")
                XCTAssertEqual(page.input.history, own.input.history)
            }
            XCTAssertNotNil(own.originals.catalogue, c.label)
            XCTAssertNotNil(own.input.copy.allPropsLabel, c.label)
        }
    }
}
