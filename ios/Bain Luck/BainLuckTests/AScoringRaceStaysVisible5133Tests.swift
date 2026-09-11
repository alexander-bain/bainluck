import XCTest

@testable import Bain_Luck

/// #5133 defect A, the native client half — CERT-2611's required repair
/// `5133-TWO-SIDED-SCORING-RACE-REMAINS-VISIBLE`.
///
/// The backend fix stops Kalshi's scoring races being served as PLAYER props
/// and lands them in `other[]` instead. On its own that makes one of the six
/// races vanish rather than move, because `isWinProbabilityMarket` treats any
/// market whose two rows sum to ~1.0 as the hero market and filters the whole
/// family out of Special Event Markets.
///
/// A scoring race is that shape and is not the hero. The hero answers *who
/// wins*; the race answers *who gets there first*; a game can be won by the
/// side that lost the race. From inside the heuristic the two are identical, so
/// the race has to be named.
///
/// MEASURED, not hypothesised — `GET /api/events/14780145/game-markets`
/// (New Orleans @ Detroit), read 2026-09-11:
///
/// | market | rows served | fate under the old rule |
/// |---|---|---|
/// | Race to 10 / 14 / 21 / 28 / 35 Points | THREE | survives, by accident |
/// | Race to 7 Points | **TWO**, 0.56 / 0.44 | **suppressed** |
///
/// The seven-point race is short a row for a reason that has nothing to do with
/// it being a hero: its third outcome, "Neither team reaches 7 points", is
/// priced 0.010 and dropped upstream. One race in six disappearing while its
/// five siblings render is not a rule a reader can learn.
///
/// The fixtures below are those exact wire rows. The web twin of this file is
/// `frontend/__tests__/lib/aTwoSidedScoringRaceRemainsVisible5133.test.ts`, and
/// the wiring of the filter into the view's `categories` — which no Swift test
/// can reach — is pinned by `frontend/__tests__/ios/aScoringRaceStaysVisible5133.test.ts`.
final class AScoringRaceStaysVisible5133Tests: XCTestCase {

    private static let race7 = "New Orleans vs Detroit: Race to 7 Points"
    private static let race14 = "New Orleans vs Detroit: Race to 14 Points"
    private static let winner = "New Orleans vs Detroit Winner"

    private func row(_ market: String, _ outcome: String, _ p: Double?) -> GameMarketOther {
        GameMarketOther(marketName: market, outcomeName: outcome, probability: p, source: "kalshi")
    }

    /// The two-row family, verbatim from the wire.
    private var raceTo7: [GameMarketOther] {
        [
            row(Self.race7, "Detroit reaches 7 points first", 0.56),
            row(Self.race7, "New Orleans reaches 7 points first", 0.44),
        ]
    }

    /// A three-row sibling, never at risk — the control.
    private var raceTo14: [GameMarketOther] {
        [
            row(Self.race14, "Detroit reaches 14 points first", 0.56),
            row(Self.race14, "New Orleans reaches 14 points first", 0.43),
            row(Self.race14, "Neither team reaches 14 points", 0.125),
        ]
    }

    /// An ordinary two-sided winner — the same shape, a different question, and
    /// the one the hero above the section already answers.
    private var matchWinner: [GameMarketOther] {
        [
            row(Self.winner, "Detroit", 0.58),
            row(Self.winner, "New Orleans", 0.42),
        ]
    }

    // MARK: - The race survives

    func testTheTwoSidedRaceIsNotTakenForTheHeroMarket() {
        let suppressed = SpecialEventMarketsView.isWinProbabilityMarket(raceTo7)

        XCTAssertFalse(
            suppressed.contains(Self.race7),
            "a 0.56/0.44 scoring race is not the moneyline")
        XCTAssertTrue(suppressed.isEmpty)
    }

    func testTheThreeRowSiblingIsUntouched() {
        XCTAssertFalse(
            SpecialEventMarketsView.isWinProbabilityMarket(raceTo14).contains(Self.race14))
    }

    // MARK: - …and the rule it rides on is still doing its job

