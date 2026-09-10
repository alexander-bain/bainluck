import XCTest

@testable import Bain_Luck

/// #4626 — a doubles pair is ONE competitor written as TWO surnames, and the
/// app named the wrong one.
///
/// #3110 ruled that a pair is shown WHOLE and its tile is three glyphs of the
/// FIRST surname, and gave the browser `isDoublesPair`. `TeamShortName.swift`
/// never got it: `short` split on spaces and took the last word, so the iPhone
/// named the SECOND player everywhere the site named the first.
///
/// ```
///   stored name                  site      iPhone (before)
///   Siniakova / Townsend         SIN       TOW
///   Hunter / Krawczyk            HUN       KRA
///   Milutinovic / Van de Peer    MIL       PEE      <- on the doubles surface,
///   Aboian / La Serna J          ABO       J           during the US Open
/// ```
///
/// It is not a regression. The iPhone has behaved this way since #3374; it is a
/// ruling that landed in one of two clients and stayed there for six months.
///
/// **THE GUARD BELONGS IN `short`, NOT IN `abbreviation`, AND THAT IS WHAT
/// `test_theLabelIsTheWholePair` IS FOR.** `abbreviation` already had a pair
/// test of its own (#4539 added `if name.contains(" / ")` to keep pairs out of
/// the initials fork), so a reader repairing this issue at the badge could
/// satisfy every badge assertion below while `short` — which also drives the
/// pair LABELS on the hero, the chart gutters and the segment rows — kept
/// printing one half of a pair as if it were the competitor's whole name. The
/// label test is the one that refuses that fix.
///
/// Population, measured on production 2026-09-10 over every distinct side
/// carrying a spaced slash on an event in the last 30 days: **388 names**, of
/// which the 300 sampled yield **297 whose badge changes** — every one from the
/// second player to the first.
final class DoublesPairNamesTheFirstPlayer4626Tests: XCTestCase {

    /// The three names from the issue, plus the one that drew a SINGLE glyph.
    ///
    /// Expected values are the browser's, read out of `teamShortName` and
    /// `teamCrestBadge` (`frontend/lib/teamShortName.ts`) rather than off the
    /// Swift under test — the rule `TeamShortNamePairTests`' header sets for
    /// every value that moves in this file.
    private static let specimens: [(name: String, badge: String)] = [
        ("Siniakova / Townsend", "SIN"),
        ("Hunter / Krawczyk", "HUN"),
        ("Milutinovic / Van de Peer", "MIL"),
        ("Aboian / La Serna J", "ABO"),
        ("Arnaldi / Struff J-L", "ARN"),
    ]

    // MARK: The label

    /// A pair is returned WHOLE, which is the half of this fix a badge-only
    /// repair does not reach.
    func test_theLabelIsTheWholePair() {
        for (name, _) in Self.specimens {
            XCTAssertEqual(
                TeamShortName.short(name), name,
                "short(\(name)) must return the pair whole, not one player")
        }
    }

    /// Stated as its own case because it is the READER's complaint: before this
    /// fix the label named a player who is in the match but is not the whole
    /// competitor, which reads as a singles fixture.
    func test_theLabelIsNotTheSecondPlayerAlone() {
        XCTAssertNotEqual(TeamShortName.short("Siniakova / Townsend"), "Townsend")
        XCTAssertNotEqual(TeamShortName.short("Milutinovic / Van de Peer"), "Peer")
        XCTAssertNotEqual(TeamShortName.short("Aboian / La Serna J"), "J")
    }

    // MARK: The badge

    func test_theBadgeIsThreeGlyphsOfTheFirstSurname() {
        for (name, want) in Self.specimens {
            XCTAssertEqual(TeamShortName.abbreviation(name), want, "badge for \(name)")
        }
    }

