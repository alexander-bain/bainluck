import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// Column widths for the Calibration surface's "Source Comparison" table.
///
/// #3954 — THE FOUR NUMERIC COLUMNS WERE HARD-CODED AT 54/48/46/52 = 200pt AND THE
/// LABEL WAS WHATEVER WAS LEFT.
///
/// Those four literals are sized for the widest value the table can ever hold —
/// `437,910` in the Combined row, `0.248`, `14.9` — while every per-source cell
/// above is narrower, so most of the reserved 200pt is whitespace on exactly the
/// rows that are running out of room. On a 402pt phone that left the label about
/// 130pt and two of seven source names truncated:
///
///     ● Spreads (Odds…       15.1K    0.3   14.9  0.248
///     ● Per-Bookmaker…      101.2K    1.4    2.0  0.216
///     ● Totals (Odds API)    15.5K    2.5   17.3  0.249
///
/// Three of those seven rows are Odds API variants, and the cut lands on the one
/// token that tells them apart. `Spreads (Odds…` sits directly under
/// `Totals (Odds API)` and a reader cannot tell whether it is the same provider.
/// Losing the provider is the worst possible place to lose characters, which is
/// what makes this more than ordinary truncation.
///
/// So the numeric columns are measured against the strings THIS render will
/// actually draw, in the font it will draw them in, and the label keeps the rest.
/// `PeriodChipGeometry` is the pattern: a width model owes accuracy in both
/// directions, and a hand-picked point count is a bound wearing a measurement's
/// clothes.
///
/// Sized against content rather than a literal, this also tracks Dynamic Type for
/// free — the old literals did not, so every step above `.large` re-broke the
/// label by widening the numbers inside fixed boxes.
///
/// **WHAT THIS DOES NOT DO, MEASURED ON PRODUCTION.** It frees a little over 40pt
/// (200 → 157.2 at `.large` on a synthetic payload), which fixes `Spreads (Odds
/// API)` — the row the issue was actually about, since it sat under `Totals (Odds
/// API)` and a reader could not tell they were the same provider. It does NOT fix
/// `Per-Bookmaker (Odds API)`, which is ~25–30pt longer than the freed space at
/// 402pt and still prints `Per-Bookmaker (Odds…`. Photographed:
/// `artifacts-native-065/AFTER-3954-calibration-sources.png`.
///
/// No column model can close that gap — the four numbers are now AT their ink
/// (`N` sized by Combined's `437,910`, `MCE` by `17.3`, `Brier` by `0.248`), so
/// the next point taken from them truncates a number instead of a name. The
/// narrow case needs a column dropped or a name wrapped, which is the layout call
/// #3954 deliberately left open. Tracked with the renders and three costed
/// options in #3966.
///
/// **#3966 — ANSWERED. Alex ruled D92 = B: the name wraps.** `sourceNameLineLimit`
/// below is that ruling, and it is the reason no later change should reach back
/// for the numeric columns: they are not the constraint any more. The two options
/// not taken are recorded because they will look tempting again — dropping `MCE`
/// and `Brier` at compact width frees ~72pt and costs half the numbers on a phone,
/// and shortening the names to `Per-sportsbook` gives up exactly the provider
/// disambiguation #3954 existed to protect.
///
/// Note the shape of the near-miss that hid this: a synthetic fixture of
/// same-length outcome counts renders every name in full at 402pt, and production
/// does not, because the column widths are a function of the DIGITS in the cells
/// and production's spread (15.1K … 219.0K under a 437,910 footer) is wider than
/// a tidy fixture's. The fixture now carries production-shaped numbers.
///
/// A `.minimumScaleFactor` backstop was built for the narrow case and REMOVED,
/// because it does not do what it looks like it does. Rendered at 375pt: at a 0.8
/// floor the name still truncates, one character later, having shrunk every OTHER
/// name in the table to match — SwiftUI scales sibling text together. Only at 0.5
/// does it fit, at a size nobody would ship. A modifier that shrinks six labels to
/// half-rescue a seventh is worse than the truncation, and a modifier that reads
/// as a safety net while changing nothing is worse still.
enum CalibrationSourceTableGeometry {
    /// The row's own inset, applied on each side (`.padding(.horizontal, 12)`).
    static let horizontalPadding: Double = 12
    /// The source's colour swatch, and the gap between it and the name.
    static let dotDiameter: Double = 8
    static let dotSpacing: Double = 6
    /// Kept between one column's ink and the column to its left, so trailing-aligned
    /// numbers never touch the value beside them. Deliberately smaller than the ~14pt
    /// of slack the old literals carried: that slack is the label's.
    static let numericGutter: Double = 6

