import XCTest
@testable import Bain_Luck

/// #5137 — a ladder whose every rung prints the same percentage is not a price
/// and must not be drawn as one. The second half is the one that matters: a rule
/// that calls too much unpriced hides real markets, so every specimen below that
/// is a genuine price is taken from the same production sample as the flat ones.
final class PlayerPropsPricingTests: XCTestCase {

    // MARK: - The photographed defect

    /// `bainluck://events/15308637`, Nick Martinez Earned Runs, hours after the
    /// final. Six rungs, six identical bars, six 50%s. The stored 0.5 is not the
    /// midpoint of any of the six rungs' bid/ask — it is the no-book placeholder.
    func testTheSixFiftiesAreNotAPrice() {
        XCTAssertFalse(
            PlayerPropsPricing.isPricedLadder([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
        )
    }

    /// Same event, Ronald Acuña Jr. Total Bases. The defect is not the 50%: a
    /// flat ladder at any value is the same impossible claim, and a rule keyed on
    /// 0.5 would have caught one of the two flat ladders on that page.
    func testAFlatLadderAwayFromFiftyIsAlsoNotAPrice() {
        XCTAssertFalse(PlayerPropsPricing.isPricedLadder([0.05, 0.05, 0.05, 0.05]))
    }

    /// Kevin Gausman Earned Runs, `15308051`. All six rungs carry bid 0.60 / ask
    /// 1.00 — one stale wide quote replicated across the ladder. The midpoint is
    /// arithmetically real and the ladder is still not a price, which is why the
    /// rule reads the shape and never the value.
    func testAReplicatedWideMidpointIsNotAPrice() {
        XCTAssertFalse(PlayerPropsPricing.isPricedLadder([0.8, 0.8, 0.8, 0.8, 0.8, 0.8]))
    }

    /// 80 of the 116 flat ladders measured have exactly two rungs. P(≥2) = P(≥1)
    /// says the stat can never land on exactly 1, so the pair is as impossible as
    /// the six.
    func testTwoEqualRungsAreEnough() {
        XCTAssertFalse(PlayerPropsPricing.isPricedLadder([0.12, 0.12]))
    }

    // MARK: - What must keep its bars

    /// Martinez's *other* Earned Runs ladder on the same event, priced normally.
    /// Filed beside the flat one in #5137 precisely because it proves the player
    /// is not the thing going wrong.
    func testADecliningLadderIsAPrice() {
        XCTAssertTrue(PlayerPropsPricing.isPricedLadder([0.41, 0.32]))
    }

    /// A weak price is a price. 5%, 5%, 4% declines, the reader can see it
    /// decline, and nothing about it is impossible.
    func testANearFlatLadderIsAPrice() {
        XCTAssertTrue(PlayerPropsPricing.isPricedLadder([0.05, 0.05, 0.04]))
    }

    /// One rung makes no claim about a shape. A lone 50% may well be the same
    /// placeholder, but nothing on the row distinguishes it from a genuine coin
    /// flip — so the ladder rule stays silent rather than hiding a real price.
    func testASingleRungIsNeverJudged() {
        XCTAssertTrue(PlayerPropsPricing.isPricedLadder([0.5]))
        XCTAssertTrue(PlayerPropsPricing.isPricedLadder([]))
    }

    /// The flat run must be the WHOLE ladder. A ladder that plateaus and then
    /// falls is a real market with a dead zone in it, and hiding it would throw
    /// away the rungs that do move.
    func testAPartiallyFlatLadderKeepsItsBars() {
        XCTAssertTrue(PlayerPropsPricing.isPricedLadder([0.5, 0.5, 0.5, 0.31]))
        XCTAssertTrue(PlayerPropsPricing.isPricedLadder([0.9, 0.5, 0.5, 0.5]))
    }

    // MARK: - The rule reads what the reader reads

    /// The test is on the printed percentage, not the raw double, because the
    /// printed percentage is the claim being handed over: 0.05004 and 0.04999
    /// both print "5%" and draw bars 0.005pt apart on a 300pt card.
    func testEqualityIsJudgedOnThePrintedPercentage() {
        XCTAssertFalse(PlayerPropsPricing.isPricedLadder([0.05004, 0.04999]))
    }

    /// …and the converse: values that round apart are a price even when they are
    /// close, so the rule cannot swallow a market whose rungs differ by a cent.
    /// (0.045 is deliberately not the second value here: it rounds to 5% too, so
    /// it would have proved the opposite of what the name claims.)
    func testValuesThatRoundApartArePriced() {
        XCTAssertTrue(PlayerPropsPricing.isPricedLadder([0.054, 0.044]))
    }

    /// The rounding the rule reads is the rounding the rung prints — the card
    /// draws its label through this same function, so "judged flat" and "prints
    /// one repeated number" cannot drift apart.
    func testDisplayPercentRoundsHalfAway() {
        XCTAssertEqual(PlayerPropsPricing.displayPercent(0.095), 10)
        XCTAssertEqual(PlayerPropsPricing.displayPercent(0.094), 9)
        XCTAssertEqual(PlayerPropsPricing.displayPercent(0.5), 50)
        XCTAssertEqual(PlayerPropsPricing.displayPercent(0.0), 0)
        XCTAssertEqual(PlayerPropsPricing.displayPercent(1.0), 100)
    }
}
