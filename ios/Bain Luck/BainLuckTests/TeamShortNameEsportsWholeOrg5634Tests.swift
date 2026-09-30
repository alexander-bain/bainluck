import XCTest
@testable import Bain_Luck

/// #5634 — an esports organisation is not its type, on the iPhone as on the site.
///
/// WHAT THE READER SAW: `/events/15319232`, G2 Esports v Paper Rex, 390px,
/// 2026-09-29 — the browser's hero read **"Esports"** and **"Rex"**. The served
/// payload carries `sport: "esports"` and the phone's hero passes `event.sport`
/// to `TeamShortName`, so the phone had the sport in hand and printed the same
/// two words. The browser's fix is PR #9682 (`keepsWholeOrgName` +
/// `ESPORTS_ORG_SUFFIXES`); this file pins the same cases against the Swift.
///
/// `productionCollapses` is DATA, not a copy of the rule: each group was read
/// verbatim from production `events` by ux (esports, 60 days, the 1,000
/// most-used names, 2026-09-29) and every name in a group printed the SAME word
/// before this fix.
final class TeamShortNameEsportsWholeOrg5634Tests: XCTestCase {

    private static let esports = "esports"

    private static let productionCollapses: [(String, [String])] = [
        ("Esports", ["G2 Esports", "Top Esports", "FURIA Esports", "Hanwha Life Esports", "KRÜ Esports"]),
        ("Gaming", ["JD Gaming", "SK Gaming", "Bilibili Gaming", "EDward Gaming"]),
        ("Esport", ["Insiders Esport", "Partizan Esport", "Falcons Esport"]),
        ("Phoenix", ["Black Phoenix", "FunPlus Phoenix", "Team Phoenix"]),
    ]

    func testTheOrganisationsThatAllPrintedOneWordAreToldApartUnderAnEsportsKey() {
        for (word, names) in Self.productionCollapses {
            for n in names {
                XCTAssertEqual(TeamShortName.short(n), word, "the before, unkeyed: \(n)")
            }
            let labels = names.map { TeamShortName.short($0, sportKey: Self.esports) }
            XCTAssertEqual(labels, names, word)
            XCTAssertFalse(labels.contains(word), word)
        }
    }

    func testTheSpecimensAndTheirNeighbours() {
        let cases: [(String, String)] = [
            ("G2 Esports", "G2 Esports"),
            ("Paper Rex", "Paper Rex"),
            ("Natus Vincere", "Natus Vincere"),
            ("Dplus KIA", "Dplus KIA"),
            // Leading short tokens are the org here, not a designator to drop.
            ("KT Rolster Challengers", "KT Rolster Challengers"),
            ("SK Gaming", "SK Gaming"),
            ("Fnatic", "Fnatic"),
            // Past three words, a type-word ending still keeps the name whole ...
            ("Gamespace Mediterranean College Esports", "Gamespace Mediterranean College Esports"),
            ("Fukuoka SoftBank Hawks Gaming", "Fukuoka SoftBank Hawks Gaming"),
            ("E WIE EINFACH E-SPORTS", "E WIE EINFACH E-SPORTS"),
            ("EDward Gaming Youth Team", "EDward Gaming Youth Team"),
            // ... and any other long name takes the shipped rule.
            ("Unicorns Of Love Sexy Edition", "Edition"),
        ]
        for (name, label) in cases {
            XCTAssertEqual(TeamShortName.short(name, sportKey: "esports_valorant"), label, name)
        }
    }

    func testTheSpecimenPairReadsBothWholeNames() {
        let pair = TeamShortName.shortPair(away: "Paper Rex", home: "G2 Esports", sportKey: Self.esports)
        XCTAssertEqual(pair.away, "Paper Rex")
        XCTAssertEqual(pair.home, "G2 Esports")
    }

    func testTheNavTitleNamesBothOrganisations() {
        XCTAssertEqual(
            EventNavTitle.scoreless(away: "Paper Rex", home: "G2 Esports", sportKey: Self.esports),
            "Paper Rex vs G2 Esports"
        )
        let live = EventNavTitle.rungs(
            away: "Paper Rex", home: "G2 Esports", awayScore: 1, homeScore: 0, sportKey: Self.esports
        )
        XCTAssertEqual(live.labelled.away, "Paper Rex")
        XCTAssertEqual(live.labelled.home, "G2 Esports")
    }

    func testTheGateIsTheFirstKeySegmentAndFailsClosed() {
        XCTAssertTrue(TeamShortName.keepsWholeOrgName(sportKey: "esports"))
        XCTAssertTrue(TeamShortName.keepsWholeOrgName(sportKey: "esports_lol"))
        XCTAssertTrue(TeamShortName.keepsWholeOrgName(sportKey: "ESPORTS"))
        XCTAssertFalse(TeamShortName.keepsWholeOrgName(sportKey: "soccer_esports_cup"))
        XCTAssertFalse(TeamShortName.keepsWholeOrgName(sportKey: "basketball_nba"))
        XCTAssertFalse(TeamShortName.keepsWholeOrgName(sportKey: nil))
        XCTAssertFalse(TeamShortName.keepsWholeOrgName(sportKey: ""))
        XCTAssertFalse(TeamShortName.keepsWholeOrgName(sportKey: "   "))
    }

    func testOtherSportsKeepTheShippedRule() {
        XCTAssertEqual(TeamShortName.short("Boston Red Sox", sportKey: "baseball_mlb"), "Red Sox")
        XCTAssertEqual(TeamShortName.short("Los Angeles Lakers", sportKey: "basketball_nba"), "Lakers")
        XCTAssertEqual(TeamShortName.short("G2 Esports", sportKey: "basketball_nba"), "Esports")
        XCTAssertEqual(TeamShortName.short("G2 Esports"), "Esports")
    }

    func testTheCrestBadgeDoesNotMove() {
        for name in ["G2 Esports", "Paper Rex", "Natus Vincere", "KT Rolster Challengers"] {
            XCTAssertEqual(
                TeamShortName.abbreviation(name, sportKey: Self.esports),
                TeamShortName.abbreviation(name), name
            )
        }
        let keyed = TeamShortName.abbreviationPair(away: "Paper Rex", home: "G2 Esports", sportKey: Self.esports)
        let unkeyed = TeamShortName.abbreviationPair(away: "Paper Rex", home: "G2 Esports")
        XCTAssertEqual(keyed.away, unkeyed.away)
        XCTAssertEqual(keyed.home, unkeyed.home)
    }
}
