import XCTest
@testable import Bain_Luck

/// #5634 — a two-word nickname keeps both words, on the iPhone as on the site.
///
/// WHAT THE READER SAW: `/events/15317515`, Guardians 0 – 1 Red Sox, Final,
/// 2026-09-24. The browser's hero read **"Sox · WON"** and its chart axis
/// **"SOX"** — a word that is also the White Sox. `TeamShortName.short` had the
/// same defect from the same line: the last-word rule drops the first half of
/// every two-word nickname ("Tide", "Irish", "Heels", and three different clubs
/// as "Devils").
///
/// `productionNames` is DATA, not a copy of the rule: every name was read
/// verbatim from production `events` by ux/1479 (60 days, MLB/NHL/NBA/WNBA/NFL/
/// NCAAF, 372 names, 2026-09-24) and each one printed only its last word before
/// this fix. The expected label is the name's own last two words, computed from
/// the name, never from the function under test.
final class TeamShortNameTwoWordNickname5634Tests: XCTestCase {

    private static let productionNames: [(String, String)] = [
        ("americanfootball_ncaaf", "Alabama Crimson Tide"),
        ("americanfootball_ncaaf", "Arizona State Sun Devils"),
        ("americanfootball_ncaaf", "Arkansas Pine Bluff Golden Lions"),
        ("americanfootball_ncaaf", "Arkansas State Red Wolves"),
        ("americanfootball_ncaaf", "Army Black Knights"),
        ("baseball_mlb", "Boston Red Sox"),
        ("americanfootball_ncaaf", "California Golden Bears"),
        ("americanfootball_ncaaf", "Campbell Fighting Camels"),
        ("americanfootball_ncaaf", "Central Connecticut Blue Devils"),
        ("baseball_mlb", "Chicago White Sox"),
        ("icehockey_nhl", "Columbus Blue Jackets"),
        ("americanfootball_ncaaf", "Delaware Blue Hens"),
        ("icehockey_nhl", "Detroit Red Wings"),
        ("americanfootball_ncaaf", "Duke Blue Devils"),
        ("americanfootball_ncaaf", "Gardner-Webb Runnin Bulldogs"),
        ("americanfootball_ncaaf", "Georgia Tech Yellow Jackets"),
        ("americanfootball_ncaaf", "Hawaii Rainbow Warriors"),
        ("americanfootball_ncaaf", "Illinois Fighting Illini"),
        ("americanfootball_ncaaf", "Kent State Golden Flashes"),
        ("americanfootball_ncaaf", "Louisiana Ragin Cajuns"),
        ("americanfootball_ncaaf", "Maine Black Bears"),
        ("americanfootball_ncaaf", "Marshall Thundering Herd"),
        ("americanfootball_ncaaf", "Middle Tennessee Blue Raiders"),
        ("americanfootball_ncaaf", "Minnesota Golden Gophers"),
        ("americanfootball_ncaaf", "Mississippi Valley State Delta Devils"),
        ("americanfootball_ncaaf", "Nevada Wolf Pack"),
        ("americanfootball_ncaaf", "North Carolina Tar Heels"),
        ("americanfootball_ncaaf", "North Dakota Fighting Hawks"),
        ("americanfootball_ncaaf", "North Texas Mean Green"),
        ("americanfootball_ncaaf", "Notre Dame Fighting Irish"),
        ("americanfootball_ncaaf", "Penn State Nittany Lions"),
        ("basketball_nba", "Portland Trail Blazers"),
        ("americanfootball_ncaaf", "Rutgers Scarlet Knights"),
        ("americanfootball_ncaaf", "Southern Mississippi Golden Eagles"),
        ("americanfootball_ncaaf", "TCU Horned Frogs"),
        ("americanfootball_ncaaf", "Texas Tech Red Raiders"),
        ("baseball_mlb", "Toronto Blue Jays"),
        ("icehockey_nhl", "Toronto Maple Leafs"),
        ("americanfootball_ncaaf", "Tulane Green Wave"),
        ("americanfootball_ncaaf", "Tulsa Golden Hurricane"),
        ("icehockey_nhl", "Vegas Golden Knights"),
        ("americanfootball_ncaaf", "Wake Forest Demon Deacons"),
    ]

    private static func lastTwo(_ name: String) -> String {
        name.split(separator: " ").suffix(2).joined(separator: " ")
    }

