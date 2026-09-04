import XCTest
@testable import Bain_Luck

/// #2902 — the win-probability bar on every tennis card was a flat grey block.
///
/// The reported defect: Tabilo **97%** / Popyrin **3%** on the Sports tab drew a
/// single uniform rectangle, and so did the 58/42 card above it and the 60/40
/// card below it. Both sides resolved to `#6b7280` because neither player has a
/// team row, so the bar's two segments were the same colour and the split had
/// no visible edge.
///
/// `testTennisMatchWithNoBrandColoursDoesNotDrawOneFlatBlock` is that case.
/// The rest hold the contract that makes it stay fixed: **the pair is never two
/// indistinguishable colours**, for any input, including ones nobody thought of.
final class ProbabilityBarPaletteTests: XCTestCase {

    private typealias P = ProbabilityBarPalette

    // MARK: - The reported defect

    func testTennisMatchWithNoBrandColoursDoesNotDrawOneFlatBlock() {
        // Two tennis players: no team row, therefore no primary_color at all.
        let pair = P.pair(awayHex: nil, homeHex: nil)
        XCTAssertNotEqual(pair.away, pair.home, "a bar with one colour cannot show where the split falls")
        XCTAssertTrue(
            P.distinguishable(pair.away, pair.home),
            "\(pair.away) and \(pair.home) are \(P.distance(pair.away, pair.home) ?? -1) apart — under the readable minimum"
        )
    }

    func testTheOldFallbackIsExactlyWhatThisRejects() {
        // The shipped bug, stated as a test: #6b7280 twice is not a pair.
        XCTAssertFalse(P.distinguishable("#6b7280", "#6b7280"))
    }

    // MARK: - Real crests are never repainted

    func testTwoBrandColoursThatReadApartAreUsedUntouched() {
        // Lakers purple vs Celtics green.
        let pair = P.pair(awayHex: "#552583", homeHex: "#007A33")
        XCTAssertEqual(pair.away, "#552583")
        XCTAssertEqual(pair.home, "#007A33")
    }

    func testLowercaseAndBareHexAreTheSameColour() {
        let withHash = P.pair(awayHex: "#552583", homeHex: "#007a33")
        let without = P.pair(awayHex: "552583", homeHex: "007A33")
        XCTAssertEqual(withHash.away, without.away)
        XCTAssertEqual(withHash.home, without.home)
    }

    // MARK: - One side missing

    func testTheKnownSideKeepsItsCrestAndThePartnerReadsApart() {
        // A tennis player against a mapped team is not a real fixture, but a
        // team we have not mapped against one we have is — every league list has
        // some. The mapped side must not lose its colour.
        let pair = P.pair(awayHex: "#552583", homeHex: nil)
        XCTAssertEqual(pair.away, "#552583")
        XCTAssertTrue(P.distinguishable(pair.away, pair.home))

        let mirrored = P.pair(awayHex: nil, homeHex: "#552583")
        XCTAssertEqual(mirrored.home, "#552583")
        XCTAssertTrue(P.distinguishable(mirrored.away, mirrored.home))
    }

    func testAPartnerCollidingWithItsSlotDefaultMovesOffIt() {
        // A crest sitting on the home slot's own default (#2563EB): the missing
        // away side must not be handed something that reads the same.
        let pair = P.pair(awayHex: nil, homeHex: "#2563EB")
        XCTAssertEqual(pair.home, "#2563EB")
        XCTAssertNotEqual(pair.away, "#2563EB")
        XCTAssertTrue(P.distinguishable(pair.away, pair.home))
    }

    // MARK: - Two crests that do not read apart

    func testTwoNearIdenticalRedsAreSeparated() {
        // Two red teams produced the same flat bar as two tennis players.
        let pair = P.pair(awayHex: "#EF4444", homeHex: "#DC2626")
        XCTAssertEqual(pair.home, "#DC2626", "home keeps its crest; away is the one that moves")
        XCTAssertTrue(P.distinguishable(pair.away, pair.home))
    }

