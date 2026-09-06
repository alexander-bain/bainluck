import XCTest
@testable import Bain_Luck

/// native/038 — #3566: a margin map names the tie where the tie is, once.
///
/// THE PHOTOGRAPH. Event 14632820 (San Francisco 49ers @ Los Angeles Rams,
/// `americanfootball_nfl`, status `scheduled`), iPhone 17 simulator against
/// production, 2026-09-06 ~09:51 EDT — `artifacts-native-038/`
/// `nfl-14632820-s900.png` (both half-margin cards in one frame) and
/// `nfl-14632820-s300.png` (the full-game axis). Three margin cards on one
/// page, each printing the same concept twice:
///
/// | card | zero on the rail | "Tie" printed at | what it looked like |
/// |---|---|---|---|
/// | Margin map | 43.4% | 50.0% | `0` and `Tie` crowded 6.6 points apart |
/// | 1st half margin | 74.3% | 50.0% | `Tie` a quarter of the rail from the tie |
/// | 2nd half margin | 50.0% | 50.0% | `0` printed ON TOP OF `Tie` |
///
/// THE MECHANISM. `densityRail` drew `Text("0")` at the real zero and `y: 48` —
/// which, on a rail of `height: 36` followed by the axis `HStack` at
/// `spacing: 10`, is the axis row. `mapCard` then drew `axisMid` between two
/// equal `Spacer()`s, so it was always at the geometric centre. There is no
/// value of the zero position at which both are right: apart they contradict,
/// together they overprint.
///
/// The rail is asymmetric whenever the parsed margins are, i.e. on every game
/// with a favourite:
/// `rangeMin = min(minMargin - 3, -marginRange)`,
/// `rangeMax = max(maxMargin + 3, marginRange)`.
final class MarketMapMidAxisLabelTests: XCTestCase {

    /// `MarketMapView.posOnRail`, so the rails below are derived the way the
    /// view derives them rather than hand-written (a hand-written zero position
    /// would agree with nothing).
    private func zeroPercent(min: Double, max: Double) -> Double {
        Swift.max(0, Swift.min(100, ((0 - min) / (max - min)) * 100))
    }

    // MARK: - Direction 1: the three cards in the photograph

    /// The full-game card. `spreads` on 14632820 parsed to margins
    /// `[-15.0, 20.5]`; `marginRange` for americanfootball is 18, so the rail is
    /// `[min(-18, -18), max(23.5, 18)] = [-18.0, 23.5]`.
    func testTheFullGameCardLabelsTheTieAt43Point4NotAt50() {
        let zero = zeroPercent(min: -18.0, max: 23.5)
        XCTAssertEqual(zero, 43.373, accuracy: 0.001, "the rail's real zero")

        guard case .at(let percent) = MarketMapRail.midAxisLabel(zeroPercent: zero) else {
            return XCTFail("a rail with a zero on it must place its mid label")
        }
        XCTAssertEqual(percent, zero, accuracy: 0.0001)
        XCTAssertNotEqual(percent, 50, "the centre is where the old HStack put it")
    }

    /// The 1st-half card — the widest miss, and the one a reader would call a
    /// lie: the tile said `LAR +1.0` while `Tie` sat 24.3 points of rail away
    /// from the marker. Rail `[-52.0, 18.0]`.
    func testTheFirstHalfCardLabelsTheTieAt74Point3NotAt50() {
        let zero = zeroPercent(min: -52.0, max: 18.0)
        XCTAssertEqual(zero, 74.286, accuracy: 0.001)

        guard case .at(let percent) = MarketMapRail.midAxisLabel(zeroPercent: zero) else {
            return XCTFail("74.3% is well inside the rail and must be labelled")
        }
        XCTAssertEqual(percent, zero, accuracy: 0.0001)
        XCTAssertEqual(abs(percent - 50), 24.286, accuracy: 0.001,
                       "the gap the photograph shows")
    }

    /// The 2nd-half card — the overprint. Rail `[-18.0, 18.0]`, zero dead
    /// centre. The label still goes AT zero; what changed is that there is only
    /// one label now, so 50% is a coincidence rather than a collision.
    func testTheSecondHalfCardIsStillLabelledAtTheCentreButOnlyOnce() {
        let zero = zeroPercent(min: -18.0, max: 18.0)
        XCTAssertEqual(zero, 50.0, accuracy: 0.0001)

        guard case .at(let percent) = MarketMapRail.midAxisLabel(zeroPercent: zero) else {
            return XCTFail("a symmetric rail is the easy case and must still label")
        }
        XCTAssertEqual(percent, 50.0, accuracy: 0.0001)
    }

    // MARK: - Direction 2: the totals maps must not move at all

