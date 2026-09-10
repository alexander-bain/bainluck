import XCTest
@testable import Bain_Luck

/// #4857 — THE PLAYER PROPS CARD RESHUFFLED ON EVERY LAUNCH.
///
/// `bainluck://events/15305028` (Seattle @ New England, 5 Kalshi fantasy-points
/// props), photographed three times in five minutes by native/098 — twice on the
/// SAME binary, `origin/master` 4f31a25a — came back in three different orders
/// with identical data and identical percentages:
///
///     11:03  … Drake Maye, NE Patriots D/ST, Andy Borregales
///     11:06  Andy Borregales, Hunter Henry, Jadarian Price, Drake Maye, NE Patriots D/ST
///     11:08  Drake Maye, Hunter Henry, NE Patriots D/ST, Andy Borregales, Jadarian Price
///
/// The old comparators sorted on a bare count at both levels. Every player on
/// that specimen had exactly one rung, so all five compared equal, `sorted` is
/// not guaranteed stable, and the per-process `Dictionary` iteration order the
/// cards were built from survived to the screen.
///
/// These tests are written against the KEY, not against a rendered list, because
/// the defect is a property of the comparator — it admits ties — and a property
/// is what has to be pinned. `testNoTwoDistinctCardsCanTie` is the one that
/// actually kills the bug class; the rest state the intended reading order.
final class PlayerPropsOrderTests: XCTestCase {

    private func card(_ rungs: Int, _ top: Double, _ name: String) -> PlayerPropsOrder.CardKey {
        PlayerPropsOrder.CardKey(rungs: rungs, topProbability: top, name: name)
    }

    // MARK: - The bug class

    /// 🔴 THE ONE THAT MATTERS. For every pair of DISTINCT cards, exactly one
    /// must precede the other. The old comparator failed this for any two
    /// players tied on rung count — which on a one-prop-each game is every pair
    /// on the card — and a comparator that reports "neither precedes" hands the
    /// order back to whatever the input order happened to be.
    func testNoTwoDistinctCardsCanTie() {
        let cards = [
            card(1, 0.89, "Jadarian Price"),
            card(1, 0.88, "Hunter Henry"),
            card(1, 0.75, "Drake Maye"),
            card(1, 0.08, "Andy Borregales"),
            card(1, 0.05, "NE Patriots D/ST"),
            // The hard case: same rung count AND the same probability. Only the
            // name can separate these, and it must.
            card(1, 0.50, "Aaron Aaronson"),
            card(1, 0.50, "Zeke Zimmerman"),
            card(3, 0.50, "Multi Rung"),
        ]
        for a in cards {
            for b in cards where a.name != b.name {
                let ab = PlayerPropsOrder.cardPrecedes(a, b)
                let ba = PlayerPropsOrder.cardPrecedes(b, a)
                XCTAssertNotEqual(
                    ab, ba,
                    "\(a.name) vs \(b.name): a comparator that says neither precedes lets the "
                    + "per-process dictionary order decide, which is #4857"
                )
            }
        }
    }

    /// A comparator is only a total order if it is also irreflexive — a card must
    /// not precede itself, or `sorted` is free to do anything at all.
    func testACardDoesNotPrecedeItself() {
        let c = card(2, 0.6, "Drake Maye")
        XCTAssertFalse(PlayerPropsOrder.cardPrecedes(c, c))
    }

    /// The end-to-end property, stated on the specimen's real numbers: the same
    /// five cards sort to the same list no matter what order they arrive in.
    /// Shuffling the INPUT is the direct stand-in for the dictionary reordering
    /// itself between launches.
    func testTheSpecimenSortsIdenticallyFromEveryInputOrder() {
        let specimen = [
            card(1, 0.89, "Jadarian Price"),
            card(1, 0.88, "Hunter Henry"),
            card(1, 0.75, "Drake Maye"),
            card(1, 0.08, "Andy Borregales"),
            card(1, 0.05, "NE Patriots D/ST"),
        ]
        let expected = ["Jadarian Price", "Hunter Henry", "Drake Maye",
                        "Andy Borregales", "NE Patriots D/ST"]

        for attempt in 0..<50 {
            let sorted = specimen.shuffled()
                .sorted(by: PlayerPropsOrder.cardPrecedes)
                .map(\.name)
            XCTAssertEqual(sorted, expected, "input shuffle \(attempt) produced a different list")
        }
    }

    // MARK: - The reading order the keys encode

    func testMostRungsComesFirst() {
        XCTAssertTrue(PlayerPropsOrder.cardPrecedes(
            card(3, 0.10, "Three Rungs"), card(1, 0.99, "One Rung")),
            "a fuller ladder outranks a likelier single prop")
    }

    func testAmongEqualLaddersTheLikeliestPropComesFirst() {
        XCTAssertTrue(PlayerPropsOrder.cardPrecedes(
            card(1, 0.89, "Jadarian Price"), card(1, 0.05, "NE Patriots D/ST")))
        XCTAssertFalse(PlayerPropsOrder.cardPrecedes(
            card(1, 0.05, "NE Patriots D/ST"), card(1, 0.89, "Jadarian Price")))
    }

    func testTheNameIsOnlyTheLastResort() {
        // Alphabetically first, but less likely — it must still come second, or
        // the card would open on the same surname every week.
        XCTAssertFalse(PlayerPropsOrder.cardPrecedes(
            card(1, 0.10, "Aaron Aaronson"), card(1, 0.90, "Zeke Zimmerman")))
        // Only with everything else equal does the name decide.
        XCTAssertTrue(PlayerPropsOrder.cardPrecedes(
            card(1, 0.50, "Aaron Aaronson"), card(1, 0.50, "Zeke Zimmerman")))
    }

    // MARK: - The second level, which the issue did not name

    /// The stat groups WITHIN one player card had the identical defect, from the
    /// identical shape — a `[String: [Rung]]` dictionary sorted on `rungs.count`
    /// alone. A player with "Hits" and "RBIs", one rung each, could swap them
    /// between launches.
    func testTwoEqualLengthStatGroupsCannotTie() {
        let hits = PlayerPropsOrder.StatGroupKey(rungs: 1, type: "Player Hits")
        let rbis = PlayerPropsOrder.StatGroupKey(rungs: 1, type: "Player RBIs")
        XCTAssertNotEqual(
            PlayerPropsOrder.statGroupPrecedes(hits, rbis),
            PlayerPropsOrder.statGroupPrecedes(rbis, hits)
        )
        XCTAssertTrue(PlayerPropsOrder.statGroupPrecedes(hits, rbis), "alphabetical is the tiebreak")
    }

    func testTheFullestLadderIsStillFirst() {
        XCTAssertTrue(PlayerPropsOrder.statGroupPrecedes(
            .init(rungs: 4, type: "Zzz Stat"), .init(rungs: 1, type: "Aaa Stat")),
            "the count still leads; the name only breaks ties")
    }

    func testAStatGroupDoesNotPrecedeItself() {
        let g = PlayerPropsOrder.StatGroupKey(rungs: 2, type: "Player Hits")
        XCTAssertFalse(PlayerPropsOrder.statGroupPrecedes(g, g))
    }
}
