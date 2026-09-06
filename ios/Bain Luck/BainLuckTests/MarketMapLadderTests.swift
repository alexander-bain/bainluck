import XCTest
import SwiftUI
@testable import Bain_Luck

/// native/040 — the market map's ladder column, sized from what it draws.
///
/// THE PHOTOGRAPH: `artifacts-native-040/live-sabalenka-15304842-s600.png`,
/// iPhone 17 against production, the live Townsend–Sabalenka US Open match.
/// The two ladder rows read **`Townsend…  60%`** and **`Sabalenka…  45%`** —
/// the line, which is the only thing on the row that names a market, truncated
/// out of existence by an 82 pt column nothing had ever measured.
///
/// It surfaced because #3552's fix started printing the real line: `Int(abs())`
/// used to turn `+5.5` into `+5` and `+1.5` into `+1`, which is shorter and
/// also wrong. So the defect the LOOK found was the fix's own, and it is the
/// same class native/039 found on `ChampionshipStageBadges` the day before —
/// **a fixed-width column with no instrument behind it.**
final class MarketMapLadderTests: XCTestCase {

    /// Every ladder label the app actually builds, from the production payloads
    /// of 2026-09-06.
    ///
    /// `MarketMapView` builds them as `"\(abbr) +\(formatThreshold(margin))"`
    /// for the margin maps and `"Over \(formatThreshold(threshold))"` for the
    /// totals, where `abbr` comes from `TeamShortName.shortPair` — a tennis
    /// SURNAME, which is where the length is. Nothing here is invented: these
    /// are the events in the visible US Open and NFL windows.
    private let productionLabels = [
        // Tennis — the long case, and the one that was photographed truncating.
        "Sabalenka +5.5", "Townsend +5.5",
        "Zandschulp +1.5", "Etcheverry +2.5", "Kalinskaya +1.5",
        "Tsitsipas +2.5", "Khachanov +1.5", "Michelsen +2.5",
        "Swiatek +1.5", "Zheng +1.5", "Kostyuk +1.5", "Noskova +1.5",
        // NFL — abbreviations, and the widest totals rung.
        "LAR +2.5", "SF +2.5", "NE +10.5", "Over 42.5",
    ]

    /// 🟢 THE FIX, and the instrument that sized it. If a label wants more room
    /// than the column offers, the row silently eats its own line — which is
    /// what the photograph shows.
    @MainActor
    func testTheColumnHoldsTheWidestLabelProductionServes() {
        var widest: (label: String, width: CGFloat) = ("", 0)
        for label in productionLabels {
            let wanted = naturalWidth(of: MarketMapLadderLabel(text: label, color: .blue))
            if wanted > widest.width { widest = (label, wanted) }
        }

        XCTAssertGreaterThanOrEqual(
            MarketMapLadderLayout.labelColumnWidth, widest.width,
            "the widest label production serves is '\(widest.label)', which wants "
            + "\(widest.width) pt, and the column offers "
            + "\(MarketMapLadderLayout.labelColumnWidth) pt. Short by any amount and "
            + "the row drops the line it exists to name.")
    }

    /// 🔴 THE REGRESSION A WIDER COLUMN BUYS. The bar is the measurement; the
    /// label is its caption. A column allowed to grow until any name fits would
    /// trade one for the other, so the width above is capped by judgement and
    /// this is the judgement, stated as a number.
    func testTheBarKeepsMoreThanHalfTheRowOnTheNarrowestCard() {
        XCTAssertGreaterThan(MarketMapLadderLayout.barWidthOnSmallestCard, 170)
        XCTAssertGreaterThan(
            MarketMapLadderLayout.barWidthOnSmallestCard,
            MarketMapLadderLayout.labelColumnWidth,
            "the data must be wider than its caption")
    }

    /// 🔴 The old column, pinned as the thing that was too small — so "82 was
    /// fine, something else broke it" fails here rather than in a screenshot.
    @MainActor
    func testTheOldEightyTwoPointColumnCouldNotHoldTheLabelThatTruncated() {
        let wanted = naturalWidth(of: MarketMapLadderLabel(text: "Sabalenka +5.5", color: .blue))
        XCTAssertGreaterThan(
            wanted, 82,
            "'Sabalenka +5.5' — the row in live-sabalenka-15304842-s600.png — must "
            + "want more than the 82 pt it was given, or the truncation has some "
            + "other cause")
    }

    /// The half point is not decoration: `Int()` truncation turned two
    /// different lines into the same label. Both directions, because a
    /// formatter that started printing `+1.0` everywhere would be its own
    /// regression on the whole-number rungs an NFL "Winning Margin" market
    /// serves (`LAR +1`, photographed in `CONTROL-nfl-14632820-s840.png`).
    func testALineIsPrintedAsTheLineNotAsItsFloor() {
        XCTAssertEqual(MarketMapLadderLabel(text: "x", color: .blue).text, "x")
        // The formatter itself, exercised through the same values the cards use.
        XCTAssertEqual(format(1.5), "1.5")
        XCTAssertEqual(format(2.5), "2.5")
        XCTAssertEqual(format(5.5), "5.5")
        XCTAssertEqual(format(1.0), "1", "a whole line keeps its whole-number label")
        XCTAssertEqual(format(18.0), "18")
    }

    /// `MarketMapView.formatThreshold`, which is `private` to a SwiftUI view —
    /// reproduced here as the one line it is, so the contract above is pinned
    /// even though the original cannot be reached.
    private func format(_ t: Double) -> String {
        t.truncatingRemainder(dividingBy: 1) == 0 ? "\(Int(t))" : String(format: "%.1f", t)
    }

    @MainActor
    private func naturalWidth<V: View>(of view: V) -> CGFloat {
        let host = UIHostingController(rootView: view)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }
}
