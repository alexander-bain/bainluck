import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// The three-column outcome row on the Discover FUTURES card — the ranked rows
/// reading `Democratic Party ▁▃▃▃ 63%` under the hero image.
///
/// #8213 — THE PERCENT COLUMN WAS A HARDCODED 34pt AND THE NAME CAP A HARDCODED
/// 140pt, BOTH UNDER FONTS THAT SCALE.
///
/// `NativeFuturesDiscoverCard.outcomeRow` drew the percentage at
/// `.frame(width: 34, alignment: .trailing)` in `.caption.weight(.bold)
/// .monospacedDigit()`. `.caption` is a TEXT STYLE, so the glyphs ramp with
/// Dynamic Type while the box does not, and at
/// `accessibility-extra-extra-extra-large` `63%` breaks one glyph per line:
///
/// ```
/// Demo-        ▁▁▁▁▁▃▃▃▃        6
/// cratic…                       3
///                               %
/// ```
///
/// Photographed on the anonymous production feed, iPhone 17 Pro, on the
/// "Which party will win the U.S. Senate?" card.
///
/// ⚠️ **#8213 was filed against the wrong file and the correction is on the
/// issue.** Its body named `DistributionCardView`'s `20pt`/`40pt` pins as the
/// finding and this row as an unphotographed candidate; it is the other way
/// round. `DistributionCardView` has no hero image, no `See more` summary and a
/// LEADING RANK COLUMN, none of which is in the frame, and its label is
/// `lineLimit(1)` so it cannot produce the two-line `Demo-`/`cratic…` that is.
/// That card's pins are the same CLASS and remain open as a candidate; they are
/// not fixed here and were never photographed.
///
/// `EventSourceLabelColumn` (#4107/#4208/#4233) and `GameCardStatusColumn`
/// (#8144) are the pattern: measure the strings THIS render will draw, in the
/// font it will draw them in, at the view's own `dynamicTypeSize`.
///
/// ## The percent column is measured ACROSS the card, not per row
///
/// The 34pt literal was buying one thing worth keeping: the three percentages
/// share a right edge, so the bars beside them start and end together. Measuring
/// each row on its own ink would size every row differently and ragged the
/// column that the literal — wrongly, but consistently — kept straight. So the
/// width is the widest ink among the labels THIS card prints, and every row is
/// given it.
///
/// ## What the name cap is, now that it is not 140
///
/// The row holds three things and the bar is one of them. A cap that is a point
/// count cannot know that: at `.large` 140pt leaves the bar 125pt and looks
/// right, and at a11y5 the same 140 leaves a percentage that needs 80pt fighting
/// a bar for what is left. The cap is therefore what remains after the measured
/// percentage and an equal share for the bar are taken out —
/// `available - percent - spacing - available/3`.
///
/// Being a PROPORTION is what keeps `barMinimumShare` out of the class of bug
/// this file repairs: it carries no point value and no text size, so it cannot
/// be right on one phone and wrong on the next. It moves the cap in BOTH
/// directions for the right reason — a 375pt card gives the name ~164pt at
/// `.large` (more than 140, because the percentage is only ~30pt of ink there)
/// and ~114pt at a11y5 (less than 140, because the percentage now needs ~80).
///
/// ## Why there is no reflow arm here, unlike `GameCardStatusColumn`
///
/// #8144's status column can be asked for more width than a phone HAS, so it
/// needs a stacked arm. This row cannot: the name is `lineLimit(2)` and
/// truncates by design, so the only unbounded quantity is the percentage, whose
/// worst case is the four glyphs of `100%` — ~80pt at a11y5 against a ~315pt
/// card. `nameMinimum + barMinimumShare + percent` never exceeds the row.
/// A stacked arm would be a branch that cannot be reached, which is the same
/// thing as a clause that cannot fail, and #8144 deleted one of those rather
/// than ship it as a safeguard that guards nothing.
enum FuturesOutcomeRowColumns {

    /// The `HStack(spacing: 8)` the row is built in, twice — name-to-bar and
    /// bar-to-percent. Read from the call site rather than assumed, and the
    /// source guard in the tests asserts the two still agree.
    static let interColumnSpacing: Double = 8

