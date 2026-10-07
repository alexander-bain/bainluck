import XCTest
@testable import Bain_Luck

/// #10714 — the iPhone twin of #10690: a photo-less competitor's letter tile must
/// never read like a result.
///
/// The browser photographed it at /events/15326071 (Halys v Wong): Chak Lam
/// Coleman Wong has no headshot, so the hero lettered him **`WON`** beside a 17%
/// chance mid-match, and after the final beside Halys's real WON chip. The phone
/// letters a person by the surname's first three glyphs, so it paints the same
/// tile; the Discover card paints "Learner Tien" `TIE` and "Dallas Wings" `WIN`.
///
/// Every expectation below was derived by hand from the web fix
/// (`shippableCrestBadge` in `frontend/lib/teamShortName.ts`, PR #10701), so the
/// two clients draw the same re-lettered tile.
final class CrestTileNeverSpellsAResult10714Tests: XCTestCase {
    private let tennis = "tennis_atp_shanghai"

    // MARK: - The specimen and its class, on the event hero circle

    func testTheHeroCircleNoLongerLettersWongAsWON() {
        XCTAssertEqual(
            TeamLogoView.badge(teamName: "Chak Lam Coleman Wong", opponentName: "Quentin Halys", sportKey: tennis),
            "CW"
        )
        XCTAssertEqual(
            TeamLogoView.badge(teamName: "Chak Lam Coleman Wong", opponentName: nil, sportKey: tennis),
            "CW"
        )
    }

    /// The STRAWMAN: the unrefused rule really does spell the word for this
    /// input, so the assertion above is testing the refusal and not a name that
    /// was never at risk. `abbreviation` is deliberately unchanged — it mirrors
    /// the browser's `teamCrestBadge`, which #10690 also left alone.
    func testTheUnderlyingBadgeStillSpellsTheWordSoTheRefusalIsWhatMoved() {
        XCTAssertEqual(TeamShortName.abbreviation("Chak Lam Coleman Wong", sportKey: tennis), "WON")
        XCTAssertEqual(TeamShortName.abbreviation("Learner Tien", sportKey: tennis), "TIE")
        XCTAssertEqual(TeamShortName.abbreviation("Dallas Wings"), "WIN")
        XCTAssertEqual(TeamShortName.abbreviation("Denver Outlaws"), "OUT")
    }

    func testAPersonTakesFirstAndLastInitial() {
        XCTAssertEqual(TeamLogoView.badge(teamName: "Learner Tien", opponentName: nil, sportKey: tennis), "LT")
    }

    func testAOneWordPersonFallsBackToTheFirstInitial() {
        XCTAssertEqual(TeamShortName.refusingResultWord("WON", name: "Wong", sportKey: tennis), "W")
    }

    func testAClubTakesItsInitials() {
        XCTAssertEqual(TeamLogoView.badge(teamName: "Dallas Wings", opponentName: "Las Vegas Aces"), "DW")
        XCTAssertEqual(TeamLogoView.badge(teamName: "Denver Outlaws", opponentName: nil), "DO")
        // Letter-only tokens: the browser's `alphanumeric`, so "&" never reaches
        // the tile ("Wingate & Finchley FC" `WFF`, not `W&F`).
        XCTAssertEqual(TeamShortName.refusingResultWord("WIN", name: "Wingate & Finchley FC"), "WFF")
    }

    // MARK: - The Discover card tiles

    func testTheDiscoverCardReLettersBothSidesAndLeavesTheRestAlone() {
        let card = DiscoverEventCard.cardBadges(away: "Learner Tien", home: "Carlos Alcaraz", sportKey: tennis)
        XCTAssertEqual(card.away, "LT")
        XCTAssertEqual(card.home, TeamShortName.abbreviationPair(away: "Learner Tien", home: "Carlos Alcaraz").home)

        let wnba = DiscoverEventCard.cardBadges(away: "Las Vegas Aces", home: "Dallas Wings", sportKey: "basketball_wnba")
        XCTAssertEqual(wnba.home, "DW")
        XCTAssertEqual(wnba.away, TeamShortName.abbreviationPair(away: "Las Vegas Aces", home: "Dallas Wings").away)
    }

    // MARK: - Controls: nothing else moves

    func testABadgeThatIsNotAResultWordPassesThroughUnchanged() {
        XCTAssertEqual(TeamShortName.refusingResultWord("ALC", name: "Eloy Mendez Alcantara", sportKey: tennis), "ALC")
        XCTAssertEqual(TeamShortName.refusingResultWord("CEL", name: "Boston Celtics"), "CEL")
        XCTAssertEqual(
            TeamLogoView.badge(teamName: "Eloy Mendez Alcantara", opponentName: nil, sportKey: tennis),
            TeamShortName.abbreviation("Eloy Mendez Alcantara", sportKey: tennis)
        )
        // Words a casual fan does not read as an outcome stay off the list, as on
        // the browser: `DEF` (Defensor Sporting), `RET` (Retford FC).
        XCTAssertEqual(TeamShortName.refusingResultWord("DEF", name: "Defensor Sporting"), "DEF")
        XCTAssertEqual(TeamShortName.refusingResultWord("RET", name: "Retford FC"), "RET")
    }

    func testTheReLetteredTileIsNeverItselfAResultOrUnshippableWord() {
        // "Wilson Inter Nacional" initials `WIN` would trade one result word for
        // another; the first-initial fallback is refused the same way, so the
        // tile is empty rather than wrong.
        let relettered = TeamShortName.refusingResultWord("WIN", name: "Wilson Inter Nacional")
        XCTAssertFalse(["WON", "WIN", "TIE", "OUT"].contains(relettered))
        XCTAssertEqual(relettered, "")
    }
}
