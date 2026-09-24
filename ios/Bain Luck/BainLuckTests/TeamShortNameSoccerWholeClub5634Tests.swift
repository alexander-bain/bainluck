import XCTest
@testable import Bain_Luck

/// #5634 — a football club is not its city, on the iPhone as on the site.
///
/// WHAT THE READER SAW: `/events/15309604`, 1. FC Köln 3-0 Union Berlin, Final,
/// 2026-09-12 — the browser's hero read **"Köln · WON — Berlin"**, and "Berlin"
/// is also Hertha, Croatia and Füchse. `TeamShortName.short` has the same
/// last-word rule, so the phone's verdict read "Berlin Win" off the same row.
/// The browser's fix is PR #8391 (`keepsWholeClubName` + `wholeClubName` in
/// `frontend/lib/teamShortName.ts`); this file pins the same cases against the
/// Swift, so the two clients name the same club the same way.
///
/// `productionCollapses` is DATA, not a copy of the rule: each group was read
/// verbatim from production `events` by ux/1481 (soccer, 60 days, first 1,000
/// distinct names, 2026-09-24) and every name in a group printed the SAME last
/// word before this fix.
final class TeamShortNameSoccerWholeClub5634Tests: XCTestCase {

    private static let soccer = "soccer_germany_bundesliga"

    private static let productionCollapses: [(String, [String])] = [
        ("Cali", ["AD Cali", "America Cali", "América de Cali", "Atletico FC Cali"]),
        ("Juniors", ["Argentinos Juniors", "Boca Juniors"]),
        ("Central", ["Atletico Central", "Barracas Central", "CA Rosario Central"]),
        ("Munich", ["1860 Munich", "Bayern Munich"]),
        ("Athens", ["AEK Athens", "Atromitos Athens"]),
    ]

    // MARK: - The clubs are told apart

    func testTheClubsThatAllPrintedOneWordAreToldApartUnderASoccerKey() {
        for (word, names) in Self.productionCollapses {
            for n in names { XCTAssertEqual(TeamShortName.short(n), word, "premise: \(n)") }
            let labels = names.map { TeamShortName.short($0, sportKey: Self.soccer) }
            XCTAssertEqual(Set(labels).count, names.count, "\(word): \(labels)")
            for l in labels { XCTAssertNotEqual(l, word) }
        }
    }

    func testTheSpecimensAndTheirNeighbours() {
        let cases: [(String, String)] = [
            ("1. FC Union Berlin", "Union Berlin"),
            ("Union Berlin", "Union Berlin"),
            ("Hertha Berlin", "Hertha Berlin"),
            ("Real Salt Lake", "Real Salt Lake"),
            ("1. FC Köln", "FC Köln"),
            ("CA Boca Juniors", "Boca Juniors"),
            ("AD Cali", "AD Cali"),
            ("AC Milan", "AC Milan"),
            ("Sporting Kansas City", "Sporting Kansas City"),
            ("Atletico Madrid", "Atletico Madrid"),
            ("New England Revolution", "New England Revolution"),
            ("Arsenal", "Arsenal"),
        ]
        for (name, label) in cases {
            XCTAssertEqual(TeamShortName.short(name, sportKey: "soccer_epl"), label, name)
        }
    }

    /// "1." and "FC" go; "Köln" alone would breach the two-word floor. And a
    /// word the TRAILING rule treats as a club type is the name when it leads.
    func testLeadingDesignatorsGoOnlyDownToTwoWordsAndNeverAClubWord() {
        XCTAssertEqual(TeamShortName.short("1. FC Köln", sportKey: Self.soccer), "FC Köln")
        XCTAssertEqual(TeamShortName.short("Sporting Kansas City", sportKey: "soccer_usa_mls"),
                       "Sporting Kansas City")
        XCTAssertEqual(TeamShortName.short("2 de Mayo", sportKey: Self.soccer), "2 de Mayo")
    }

    func testTheWordCountIsTakenAfterLeadingDesignatorsGo() {
        XCTAssertEqual(TeamShortName.short("1. FC Union Berlin", sportKey: Self.soccer), "Union Berlin")
        XCTAssertEqual(TeamShortName.short("BV Borussia 09 Dortmund", sportKey: Self.soccer),
                       "Borussia 09 Dortmund")
    }

    func testTheHandPickedLabelStillWins() {
        XCTAssertEqual(TeamShortName.short("Paris Saint-Germain", sportKey: "soccer_france_ligue_one"), "PSG")
    }

    func testEveryLabelIsATailOfTheClubsOwnName() {
        for (_, names) in Self.productionCollapses {
            for n in names {
                let label = TeamShortName.short(n, sportKey: Self.soccer)
                XCTAssertTrue(n.hasSuffix(label), "\(n) → \(label)")
            }
        }
    }

    // MARK: - A formal name keeps its shipped label

    func testAFormalNameOfFourWordsOrMoreKeepsItsShippedLabel() {
        let cases: [(String, String)] = [
            ("Sport Lisboa e Benfica", "Benfica"),
            ("Futebol Clube do Porto", "Porto"),
            ("Tigres de la UANL", "UANL"),
            ("Deportivo de La Coruna", "Coruna"),
            ("Aldosivi Mar del Plata", "Plata"),
            ("Churriana de la Vega", "Vega"),
        ]
        for (name, label) in cases {
            XCTAssertEqual(TeamShortName.short(name), label, "premise: \(name)")
            XCTAssertEqual(TeamShortName.short(name, sportKey: "soccer_portugal_primeira_liga"), label, name)
        }
    }

