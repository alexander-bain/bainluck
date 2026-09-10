import XCTest
@testable import Bain_Luck

/// #4539 — THE IPHONE BADGES PARIS SAINT-GERMAIN AS `GER`.
///
/// #4466 is the browser half, photographed by Alex on production `/discover` at
/// 390px on 2026-09-09 12:40 PT: the live UCL card "ŠK Slovan Bratislava @ Paris
/// Saint Germain" drew PSG's crest tile as **`GER`**. An independent LOOK an hour
/// later shot the same fixture drawing **`SAI`**. The app reaches both values by
/// the same route, because `abbreviation` derives from `short`, and `short`
/// returns the last word:
///
///     "Paris Saint Germain"  -> "Germain"       -> GER
///     "Paris Saint-Germain"  -> "Saint-Germain" -> SAI
///
/// THE STORED SPELLING IS AN INPUT AND BOTH ARE LIVE, which is why a fix
/// validated against one spelling has not been tested. That pair is the first
/// case below.
///
/// #4466 fixed the browser and did not touch Swift, so from the moment it landed
/// the two clients disagreed on the badge for roughly a fifth of all names. This
/// file is the iPhone catching up, and every expected value in it was read off
/// the BROWSER's `teamCrestBadge` before being written down — a separately
/// written implementation of the same rule is the only honest oracle for a
/// parity port, and re-deriving them from the Swift under test would make this
/// file agree with the bug.
final class CrestBadgeInitialsTests: XCTestCase {

    // MARK: The photographed defect

    func testTheUCLCardBadgesTheClubAndNotAFragmentOfItsName() {
        XCTAssertEqual(TeamShortName.abbreviation("Paris Saint Germain"), "PSG")
        XCTAssertNotEqual(TeamShortName.abbreviation("Paris Saint Germain"), "GER")
    }

    /// The half a single-specimen fix passes while a reader still fails: one club
    /// must not wear two different badges on two rows of the same page.
    func testBothStoredSpellingsOfOneClubBadgeTheSame() {
        let spaced = TeamShortName.abbreviation("Paris Saint Germain")
        let hyphenated = TeamShortName.abbreviation("Paris Saint-Germain")
        XCTAssertEqual(spaced, hyphenated)
        XCTAssertEqual(hyphenated, "PSG")
        XCTAssertNotEqual(hyphenated, "SAI")
    }

    // MARK: The fork, and the 80% it must not touch

    /// The last-word rule is RIGHT for `<place> <nickname>` and — thanks to the
    /// designator set — for `<place> <club-type>` too. Two-part names keep their
    /// shipped badge exactly; at two initials these would read `IT`, `RM`, `BC`.
    func testATwoPartNameKeepsTheBadgeItShipped() {
        for (name, expected) in [
            ("Ipswich Town", "IPS"),
            ("Real Madrid", "MAD"),
            ("Boston Celtics", "CEL"),
            ("Altrincham FC", "ALT"),
            ("Charlotte FC", "CHA"),
            ("Baltimore Orioles", "ORI"),
        ] {
            XCTAssertEqual(TeamShortName.abbreviation(name), expected, "for \(name)")
        }
    }

    /// Three or more DISTINCTIVE words means the last one is a fragment of a
    /// compound rather than a name anybody uses.
    func testAThreePartNameTakesItsInitials() {
        for (name, expected) in [
            ("Los Angeles Lakers", "LAL"),
            ("New York Mets", "NYM"),
            ("Los Angeles Dodgers", "LAD"),
            ("Sport Lisboa e Benfica", "SLB"),
            ("Johor Darul Ta'zim", "JDT"),
            ("Central Coast Mariners", "CCM"),
        ] {
            XCTAssertEqual(TeamShortName.abbreviation(name), expected, "for \(name)")
        }
    }

