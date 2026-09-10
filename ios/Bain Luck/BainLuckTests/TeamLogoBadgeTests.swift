import XCTest
@testable import Bain_Luck

/// #4720 — THE EVENT HERO DRAWS ONE LETTER FOR A DOUBLES PAIR.
///
/// Found by native/093 paying the LOOK on #4626. On `bainluck://events/15308212`
/// — Behar / Romboli vs Alcala Gurri / Sanchez Izquierdo — the crest circles read
/// **`B`** and **`A`**. Two pairs whose first players share an initial draw the
/// same circle twice, on a page whose only job is to tell them apart.
///
/// The cause was `String(teamName.prefix(1))` in `TeamLogoView`: one character of
/// the RAW name, never routed through `TeamShortName`. It was a FOURTH hand-rolled
/// spelling of the shorten-a-name rule on this target — the class #3374 removed,
/// that #3557 named again, and that `teamShortNameSingleSource.test.ts` exists to
/// discover. It went undiscovered because that scan looked for the LAST-WORD rule
/// and this is a first-character rule; the scan now carries both tells, and this
/// file is the behaviour half of the same fix.
///
/// MEASURED over the COMPLETE population of distinct (away, home) name pairs on
/// events in the last 45 days — 24,066 pairs / 14,025 distinct names, pulled in
/// hash chunks past the 1,000-row cap and reconciled against its own `COUNT(*)`
/// on 2026-09-10, then run through the real `TeamShortName.swift` rather than a
/// Python approximation of it:
///
///                                        today      solo      pair-aware
///     both circles draw the SAME glyph    2,238       120           67
///     pairs BROKEN (differed, now equal)      -        75           31
///     first glyph is not even a LETTER       42        28           28
///
/// Every expected value below was derived by hand from the rule's documented
/// behaviour before the code was run, not read back out of it.
final class TeamLogoBadgeTests: XCTestCase {

    // MARK: - The photographed specimen

    /// The circle Alex would see on the doubles hero. `B` names one of four
    /// players; `BEH` names the pair the way #3110 pinned it.
    func testTheDoublesHeroBadgesThePairAndNotOneLetter() {
        let away = TeamLogoView.badge(teamName: "Behar / Romboli", opponentName: "Alcala Gurri / Sanchez Izquierdo")
        let home = TeamLogoView.badge(teamName: "Alcala Gurri / Sanchez Izquierdo", opponentName: "Behar / Romboli")
        XCTAssertEqual(away, "BEH")
        XCTAssertEqual(home, "ALC")
        XCTAssertNotEqual(away, "B")
        XCTAssertNotEqual(home, "A")
    }

    /// The collision the single letter actually produces: two pairs whose first
    /// players share an initial. This is the defect in its purest form — before
    /// the fix BOTH circles read `A`.
    func testTwoPairsSharingAFirstInitialDrawDifferentCircles() {
        let a = "Abanda / Vickery"
        let b = "Aboian / La Serna J"
        XCTAssertEqual(String(a.prefix(1)).uppercased(), String(b.prefix(1)).uppercased(),
                       "premise: the shipped rule drew the same glyph for both")
        XCTAssertNotEqual(
            TeamLogoView.badge(teamName: a, opponentName: b),
            TeamLogoView.badge(teamName: b, opponentName: a)
        )
    }

    // MARK: - The name shapes one character cannot survive

    /// 716 names in the population open with a club-type designator, and the
    /// first character is that designator's initial rather than the club's.
    func testAClubNamedAfterItsDesignatorDoesNotBadgeTheDesignator() {
        XCTAssertEqual(TeamLogoView.badge(teamName: "FC Schalke 04", opponentName: nil), "SCH")
        XCTAssertEqual(TeamLogoView.badge(teamName: "AC Milan", opponentName: nil), "MIL")
        XCTAssertEqual(TeamLogoView.badge(teamName: "AD Ceuta FC", opponentName: nil), "CEU")
    }

    /// 42 names draw a first glyph that is not a letter at all.
    func testALeadingFoundingNumberIsNotABadge() {
        XCTAssertEqual(TeamLogoView.badge(teamName: "1. FC Heidenheim 1846", opponentName: nil), "HEI")
        XCTAssertEqual(TeamLogoView.badge(teamName: "1. FC Köln", opponentName: nil), "KÖL")
        XCTAssertEqual(TeamLogoView.badge(teamName: "07 Vestur Sorvagur", opponentName: nil), "SOR")
    }

    /// The rule it replaced, stated as a property over the shapes above rather
    /// than as three more literals: whatever the badge is, it is not one raw
    /// character off the front of the name.
    func testTheBadgeIsNeverJustTheFirstRawCharacter() {
        for name in ["1. FC Heidenheim 1846", "FC Schalke 04", "Behar / Romboli",
                     "AC Milan", "07 Vestur Sorvagur", "Boston Celtics"] {
            XCTAssertNotEqual(TeamLogoView.badge(teamName: name, opponentName: nil),
                              String(name.prefix(1)).uppercased(),
                              "\(name) still badges its first raw character")
        }
    }

