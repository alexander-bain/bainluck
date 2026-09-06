import XCTest
@testable import Bain_Luck

/// native/042 — #3642: a margin map's axis stops overstating one side's scale.
///
/// THE PHOTOGRAPH. Event 14780138 (New England Patriots at Seattle Seahawks,
/// `americanfootball_nfl`, status `scheduled`), iPad Pro 11-inch simulator
/// against production, 2026-09-06 — `artifacts-native-042/ipad-nfl-14780138-top.png`.
/// The full-game margin card's axis read
///
///     NE by 23.5+          Tie          SEA by 23.5+
///
/// which states a rail symmetric about zero. The word "Tie" was drawn at 43% of
/// the rail's width, because `midAxisLabel` puts it where zero actually falls —
/// so the card contradicted itself in one row.
///
/// THE MECHANISM, from the event's own `/api/events/14780138/game-markets`: 31
/// spread rows, Seattle quoted out to a `20.5` threshold and New England only to
/// `15.0`. Football declares `marginRange: 18` and the maps pad by 3, so
/// `marginBounds` returned
///
///     min = min(-15.0 - 3, -18) = -18.0
///     max = max( 20.5 + 3,  18) =  23.5
///
/// Both call sites then derived a single `axisEnd = formatThreshold(rangeMax)`
/// and printed it on BOTH ends. The right label was right. The left one named a
/// bound 5.5 points beyond the end of New England's half of the rail.
///
/// The arithmetic is confirmed against the pixels: zero at `18 / 41.5 = 43.4%`
/// and the PROJECTION marker (`SEA +1.0`) at `19 / 41.5 = 45.8%`, i.e. 395.7 px
/// along a rail measured at x 61–792 in that PNG, against a marker ring
/// measured at 395.5 px.
///
/// WHY #3566 DID NOT CATCH IT. #3566 rewrote this exact axis row, and
/// `MarketMapRail.midAxisLabel`'s doc comment records the asymmetric rail in so
/// many words — *"full game, margins `[-15.0, 20.5]` → rail `[-18.0, 23.5]` →
/// zero at 43.4%"*. The measurement existed. It was simply never turned on the
/// end labels, because the subject that day was where the MIDDLE label goes,
/// and the specimen the end labels WERE measured on
/// (`artifacts-native-038/nfl-14632820-s900.png`, `SF by 18+ … LAR by 18+`) is
/// a `[-18, 18]` rail, where one shared label and two correct ones render
/// identically.
///
/// A symmetric specimen cannot see an asymmetry bug. Hence the fixtures below
/// are asymmetric on purpose, in BOTH directions, and the symmetric case is
/// pinned separately so the old behaviour is proved unmoved rather than assumed.
final class MarginAxisEndsTests: XCTestCase {

    // MARK: - The photographed case

    /// The exact bounds `marginBounds` returns for event 14780138, from the
    /// thresholds its payload actually carried.
    private var patriotsAtSeahawks: MarketMapRail.Bounds {
        MarketMapRail.marginBounds(
            margins: [-15.0, 20.5],   // NE's deepest rung, SEA's deepest rung
            declared: 18,             // SportVocab football
            pad: 3
        )
    }

    func testPhotographedNFLRailIsAsymmetric() {
        let bounds = patriotsAtSeahawks
        XCTAssertEqual(bounds.min, -18.0, accuracy: 0.0001)
        XCTAssertEqual(bounds.max, 23.5, accuracy: 0.0001)
        XCTAssertNotEqual(
            abs(bounds.min), bounds.max,
            "The premise of this bug: the declared branch of marginBounds is asymmetric here."
        )
    }

    func testEachEndNamesItsOwnBound() {
        let ends = MarketMapRail.marginAxisEnds(patriotsAtSeahawks)
        XCTAssertEqual(ends.left, 18.0, accuracy: 0.0001, "the away end names the rail's own left bound")
        XCTAssertEqual(ends.right, 23.5, accuracy: 0.0001, "the home end names the rail's own right bound")
    }

