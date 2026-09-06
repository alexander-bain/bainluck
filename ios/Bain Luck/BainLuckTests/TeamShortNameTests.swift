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

    /// Deriving the badge from `short` alone put the designator straight back on
    /// it whenever the designator leads the name — "FC Schalke 04" drew `FC `,
    /// "AD Ceuta FC" drew `AD `. Measured over the population, 11 badges came
    /// out worse than the pre-#3374 rule. These are those names.
    func testTheBadgeSkipsALeadingDesignator() {
        for (name, expected) in [
            ("FC Schalke 04", "SCH"),
            ("FC Ingolstadt 04", "ING"),
            ("AD Ceuta FC", "CEU"),
            // "AE" is not in the designator set, so it is kept and read as part
            // of the name — AEK, which is what that club is called.
            ("AE Kifisia FC", "AEK"),
            ("AC Milan U20", "MIL"),
            ("AS Roma U20", "ROM"),
            ("1. FC Heidenheim 1846", "HEI"),
            ("FC Viktoria Köln 1904", "VIK"),
            ("US Catanzaro 1929", "USC"),
            ("OB Odense BK", "OBO"),
            ("FK Pardubice W", "PAR"),
        ] {
            XCTAssertEqual(TeamShortName.abbreviation(name), expected, "for \(name)")
        }
    }

    /// The over-correction: skipping leading designators unconditionally leaves
    /// "Athletic Club" reading `CLU`, which names the kind rather than the club.
    /// When every token is a designator the name is already all there is.
    func testTheBadgeNeverSkipsDownToNothing() {
        XCTAssertEqual(TeamShortName.abbreviation("Athletic Club"), "ATH")
        XCTAssertEqual(TeamShortName.abbreviation("AIK"), "AIK")
    }

    /// A badge has room for three characters and a space is not one of them.
    func testTheBadgeIsAlwaysThreeRealGlyphs() {
        XCTAssertEqual(TeamShortName.abbreviation("St. Louis City SC"), "STL")
        XCTAssertEqual(TeamShortName.abbreviation("D.C. United"), "DCU")
        XCTAssertEqual(TeamShortName.abbreviation("Le Mans FC"), "LEM")
        XCTAssertEqual(TeamShortName.abbreviation("St Patricks Athletic"), "STP")
        for name in ["Charlotte FC", "FC Schalke 04", "D.C. United",
                     "St. Louis City SC", "1. FC Heidenheim 1846", "Baltimore Orioles"] {
            let badge = TeamShortName.abbreviation(name)
            XCTAssertEqual(badge.count, 3, "\(name) drew \(badge)")
            XCTAssertTrue(badge.allSatisfy { $0.isLetter || $0.isNumber },
                          "\(name) drew \(badge), which is not three glyphs")
        }
    }

    /// `teams` spells the women's marker both ways. Trimming only `.` and `,`
    /// caught "Argentina W" and missed "Harvard Crimson (W)", so three women's
    /// sides still rendered with `(W)` as their entire label.
    func testTheParenthesisedWomensMarkerIsADesignatorToo() {
        XCTAssertEqual(TeamShortName.short("Harvard Crimson (W)"), "Harvard Crimson (W)")
        XCTAssertEqual(TeamShortName.short("Stanford Cardinal (W)"), "Stanford Cardinal (W)")
        XCTAssertEqual(TeamShortName.short("Alabama State Hornets (W)"), "Alabama State Hornets (W)")
        XCTAssertEqual(TeamShortName.abbreviation("Harvard Crimson (W)"), "HAR")
    }

    // MARK: - degenerate input

    func testNothingToShortenIsReturnedUnchanged() {
        XCTAssertEqual(TeamShortName.short(""), "")
        XCTAssertEqual(TeamShortName.short("Barcelona"), "Barcelona")
        XCTAssertEqual(TeamShortName.short("  "), "  ")
    }
}
