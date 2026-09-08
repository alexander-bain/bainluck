import XCTest
import SwiftUI
@testable import Bain_Luck

/// #3885 — a settled game's margin and totals maps stop captioning a settlement
/// price `PRE-GAME`. The margin-side twin of #3850, one card higher on the same
/// page, and the same root cause.
///
/// The SwiftUI views are not rasterised here. What is asserted is the pure rule
/// the four cards now defer to — `MarketMapRail.drawsPregameMarker` — plus the
/// arithmetic that produced the bug, `MarketMapView.closestToEvenMargin`, which
/// #3885 made `static` precisely so this file can call the real thing instead of
/// reconstructing it (`SpreadRungTests.nearestEven` is the copy that motivated
/// it).
///
/// THE SPECIMEN, used throughout: event **15305476**, `Washington Nationals 5 —
/// Los Angeles Dodgers 7`, `completed`. `/api/events/15305476/game-markets`
/// served exactly two full-game spread rungs, quoted in the issue and re-read
/// from production; the event row's own `opening_home_spread` / `opening_over_under`
/// are `-1.5` / `8.5` and are NOT served to this client (see
/// ``MarketMapRail/drawsPregameMarker(isDone:)``).
final class MarketMapPregameMarkerTests: XCTestCase {

    // MARK: - The specimen, exactly as the venue priced it

    /// `Los Angeles D wins by over 1.5 runs`, probability 0.99 — home-signed +1.5.
    private let dodgersPlus1point5 = SpreadRungs.Rung(
        margin: 1.5, probability: 0.99, isHome: true, quotedUnit: "runs"
    )
    /// `Washington wins by over 5.5 runs`, probability 0.02 — home-signed -5.5.
    private let nationalsPlus5point5 = SpreadRungs.Rung(
        margin: -5.5, probability: 0.02, isHome: false, quotedUnit: "runs"
    )
    private var specimenRungs: [SpreadRungs.Rung] { [dodgersPlus1point5, nationalsPlus5point5] }

    /// Dodgers 7 — Nationals 5, home-signed.
    private let specimenGameMargin = 2

    // MARK: - The bug is real, and it is a coin toss

    /// 🔴 THE CONTROL. Reproduces the tile in the issue's photograph from the
    /// venue's own two prices, so this file fails if the arithmetic that caused
    /// the bug is ever "fixed" somewhere else and this gate is left behind as
    /// dead weight.
    ///
    /// `|0.99 - 0.5| = 0.490` against `|0.02 - 0.5| = 0.480`: the LOSING side's
    /// deepest line wins the tile by a thousandth.
    func testTheSettledSpecimenHandsTheTileToTheLosingSidesDeepestLine() {
        let picked = MarketMapView.closestToEvenMargin(specimenRungs)
        XCTAssertEqual(
            picked, -5.5,
            "the tile lands on the AWAY -5.5 rung — `Nationals +5.5` as the card prints it, "
            + "which is what the issue photographed"
        )

        // A thousandth. Not a rounding artefact, not a tie: a real ordering
        // between two numbers that are both meaningless once every line has
        // resolved.
        let homeDistance = abs(dodgersPlus1point5.probability - 0.5)
        let awayDistance = abs(nationalsPlus5point5.probability - 0.5)
        XCTAssertEqual(homeDistance, 0.49, accuracy: 1e-9)
        XCTAssertEqual(awayDistance, 0.48, accuracy: 1e-9)
        XCTAssertLessThan(awayDistance, homeDistance)
        XCTAssertEqual(
            homeDistance - awayDistance, 0.01, accuracy: 1e-9,
            "one hundredth of a probability decides which line the card calls the "
            + "market's expectation — that is the definition of a coin toss"
        )
    }

