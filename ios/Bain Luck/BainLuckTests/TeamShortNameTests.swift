import XCTest
@testable import Bain_Luck

/// #3374 — the live Discover card labelled Charlotte FC **"FC"**.
///
/// Photographed 2026-09-05 on the MLS card for Houston Dynamo @ Charlotte FC:
/// the crest row read `Dynamo` and `FC`. The rule that produced it —
/// `name.split(separator: " ").last` — was hand-rolled in 39 places across 15
/// files on this target, so every surface showing a team in less room than its
/// full name had the same defect.
///
/// The inputs below are real `teams.name` rows pulled from production on
/// 2026-09-05 (`artifacts-native-031/teams_population.json`, 5,559 distinct
/// names). The expected labels are what a reader should see, which is the one
/// thing a test must assert by hand.
final class TeamShortNameTests: XCTestCase {

    // MARK: - the photographed defect

    func testTheCardNamesTheTeamItIsShowing() {
        // The exact pair on the card in artifacts-native-031/discover.png.
        XCTAssertEqual(TeamShortName.short("Houston Dynamo"), "Dynamo")
        XCTAssertEqual(TeamShortName.short("Charlotte FC"), "Charlotte FC")
        XCTAssertNotEqual(TeamShortName.short("Charlotte FC"), "FC")
    }

    // MARK: - the last word is right far more often than it is wrong

    func testAMascotLastWordIsLeftAlone() {
        // 5,174 of 5,559 names are unchanged by this rule; these are the shape.
        for (name, expected) in [
            ("Baltimore Orioles", "Orioles"),
            ("Boston Red Sox", "Sox"),
            ("Texas Tech Red Raiders", "Raiders"),
            ("Abilene Christian Wildcats", "Wildcats"),
            ("Houston Dynamo", "Dynamo"),
            ("CF Montreal", "Montreal"),
            ("1. FC Köln", "Köln"),
        ] {
            XCTAssertEqual(TeamShortName.short(name), expected, "for \(name)")
        }
    }

    // MARK: - a designator names nothing, so the name is shown instead

    func testADesignatorIsNeverTheWholeLabel() {
        // Each of these produced the bare designator before #3374. The counts in
        // the comments are how many distinct teams collapsed onto that label.
        for (name, expected) in [
            ("Charlotte FC", "Charlotte FC"),              // FC   — 102 teams
            ("Toronto FC", "Toronto FC"),
            ("Inter Miami CF", "Inter Miami CF"),
            ("Columbus Crew SC", "Columbus Crew SC"),      // SC   — 10 teams
            ("Orlando City SC", "Orlando City SC"),
            ("D.C. United", "D.C. United"),                // United — 24 teams
            ("Sporting Kansas City", "Sporting Kansas City"), // City — 26 teams
            ("Cheltenham Town", "Cheltenham Town"),        // Town — 11 teams
            ("Argentina W", "Argentina W"),                // W    — 30 teams
            ("Andy Ruiz Jr", "Andy Ruiz Jr"),              // Jr   — 23 boxers
            ("Alverca B", "Alverca B"),                    // B    — 22 teams
            ("Arminia Bielefeld II", "Arminia Bielefeld II"), // II — 15 teams
            ("AC Milan U20", "AC Milan U20"),
            ("Abha Club", "Abha Club"),
        ] {
            XCTAssertEqual(TeamShortName.short(name), expected, "for \(name)")
        }
    }

    func testAFoundingYearIsADesignatorToo() {
        // The shipped rule printed "1. FC Heidenheim 1846" as `1846`.
        XCTAssertEqual(TeamShortName.short("1. FC Heidenheim 1846"), "1. FC Heidenheim 1846")
        XCTAssertEqual(TeamShortName.short("AD Marco 09"), "AD Marco 09")
    }

    /// The rule must not split a multi-word place to reach the designator — an
    /// earlier draft extended leftward one token and rendered "San Diego FC" as
    /// `Diego FC`, which is a different wrong answer, not a fix.
    func testAMultiWordPlaceIsNotCutInHalf() {
        XCTAssertEqual(TeamShortName.short("San Diego FC"), "San Diego FC")
        XCTAssertEqual(TeamShortName.short("Los Angeles FC"), "Los Angeles FC")
        XCTAssertEqual(TeamShortName.short("Felixstowe and Walton United FC"),
                       "Felixstowe and Walton United FC")
    }

    // MARK: - the output vocabulary is closed

    /// Measured over all 5,559 production names: the only labels that are still
    /// a bare designator are the two clubs whose entire name is that word.
    func testTheOnlyBareDesignatorLabelsAreWholeTeamNames() {
        XCTAssertEqual(TeamShortName.short("AIK"), "AIK")
        XCTAssertEqual(TeamShortName.short("Wanderers"), "Wanderers")
    }

    /// Anything with more than one word must never render as a lone designator.
    func testNoMultiWordNameEverRendersAsALoneDesignator() {
        let designators = ["FC", "SC", "CF", "AC", "United", "City", "Town",
                           "County", "Club", "W", "B", "II", "Jr", "Sr", "U21"]
        for d in designators {
            for prefix in ["Charlotte", "San Diego", "Real Sociedad de Futbol"] {
                let label = TeamShortName.short("\(prefix) \(d)")
                XCTAssertNotEqual(label.lowercased(), d.lowercased(),
                                  "\(prefix) \(d) rendered as the bare designator \(d)")
                XCTAssertTrue(label.contains(prefix), "\(prefix) \(d) lost its name")
            }
        }
    }

    // MARK: - the crest placeholder had the same defect

    func testTheCrestPlaceholderSpellsTheTeamNotTheDesignator() {
        XCTAssertEqual(TeamShortName.abbreviation("Charlotte FC"), "CHA")
        XCTAssertEqual(TeamShortName.abbreviation("Toronto FC"), "TOR")
        XCTAssertEqual(TeamShortName.abbreviation("Baltimore Orioles"), "ORI")
        XCTAssertEqual(TeamShortName.abbreviation("Boston Red Sox"), "SOX")
        // Before #3374 all four FC clubs drew the same two letters.
        XCTAssertNotEqual(TeamShortName.abbreviation("Charlotte FC"),
                          TeamShortName.abbreviation("Toronto FC"))
    }

    // MARK: - degenerate input

    func testNothingToShortenIsReturnedUnchanged() {
        XCTAssertEqual(TeamShortName.short(""), "")
        XCTAssertEqual(TeamShortName.short("Barcelona"), "Barcelona")
        XCTAssertEqual(TeamShortName.short("  "), "  ")
    }
}