    /// The photographed string, and the one that replaces it.
    func testTheLeftLabelNoLongerNamesTheRightBound() {
        let ends = MarketMapRail.marginAxisEnds(patriotsAtSeahawks)
        XCTAssertNotEqual(
            ends.left, 23.5,
            "`NE by 23.5+` is the defect exactly: 23.5 is Seattle's end of this rail, not New England's."
        )
    }

    // MARK: - The other direction

    /// The mirror image — the AWAY side quoted deeper than the home side. A fix
    /// that hard-coded `18` for the left end, or that swapped the two labels,
    /// passes every assertion above and fails here.
    func testAsymmetryTheOtherWayRound() {
        let bounds = MarketMapRail.marginBounds(margins: [-20.5, 15.0], declared: 18, pad: 3)
        XCTAssertEqual(bounds.min, -23.5, accuracy: 0.0001)
        XCTAssertEqual(bounds.max, 18.0, accuracy: 0.0001)

        let ends = MarketMapRail.marginAxisEnds(bounds)
        XCTAssertEqual(ends.left, 23.5, accuracy: 0.0001)
        XCTAssertEqual(ends.right, 18.0, accuracy: 0.0001)
    }

    // MARK: - The cases that must not move

    /// #3566's own specimen. Both ends said 18 before this change and must say
    /// 18 after it, or the measurement behind `endLabelBandPercent` is invalid.
    func testSymmetricRailIsUnchanged() {
        let bounds = MarketMapRail.marginBounds(margins: [-14.5, 14.5], declared: 18, pad: 3)
        let ends = MarketMapRail.marginAxisEnds(bounds)
        XCTAssertEqual(ends.left, 18.0, accuracy: 0.0001)
        XCTAssertEqual(ends.right, 18.0, accuracy: 0.0001)
        XCTAssertEqual(ends.left, ends.right, accuracy: 0.0001)
    }

    /// The undeclared branch is symmetric by construction (`-half … half`), so
    /// the two ends agree there and always did. Pinned so a later change to
    /// `marginBounds` cannot make a tennis SET rail lopsided unnoticed.
    func testUndeclaredRailStaysSymmetric() {
        let bounds = MarketMapRail.marginBounds(margins: [-1.5, 2.5], declared: nil, pad: 3)
        let ends = MarketMapRail.marginAxisEnds(bounds)
        XCTAssertEqual(ends.left, ends.right, accuracy: 0.0001,
                       "an undeclared margin rail is symmetric about zero")
        XCTAssertEqual(ends.right, 3.0, accuracy: 0.0001)
    }

    /// Magnitudes, not signed values: the axis prints "NE by 18+", and the side
    /// of the rail already carries the sign. A `left` that came back negative
    /// would render "NE by -18+".
    func testEndsAreMagnitudes() {
        let ends = MarketMapRail.marginAxisEnds(MarketMapRail.Bounds(min: -7.5, max: 4.0))
        XCTAssertGreaterThan(ends.left, 0, "a left end is printed as a magnitude")
        XCTAssertEqual(ends.left, 7.5, accuracy: 0.0001)
        XCTAssertEqual(ends.right, 4.0, accuracy: 0.0001)
    }

    /// The zero the axis row positions "Tie" on is the same zero these ends
    /// bracket. If the labels and the mid label ever read different bounds the
    /// card contradicts itself again, which is what the photograph showed.
    func testMidLabelAgreesWithTheEndsItSitsBetween() {
        let bounds = patriotsAtSeahawks
        let ends = MarketMapRail.marginAxisEnds(bounds)
        let zeroPercent = (0 - bounds.min) / (bounds.max - bounds.min) * 100
        XCTAssertEqual(zeroPercent, 43.37, accuracy: 0.01, "the photographed 43%")

        // Zero sits at the share of the rail the left end claims.
        let leftShare = ends.left / (ends.left + ends.right) * 100
        XCTAssertEqual(leftShare, zeroPercent, accuracy: 0.0001)

        // And it is far enough from both ends that the word is drawn, not withheld.
        switch MarketMapRail.midAxisLabel(zeroPercent: zeroPercent) {
        case .at(let p): XCTAssertEqual(p, zeroPercent, accuracy: 0.0001)
        case .centred, .withheld:
            XCTFail("an asymmetric rail's zero is neither centred nor inside an end band")
        }
    }
}
