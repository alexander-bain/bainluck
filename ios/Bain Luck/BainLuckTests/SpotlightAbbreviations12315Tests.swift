import XCTest
@testable import Bain_Luck

/// #12315 — Spotlight finds a game by the abbreviation the server sends and by
/// each team's short name, never by a guessed badge; and each entry names its
/// own game or market to Siri, with nothing that goes stale.
@MainActor
final class SpotlightAbbreviations12315Tests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 1_794_160_000) // Sun 2026-11-08 18:13:20Z

    private func chiefsGame(away: String? = "NYJ", home: String? = "KC") throws -> SpotlightSubject10874 {
        try XCTUnwrap(SpotlightSubject10874.game(
            id: 14969879, away: "New York Jets", home: "Kansas City Chiefs", sportKey: "americanfootball_nfl",
            commenceTime: "2026-11-08T18:00:00Z", awayAbbreviation: away, homeAbbreviation: home))
    }

    // MARK: - Spotlight finds "KC"

    func testTheServedAbbreviationsAndShortNamesBecomeKeywords() throws {
        XCTAssertEqual(try chiefsGame().aliases,
                       ["New York Jets", "Kansas City Chiefs", "NFL", "Jets", "Chiefs", "NYJ", "KC"])
    }

    func testNoGuessedBadgeEverBecomesAKeyword() throws {
        let guessed = TeamShortName.abbreviation("Kansas City Chiefs", sportKey: "americanfootball_nfl")
        XCTAssertNotEqual(guessed, "KC", "the control needs a guess that differs from the served badge")
        for subject in [try chiefsGame(), try chiefsGame(away: nil, home: nil), try chiefsGame(away: " ", home: "K C")] {
            XCTAssertFalse(subject.aliases.contains(guessed), "a guessed badge reached Spotlight: \(subject.aliases)")
        }
        XCTAssertEqual(try chiefsGame(away: nil, home: nil).aliases,
                       ["New York Jets", "Kansas City Chiefs", "NFL", "Jets", "Chiefs"])
    }

    func testOnlyAPlainShortAbbreviationCountsAsServed() {
        XCTAssertEqual(SpotlightIndexPlan10874.servedAbbreviation(" KC "), "KC")
        XCTAssertEqual(SpotlightIndexPlan10874.servedAbbreviation("WSH"), "WSH")
        for raw in [nil, "", "   ", "K C", "KC!", "KANSASC"] {
            XCTAssertNil(SpotlightIndexPlan10874.servedAbbreviation(raw), String(describing: raw))
        }
    }

    // MARK: - Each entry is its own game or market

    func testEachEntryNamesItsOwnGameOrMarketAndNothingThatGoesStale() throws {
        let market = try XCTUnwrap(SpotlightSubject10874.market(id: 512, name: "Fed cuts in December?",
                                                                category: "economics"))
        let items = SpotlightIndexPlan10874.items(
            [SpotlightEntry10874(subject: try chiefsGame(), viewedAt: t0), SpotlightEntry10874(subject: market, viewedAt: t0)],
            saved: [], scope: "guest", now: t0)
        XCTAssertEqual(items.count, 2)
        let expected: [String: (String, URL?)] = [
            "https://bainluck.com/events/14969879": ("game-14969879", IntentLinks10873.event(id: 14969879)),
            "https://bainluck.com/futures/512": ("market-512", IntentLinks10873.market(id: 512)),
        ]
        for item in items {
            let entity = try XCTUnwrap(SpotlightIndexPlan10874.entity(for: item), item.identifier)
            let (id, link) = try XCTUnwrap(expected[item.identifier], item.identifier)
            XCTAssertEqual(entity.id, id, "an entry named another game or market")
            XCTAssertEqual(entity.link, link, "an entry opens somewhere else")
            XCTAssertEqual(entity.title, item.title)
            XCTAssertEqual(entity.detail, item.detail.isEmpty ? nil : item.detail)
            let text = [entity.title, entity.detail ?? ""].joined(separator: " ")
            for stale in ["Live", "Final", "Settled", "%"] {
                XCTAssertFalse(text.contains(stale), "the entity carries '\(stale)', which goes stale: \(text)")
            }
        }
        let foreign = SpotlightIndexItem10874(identifier: "https://bainluck.com/teams/12", domain: "d",
                                              title: "Chiefs", detail: "", keywords: [], expiration: t0)
        XCTAssertNil(SpotlightIndexPlan10874.entity(for: foreign), "an identifier that is not ours named an entity")
    }
}
