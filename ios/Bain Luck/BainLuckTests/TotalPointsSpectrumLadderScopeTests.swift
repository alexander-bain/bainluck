import XCTest
@testable import Bain_Luck

/// #3925 item 2 — the combined-scoring ladder stops pooling two different
/// quantities onto one ascending axis.
///
/// **THE PHOTOGRAPHED CARD** (event 15305795, `Darderi 0 — Zverev 3`,
/// `completed`; frames `artifacts-native-062/MASTER-3925-tennis-15305795-s900-c0f46f3b.png`
/// and the #3930 ship frame at `540bf682`, which shows the same five rungs):
///
/// ```
/// Settled combined scoring
///    3.5+   LAST QUOTE   0%     <- Total Sets O/U 3.5      SETS, whole match
///    4.5+   LAST QUOTE   0%     <- Total Sets O/U 4.5      SETS, whole match
///    8.5+   LAST QUOTE   0%     <- Set 1 Games O/U 8.5     GAMES, inside ONE set
///    9.5+   LAST QUOTE   0%     <- Set 1 Games O/U 9.5     GAMES, inside ONE set
///   10.5+   LAST QUOTE   0%     <- Set 1 Games O/U 10.5    GAMES, inside ONE set
/// ```
///
/// `4.5+` and `8.5+` are adjacent rungs on one ladder while one counts sets in
/// a match and the other counts games in a single set. Both families were read
/// off `GET /api/events/15305795/game-markets` on 2026-09-08; all five carry
/// `market_type: "game_total"`, which is why the view's filter pooled them.
///
/// 🔴 **`period` IS NOT THE DISCRIMINATOR — IT IS `null` ON ALL FIVE ROWS.**
/// Measured, not assumed, on the same payload. The rows' own `market_name` is
/// the only signal the client has, which is what makes the name test the fix.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the pure
/// rule it defers to, plus the ``SportVocab`` reading that proves the repair
/// reaches the card's heading.
final class TotalPointsSpectrumLadderScopeTests: XCTestCase {

    /// The five rungs the card served, in payload order.
    private let photographed: [String] = [
        "Alexander Zverev vs. Luciano Darderi: Total Sets O/U 3.5",
        "Alexander Zverev vs. Luciano Darderi: Total Sets O/U 4.5",
        "Zverev vs. Darderi: Set 1 Games O/U 8.5",
        "Zverev vs. Darderi: Set 1 Games O/U 9.5",
        "Zverev vs. Darderi: Set 1 Games O/U 10.5",
    ]

    // MARK: - The photographed defect

    func testThePhotographedCardDrawsOnlyTheWholeMatchFamily() {
        XCTAssertEqual(
            MarketMapRail.matchScopeLadderIndices(marketNames: photographed),
            [0, 1],
            "the two whole-match sets rungs draw; the three Set-1 games rungs do not"
        )
    }

    /// The heading repair, and the reason it comes free rather than as a second
    /// edit: `totalsUnit` returns `""` — which the view prints as the word
    /// "scoring" — exactly BECAUSE the names disagreed. One family in, and the
    /// card names the noun the market itself quotes.
    func testTheSurvivingFamilyLetsTheCardNameItsOwnUnit() {
        let tennis = SportVocab.forSport("tennis_atp_us_open")
        XCTAssertEqual(tennis.totalsUnit(quotedBy: photographed), "",
                       "the pooled five declare two units, so the card fell back to 'scoring'")

        let drawn = MarketMapRail.matchScopeLadderIndices(marketNames: photographed)
            .map { photographed[$0] }
        XCTAssertEqual(tennis.totalsUnit(quotedBy: drawn), "sets",
                       "the family that survives says what it counts")
    }

    // MARK: - The boundary the whole rule balances on

    /// `Total Sets` and `Set 1` differ by one character of lookahead. "set"
    /// does match inside "sets"; what follows it is `s`, not a digit.
    func testTheSetsUnitFamilyIsNotMistakenForASetScopedOne() {
        XCTAssertFalse(MarketMapRail.namesASubContestScope(
            "Alexander Zverev vs. Luciano Darderi: Total Sets O/U 3.5"))
        XCTAssertFalse(MarketMapRail.namesASubContestScope("Set Betting: 3-0"),
                       "a scope needs an ordinal, not just the word 'set'")
        XCTAssertTrue(MarketMapRail.namesASubContestScope(
            "Zverev vs. Darderi: Set 1 Games O/U 8.5"))
        XCTAssertTrue(MarketMapRail.namesASubContestScope("Set 2 Games O/U 9.5"))
    }