    // MARK: - Why the opponent is an argument (#3430, reached through this view)

    /// THE REGRESSION THE SOLO RULE WOULD HAVE SHIPPED. Measured at 75 pairs:
    /// names that discriminate TODAY on their first letter and collapse onto one
    /// badge when each is judged alone. Clemson and LSU are #3430's own
    /// photographed matchup, one component over.
    func testADerbyDoesNotCollapseOntoTheWordBothClubsShare() {
        let away = "Clemson Tigers"
        let home = "LSU Tigers"
        // The premise: judged alone, both are TIG. If this stops being true the
        // test below is passing for a reason that has nothing to do with #4720.
        XCTAssertEqual(TeamShortName.abbreviation(away), TeamShortName.abbreviation(home),
                       "premise: the solo rule collides on this pair")
        XCTAssertNotEqual(
            TeamLogoView.badge(teamName: away, opponentName: home),
            TeamLogoView.badge(teamName: home, opponentName: away)
        )
    }

    /// The other side of that: growth must not be triggered for the 23,000-odd
    /// pairs that already read correctly, and the badge a side gets with an
    /// opponent in hand is the badge it gets alone whenever the two differ.
    func testAPairThatAlreadyDiscriminatesIsReturnedUnchanged() {
        for (a, h) in [("Boston Celtics", "Miami Heat"),
                       ("Paris Saint Germain", "Olympique Lyonnais"),
                       ("Behar / Romboli", "Alcala Gurri / Sanchez Izquierdo")] {
            XCTAssertEqual(TeamLogoView.badge(teamName: a, opponentName: h),
                           TeamShortName.abbreviation(a), "\(a) v \(h)")
            XCTAssertEqual(TeamLogoView.badge(teamName: h, opponentName: a),
                           TeamShortName.abbreviation(h), "\(a) v \(h)")
        }
    }

    /// The one-circle surfaces — a leaderboard row, a followed team, an
    /// onboarding chip — have no opponent to resolve against and must not be
    /// made to invent one.
    func testAbsentOrSelfOpponentFallsBackToTheSoloBadge() {
        XCTAssertEqual(TeamLogoView.badge(teamName: "FC Schalke 04", opponentName: nil),
                       TeamShortName.abbreviation("FC Schalke 04"))
        XCTAssertEqual(TeamLogoView.badge(teamName: "FC Schalke 04", opponentName: ""),
                       TeamShortName.abbreviation("FC Schalke 04"))
        // A row whose two sides carry the same stored name is one team playing
        // itself; growing it would return the whole name and overflow the circle.
        XCTAssertEqual(TeamLogoView.badge(teamName: "FC Schalke 04", opponentName: "FC Schalke 04"),
                       TeamShortName.abbreviation("FC Schalke 04"))
    }

    /// The existence rule and the collision rule are SEPARATE, and a fix that
    /// collapses them would still pass every assertion above. A name with no
    /// opponent must be badged; a name with one must be badged too.
    func testTheBadgeIsProducedOnBothArms() {
        XCTAssertFalse(TeamLogoView.badge(teamName: "Boston Celtics", opponentName: nil).isEmpty)
        XCTAssertFalse(TeamLogoView.badge(teamName: "Boston Celtics", opponentName: "Miami Heat").isEmpty)
    }

    // MARK: - It has to FIT

    /// The circle is `size` across and the text is framed at `size * 0.82`, which
    /// only holds if the badge stays at three glyphs. A four-glyph badge would
    /// shrink under `minimumScaleFactor` until it was unreadable at size 18.
    func testTheBadgeIsAtMostThreeGlyphsOnEveryArm() {
        let names = ["Behar / Romboli", "1. FC Heidenheim 1846", "FC Schalke 04",
                     "Paris Saint-Germain", "Clemson Tigers", "Chicago White Sox",
                     "Wolverhampton Wanderers", "Al Diraiyah Saudi Club"]
        for name in names {
            XCTAssertLessThanOrEqual(TeamLogoView.badge(teamName: name, opponentName: nil).count, 3, name)
        }
        // Including the grown arm, which is the one that can widen a label.
        for (a, h) in [("Clemson Tigers", "LSU Tigers"),
                       ("Chicago White Sox", "Boston Red Sox"),
                       ("FK Septemvri Sofia", "PFC Levski Sofia")] {
            XCTAssertLessThanOrEqual(TeamLogoView.badge(teamName: a, opponentName: h).count, 3, "\(a) v \(h)")
            XCTAssertLessThanOrEqual(TeamLogoView.badge(teamName: h, opponentName: a).count, 3, "\(a) v \(h)")
        }
    }

    /// An empty name is a real served value and must not crash or draw junk.
    func testAnEmptyNameDrawsNothingRatherThanCrashing() {
        XCTAssertEqual(TeamLogoView.badge(teamName: "", opponentName: nil), "")
        XCTAssertEqual(TeamLogoView.badge(teamName: "", opponentName: "Miami Heat"), "")
    }
}