    /// #3966 (Alex, D92 = B) — how many lines a source name may spend.
    ///
    /// TWO, not `nil`. An unbounded label lets one pathological name set the
    /// height of a row in a table whose whole job is to be scanned, and the
    /// decision Alex made was specifically "wrap onto a second line".
    ///
    /// **That leaves a third line's worth of truncation still reachable, and this
    /// comment is where that is admitted rather than hidden.** Whether two lines
    /// hold today's longest name is a claim about drawn text, and the tests in
    /// this area cannot make it: a raster assertion cannot read characters, and
    /// the arithmetic model that could was measured wrong by ~21pt in the
    /// SAFE-LOOKING direction while #3954 was being built (see the fit note on
    /// `testTheTableRendersAtEveryPhoneWidthAndReflowsWithIt`). So the guards
    /// below prove only that a name too long for one line takes two — the claim
    /// that the second line is enough is carried by the 375pt and 402pt
    /// screenshots on #3966's PR, and it is re-owed by anyone who adds a longer
    /// name.
    ///
    /// A constant rather than a literal at the call site because the guard has to
    /// be able to say what it is checking against: a test that hard-codes `2`
    /// keeps passing after the view stops asking for it.
    static let sourceNameLineLimit: Int = 2

    /// The four numeric columns, in the order the table draws them.
    struct NumericWidths: Equatable {
        let n: Double
        let ece: Double
        let mce: Double
        let brier: Double

        var total: Double { n + ece + mce + brier }
        var all: [Double] { [n, ece, mce, brier] }
    }

    /// Which font a cell is drawn in. The header row is `.caption2` semibold and the
    /// value rows are `.caption`; a column must clear BOTH, because "Brier" is wider
    /// than several of the numbers under it.
    enum CellFont {
        case header
        case value

        #if canImport(UIKit)
        func uiFont(at typeSize: DynamicTypeSize) -> UIFont {
            let traits = UITraitCollection(
                preferredContentSizeCategory: Self.contentSizeCategory(typeSize))
            switch self {
            case .header:
                let base = UIFont.preferredFont(forTextStyle: .caption2, compatibleWith: traits)
                return UIFont.systemFont(ofSize: base.pointSize, weight: .semibold)
            case .value:
                // `.monospacedDigit()` + `.fontWeight(.semibold)` is the widest
                // combination any value cell uses (the ECE column). Measuring the
                // plain face would under-charge that column by a point per digit.
                let base = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: traits)
                return UIFont.monospacedDigitSystemFont(
                    ofSize: base.pointSize, weight: .semibold)
            }
        }

        /// SwiftUI resolves `.caption` against the view's `dynamicTypeSize`, which a
        /// parent can override; `UIFont.preferredFont` with no traits resolves
        /// against the APP's setting instead. Measuring one and drawing the other is
        /// how a column ends up narrower than the number inside it, so the size is
        /// always threaded through rather than read from the process.
        static func contentSizeCategory(_ size: DynamicTypeSize) -> UIContentSizeCategory {
            switch size {
            case .xSmall: return .extraSmall
            case .small: return .small
            case .medium: return .medium
            case .large: return .large
            case .xLarge: return .extraLarge
            case .xxLarge: return .extraExtraLarge
            case .xxxLarge: return .extraExtraExtraLarge
            case .accessibility1: return .accessibilityMedium
            case .accessibility2: return .accessibilityLarge
            case .accessibility3: return .accessibilityExtraLarge
            case .accessibility4: return .accessibilityExtraExtraLarge
            case .accessibility5: return .accessibilityExtraExtraExtraLarge
            @unknown default: return .large
            }
        }
        #endif

        /// Per-character fallback for a platform that cannot measure text. Never
        /// used on iOS; see `textWidth`.
        var fallbackCharacterWidth: Double {
            switch self {
            case .header: return 6.5
            case .value: return 7.5
            }
        }
    }

    /// The ink a string actually occupies, MEASURED in the font it is drawn in.
    static func textWidth(
        _ string: String, font: CellFont, typeSize: DynamicTypeSize = .large
    ) -> Double {
        #if canImport(UIKit)
        return Double((string as NSString)
            .size(withAttributes: [.font: font.uiFont(at: typeSize)]).width)
        #else
        return Double(string.count) * font.fallbackCharacterWidth
        #endif
    }

    /// One column's width: the widest thing it will draw — header included — plus
    /// the gutter to its left.
    static func columnWidth(
        header: String, values: [String], typeSize: DynamicTypeSize = .large
    ) -> Double {
        let headerInk = textWidth(header, font: .header, typeSize: typeSize)
        let valueInk = values.map { textWidth($0, font: .value, typeSize: typeSize) }.max() ?? 0
        return max(headerInk, valueInk) + numericGutter
    }

    /// Every numeric column, sized against the strings this render will draw.
    ///
    /// The Combined row's values belong in these arrays even though it is a
    /// different kind of row: it shares the columns, so a `437,910` down there is
    /// as binding on the `N` column as any source above it.
    static func numericWidths(
        n: [String], ece: [String], mce: [String], brier: [String],
        typeSize: DynamicTypeSize = .large
    ) -> NumericWidths {
        NumericWidths(
            n: columnWidth(header: "N", values: n, typeSize: typeSize),
            ece: columnWidth(header: "ECE", values: ece, typeSize: typeSize),
            mce: columnWidth(header: "MCE", values: mce, typeSize: typeSize),
            brier: columnWidth(header: "Brier", values: brier, typeSize: typeSize))
    }

}