    func testTheSameHexTwiceIsSeparated() {
        let pair = P.pair(awayHex: "#10B981", homeHex: "#10B981")
        XCTAssertTrue(P.distinguishable(pair.away, pair.home))
    }

    // MARK: - Malformed input is absent, not black

    func testMalformedHexIsTreatedAsAbsent() {
        // Color(hex:) scans with Scanner and leaves rgb = 0 on failure, so each
        // of these renders BLACK today — a colour nobody chose, on both sides.
        for junk in ["", "   ", "#", "not-a-color", "#12", "#1234567", "#GGGGGG", "rgb(1,2,3)"] {
            XCTAssertNil(P.rgb(junk), "\(junk) must not parse as a colour")
            let pair = P.pair(awayHex: junk, homeHex: junk)
            XCTAssertEqual(pair.away, P.awayDefault, "\(junk) should fall back like an absent colour")
            XCTAssertEqual(pair.home, P.homeDefault, "\(junk) should fall back like an absent colour")
        }
    }

    func testThreeDigitShorthandIsAbsentRatherThanWrong() {
        // Color(hex:) reads "#F00" as 0x000F00 — a dark green for a red team.
        XCTAssertNil(P.rgb("#F00"))
    }

    // MARK: - The contract, over everything

    func testEveryPairOfInputsReadsApart() {
        let inputs: [String?] = [
            nil, "", "not-a-color", "#6b7280", "#6B7280", "#64748B", "#2563EB",
            "#10B981", "#9CA3AF", "#EF4444", "#DC2626", "#552583", "#FDB927",
            "#000000", "#FFFFFF", "#111827", "#F59E0B", "#8B5CF6", "#007A33",
        ]
        for away in inputs {
            for home in inputs {
                let pair = P.pair(awayHex: away, homeHex: home)
                XCTAssertTrue(
                    P.distinguishable(pair.away, pair.home),
                    "away=\(away ?? "nil") home=\(home ?? "nil") -> \(pair.away)/\(pair.home), "
                        + "distance \(P.distance(pair.away, pair.home) ?? -1)"
                )
            }
        }
    }

    func testThePairIsDeterministic() {
        // A card that changes colour between renders is its own bug.
        for _ in 0..<5 {
            XCTAssertEqual(P.pair(awayHex: nil, homeHex: nil).away, P.awayDefault)
            XCTAssertEqual(P.pair(awayHex: nil, homeHex: nil).home, P.homeDefault)
            XCTAssertEqual(P.pair(awayHex: "#EF4444", homeHex: "#DC2626").away,
                           P.pair(awayHex: "#EF4444", homeHex: "#DC2626").away)
        }
    }

    // MARK: - The maths itself

    func testDistanceIsSymmetricAndZeroOnItself() {
        XCTAssertEqual(P.distance("#552583", "#552583"), 0)
        XCTAssertEqual(P.distance("#552583", "#FDB927")!, P.distance("#FDB927", "#552583")!, accuracy: 0.0001)
    }

    func testDistanceIsNilWhenEitherSideIsUnparseable() {
        XCTAssertNil(P.distance(nil, "#552583"))
        XCTAssertNil(P.distance("#552583", "zzzzzz"))
    }

    func testTheDefaultsThemselvesReadApart() {
        // If these two ever collide, every unmapped card goes flat again and no
        // other test in this file would necessarily catch it.
        XCTAssertTrue(P.distinguishable(P.awayDefault, P.homeDefault))
    }

    func testEveryLadderRungReadsApartFromEveryOther() {
        for (i, a) in P.ladder.enumerated() {
            for b in P.ladder[(i + 1)...] {
                XCTAssertTrue(P.distinguishable(a, b), "ladder rungs \(a) and \(b) collide")
            }
        }
    }

    func testPartnerNeverReturnsTheColourItWasAvoiding() {
        for taken in P.ladder + ["#6B7280", "#552583", "#000000", "#FFFFFF"] {
            let partner = P.partner(for: taken, preferring: P.awayDefault)
            XCTAssertTrue(
                P.distinguishable(partner, taken),
                "partner(for: \(taken)) returned \(partner)"
            )
        }
    }
}
