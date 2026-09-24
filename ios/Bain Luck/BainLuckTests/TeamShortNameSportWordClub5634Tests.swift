import XCTest
@testable import Bain_Luck

/// #5634 — a club is not the name of its sport, on the iPhone as on the site.
///
/// WHAT THE READER SAW: `/events/15292394`, Dubai Basketball v Real Madrid, live
/// EuroLeague, 2026-09-24 (shopper pass 0040) — the browser's hero named the
/// home side **"Basketball"** and its badge read **`BAS`**. `TeamShortName` took
/// the same last word by the same rule. The browser's fix is ux's 236ae1f621
/// (`SPORT_WORD_SUFFIXES`); this pins the same cases against the Swift.
///
/// `productionNames` is DATA: every `teams.name` on production ending in a sport
/// word, read by ux 2026-09-24 (5 rows), with the sport key each row carries.
final class TeamShortNameSportWordClub5634Tests: XCTestCase {

    private static let productionNames: [(name: String, sport: String, word: String, badge: String)] = [
        ("Dubai Basketball", "basketball_euroleague", "Basketball", "DUB"),
        ("Paris Basketball", "basketball_euroleague", "Basketball", "PAR"),
        ("Valencia Basket", "basketball_euroleague", "Basket", "VAL"),
        ("Modo Hockey", "icehockey_sweden_allsvenskan", "Hockey", "MOD"),
        ("TUTO Hockey", "icehockey_mestis", "Hockey", "TUT"),
    ]

    func testEveryProductionNameKeepsItsWholeNameWithOrWithoutItsSport() {
        for row in Self.productionNames {
            XCTAssertEqual(TeamShortName.short(row.name, sportKey: row.sport), row.name, row.name)
            XCTAssertEqual(TeamShortName.short(row.name), row.name, row.name)
            XCTAssertNotEqual(TeamShortName.short(row.name, sportKey: row.sport), row.word)
        }
    }

    func testTheCrestBadgeIsTheClubsLettersNotTheSports() {
        for row in Self.productionNames {
            XCTAssertEqual(TeamShortName.abbreviation(row.name, sportKey: row.sport), row.badge, row.name)
            XCTAssertEqual(TeamShortName.abbreviation(row.name), row.badge, row.name)
        }
    }

    func testTheSpecimensHeroPairNamesDubaiAndRealMadridIsUntouched() {
        let pair = TeamShortName.shortPair(
            away: "Real Madrid", home: "Dubai Basketball", sportKey: "basketball_euroleague")
        XCTAssertEqual(pair.home, "Dubai Basketball")
        XCTAssertEqual(pair.away, "Madrid")
        let badges = TeamShortName.abbreviationPair(
            away: "Real Madrid", home: "Dubai Basketball", sportKey: "basketball_euroleague")
        XCTAssertEqual(badges.home, "DUB")
        XCTAssertEqual(badges.away, "MAD")
    }

    func testTheTwoEuroLeagueClubsThatBothPrintedBasketballAreToldApart() {
        let labels = ["Dubai Basketball", "Paris Basketball"].map {
            TeamShortName.short($0, sportKey: "basketball_euroleague")
        }
        XCTAssertEqual(Set(labels).count, 2)
    }

    func testTheWordIsMatchedWholeAndNothingThatMerelyContainsItMoves() {
        XCTAssertEqual(TeamShortName.short("DUBAI BASKETBALL"), "DUBAI BASKETBALL")
        // A nickname that contains a sport word is still a nickname.
        XCTAssertEqual(TeamShortName.short("Kitchener Hockeyists"), "Hockeyists")
        // North American nicknames are unaffected.
        XCTAssertEqual(TeamShortName.short("Boston Celtics", sportKey: "basketball_nba"), "Celtics")
        XCTAssertEqual(TeamShortName.short("Toronto Maple Leafs", sportKey: "icehockey_nhl"), "Maple Leafs")
    }
}
