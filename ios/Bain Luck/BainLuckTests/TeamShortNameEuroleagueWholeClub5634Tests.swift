import XCTest
@testable import Bain_Luck

/// #5634 — a EuroLeague club is not its city either, on the iPhone as on the site.
///
/// WHAT THE READER SAW: `/events/15318709`, Fenerbahce SK 100-76 FC Bayern
/// München, EuroLeague final, 390px, 2026-09-29 — the hero named the away side
/// **"München"**. The browser's fix is PR #9720 (`2b90fa32e5`): the football
/// whole-club rule also covers the WHOLE key `basketball_euroleague`
/// (`WHOLE_CLUB_NAME_KEYS` in `frontend/lib/teamShortName.ts`). This file pins
/// the browser's table (`frontend/__tests__/teamShortNameEuroleagueWholeClub5634.test.ts`)
/// against the Swift, so the two clients name the same club the same way.
///
/// Every name was read verbatim from production `events` by ux
/// (`basketball_euroleague`, 60 days, all 30 distinct names, 2026-09-30).
final class TeamShortNameEuroleagueWholeClub5634Tests: XCTestCase {

    private static let euroleague = "basketball_euroleague"

    func testAEuroleagueClubKeepsItsWholeName() {
        let cases: [(String, String, String)] = [
            ("FC Bayern München", "München", "Bayern München"),
            ("FC Bayern Munchen", "Munchen", "Bayern Munchen"),
            ("Real Madrid", "Madrid", "Real Madrid"),
            ("Zalgiris Kaunas", "Kaunas", "Zalgiris Kaunas"),
            ("KK Crvena zvezda", "zvezda", "Crvena zvezda"),
            ("KK Partizan NIS", "NIS", "Partizan NIS"),
            ("Olimpia Milano", "Milano", "Olimpia Milano"),
            ("Pallacanestro Olimpia Milano", "Milano", "Pallacanestro Olimpia Milano"),
            ("Virtus Bologna", "Bologna", "Virtus Bologna"),
            ("ASVEL Lyon Villeurbanne", "Villeurbanne", "ASVEL Lyon Villeurbanne"),
            ("Anadolu Efes", "Efes", "Anadolu Efes"),
        ]
        for (name, before, after) in cases {
            XCTAssertEqual(TeamShortName.short(name), before, "premise: \(name)")
            XCTAssertEqual(TeamShortName.short(name, sportKey: Self.euroleague), after, name)
        }
    }

    func testBothTelAvivClubsStopReadingAvivOnTheirOwn() {
        XCTAssertEqual(TeamShortName.short("Maccabi Tel Aviv"), "Aviv")
        XCTAssertEqual(TeamShortName.short("Hapoel Tel Aviv"), "Aviv")
        XCTAssertEqual(TeamShortName.short("Maccabi Tel Aviv", sportKey: Self.euroleague), "Maccabi Tel Aviv")
        XCTAssertEqual(TeamShortName.short("Hapoel Tel Aviv", sportKey: Self.euroleague), "Hapoel Tel Aviv")
        let pair = TeamShortName.shortPair(
            away: "Hapoel Tel Aviv", home: "Maccabi Tel Aviv", sportKey: Self.euroleague)
        XCTAssertEqual(pair.home, "Maccabi Tel Aviv")
        XCTAssertEqual(pair.away, "Hapoel Tel Aviv")
    }

    func testClubsWhoseLabelWasAlreadyRightKeepIt() {
        for name in ["Fenerbahce SK", "Paris Basketball", "Dubai Basketball", "Valencia Basket",
                     "Olympiacos B.C.", "Panathinaikos", "Barcelona"] {
            XCTAssertEqual(TeamShortName.short(name, sportKey: Self.euroleague),
                           TeamShortName.short(name), name)
        }
    }

    func testTheKeyIsMatchedWholeSoCityFirstBasketballKeepsTheLastWordRule() {
        XCTAssertTrue(TeamShortName.keepsWholeClubName(sportKey: Self.euroleague))
        XCTAssertTrue(TeamShortName.keepsWholeClubName(sportKey: " Basketball_EuroLeague "))
        for key in ["basketball_nba", "basketball_wnba", "basketball_nbl", "basketball_other", "basketball",
                    "basketball_euroleague_women"] {
            XCTAssertFalse(TeamShortName.keepsWholeClubName(sportKey: key), key)
        }
        XCTAssertEqual(TeamShortName.short("Sydney Kings", sportKey: "basketball_nbl"), "Kings")
        XCTAssertEqual(TeamShortName.short("Las Vegas Aces", sportKey: "basketball_other"), "Aces")
        XCTAssertEqual(TeamShortName.short("Los Angeles Lakers", sportKey: "basketball_nba"), "Lakers")
    }

    /// ux's after-LOOK: the label changes, the crest does not (`MÜN` stays —
    /// withdrawn as a residual 2026-09-30 06:55Z; three-letter codes are city-based).
    func testTheCrestIsNotReLettered() {
        for name in ["FC Bayern München", "Real Madrid", "Zalgiris Kaunas", "Maccabi Tel Aviv", "KK Crvena zvezda"] {
            XCTAssertEqual(TeamShortName.abbreviation(name, sportKey: Self.euroleague),
                           TeamShortName.abbreviation(name), name)
        }
    }
}
