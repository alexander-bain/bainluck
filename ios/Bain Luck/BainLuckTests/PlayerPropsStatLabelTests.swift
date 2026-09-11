import XCTest
@testable import Bain_Luck

/// #5113 — the stat label must drop a prefix the reader can already see, and
/// must keep everything else. The second half is the one that matters: a rule
/// that strips too eagerly loses the stat's own name, which is worse than the
/// truncation it set out to fix.
final class PlayerPropsStatLabelTests: XCTestCase {

    private func label(
        _ marketName: String,
        home: String = "Atlanta Braves",
        away: String = "Tampa Bay Rays",
        player: String? = "Ronald Acuña Jr."
    ) -> String {
        PlayerPropsStatLabel.display(
            marketName: marketName,
            homeTeam: home,
            awayTeam: away,
            player: player
        )
    }

    // MARK: - The photographed defect

    func testMatchupPrefixIsDropped() {
        XCTAssertEqual(
            label("Tampa Bay vs Atlanta: Hits + Runs + RBIs"),
            "Hits + Runs + RBIs"
        )
    }

    func testAbbreviatedTeamShapesStillMatch() {
        // Both observed in production on 2026-09-11.
        XCTAssertEqual(
            label(
                "Dallas vs New York G: Passing Yards",
                home: "New York Giants",
                away: "Dallas Cowboys",
                player: "Dak Prescott"
            ),
            "Passing Yards"
        )
        XCTAssertEqual(
            label(
                "New York J vs Tennessee: Receptions",
                home: "Tennessee Titans",
                away: "New York Jets",
                player: "Garrett Wilson"
            ),
            "Receptions"
        )
    }

    // MARK: - The other served shape

    func testPlayerPrefixIsDropped() {
        // Polymarket puts the player where Kalshi puts the matchup.
        XCTAssertEqual(
            label("Cole Young: Total Bases O/U 2.5", player: "Cole Young"),
            "Total Bases O/U 2.5"
        )
    }

    func testPlayerPrefixMatchesAcrossDiacriticsAndCase() {
        XCTAssertEqual(
            label("ronald acuna jr.: Stolen Bases", player: "Ronald Acuña Jr."),
            "Stolen Bases"
        )
    }

    // MARK: - What must NOT be stripped

    func testOnlyOneTeamNamedIsNotAMatchup() {
        // "Atlanta" alone could be the stat's own subject; one side is not the
        // pair the nav bar shows.
        XCTAssertEqual(
            label("Atlanta: Team Total Runs"),
            "Atlanta: Team Total Runs"
        )
    }

    func testAStatNameContainingAColonSurvives() {
        XCTAssertEqual(
            label("Shots at Goal: First Half", player: "Bukayo Saka"),
            "Shots at Goal: First Half"
        )
    }

    func testUnrelatedPrefixSurvives() {
        XCTAssertEqual(
            label("Longest Reception: Yards", player: "Garrett Wilson"),
            "Longest Reception: Yards"
        )
    }

    func testEmptyRemainderKeepsTheServedName() {
        // Never render nothing.
        XCTAssertEqual(
            label("Tampa Bay vs Atlanta:"),
            "Tampa Bay vs Atlanta:"
        )
    }

    func testNoColonIsUntouchedApartFromNoisePrefix() {
        XCTAssertEqual(label("Total Bases"), "Total Bases")
        XCTAssertEqual(label("Player Strikeouts"), "Strikeouts")
    }

    // MARK: - Degenerate inputs

    func testMissingTeamNamesStripNothing() {
        // An event that has not named its teams cannot claim the prefix is
        // redundant.
        XCTAssertEqual(
            label("Tampa Bay vs Atlanta: RBIs", home: "", away: "", player: nil),
            "Tampa Bay vs Atlanta: RBIs"
        )
    }

    func testNilPlayerDoesNotStripAPlayerPrefix() {
        XCTAssertEqual(
            label("Cole Young: Total Bases", home: "", away: "", player: nil),
            "Cole Young: Total Bases"
        )
    }

    func testJoinerAloneCannotSatisfyBothSides() {
        // "vs" is below the token floor, so a prefix naming one team plus the
        // joiner must not read as naming both.
        XCTAssertEqual(
            label(
                "Atlanta vs Atlanta: RBIs",
                home: "Atlanta Braves",
                away: "Boston Red Sox",
                player: nil
            ),
            "Atlanta vs Atlanta: RBIs"
        )
    }

    func testNoisePrefixIsStrippedAfterTheMatchup() {
        XCTAssertEqual(
            label("Tampa Bay vs Atlanta: Player Hits"),
            "Hits"
        )
    }
}