    func testTheSpecimenHeroNamesTheRedSox() {
        XCTAssertEqual(TeamShortName.short("Boston Red Sox", sportKey: "baseball_mlb"), "Red Sox")
        let pair = TeamShortName.shortPair(
            away: "Cleveland Guardians", home: "Boston Red Sox", sportKey: "baseball_mlb")
        XCTAssertEqual(pair.home, "Red Sox")
        XCTAssertEqual(pair.away, "Guardians")
    }

    func testEveryProductionNameKeepsItsLastTwoWords() {
        for (sport, name) in Self.productionNames {
            XCTAssertEqual(TeamShortName.short(name, sportKey: sport), Self.lastTwo(name), "\(sport) · \(name)")
            // A caller that does not know its sport gets the same label: the
            // gate only ever CLOSES the list, for a person's sport.
            XCTAssertEqual(TeamShortName.short(name), Self.lastTwo(name), name)
        }
    }

    func testEveryEntryIsReachedByAProductionNameNoDeadKeys() {
        let reached = Set(Self.productionNames.map {
            Self.lastTwo($0.1).lowercased().filter { $0.isLetter || $0.isNumber || $0 == " " }
        })
        for key in TeamShortName.twoWordNicknames {
            XCTAssertTrue(reached.contains(key), "dead key: \(key)")
        }
        XCTAssertEqual(TeamShortName.twoWordNicknames.count, 41)
    }

    func testEveryKeyIsTwoLowerCaseWordsTheFormTheLookupProduces() {
        for key in TeamShortName.twoWordNicknames {
            XCTAssertNotNil(key.range(of: "^[a-z0-9]+ [a-z0-9]+$", options: .regularExpression), key)
        }
    }

    func testClubsThatWereOneWordApartStopColliding() {
        let sox = TeamShortName.shortPair(away: "Chicago White Sox", home: "Boston Red Sox")
        XCTAssertEqual(sox.away, "White Sox")
        XCTAssertEqual(sox.home, "Red Sox")
        let devils = TeamShortName.shortPair(away: "Arizona State Sun Devils", home: "Duke Blue Devils")
        XCTAssertEqual(devils.away, "Sun Devils")
        XCTAssertEqual(devils.home, "Blue Devils")
    }

    func testPunctuationReachesTheSameEntryAndIsKeptAsWritten() {
        XCTAssertEqual(TeamShortName.short("Louisiana Ragin' Cajuns"), "Ragin' Cajuns")
    }

    func testANameThatIsTheNicknameReturnsItself() {
        XCTAssertEqual(TeamShortName.twoWordNickname(["Red", "Sox"]), "Red Sox")
        XCTAssertEqual(TeamShortName.short("Red Sox"), "Red Sox")
        XCTAssertNil(TeamShortName.twoWordNickname(["Sox"]))
    }

    /// Badges read off the browser's `teamCrestBadge` 2026-09-24. A three-word
    /// name was already badged by its initials (#4539), so the list moves no
    /// badge there; a bare two-word nickname badges its first word, as on the site.
    func testTheBadgesAgreeWithTheBrowser() {
        XCTAssertEqual(TeamShortName.abbreviation("Boston Red Sox"), "BRS")
        XCTAssertEqual(TeamShortName.abbreviation("Chicago White Sox"), "CWS")
        XCTAssertEqual(TeamShortName.abbreviation("Tohoku Rakuten Golden Eagles"), "TRG")
        XCTAssertEqual(TeamShortName.abbreviation("Red Sox"), "RED")
        XCTAssertEqual(TeamShortName.abbreviation("Tar Heels"), "TAR")
    }

    func testControlOneWordNicknamesBehindATwoWordPlaceAreUntouched() {
        XCTAssertEqual(TeamShortName.short("Golden State Warriors"), "Warriors")
        XCTAssertEqual(TeamShortName.short("Golden State Valkyries"), "Valkyries")
        XCTAssertEqual(TeamShortName.short("Tampa Bay Rays"), "Rays")
        XCTAssertEqual(TeamShortName.short("Kansas City Royals"), "Royals")
        XCTAssertEqual(TeamShortName.short("New Jersey Devils"), "Devils")
        XCTAssertEqual(TeamShortName.short("Miami (OH) RedHawks"), "RedHawks")
    }

    func testControlAPersonsNameNeverReachesTheList() {
        XCTAssertEqual(TeamShortName.short("Mean Green", sportKey: "tennis_atp_us_open"), "Green")
    }
}
