import XCTest

@testable import Bain_Luck

/// #5271 — the event page printed `1 − P(home)` under the away crest, and on a
/// three-outcome market that figure is *away win **or** draw*.
///
/// Photographed on production 2026-09-11, event `15304603` (Al-Faisaly KSA FC v
/// Al-Ittihad, live 0–2), one source — `{"kalshi": {"value": 0.01}}`:
///
/// | where | Al-Ittihad | Tie | Al-Faisaly |
/// |---|---|---|---|
/// | hero | **99%** | — | 1% |
/// | Other Markets card, same page | **93%** | 5% | 1% |
///
/// and Alex found the same 99% a third time in the goal-margin map's header.
///
/// WHAT THESE TESTS PIN, and each one is a mutant:
///
/// 1. the sport gate itself — soccer withholds, and the sports either side of
///    it in `SportVocab.table` do not, so a row transposed into the wrong entry
///    is caught;
/// 2. `nil away` ≠ `nil pair` — the two states the callers draw differently,
///    and the reason this returns an optional inside an optional;
/// 3. that a two-way sport's behaviour is BYTE-IDENTICAL to before, including
///    the "no away price ⇒ print nothing" case that predates this issue;
/// 4. `headlineSide` naming home when home is the UNDERDOG, which is the
///    specimen and the one case a "name the favourite" rule gets wrong;
/// 5. `trendSubject` keeping the sign on a draw-priced sport — #1830's
///    riser-is-always-a-gain identity holds only while `away == 1 − home`.
///
/// WHAT THEY CANNOT PIN. A SwiftUI view BODY is invisible to XCTest, and every
/// one of the six call sites is an expression inside one. That the views
/// actually CALL this type — and that `1 - home` has not grown back beside a
/// team's name — is asserted by
/// `frontend/__tests__/ios/aDrawIsNotTheAwayTeam5271.test.ts`, which reads the
/// Swift as text and runs in CI, which compiles no Swift at all (#4302).
final class DrawPricedWinnerTests: XCTestCase {

    // MARK: - The sport gate

    /// Every soccer key shape the app actually serves. All 60 soccer keys in
    /// production carry the `soccer` prefix (measured 2026-09-11), and the
    /// extra tokens are the ones `SportVocab`'s soccer row already lists.
    func testSoccerPricesADraw() {
        for key in [
            "soccer", "soccer_epl", "soccer_usa_mls", "soccer_spain_la_liga",
            "soccer_uefa_champs_league", "soccer_brazil_campeonato",
            "SOCCER_EPL",
        ] {
            XCTAssertTrue(
                DrawPricedWinner.sportPricesADraw(key),
                "\(key) must be draw-priced")
        }
    }

    /// The declared two-way sports, including the two that sit either side of
    /// soccer in the table — a row pasted into the wrong entry fails here.
    func testTwoWaySportsDoNotPriceADraw() {
        for key in [
            "baseball_mlb", "icehockey_nhl", "tennis_wta_us_open",
            "basketball_nba", "americanfootball_nfl", "americanfootball_ncaaf",
            "mma_mixed_martial_arts", "cricket_test_match", "esports_lol",
            "", "boxing_heavyweight",
        ] {
            XCTAssertFalse(
                DrawPricedWinner.sportPricesADraw(key),
                "\(key) must not be draw-priced")
        }
        XCTAssertFalse(DrawPricedWinner.sportPricesADraw(nil))
    }

    /// An NFL tie is possible and the books price two outcomes. This is the
    /// case that makes "the sport can end level" the WRONG predicate, and it
    /// is why the field is declared rather than derived.
    func testATieBeingPossibleIsNotTheTest() {
        XCTAssertFalse(DrawPricedWinner.sportPricesADraw("americanfootball_nfl"))
        XCTAssertFalse(DrawPricedWinner.sportPricesADraw("icehockey_nhl"))
    }

    // MARK: - printablePair

    /// The specimen. The away slot is withheld; the home price survives intact.
    func testSpecimenWithholdsTheComplementAndKeepsHome() {
        let pair = DrawPricedWinner.printablePair(
            away: 0.99, home: 0.01, sport: "soccer_saudi_pro_league")
        XCTAssertNotNil(pair)
        XCTAssertNil(pair?.away, "1 - 0.01 = 0.99 is the away side PLUS the tie")
        XCTAssertEqual(pair?.home, 0.01)
    }

    /// A served away price is withheld too. The backend derives it as
    /// `round(1 - home, 6)`, so "the server said so" is not independent
    /// evidence — it is the same complement one hop earlier.
    func testAServedAwayPriceIsWithheldToo() {
        XCTAssertNil(
            DrawPricedWinner.printablePair(
                away: 0.85, home: 0.15, sport: "soccer_epl")?.away)
    }

    /// A withheld away side is NOT an absent pair. The callers draw the two
    /// states differently — one prints a named home number, the other prints
    /// nothing at all — so collapsing them is the mutant this kills.
    func testWithheldAwayIsNotAnAbsentPair() {
        let withheld = DrawPricedWinner.printablePair(
            away: 0.99, home: 0.01, sport: "soccer_epl")
        XCTAssertNotNil(withheld, "the pair exists; only its away side does not")
        XCTAssertNil(withheld?.away)

        XCTAssertNil(
            DrawPricedWinner.printablePair(away: 0.99, home: nil, sport: "soccer_epl"),
            "no home price is a genuinely absent pair")
    }