    /// THE OTHER HALF OF THE REPAIR. Widening until the race survives is easy;
    /// the fix has to stay narrow enough that the hero's own question does not
    /// reappear as a second, worse moneyline further down the page.
    func testAnOrdinaryTwoSidedWinnerIsStillSuppressed() {
        XCTAssertTrue(
            SpecialEventMarketsView.isWinProbabilityMarket(matchWinner).contains(Self.winner))
    }

    /// Both at once, in ONE call — an absence is only evidence beside a
    /// presence the same call produced.
    func testOneCallKeepsTheRaceAndDropsTheWinner() {
        let suppressed = SpecialEventMarketsView.isWinProbabilityMarket(
            raceTo7 + raceTo14 + matchWinner)

        XCTAssertEqual(
            suppressed, [Self.winner],
            "exactly the winner, and nothing else, is treated as the hero market")
    }

    /// A two-sided market whose NAME trips none of the redundancy keywords.
    ///
    /// It matters because `categories` applies TWO filters, and the web twin of
    /// this repair was briefly guarded by a fixture the FIRST one declined:
    /// "…Winner" is caught by `isRedundantWithMarketMaps` before hero
    /// suppression is ever consulted, so a mutant that disabled hero
    /// suppression entirely survived that test. These tests call
    /// `isWinProbabilityMarket` directly and so cannot have that hole — this
    /// case is here so the fixture set says out loud which rule catches what.
    func testAHeroShapedPairWithANeutralNameIsStillSuppressed() {
        let name = "Detroit to Lead at Halftime"
        let heroShaped = [row(name, "Yes", 0.58), row(name, "No", 0.42)]

        XCTAssertFalse(
            SpecialEventMarketsView.isRedundantWithMarketMaps(heroShaped[0]),
            "this fixture reaches the guarded rule instead of being declined earlier")
        XCTAssertTrue(SpecialEventMarketsView.isWinProbabilityMarket(heroShaped).contains(name))
    }

    // MARK: - The predicate is narrower than its own words

    func testItRequiresTheScoreUnit() {
        for name in [
            "New Orleans vs Detroit: Race to 7 Points",
            "New Orleans vs Detroit: Race to 14 Points",
            "race to 21 points",
            "RACE TO 35 POINTS",
            "Race to 10.5 Points",
            "Race to 1 Point",
        ] {
            XCTAssertTrue(
                SpecialEventMarketsView.isScoringRaceMarket(name), "\(name) is a scoring race")
        }
    }

    /// A player race ("Race to 5 catches") is a shape nobody has measured, and
    /// a rule measured only on team scoring races has no business claiming it
    /// by grammar. Pinned in both directions so a later widening is deliberate.
    func testItDoesNotSweepUpEverythingNamedRace() {
        for name in [
            "Race to 5 catches",
            "Race to the Playoffs",
            "Points Race",
            "Race to 7",
            "Embrace to 7 Points",
            "New Orleans vs Detroit Winner",
            "",
        ] {
            XCTAssertFalse(
                SpecialEventMarketsView.isScoringRaceMarket(name), "\(name) is not a scoring race")
        }
    }

    /// The Swift pattern and the web's `isScoringRaceMarket` must agree — the
    /// third copy is the server's `_SCORING_RACE_RE`. Stated as a test rather
    /// than a comment because three copies of one rule is exactly the shape
    /// that drifts.
    func testThePatternMatchesTheOneTheServerUses() {
        // `\brace to\s+\d+(?:\.\d+)?\s+points?\b`, applied to the boundary
        // cases that distinguish it from every looser spelling.
        XCTAssertTrue(SpecialEventMarketsView.isScoringRaceMarket("x Race to 7 Points y"))
        XCTAssertFalse(
            SpecialEventMarketsView.isScoringRaceMarket("Race to 7 Pointsy"),
            "the trailing word boundary is load-bearing")
        XCTAssertFalse(
            SpecialEventMarketsView.isScoringRaceMarket("Racetoto 7 Points"),
            "the leading word boundary is load-bearing")
    }
}