    /// 🔴 THE SENTENCE THE CARD WAS PRINTING: the tile named the very rung the
    /// same card grades MISS two lines below it.
    func testTheTileNamedTheRungTheCardItselfGradesAMiss() {
        let picked = MarketMapView.closestToEvenMargin(specimenRungs)
        XCTAssertEqual(picked, nationalsPlus5point5.margin)

        // How the ladder beneath grades that same rung, via #3852's own helpers.
        let awayFinal = MarketMapRail.sideFinalMargin(
            gameMargin: specimenGameMargin, isHome: false
        )
        XCTAssertEqual(awayFinal, -2, "Washington lost by 2, so its cover ladder is graded against -2")

        let verdict = MarketMapRail.totalLadderResult(threshold: 5.5, finalTotal: awayFinal)
        XCTAssertEqual(
            MarketMapRail.totalLadderResultLabel(verdict), "MISS",
            "`Nationals +5.5` is a MISS — and the PRE-GAME tile was pointing at it"
        )

        // And the rung the card grades HIT is the one the tile passed over.
        let homeFinal = MarketMapRail.sideFinalMargin(
            gameMargin: specimenGameMargin, isHome: true
        )
        XCTAssertEqual(
            MarketMapRail.totalLadderResultLabel(
                MarketMapRail.totalLadderResult(threshold: 1.5, finalTotal: homeFinal)
            ),
            "HIT"
        )
    }

    // MARK: - The gate

    func testASettledMapMayNotDrawThePregameTile() {
        XCTAssertFalse(
            MarketMapRail.drawsPregameMarker(isDone: true),
            "once the game is over neither number the tile can reach is a pre-game number"
        )
    }

    /// 🟢 NARROW ON PURPOSE. #3885 is a settled-state fix; a live or unplayed map
    /// is untouched, which is what keeps the NFL projection marker pinned by
    /// `SpreadRungTests` from moving.
    func testALiveOrUnplayedMapIsUntouched() {
        XCTAssertTrue(MarketMapRail.drawsPregameMarker(isDone: false))

        // The unsettled specimen control: before the off the same two rungs are
        // priced like a real question, and the tile is both wanted and honest.
        let unplayed = [
            SpreadRungs.Rung(margin: 1.5, probability: 0.58, isHome: true, quotedUnit: "runs"),
            SpreadRungs.Rung(margin: -1.5, probability: 0.42, isHome: false, quotedUnit: "runs"),
        ]
        XCTAssertNotNil(
            MarketMapView.closestToEvenMargin(unplayed),
            "an unsettled ladder still yields a marker — the fix must not empty a pre-game card"
        )
    }

    // MARK: - It fires on EVERY settled ladder, not just this one

    /// 🔴 THE REASON A GATE IS THE RIGHT SHAPE OF FIX. On a settled ladder every
    /// line has resolved, so `closestToEvenMargin` always returns something and
    /// always returns something arbitrary. Swept over every settled two-sided
    /// shape the venue produces: the tile is never absent and never meaningful,
    /// so there is no subset of settled cards that could keep it.
    func testEverySettledLadderStillProducesAnArbitraryTile() {
        let resolvedPrices: [Double] = [0.99, 0.98, 0.97, 0.02, 0.01, 0.005]
        for homePrice in resolvedPrices {
            for awayPrice in resolvedPrices {
                for depth in [1.5, 2.5, 5.5, 9.5] {
                    let rungs = [
                        SpreadRungs.Rung(margin: 1.5, probability: homePrice, isHome: true, quotedUnit: "runs"),
                        SpreadRungs.Rung(margin: -depth, probability: awayPrice, isHome: false, quotedUnit: "runs"),
                    ]
                    XCTAssertNotNil(
                        MarketMapView.closestToEvenMargin(rungs),
                        "a settled ladder ALWAYS yields a tile (home \(homePrice) / away \(awayPrice)) — "
                        + "the old code could not fail to draw one, so nothing but a gate removes it"
                    )
                    XCTAssertFalse(
                        MarketMapRail.drawsPregameMarker(isDone: true),
                        "and the gate removes it in every one of those shapes"
                    )
                }
            }
        }
    }

    /// 🟠 The issue's second specimen (15305475, `Twins 1 — Sox 10`, tile reading
    /// `PRE-GAME Sox +1.5`) is NOT reconstructed here. Its market rows have since
    /// aged out of `/api/events/15305475/game-markets` — the endpoint now serves
    /// zero outcomes — so its per-rung prices could not be re-read, and a
    /// specimen test built on invented prices would assert this file's guesses
    /// rather than the venue's. The sweep above already covers the shape it
    /// belongs to.
}
