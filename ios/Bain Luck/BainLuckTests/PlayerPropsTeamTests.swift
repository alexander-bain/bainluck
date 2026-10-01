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

    // MARK: - #6866 — a team's own ladders

    /// Served verbatim on `/api/events/14780550/game-markets` (Steelers at
    /// Browns, 2026-10-01), every row `player_team: null`.
    private let home = "Cleveland Browns"
    private let away = "Pittsburgh Steelers"

    private func side(_ subject: String, _ market: String,
                      home: String? = nil, away: String? = nil) -> PlayerPropsTeam.Side {
        PlayerPropsTeam.teamSubjectSide(
            subject: subject, marketName: market,
            homeTeam: home ?? self.home, awayTeam: away ?? self.away
        )
    }

    /// The specimen: both teams' ladders land on their own side, so the crest,
    /// the word and the Steelers/Browns filter can all name them.
    func testTheSpecimensTeamLaddersNameTheirSide() {
        XCTAssertEqual(side("Pittsburgh", "Pittsburgh vs Cleveland: Team Sacks"), .away)
        XCTAssertEqual(side("Pittsburgh", "Pittsburgh vs Cleveland: Team Total Yards"), .away)
        XCTAssertEqual(side("Cleveland", "Pittsburgh vs Cleveland: Team Sacks"), .home)
        XCTAssertEqual(side("Cleveland", "Pittsburgh vs Cleveland: Team Total Yards"), .home)
        XCTAssertEqual(side("Cleveland", "Pittsburgh vs. Cleveland: Team Field Goals"), .home)
        // A whole-name subject is the team too.
        XCTAssertEqual(side("Cleveland Browns", "Pittsburgh Steelers vs Cleveland Browns: Team Touchdowns"), .home)
    }

    /// 🔴 The no-claim arms. Each is one clause of the rule failing on its own,
    /// with the other two still true — so a rule that dropped any clause fails
    /// exactly one of these.
    func testEveryClauseRefusesOnItsOwn() {
        // Clause 1 — not a `Team ` phrase: a player's ladder, even if the
        // subject happened to be a city.
        XCTAssertEqual(side("Pittsburgh", "Pittsburgh vs Cleveland: Total Yards"), .unknown)
        XCTAssertEqual(side("Deshaun Watson", "Pittsburgh vs Cleveland: Passing Yards"), .unknown)
        // Clause 2 — the subject is not one of THIS market's two names.
        XCTAssertEqual(side("Pittsburgh", "Cincinnati vs Cleveland: Team Sacks"), .unknown)
        XCTAssertEqual(side("Pittsburgh", "Team Sacks"), .unknown, "no colon, no matchup")
        // Esports organisations, measured on production in #6866, where "Team"
        // is part of the club's name: a row that reaches the wrong game names
        // neither of ITS teams, so it claims nothing…
        XCTAssertEqual(side("Team Liquid", "Team Liquid vs Karmine Corp: Team Kills"), .unknown)
        // …and on its own game it is honestly that club's ladder.
        XCTAssertEqual(side("Team Liquid", "Team Liquid vs Karmine Corp: Team Kills",
                            home: "Karmine Corp", away: "Team Liquid"), .away)
        // Clause 3 — a name that answers BOTH clubs proves neither.
        XCTAssertEqual(side("Los Angeles", "Los Angeles vs Los Angeles: Team Sacks",
                            home: "Los Angeles Rams", away: "Los Angeles Chargers"), .unknown)
        // …and a name that answers NEITHER (a word prefix, not a whole word).
        XCTAssertEqual(side("Pitt", "Pitt vs Cleveland: Team Sacks"), .unknown)
    }

    /// The team rule feeds the same three outputs the served side does, so a
    /// proven team gets the word, the colour and the filter — not just a crest.
    func testAProvenTeamAnswersItsOwnFilter() {
        let s = side("Pittsburgh", "Pittsburgh vs Cleveland: Team Sacks")
        XCTAssertEqual(PlayerPropsTeam.label(for: s), "Away")
        XCTAssertEqual(PlayerPropsTeam.filterValue(for: s), "away")
        XCTAssertEqual(PlayerPropsTeam.color(for: s, home: .red, away: .blue), .blue)
    }
}