    /// A two-way sport is untouched, both sides, exactly as served.
    func testTwoWaySportKeepsBothSides() {
        let pair = DrawPricedWinner.printablePair(
            away: 0.32, home: 0.68, sport: "baseball_mlb")
        XCTAssertEqual(pair?.away, 0.32)
        XCTAssertEqual(pair?.home, 0.68)
    }

    /// And a two-way sport with no away price still prints nothing — today's
    /// behaviour, preserved. Widening the hero to draw on a home price alone
    /// would be a change this issue did not ask for.
    func testTwoWaySportWithNoAwayPriceStillHasNoPair() {
        XCTAssertNil(
            DrawPricedWinner.printablePair(away: nil, home: 0.68, sport: "baseball_mlb"))
    }

    // MARK: - headlineSide

    /// THE SPECIMEN AS ALEX FOUND IT. Home is the 1% underdog, so a
    /// name-the-favourite rule reaches for the 99% complement and prints the
    /// away abbreviation beside it. Home is named instead.
    func testHeadlineNamesHomeEvenWhenHomeIsTheUnderdog() {
        let side = DrawPricedWinner.headlineSide(
            away: 0.99, home: 0.01, sport: "soccer_saudi_pro_league")
        XCTAssertEqual(side?.isHome, true)
        XCTAssertEqual(side?.probability, 0.01)
    }

    /// A draw-priced favourite at home is named as well — same rule, and the
    /// answer happens to agree with the old one, which is why the underdog
    /// case above is the one that proves the change.
    func testHeadlineNamesADrawPricedHomeFavourite() {
        let side = DrawPricedWinner.headlineSide(
            away: 0.28, home: 0.72, sport: "soccer_epl")
        XCTAssertEqual(side?.isHome, true)
        XCTAssertEqual(side?.probability, 0.72)
    }

    /// A two-way sport keeps naming the favourite, on both sides of 0.5.
    func testTwoWayHeadlineStillNamesTheFavourite() {
        let awayFavoured = DrawPricedWinner.headlineSide(
            away: 0.74, home: 0.26, sport: "basketball_nba")
        XCTAssertEqual(awayFavoured?.isHome, false)
        XCTAssertEqual(awayFavoured?.probability, 0.74)

        let homeFavoured = DrawPricedWinner.headlineSide(
            away: 0.26, home: 0.74, sport: "basketball_nba")
        XCTAssertEqual(homeFavoured?.isHome, true)
        XCTAssertEqual(homeFavoured?.probability, 0.74)
    }

    /// No home price, no headline — on either kind of sport.
    func testHeadlineNeedsAHomePrice() {
        XCTAssertNil(
            DrawPricedWinner.headlineSide(away: 0.6, home: nil, sport: "soccer_epl"))
        XCTAssertNil(
            DrawPricedWinner.headlineSide(away: 0.6, home: nil, sport: "baseball_mlb"))
        XCTAssertNil(
            DrawPricedWinner.headlineSide(away: nil, home: 0.6, sport: "baseball_mlb"))
    }

    // MARK: - trendSubject

    /// #1830's rule, unchanged on a two-way sport: name the RISER and state a
    /// gain, whichever side rose.
    func testTwoWayTrendNamesTheRiserAsAGain() {
        let homeRose = DrawPricedWinner.trendSubject(
            homeDelta: 0.27, sport: "baseball_mlb")
        XCTAssertEqual(homeRose.isHome, true)
        XCTAssertEqual(homeRose.signedPoints, 27)

        let awayRose = DrawPricedWinner.trendSubject(
            homeDelta: -0.27, sport: "baseball_mlb")
        XCTAssertEqual(awayRose.isHome, false)
        XCTAssertEqual(
            awayRose.signedPoints, 27,
            "the caption reads '+27' for the side that GAINED it")
    }

    /// A draw-priced sport names home and keeps the sign, because the points
    /// home shed are not points the away side gained — the draw can take any
    /// part of them, and #1830's identity does not hold.
    func testDrawPricedTrendNamesHomeAndKeepsTheSign() {
        let fell = DrawPricedWinner.trendSubject(homeDelta: -0.06, sport: "soccer_epl")
        XCTAssertEqual(fell.isHome, true, "never name away off a home delta")
        XCTAssertEqual(fell.signedPoints, -6)

        let rose = DrawPricedWinner.trendSubject(homeDelta: 0.06, sport: "soccer_epl")
        XCTAssertEqual(rose.isHome, true)
        XCTAssertEqual(rose.signedPoints, 6)
    }

    /// The sign is the whole difference between the two rules, on identical
    /// input. A soccer row that quietly used the two-way branch would print
    /// "+6" for a home side that FELL six points.
    func testTheTwoRulesDisagreeOnTheSameFall() {
        let soccer = DrawPricedWinner.trendSubject(homeDelta: -0.06, sport: "soccer_epl")
        let baseball = DrawPricedWinner.trendSubject(homeDelta: -0.06, sport: "baseball_mlb")
        XCTAssertNotEqual(soccer.isHome, baseball.isHome)
        XCTAssertNotEqual(soccer.signedPoints, baseball.signedPoints)
    }
}