    /// The measured regression that ruled out a two-glyph badge: at two initials
    /// the Mets and the Yankees are both `NY`.
    func testTheSameCityPairsTwoInitialsCannotSeparate() {
        XCTAssertNotEqual(TeamShortName.abbreviation("New York Mets"),
                          TeamShortName.abbreviation("New York Yankees"))
    }

    // MARK: It is not a bare word count, and that is the whole design

    /// THE CLASS THAT NEARLY SHIPPED ON THE BROWSER. Taking initials of every
    /// token once a name has three parts introduced 33 badges master does not
    /// paint, measured over the whole production population — every `<W> Town FC`
    /// club rendering `WTF` among them. Filtering the tokens that identify nobody
    /// BEFORE counting them removes the class structurally rather than by
    /// blocklist, which is why each of these resolves to the CLUB and not merely
    /// to something unobjectionable.
    func testATokenThatIdentifiesNobodyIsNotCounted() {
        for (name, expected) in [
            ("Warrington Town FC", "WAR"),
            ("Whitby Town FC", "WHI"),
            ("FC Akhmat Grozny", "GRO"),
            ("FC Universitatea Cluj", "CLU"),
            // The browser draws `SAD` here and the iPhone `ALS`, and both are
            // the club. This is the one place the two clients' <3-token
            // fallbacks legitimately differ: the browser SLICES the short name
            // and repairs the fragment afterwards, while `glyphs` has crossed
            // word boundaries since #3374. Neither is #4539's fork — what
            // matters is that `ASS` is unreachable on both.
            ("Al Sadd SC", "ALS"),
            ("AC Milan U20", "MIL"),
            ("1. FC Heidenheim 1846", "HEI"),
        ] {
            XCTAssertEqual(TeamShortName.abbreviation(name), expected, "for \(name)")
        }
    }

    /// The backstop, and the control that it did not over-fire. A three-part
    /// PERSON name is all-distinctive by construction and no filter that keeps
    /// "Paris Saint Germain" working can tell the two apart from the string
    /// alone — so when the initials spell something unshippable the badge reverts
    /// to the surname, which is the right answer for a person anyway.
    func testAnUnshippableBadgeIsNeverIntroduced() {
        XCTAssertEqual(TeamShortName.abbreviation("Ana Sofia Sanchez"), "SAN")
        XCTAssertEqual(TeamShortName.abbreviation("Abhinav Sanjeev Shanmugam"), "SHA")
        XCTAssertEqual(TeamShortName.abbreviation("Ku Keon Kang"), "KAN")
        // …and the fix survives the backstop.
        XCTAssertEqual(TeamShortName.abbreviation("Paris Saint Germain"), "PSG")
    }

    /// A badge is three real glyphs. A distinctive token can OPEN with
    /// punctuation the split does not separate on, and taking its first
    /// CHARACTER puts a bracket on a crest: the browser draws `A(L` for "Atalanta
    /// (1st Leg)" and `B(A` for the real club "Bradford (Park Avenue) AFC", 33
    /// distinct production names in all. The iPhone takes the first GLYPH
    /// instead. This is a deliberate divergence from the browser — filed as
    /// #4625 — and it is the one place this port does not copy it.
    func testAnInitialIsAGlyphAndNeverPunctuation() {
        for name in ["Atalanta (1st Leg)", "Bradford (Park Avenue) AFC",
                     "Loyola (Chi) Ramblers", "Southern Indiana (Game 1)"] {
            let badge = TeamShortName.abbreviation(name)
            XCTAssertTrue(badge.allSatisfy { $0.isLetter || $0.isNumber },
                          "\(name) drew \(badge), which is not three glyphs")
        }
        XCTAssertEqual(TeamShortName.abbreviation("Bradford (Park Avenue) AFC"), "BPA")
    }