    // MARK: - Fail-open

    /// 🔴 The 4,451-event case. Measured on production 2026-09-08 over 21,928
    /// tennis events: 3,941 carry both families (repaired above) and **4,451
    /// carry a set-scoped family and nothing else**. Dropping unconditionally
    /// would leave `thresholds` empty, which the view renders as `EmptyView()`
    /// — deleting the card from more pages than the fix repairs.
    func testACardWhoseOnlyRungsAreSetScopedKeepsEveryOne() {
        let onlySetScoped = [
            "Zverev vs. Darderi: Set 1 Games O/U 8.5",
            "Zverev vs. Darderi: Set 1 Games O/U 9.5",
            "Zverev vs. Darderi: Set 1 Games O/U 10.5",
        ]
        XCTAssertEqual(
            MarketMapRail.matchScopeLadderIndices(marketNames: onlySetScoped),
            [0, 1, 2],
            "a card with nothing else to draw keeps what it renders today"
        )
    }

    func testAnEmptyLadderStaysEmpty() {
        XCTAssertEqual(MarketMapRail.matchScopeLadderIndices(marketNames: []), [])
    }

    // MARK: - The quiet majority must not move

    /// Every honest card in the app goes through this function. A payload that
    /// names no sub-contest keeps every rung, in order.
    func testAPayloadWithNoSubContestRungsIsUntouched() {
        let matchTotals = [
            "Shelton vs. Hurkacz: Match O/U 36.5",
            "Shelton vs. Hurkacz: Match O/U 40.5",
            "Cardinals vs. Reds: O/U 10.5",
            nil,
        ]
        XCTAssertEqual(
            MarketMapRail.matchScopeLadderIndices(marketNames: matchTotals),
            [0, 1, 2, 3],
            "a nameless rung is not a sub-contest either"
        )
        XCTAssertFalse(MarketMapRail.namesASubContestScope(nil))
        XCTAssertFalse(MarketMapRail.namesASubContestScope(""))
    }

    // MARK: - The other scopes, each measured reachable before it was written

    /// Counts over linked `futures_markets` names carrying `O/U` or `total`,
    /// production 2026-09-08 — the evidence that each pattern earns its line.
    func testTheOtherMeasuredSubContestScopesAreRead() {
        // 1st/2nd half — 36,348 rows, the largest family of all.
        XCTAssertTrue(MarketMapRail.namesASubContestScope("Chelsea vs. Arsenal: 1st Half Total Goals O/U 1.5"))
        XCTAssertTrue(MarketMapRail.namesASubContestScope("2nd Half Total Points O/U 108.5"))
        // map N — 653 rows, #3161's esports arm.
        XCTAssertTrue(MarketMapRail.namesASubContestScope("Map 1 Total Rounds: Over/Under 21.5"))
        // first 5 — 2,053 rows.
        XCTAssertTrue(MarketMapRail.namesASubContestScope("Yankees at Red Sox: First 5 Innings O/U 4.5"))
        // Nth quarter / period — 133 rows.
        XCTAssertTrue(MarketMapRail.namesASubContestScope("1st Quarter Total Points O/U 55.5"))
        XCTAssertTrue(MarketMapRail.namesASubContestScope("3rd Period Total Goals O/U 2.5"))
    }

    /// 🟠 **A DELIBERATE OMISSION, RECORDED SO IT CAN BE REVERSED WITH
    /// EVIDENCE.** `q1`–`q4` and `inning N` were measured on the same pass and
    /// returned **0 rows each**, so they are not implemented: an unreachable
    /// pattern is a claim nothing supports, and the next reader would trust it.
    /// If a venue starts writing them, this test is the place to flip — with a
    /// fresh count in the same breath, never on the strength of the shape alone.
    func testTheScopesThatMeasuredZeroAreDeliberatelyNotRead() {
        XCTAssertFalse(MarketMapRail.namesASubContestScope("Q1 Total Points O/U 55.5"),
                       "measured 0 rows on 2026-09-08 — see the doc comment before changing this")
        XCTAssertFalse(MarketMapRail.namesASubContestScope("Inning 3 Total Runs O/U 1.5"),
                       "measured 0 rows on 2026-09-08")
    }
}