    /// 🔴 THE REGRESSION THAT WOULD BE WORSE THAN THE BUG. Every totals card in
    /// the app passes `zeroPosition: nil` and an `axisMid` that genuinely IS
    /// the midpoint of its range (`"\(Int((rangeMin + rangeMax) / 2))"`).
    /// Moving those would put a number in a place it does not describe on
    /// every sport, to fix a defect none of them had. Pinned first among the
    /// mirror directions.
    func testARailWithNoZeroKeepsItsCentredMidpointLabel() {
        XCTAssertEqual(MarketMapRail.midAxisLabel(zeroPercent: nil), .centred)
    }

    // MARK: - Direction 3: the end-label band

    /// The word "Tie" is ~22 pt wide and the end labels are not narrow —
    /// measured off `nfl-14632820-s900.png` at 402 pt, `SF by 18+` runs to
    /// 13.5% and `LAR by 18+` back to 16.2%. Inside that band the label is
    /// withheld rather than printed over an end label.
    func testAZeroInsideTheEndLabelBandWithholdsTheLabel() {
        XCTAssertEqual(MarketMapRail.midAxisLabel(zeroPercent: 0), .withheld)
        XCTAssertEqual(MarketMapRail.midAxisLabel(zeroPercent: 13.5), .withheld,
                       "where `SF by 18+` ends")
        XCTAssertEqual(MarketMapRail.midAxisLabel(zeroPercent: 83.8), .withheld,
                       "where `LAR by 18+` starts")
        XCTAssertEqual(MarketMapRail.midAxisLabel(zeroPercent: 100), .withheld)
    }

    /// Both edges of the band, exactly. A `<` written for a `<=` moves these.
    func testTheBandBoundariesAreClosed() {
        XCTAssertEqual(MarketMapRail.midAxisLabel(zeroPercent: 20), .withheld)
        XCTAssertEqual(MarketMapRail.midAxisLabel(zeroPercent: 80), .withheld)

        guard case .at(let low) = MarketMapRail.midAxisLabel(zeroPercent: 20.01) else {
            return XCTFail("just inside the band's low edge must be labelled")
        }
        XCTAssertEqual(low, 20.01, accuracy: 0.0001)

        guard case .at(let high) = MarketMapRail.midAxisLabel(zeroPercent: 79.99) else {
            return XCTFail("just inside the band's high edge must be labelled")
        }
        XCTAssertEqual(high, 79.99, accuracy: 0.0001)
    }

    /// 🔴 The band must not eat the working middle. A guard that widened to
    /// swallow ordinary rails would silently delete the tie label from every
    /// margin map in the app — the same "fixed it by removing it" failure
    /// `marginMapIsEmptyChrome` exists to avoid, one label smaller.
    ///
    /// The reachable range is narrow and it is arithmetic, not taste: both
    /// bounds are at least `marginRange` in magnitude, so zero can only leave
    /// `[25%, 75%]` when one side's parsed margin is more than three times the
    /// sport's whole realistic spread — which on 14632820's 1st half is exactly
    /// what a bad `threshold` did (see #3567).
    func testEveryOrdinaryRailKeepsItsTieLabel() {
        for zero in stride(from: 25.0, through: 75.0, by: 0.5) {
            guard case .at(let percent) = MarketMapRail.midAxisLabel(zeroPercent: zero) else {
                return XCTFail("an ordinary rail at \(zero)% lost its tie label")
            }
            XCTAssertEqual(percent, zero, accuracy: 0.0001)
        }
    }

    /// The band is a parameter so the measurement can be restated, but its
    /// default is the one the view uses. A change to the constant that forgets
    /// the measurement fails here.
    func testTheDefaultBandIsTheMeasuredOne() {
        XCTAssertEqual(MarketMapRail.endLabelBandPercent, 20)
        XCTAssertEqual(
            MarketMapRail.midAxisLabel(zeroPercent: 18),
            MarketMapRail.midAxisLabel(zeroPercent: 18, endLabelBand: MarketMapRail.endLabelBandPercent)
        )
    }

    // MARK: - The rule the view can no longer break

    /// 🔴 The defect was two labels, not a misplaced one. This is the invariant
    /// that kills the old code even if someone re-places the mid label
    /// correctly and leaves the rail's `Text("0")` in: at most ONE label
    /// describes zero, so the placed case and a second literal cannot coexist.
    /// Asserted on the source, because a second `Text` in a `@ViewBuilder` is
    /// otherwise only visible in a raster.
    func testTheDensityRailNoLongerDrawsItsOwnZeroLabel() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck
            .appendingPathComponent("Bain Luck/Components/MarketMapView.swift")
        // Comments are stripped first. The `//` line explaining why the old
        // `Text("0")` was removed quotes it verbatim, and the first run of this
        // guard failed on that comment — a scanner that reads prose is
        // measuring the write-up, not the code.
        let source = try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertFalse(
            source.contains(#"Text("0")"#),
            "`densityRail` drawing its own zero label is #3566: the axis row already carries one"
        )
        XCTAssertTrue(
            source.contains("MarketMapRail.midAxisLabel(zeroPercent: zeroPosition)"),
            "`mapCard` must place its mid label through the rule, not between two Spacers"
        )
    }
}
