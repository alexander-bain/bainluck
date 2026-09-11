import SwiftUI
import XCTest
@testable import Bain_Luck

/// #4919 — A NULL `player_team` WAS RENDERED AS "AWAY".
///
/// Photographed on `bainluck://events/15305028` (Seattle @ New England): all
/// five player cards printed "Away" under the name — on New England's own home
/// game. The filed specimen is also a badly-attached row (#3529), which invites
/// the reading that this is downstream of that; it is not. Mirroring the card's
/// render condition against `/api/events/14780143/game-markets` — Bucs @
/// Bengals, correctly matched, scheduled, 325 prop rows — measured by native/109
/// on 2026-09-10:
///
///     player_team over 325 rows      home 126 · away 104 · **null 95**
///     rendered player cards          20
///     cards whose rows are all null  **4**  (Kenny Gainwell, Colbie Young,
///                                            Jack Endries, Ted Hurst III)
///
/// Gainwell is a Bengal — the HOME side — and the app printed "Away" under his
/// name. The old line was `props.first?.prop.playerTeam ?? "away"`, and `"home"`
/// was the only value that produced "Home", so every unknown fell one way.
///
/// These tests are written against the mapping, not against a rendered card,
/// because the defect is a property of the mapping: it had no third state, so
/// there was nowhere for "we do not know" to go. `testUnknownMakesNoClaim` is
/// the arm that fails on the old code and kills the bug class; the other two
/// pin the known sides so the fix cannot be "stop labelling anything".
final class PlayerPropsTeamTests: XCTestCase {

    // MARK: - The bug class

    /// 🔴 THE ONE THAT MATTERS. An absent side must make no claim in ANY of the
    /// three places one served value feeds. Testing only the label would leave
    /// the colour and the filter still asserting "away" — the card would read
    /// silent and still be tinted and filed as the away team, which is what a
    /// reader who ignores small grey type actually saw.
    func testUnknownMakesNoClaim() {
        let home = Color.red
        let away = Color.blue

        for served in [nil, "", "HOME", "Home", "cincinnati bengals", "unknown"] as [String?] {
            let side = PlayerPropsTeam.side(for: served)
            XCTAssertEqual(
                side, .unknown,
                "\(String(describing: served)) is not evidence for a side"
            )
            XCTAssertNil(
                PlayerPropsTeam.label(for: side),
                "an unattributed player must print no label"
            )
            XCTAssertNil(
                PlayerPropsTeam.filterValue(for: side),
                "an unattributed player must answer neither team filter"
            )
            let tint = PlayerPropsTeam.color(for: side, home: home, away: away)
            XCTAssertNotEqual(tint, away, "the neutral tint must not be the away colour")
            XCTAssertNotEqual(tint, home, "the neutral tint must not be the home colour")
        }
    }

    /// The regression guard for the filter specifically: `nil` must not compare
    /// equal to either filter value. `PlayerPropsCardView.filteredCards` matches
    /// with `$0.team == teamFilter` against a `String?`, so this is the property
    /// that keeps Gainwell out of the away team's roster.
    func testUnknownAnswersNeitherTeamFilter() {
        let unknown = PlayerPropsTeam.filterValue(for: .unknown)
        XCTAssertFalse(unknown == "home")
        XCTAssertFalse(unknown == "away")
    }

    // MARK: - The known sides still read

    func testHomeIsLabelledAndTintedHome() {
        let side = PlayerPropsTeam.side(for: "home")
        XCTAssertEqual(side, .home)
        XCTAssertEqual(PlayerPropsTeam.label(for: side), "Home")
        XCTAssertEqual(PlayerPropsTeam.filterValue(for: side), "home")
        XCTAssertEqual(
            PlayerPropsTeam.color(for: side, home: .red, away: .blue), .red
        )
    }

    func testAwayIsLabelledAndTintedAway() {
        let side = PlayerPropsTeam.side(for: "away")
        XCTAssertEqual(side, .away)
        XCTAssertEqual(PlayerPropsTeam.label(for: side), "Away")
        XCTAssertEqual(PlayerPropsTeam.filterValue(for: side), "away")
        XCTAssertEqual(
            PlayerPropsTeam.color(for: side, home: .red, away: .blue), .blue
        )
    }

    /// The two values the serializer actually emits (`routes/events.py`,
    /// `side = "home" if home_short.lower() in tn_lower else "away"`) are the
    /// only two that may reach a side. Stated as a test so that widening the
    /// mapping is a deliberate edit rather than a `default:` someone loosens.
    func testOnlyTheTwoServedValuesReachASide() {
        XCTAssertNotEqual(PlayerPropsTeam.side(for: "home"), .unknown)
        XCTAssertNotEqual(PlayerPropsTeam.side(for: "away"), .unknown)
        XCTAssertEqual(PlayerPropsTeam.side(for: "neutral"), .unknown)
    }
}