    /// #7163's club corpus under a soccer key — the browser's pinned outputs.
    func testTheParticleClubCorpusUnderASoccerKey() {
        let cases: [(String, String)] = [
            ("Defensa y Justicia", "Defensa y Justicia"),
            ("Heart of Midlothian", "Heart of Midlothian"),
            ("Wingate and Finchley", "Wingate and Finchley"),
            ("Vasco da Gama", "Vasco da Gama"),
            ("Bourg en Bresse", "Bourg en Bresse"),
            ("FC United of Manchester", "United of Manchester"),
            // A person's name under a soccer key is kept whole by the club rule,
            // never hoisted by the person rule.
            ("Alex de Minaur", "Alex de Minaur"),
        ]
        for (name, label) in cases {
            XCTAssertEqual(TeamShortName.short(name, sportKey: Self.soccer), label, name)
        }
    }

    // MARK: - Nothing outside football moves

    func testNothingOutsideFootballMoves() {
        let cases: [(String?, String, String)] = [
            (nil, "Bayern Munich", "Munich"),
            ("", "Union Berlin", "Berlin"),
            ("   ", "Union Berlin", "Berlin"),
            ("basketball_nba", "Los Angeles Lakers", "Lakers"),
            ("baseball_mlb", "Boston Red Sox", "Red Sox"),
            ("americanfootball_nfl", "Kansas City Chiefs", "Chiefs"),
            ("tennis_atp_us_open", "Carlos Alcaraz", "Alcaraz"),
            // A key that merely CONTAINS the word is not football.
            ("esports_soccer_sim", "Team Berlin", "Berlin"),
        ]
        for (sport, name, label) in cases {
            XCTAssertEqual(TeamShortName.short(name, sportKey: sport), label, "\(sport ?? "nil") · \(name)")
        }
    }

    func testTheGateMatchesTheFirstSegmentOnlyAndFailsClosed() {
        XCTAssertTrue(TeamShortName.keepsWholeClubName(sportKey: "soccer_epl"))
        XCTAssertTrue(TeamShortName.keepsWholeClubName(sportKey: "SOCCER_usa_mls"))
        XCTAssertTrue(TeamShortName.keepsWholeClubName(sportKey: "soccer"))
        XCTAssertFalse(TeamShortName.keepsWholeClubName(sportKey: "esports_soccer_sim"))
        XCTAssertFalse(TeamShortName.keepsWholeClubName(sportKey: nil))
        XCTAssertFalse(TeamShortName.keepsWholeClubName(sportKey: ""))
    }

    // MARK: - The pair, the badge and the nav title

    /// The specimen: the finished hero's verdict takes the PAIR's label.
    func testKolnVUnionBerlinNamesBothClubs() {
        let pair = TeamShortName.shortPair(
            away: "Union Berlin", home: "1. FC Köln", sportKey: "soccer_germany_bundesliga_women")
        XCTAssertEqual(pair.away, "Union Berlin")
        XCTAssertEqual(pair.home, "FC Köln")
        // Without the sport it is exactly the shipped label.
        XCTAssertEqual(TeamShortName.shortPair(away: "Union Berlin", home: "1. FC Köln").away, "Berlin")
    }

    func testWithoutServedCodesSeattleVRealSaltLakePrintsBothWholeNamesNotLake() {
        let pair = TeamShortName.shortPair(
            away: "Real Salt Lake", home: "Seattle Sounders FC", sportKey: "soccer_usa_mls")
        XCTAssertEqual(pair.away, "Real Salt Lake")
        XCTAssertEqual(pair.home, "Seattle Sounders FC")
    }

    /// Served codes win on the phone whenever they differ, as they always have;
    /// the club rule does not change that.
    func testServedCodesStillWin() {
        let pair = TeamShortName.shortPair(
            away: "Real Salt Lake", home: "Seattle Sounders FC",
            awayServed: "RSL", homeServed: "SEA", sportKey: "soccer_usa_mls")
        XCTAssertEqual(pair.away, "RSL")
        XCTAssertEqual(pair.home, "SEA")
    }

    /// Two clubs whose whole labels still collide are grown to their full names
    /// rather than printed as one word twice.
    func testACollidingPairIsStillSeparated() {
        let pair = TeamShortName.shortPair(
            away: "1. FC Union Berlin", home: "FC Union Berlin", sportKey: Self.soccer)
        XCTAssertNotEqual(pair.away, pair.home)
    }

    /// The crest badge is the browser's `teamCrestBadge`, which never takes this
    /// rule — so neither may the phone's, even when the caller knows the sport.
    func testTheBadgeDoesNotMoveWithTheLabel() {
        for (_, names) in Self.productionCollapses {
            for n in names {
                XCTAssertEqual(TeamShortName.abbreviation(n, sportKey: Self.soccer),
                               TeamShortName.abbreviation(n), n)
            }
        }
        let pair = TeamShortName.abbreviationPair(
            away: "Union Berlin", home: "Hertha Berlin", sportKey: Self.soccer)
        let shipped = TeamShortName.abbreviationPair(away: "Union Berlin", home: "Hertha Berlin")
        XCTAssertEqual(pair.away, shipped.away)
        XCTAssertEqual(pair.home, shipped.home)
    }

    func testTheNavTitleNamesTheClub() {
        XCTAssertEqual(
            EventNavTitle.scoreless(away: "Union Berlin", home: "1. FC Köln", sportKey: Self.soccer),
            "Union Berlin vs FC Köln")
    }
}
