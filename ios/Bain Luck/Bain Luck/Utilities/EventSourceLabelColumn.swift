import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// The label column of the event page's Sources list.
///
/// #4107 — THE COLUMN WAS A HARDCODED 118pt AND HAD NEVER TRACKED DYNAMIC TYPE.
///
/// Alex read `Sportsbooks (…` on the Angels–Red Sox page. The issue blamed the
/// label growing from `Sportsbooks (10)` to `Sportsbooks (14)`, and the comment
/// on the literal said the width had already been raised 90 → 118 for that
/// reason. **Measured, that is not what happened.** At default type size
/// `Sportsbooks (14)` is 99.9pt in a 118pt column — 18pt of headroom — and even
/// a three-digit count (107.6pt) fits. The label never truncated at `.large`.
///
/// What truncates is the same label at a larger text size, and the row's
/// `.minimumScaleFactor(0.85)` sets exactly where: effective capacity was
/// `118 / 0.85 = 138.8pt`, so
///
///   - xxLarge   `Sportsbooks (14)` = 128.2 — fits, by shrinking every label
///   - xxxLarge  = 142.1 — **truncates**, and `Bain Luck Model` (135.3) does not
///   - a11y1     = 169.2 — truncates badly, and now so does `Bain Luck Model`
///
/// which matches the report: one cut label rather than a broken table. So the
/// bug is Dynamic Type, the `Sportsbooks (N)` row is merely the longest string
/// and therefore first over the line, and `Bain Luck Model` is next. A third
/// literal would be correct for exactly one text size, the same way 90 was and
/// 118 was.
///
/// `CalibrationSourceTableGeometry` and `PeriodChipGeometry` are the pattern:
/// measure the strings THIS render will draw, in the font it will draw them in,
/// at the view's own `dynamicTypeSize`. Sized that way the column also gets
/// NARROWER than 118 at default (about 101pt for a real five-source event),
/// which hands the probability bar back ~17pt on every phone.
///
/// **`.minimumScaleFactor` is deliberately not part of this and was removed from
/// the call site.** `CalibrationSourceTableGeometry` already records it measured
/// and rejected on the same row shape: SwiftUI scales sibling `Text` together,
/// so a floor shrinks every label in the list to half-rescue one, still
/// truncates a character later, and reads as a safety net while changing
/// nothing.
///
/// **What this does NOT do.** Ink alone is unbounded — at accessibility sizes
/// `Sportsbooks (100)` wants 183pt, which on a 375pt phone would leave the bar
/// about 20pt and make the row pointless. So the width is clamped against the
/// space the row actually has, and the call site keeps `lineLimit(2)` +
/// `.fixedSize(horizontal: false, vertical: true)` to absorb whatever the clamp
/// cannot give. Both of those are load-bearing together — #3966 found that
/// `lineLimit(2)` alone still truncates when a parent proposes one line's
/// height. Past the clamp, at the largest accessibility sizes, a long label
/// takes two lines; it does not truncate.
enum EventSourceLabelColumn {

    // MARK: - The row's fixed costs

    /// `.padding(.horizontal, 16)`, applied on each side of the row.
    static let horizontalPadding: Double = 16
    /// `HStack(spacing: 6)` — three gaps between the row's four children.
    static let interColumnSpacing: Double = 6
    static let interColumnGapCount: Double = 3
    /// The two trailing probability columns, each `.frame(width: 36)`.
    static let numericColumnWidth: Double = 36
    static let numericColumnCount: Double = 2

    /// Everything in the row that is not the label or the bar.
    ///
    /// A named sum rather than `122` written down, because the whole defect
    /// being fixed here is a layout number that stopped matching the layout it
    /// described. If a padding changes, this follows it.
    static var fixedRowCost: Double {
        horizontalPadding * 2
            + interColumnSpacing * interColumnGapCount
            + numericColumnWidth * numericColumnCount
    }

    /// The floor under the probability bar.
    ///
    /// The bar is the row's entire point — it is the only part a reader compares
    /// across sources — and below roughly this width a two-segment 6pt bar can no
    /// longer show a split anyone can read. The label yields first.
    static let minimumBarWidth: Double = 72

    /// The floor under the label column, so a table of short names
    /// (`Kalshi` is 34.8pt at `.large`) does not collapse into a ragged edge.
    static let minimumLabelWidth: Double = 60

    /// A point of slack over measured ink. `NSString.size` returns a fractional
    /// width and SwiftUI truncates on the fractional overflow, so a column sized
    /// to the exact measurement can still clip its own last glyph.
    static let inkSlack: Double = 1

    // MARK: - The font the label is actually drawn in

    #if canImport(UIKit)
    /// `.font(.caption.weight(.medium))` at the call site. SwiftUI's `.caption`
    /// is `caption1`; measuring the plain face would under-charge the column,
    /// and measuring without the trait collection would resolve against the
    /// APP's text size rather than the view's — the mistake that makes a column
    /// narrower than the string inside it.
    static func labelFont(at typeSize: DynamicTypeSize) -> UIFont {
        let traits = UITraitCollection(
            preferredContentSizeCategory:
                CalibrationSourceTableGeometry.CellFont.contentSizeCategory(typeSize))
        let base = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: traits)
        return UIFont.systemFont(ofSize: base.pointSize, weight: .medium)
    }
    #endif

    /// Per-character fallback for a platform that cannot measure text. Never used
    /// on iOS.
    static let fallbackCharacterWidth: Double = 6.5

    /// The ink a label actually occupies, measured in the font it is drawn in.
    static func textWidth(_ string: String, typeSize: DynamicTypeSize = .large) -> Double {
        #if canImport(UIKit)
        return Double((string as NSString)
            .size(withAttributes: [.font: labelFont(at: typeSize)]).width)
        #else
        return Double(string.count) * fallbackCharacterWidth
        #endif
    }

    // MARK: - The column

    /// The widest the label column may become, given the row it sits in.
    ///
    /// `availableWidth <= 0` means the row has not been measured yet — the first
    /// layout pass, before the `GeometryReader` behind it has reported. Returning
    /// `.infinity` there uses the ink-derived width for that frame rather than
    /// slamming the column to `minimumLabelWidth` and visibly snapping wider a
    /// frame later.
    static func maximumLabelWidth(availableWidth: Double) -> Double {
        guard availableWidth > 0 else { return .infinity }
        return max(minimumLabelWidth, availableWidth - fixedRowCost - minimumBarWidth)
    }

    /// The label column for THIS render: the widest label it will draw, at the
    /// view's own text size, clamped to what the row can spare.
    static func width(
        for labels: [String], availableWidth: Double, typeSize: DynamicTypeSize = .large
    ) -> Double {
        let ink = labels.map { textWidth($0, typeSize: typeSize) }.max() ?? 0
        let wanted = ink.rounded(.up) + inkSlack
        return min(
            max(wanted, minimumLabelWidth),
            maximumLabelWidth(availableWidth: availableWidth))
    }
}
