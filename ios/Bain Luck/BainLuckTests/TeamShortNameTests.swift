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
        // #4539 — three distinctive words, so the badge is their initials. `SOX`
        // was this row until the initials fork landed; the browser has printed
        // `BRS` since #4466 and the two clients now agree. Pinned as the accepted
        // cost it is: familiarity traded for a badge that cannot be the White Sox
        // too. The two-part names above are deliberately untouched by the fork.
        XCTAssertEqual(TeamShortName.abbreviation("Boston Red Sox"), "BRS")
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
            // #4271. This row read `USC` until the Italian society initials
            // went into the designator set, and it was the one name in this
            // list that the test's own thesis did not hold for: "US" is
            // Unione Sportiva, so `USC` names the kind of club and then
            // borrows three letters from a university in another sport.
            // Unlike "AE Kifisia" above, nobody calls Catanzaro "USC".
            ("US Catanzaro 1929", "CAT"),
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

    // MARK: - #4627, the hand-picked label

    /// The photographed defect. `bainluck://events/15296760`, Champions League,
    /// shot 2026-09-09: the hero read "Germain Win".
    ///
    /// Alex ruled the list, not a rule (2026-09-12, option B): "PSG Win", as an
    /// explicit entry. All three spellings are live on production — measured over
    /// 60 days of `events` on 2026-09-12 — and they produced three DIFFERENT
    /// labels before this entry, which is the half of the defect the issue did
    /// not name.
    func testTheHandPickedLabelNamesTheClubOnEverySpellingProductionCarries() {
        for name in [
            "Paris Saint Germain",    // 9 events — was "Germain"
            "Paris Saint-Germain",    // 9 events — was "Saint-Germain"
            "Paris Saint-Germain FC", // 14 events — was the whole name
        ] {
            XCTAssertEqual(TeamShortName.short(name), "PSG", "for \(name)")
        }
    }

    /// The control Alex named in the ruling itself: this may not become a rule
    /// that turns the Lakers into "LAL Win". The badge's three-distinctive-token
    /// fork counts all three of these as three distinctive tokens, so a label
    /// built on it would rewrite every one of them.
    func testTheListDoesNotBecomeARuleAboutThreeWordNames() {
        for (name, expected) in [
            ("Los Angeles Lakers", "Lakers"),
            ("Boston Red Sox", "Sox"),
            ("Texas Tech Red Raiders", "Raiders"),
            ("New England Revolution", "Revolution"),
            ("Baltimore Orioles", "Orioles"),
        ] {
            XCTAssertEqual(TeamShortName.short(name), expected, "for \(name)")
        }
    }

    /// A key is only worth anything if a real row reaches it. One written in the
    /// spelling a human types — "Paris Saint-Germain", capitals and a dash — can
    /// never be looked up, and every test that went through `short` alone would
    /// still pass because the rule would answer instead.
    func testEveryHandPickedKeyIsReachable() {
        XCTAssertFalse(TeamShortName.handPickedLabels.isEmpty)
        for key in TeamShortName.handPickedLabels.keys {
            XCTAssertEqual(TeamShortName.handPickedKey(key), key,
                           "\(key) is not in normalised form, so no name can reach it")
        }
    }

    /// Two clubs claiming one label is #3430's photographed defect ("Tigers 10 -
    /// Tigers 51") reintroduced by hand, and the pair rule cannot repair it —
    /// growth works on the raw names and would hand back the fragments this list
    /// exists to remove.
    func testNoTwoClubsClaimTheSameHandPickedLabel() {
        let values = Array(TeamShortName.handPickedLabels.values)
        XCTAssertEqual(Set(values).count, values.count,
                       "two entries share a label: \(values.sorted())")
    }

    /// The key folds the spellings of ONE club together and no further. The
    /// two-token floor is the whole of that second half: without it "Manchester
    /// United" keys as `manchester`, which is also what "Manchester City" would
    /// key as, and a future entry for either would silently relabel the other.
    func testTheKeyFoldsSpellingsWithoutMergingClubs() {
        // One club, four spellings, one key.
        for spelling in ["Paris Saint Germain", "Paris Saint-Germain",
                         "Paris Saint-Germain FC", "Paris Saint Germain W"] {
            XCTAssertEqual(TeamShortName.handPickedKey(spelling), "paris saint germain",
                           "for \(spelling)")
        }
        // Different clubs, different keys — the designator is the only thing
        // telling these apart, so the floor is what keeps them apart.
        XCTAssertEqual(TeamShortName.handPickedKey("Manchester United"), "manchester united")
        XCTAssertEqual(TeamShortName.handPickedKey("Manchester United FC"), "manchester united")
        XCTAssertEqual(TeamShortName.handPickedKey("Manchester City"), "manchester city")
        XCTAssertNotEqual(TeamShortName.handPickedKey("Manchester United"),
                          TeamShortName.handPickedKey("Manchester City"))
        // A squad marker is not noise either: the women's side keeps its own key.
        XCTAssertNotEqual(TeamShortName.handPickedKey("Arsenal W"),
                          TeamShortName.handPickedKey("Arsenal"))
        XCTAssertNotEqual(TeamShortName.handPickedKey("Arsenal WFC"),
                          TeamShortName.handPickedKey("Arsenal"))
        // Punctuation is not part of a club's identity.
        XCTAssertEqual(TeamShortName.handPickedKey("1. FC Köln"),
                       TeamShortName.handPickedKey("1 FC Köln"))
    }

    /// The badge has printed `PSG` correctly since #4539 and must not move: the
    /// initials fork reaches the same three letters from the raw name, so the
    /// label changing underneath it is a no-op there. Measured over all 13,651
    /// distinct production names on 2026-09-12: **3 labels change and 0 badges**.
    func testTheHandPickedLabelLeavesTheBadgeWhereItWas() {
        for name in ["Paris Saint Germain", "Paris Saint-Germain", "Paris Saint-Germain FC"] {
            XCTAssertEqual(TeamShortName.abbreviation(name), "PSG", "for \(name)")
        }
        // The controls, one from each branch of `abbreviation`.
        XCTAssertEqual(TeamShortName.abbreviation("Charlotte FC"), "CHA")
        XCTAssertEqual(TeamShortName.abbreviation("Los Angeles Lakers"), "LAL")
        XCTAssertEqual(TeamShortName.abbreviation("Siniakova / Townsend"), "SIN")
    }

    /// The photographed matchup, end to end. The other side is returned
    /// byte-identical: measured over the 23,402 distinct (away, home) pairs on
    /// events in the last 45 days, 26 matchups move and every one is a PSG
    /// fixture whose opponent's label is unchanged.
    func testTheHandPickedLabelSurvivesTheMatchupRule() {
        let shot = TeamShortName.shortPair(away: "ŠK Slovan Bratislava",
                                           home: "Paris Saint Germain")
        XCTAssertEqual(shot.home, "PSG")
        XCTAssertEqual(shot.away, "Bratislava")
        let french = TeamShortName.shortPair(away: "Paris Saint-Germain FC",
                                             home: "Olympique de Marseille")
        XCTAssertEqual(french.away, "PSG")
        XCTAssertEqual(french.home, "Marseille")
    }

    /// #4626's invariant is read FIRST and this list does not reopen it: a pair is
    /// two names, and a name that happens to contain a listed club is still a pair.
    func testADoublesPairIsStillReturnedWhole() {
        XCTAssertEqual(TeamShortName.short("Siniakova / Townsend"), "Siniakova / Townsend")
        XCTAssertEqual(TeamShortName.short("Paris Saint Germain / Marseille"),
                       "Paris Saint Germain / Marseille")
    }

    // MARK: - #5651, the two-letter tail

    /// The photographed defect: a trailing token of one or two characters that
    /// nobody thought to list became the whole label, so the iPhone called
    /// Atalanta BC **"BC"** while the website spelled it out.
    ///
    /// Specimens are taken from the measured population, one per shape — a club
    /// type nobody listed (`BC`, `GF`, `HC`, `JK`), a Brazilian state suffix
    /// (`SP`, `MG`, `GO`), a genuine two-letter SURNAME (`Li`, `Oh`), a token
    /// that is only short once its punctuation is stripped (`J.K.`, `R.`), and
    /// the parenthesised marker that `isDesignator`'s trim set never reached
    /// (`(MG)`, `(OH)`). Measured over all 13,618 distinct names on `events` in
    /// the last 45 days (2026-09-12): 177 labels move, every one of them onto
    /// the full name, and 0 move the other way.
    func testATwoLetterTailNeverBecomesTheWholeLabel() {
        for name in [
            "Atalanta BC", "Aarhus GF", "Bergischer HC", "Besiktas JK",
            "AA Internacional Limeira SP", "Atletico Mineiro MG", "Anapolis FC GO",
            "Ann Li", "Chan-Yeong Oh",
            "Beşiktaş J.K.", "Akpejiori R.",
            "Athletic Club (MG)", "Central State (OH)",
        ] {
            XCTAssertEqual(TeamShortName.short(name), name,
                           "\(name) must be spelled out, not reduced to its tail")
        }
    }

    /// The direction invariant, and the reason this change is safe: the new
    /// predicate is a strict superset of the old one on the trailing slot, so a
    /// label may only ever WIDEN. A name whose last word really does name the
    /// team keeps shortening exactly as it always has.
    ///
    /// `Sox` is also the control that pins the clause at two characters: move it
    /// to `<= 3` and "Boston Red Sox" stops shortening.
    func testAThreeLetterTailThatNamesTheTeamStillShortens() {
        XCTAssertEqual(TeamShortName.short("Boston Red Sox"), "Sox")
        XCTAssertEqual(TeamShortName.short("Baltimore Orioles"), "Orioles")
        XCTAssertEqual(TeamShortName.short("Ipswich Town"), "Ipswich Town")
        XCTAssertEqual(TeamShortName.short("Bradford City"), "Bradford City")
        // Two characters is the bar, so a THREE-character tail outside the
        // designator set is untouched — this is the browser's rule, not a
        // blanket refusal to shorten.
        XCTAssertEqual(TeamShortName.short("Chen Hui Ho"), "Chen Hui Ho")
        XCTAssertEqual(TeamShortName.short("Los Angeles Rams"), "Rams")
    }

    /// THE FIX IS ROUTED, NOT WIDENED, AND THIS IS THE TEST THAT SAYS SO.
    ///
    /// The tempting repair is to put the browser's length clause into
    /// `isDesignator`. That function also drives `glyphs(ofLabel:)`'s LEADING
    /// skip, so "Le" would become a designator and the badge for "Le Mans FC"
    /// would move off `LEM` onto `MAN` — a regression invisible to every
    /// assertion about labels. `isDesignator`'s other two callers are pinned
    /// here for the same reason.
    func testTheBadgeAndTheKeyDoNotMoveWithTheLabel() {
        // `glyphs(ofLabel:)` — the leading skip must still see "Le" as a name.
        XCTAssertEqual(TeamShortName.abbreviation("Le Mans FC"), "LEM")
        // ...while still skipping a real leading designator.
        XCTAssertEqual(TeamShortName.abbreviation("FC Schalke 04"), "SCH")
        XCTAssertEqual(TeamShortName.abbreviation("AD Ceuta FC"), "CEU")
        // `handPickedKey` — the trailing strip and its two-token floor.
        XCTAssertEqual(TeamShortName.handPickedKey("Paris Saint-Germain FC"),
                       TeamShortName.handPickedKey("Paris Saint Germain"))
        XCTAssertNotEqual(TeamShortName.handPickedKey("Manchester United"),
                          TeamShortName.handPickedKey("Manchester City"))
        // `namesSomething` — growth must not stop on a leading designator.
        let pair = TeamShortName.shortPair(away: "Guarani FC SP", home: "Guarani FC RJ")
        XCTAssertNotEqual(pair.away, pair.home)
        XCTAssertEqual(pair.away, "Guarani FC SP")
        XCTAssertEqual(pair.home, "Guarani FC RJ")
    }

    /// The widened label reaches the badge, which is the half of this defect
    /// nobody filed: a club whose label was `BC` badged `BC` too, because the
    /// badge takes three glyphs of the label. Measured over the same population:
    /// 169 badges move, every one off a designator and onto a real stamp.
    func testTheWidenedLabelGivesTheBadgeRealLetters() {
        XCTAssertEqual(TeamShortName.abbreviation("Atalanta BC"), "ATA")
        XCTAssertEqual(TeamShortName.abbreviation("Aarhus GF"), "AAR")
        XCTAssertEqual(TeamShortName.abbreviation("Besiktas JK"), "BES")
        XCTAssertEqual(TeamShortName.abbreviation("Amazonas FC AM"), "AMA")
        // #4627's hand-picked entry is read before the rule and is unmoved.
        XCTAssertEqual(TeamShortName.short("Paris Saint-Germain FC"), "PSG")
        XCTAssertEqual(TeamShortName.abbreviation("Paris Saint Germain"), "PSG")
    }

    /// A single-token name has no last word to fall off, so the 49 two-character
    /// labels left in the population after this change are names that ARE two
    /// characters. The browser returns the same thing; this is parity, not a
    /// residue to chase.
    func testASingleTokenNameIsStillReturnedWhole() {
        XCTAssertEqual(TeamShortName.short("AZ"), "AZ")
        XCTAssertEqual(TeamShortName.short("Ai"), "Ai")
    }

    // MARK: - degenerate input

    func testNothingToShortenIsReturnedUnchanged() {
        XCTAssertEqual(TeamShortName.short(""), "")
        XCTAssertEqual(TeamShortName.short("Barcelona"), "Barcelona")
        XCTAssertEqual(TeamShortName.short("  "), "  ")
    }
}