    /// `.frame(minWidth: 60, …)` at the call site, kept: it is a FLOOR, and a
    /// floor does not rot the way a ceiling does — it stops a one-word outcome
    /// (`Yes`) collapsing its column and misaligning the bars beside the longer
    /// rows, at every text size equally.
    static let nameMinimum: Double = 60

    /// A point of slack over measured ink. `NSString.size` returns a fractional
    /// width and SwiftUI truncates on the fractional overflow, so a column sized
    /// to the exact measurement can still clip its own last glyph.
    static let inkSlack: Double = 1

    /// The share of the row the bar keeps when the name is at its cap.
    ///
    /// DERIVED, not picked: the row is three columns and the bar is one of them,
    /// so "the bar is never squeezed below an equal share" is `available / 3`.
    /// The bar is the only column here that carries no text — it cannot
    /// truncate, wrap or ellipsis its way out of being too small, it just stops
    /// being a bar — so it is the one that needs the floor stated as a rule.
    static let barMinimumShare: Double = 1.0 / 3.0

    /// What the row's three columns measure, for a given render.
    struct Layout: Equatable {
        /// Shared by every row on the card so the percentages share a right edge.
        let percentWidth: Double
        /// The ceiling the name column may grow to; it still starts at
        /// ``nameMinimum`` and takes only the ink it needs in between.
        let nameMaximum: Double
    }

    // MARK: - The font the percentage is actually drawn in

    #if canImport(UIKit)
    /// `.font(.caption.weight(.bold).monospacedDigit())` at the call site.
    ///
    /// The trait collection is what makes this the VIEW's text size rather than
    /// the APP's: `UIFont.preferredFont` with no traits resolves against the
    /// process setting, and measuring one while drawing the other is how a
    /// column ends up narrower than the string inside it.
    static func percentFont(at typeSize: DynamicTypeSize) -> UIFont {
        let traits = UITraitCollection(
            preferredContentSizeCategory:
                CalibrationSourceTableGeometry.CellFont.contentSizeCategory(typeSize))
        let base = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: traits)
        return UIFont.monospacedDigitSystemFont(ofSize: base.pointSize, weight: .bold)
    }
    #endif

    /// Per-character fallback for a platform that cannot measure text. Never
    /// used on iOS.
    static let fallbackCharacterWidth: Double = 6.5

    /// The ink one percentage label occupies, in the font it is drawn in.
    static func percentWidth(
        _ label: String, typeSize: DynamicTypeSize = .large
    ) -> Double {
        #if canImport(UIKit)
        return Double((label as NSString)
            .size(withAttributes: [.font: percentFont(at: typeSize)]).width)
        #else
        return Double(label.count) * fallbackCharacterWidth
        #endif
    }

    // MARK: - The decision

    /// The column measurements for one card's worth of rows.
    ///
    /// - `percentLabels` are the strings THIS card will print, already rounded
    ///   and suffixed by `discoverFuturesCardPercentLabel` — passing the printed
    ///   strings rather than the numbers is what stops the model measuring
    ///   `63` while the row draws `63%`.
    /// - `availableWidth` is the row's own content width, published by a
    ///   `GeometryReader` at the call site rather than derived from the screen —
    ///   a card's width is a layout outcome (padding, iPad columns, Stage
    ///   Manager) and a model that recomputed it from a screen size would be
    ///   asserting a layout instead of measuring one.
    static func layout(
        percentLabels: [String],
        availableWidth: Double,
        typeSize: DynamicTypeSize = .large
    ) -> Layout {
        let ink = (percentLabels
            .map { percentWidth($0, typeSize: typeSize) }
            .max() ?? 0) + inkSlack

        // Before the first `GeometryReader` pass the row has no published
        // width. The measured percentage is still the honest answer for that
        // column — it does not depend on the row's width — and the name keeps
        // its floor until there is a width to derive a ceiling from.
        guard availableWidth > 0 else {
            return Layout(percentWidth: ink, nameMaximum: nameMinimum)
        }

        let remaining = availableWidth
            - ink
            - interColumnSpacing * 2
            - availableWidth * barMinimumShare

        return Layout(percentWidth: ink, nameMaximum: max(nameMinimum, remaining))
    }
}