    /// A doubles pair is two names, not a compound one, so the fork must not see
    /// it — unguarded, "Milutinovic / Van de Peer" has three surviving tokens and
    /// would badge `MVP`. These are the values the iPhone draws TODAY and they
    /// are pinned here unchanged, which is the whole point of the guard.
    ///
    /// #4626 UPDATED THE EXPECTED VALUES, NOT THE RULE THIS TEST GUARDS. When
    /// this test was written the three values below were `TOW`, `PEE` and `KRA`
    /// — the SECOND surname — because `TeamShortName.short` had no
    /// `isDoublesPair` guard and simply took the last word, while the browser
    /// obeyed #3110 and drew the first. #4626 gave `short` the browser's guard,
    /// so the pair now arrives here whole and `glyphs(ofLabel:)` takes the first
    /// three of it: `SIN`, `MIL`, `HUN`, matching the site.
    ///
    /// What #4539's guard still does, and what this test is still for, is keep
    /// the pair OUT of the initials fork. That is a different question from
    /// which player the badge names, and it is the one that would silently
    /// change if somebody deleted the `isDoublesPair(name)` line from
    /// `abbreviation`: unguarded, "Milutinovic / Van de Peer" has three
    /// surviving distinctive tokens and would badge `MVP`.
    func testADoublesPairIsNotReopened() {
        XCTAssertEqual(TeamShortName.abbreviation("Siniakova / Townsend"), "SIN")
        XCTAssertEqual(TeamShortName.abbreviation("Milutinovic / Van de Peer"), "MIL")
        XCTAssertEqual(TeamShortName.abbreviation("Hunter / Krawczyk"), "HUN")
        // The guard is what keeps these three glyphs of ONE name rather than
        // initials of three: each of these names has three or more distinctive
        // tokens once the pair separator is not treated as a boundary.
        XCTAssertNotEqual(TeamShortName.abbreviation("Milutinovic / Van de Peer"), "MVP")
    }

    // MARK: The fork must not disarm #3430

    /// THE REGRESSION THIS ALMOST SHIPPED, and the reason `abbreviationPair` grows
    /// on the LABELS. The fork can move ONE side of a derby off the word the two
    /// clubs share while the other keeps it; two badges that now differ are never
    /// grown, so the collision stops being detected. Growing on badges alone
    /// moved 79 rows of `TeamShortNamePairTests` and left the away side of each
    /// of these naming the city — or the sport — that both sides share.
    func testADerbyStillSeparatesWhenOnlyOneSideTakesTheFork() {
        for (away, home, wantAway, wantHome) in [
            ("FK Septemvri Sofia", "PFC Levski Sofia", "SEP", "LEV"),
            ("FK Partizan Belgrade", "FK Crvena Zvezda Belgrade", "PAR", "ZVE"),
            ("Chartres Metropole Handball", "Montpellier Handball", "MET", "MON"),
            ("AD San Carlos", "Inter San Carlos", "SAN", "INT"),
        ] {
            let badges = TeamShortName.abbreviationPair(away: away, home: home)
            XCTAssertEqual(badges.away, wantAway, "away badge for \(away) v \(home)")
            XCTAssertEqual(badges.home, wantHome, "home badge for \(away) v \(home)")
            XCTAssertNotEqual(badges.away, badges.home)
        }
    }

    /// The control for the clause above: it must not fire on every pair, or the
    /// fork would be dead code. These two labels differ, so the fork applies.
    func testThePairRuleStillLetsTheForkThroughWhenTheLabelsDiffer() {
        let badges = TeamShortName.abbreviationPair(away: "Slovan Bratislava",
                                                    home: "Paris Saint Germain")
        XCTAssertEqual(badges.home, "PSG")
    }

    /// A served abbreviation still wins wherever it discriminates — growth is
    /// only ever reached for labels we derived ourselves, and #4539 did not
    /// change that.
    func testAServedPairStillWinsEvenWhenTheLabelsCollide() {
        let badges = TeamShortName.abbreviationPair(
            away: "Clemson Tigers", home: "LSU Tigers",
            awayServed: "CLEM", homeServed: "LSU"
        )
        XCTAssertEqual(badges.away, "CLEM")
        XCTAssertEqual(badges.home, "LSU")
    }
}