    /// "Aboian / La Serna J" badged the bare letter `J` — the last word of the
    /// name is a one-character initial — so this class was not merely naming the
    /// wrong player, it was breaking the three-glyph invariant the crest tile is
    /// laid out for. Asserted as a property so the next such name is caught
    /// without being listed.
    func test_everyPairBadgeFillsThreeRealGlyphs() {
        for (name, _) in Self.specimens {
            let badge = TeamShortName.abbreviation(name)
            XCTAssertEqual(badge.count, 3, "\(name) drew \(badge)")
            XCTAssertTrue(
                badge.allSatisfy { $0.isLetter || $0.isNumber },
                "\(name) drew \(badge), which is not three real glyphs")
        }
    }

    /// #4539's guard is a different question from #4626's and both must hold: the
    /// pair stays OUT of the initials fork. Unguarded, this name has three
    /// surviving distinctive tokens and badges `MVP`.
    func test_thePairStillDoesNotEnterTheInitialsFork() {
        XCTAssertNotEqual(TeamShortName.abbreviation("Milutinovic / Van de Peer"), "MVP")
        XCTAssertNotEqual(TeamShortName.abbreviation("Aboian / La Serna J"), "ALS")
    }

    // MARK: What is NOT a pair

    /// AN UNSPACED SLASH IS PART OF ONE ENTITY'S OWN NAME. The separator that
    /// means "and" is a SPACED slash and nothing else — the browser's rule,
    /// same spelling. Widening it to any slash would take a club's name apart.
    func test_anUnspacedSlashIsOneCompetitor() {
        XCTAssertFalse(TeamShortName.isDoublesPair("Bodo/Glimt"))
        XCTAssertFalse(TeamShortName.isDoublesPair("Scranton/Wilkes-Barre RailRiders"))
        XCTAssertFalse(TeamShortName.isDoublesPair("W-B/Scranton Penguins"))
        // And the values those names had before this fix are untouched.
        XCTAssertEqual(TeamShortName.short("Bodo/Glimt"), "Bodo/Glimt")
        XCTAssertEqual(TeamShortName.abbreviation("Bodo/Glimt"), "BOD")
        XCTAssertEqual(
            TeamShortName.short("Scranton/Wilkes-Barre RailRiders"), "RailRiders")
    }

    /// A single name is not a pair however many spaces it has, and the
    /// single-name rule is unchanged for all of them.
    func test_theSingleNameRuleIsUntouched() {
        XCTAssertEqual(TeamShortName.short("Cincinnati Reds"), "Reds")
        XCTAssertEqual(TeamShortName.short("Charlotte FC"), "Charlotte FC")
        XCTAssertEqual(TeamShortName.abbreviation("Paris Saint Germain"), "PSG")
        XCTAssertEqual(TeamShortName.short("Davis Love III"), "Davis Love III")
        XCTAssertEqual(TeamShortName.abbreviation("Davis Love III"), "DAV")
    }

    // MARK: Both competitors of one matchup

    /// Two pairs in one fixture: both labels whole, both badges naming their own
    /// first player, and no growth — `short` already separates them.
    func test_aDoublesFixtureNamesFourPlayersAcrossTwoLabels() {
        let labels = TeamShortName.shortPair(
            away: "Krajicek / Mektic", home: "Arribage / Guinard")
        XCTAssertEqual(labels.away, "Krajicek / Mektic")
        XCTAssertEqual(labels.home, "Arribage / Guinard")

        let badges = TeamShortName.abbreviationPair(
            away: "Krajicek / Mektic", home: "Arribage / Guinard")
        XCTAssertEqual(badges.away, "KRA")
        XCTAssertEqual(badges.home, "ARR")
    }

    /// A served provider abbreviation still wins, exactly as it always has —
    /// this fix moves what we DERIVE, never what a venue told us.
    func test_aServedAbbreviationStillWins() {
        let badges = TeamShortName.abbreviationPair(
            away: "Krajicek / Mektic", home: "Arribage / Guinard",
            awayServed: "KM", homeServed: "AG")
        XCTAssertEqual(badges.away, "KM")
        XCTAssertEqual(badges.home, "AG")
    }
}
