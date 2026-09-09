import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// Column widths for the Evolution chart's leaderboard grid.
///
/// 🔴 #4373 — THE `Prob` COLUMN WAS A 50pt CELL HOLDING A 24pt BAR AND A NUMBER,
/// SO EVERY ROW WRAPPED ITS PERCENT SIGN ONTO A SECOND LINE. Photographed on
/// master at both phone widths (`artifacts-native-082/BEFORE-4199-p402b.png`,
/// `AFTER-4199-se375b.png`):
///
///     1  Los Angeles Rams   ▮      14      -
///                                   %
///     2  Buffalo Bills      ▮       8      -
///                                   %
///
/// The cell was pinned at 50pt; the mini bar took 24 and the spacing 4, leaving
/// **22pt** for the text. Measured here on the simulator at `.large`, `100%` in
/// the face it is drawn in (`.subheadline`, semibold, monospaced digits) is
/// **43.5pt** of ink and `0.5%` is 38.6pt. A `Text` with no `lineLimit` given half
/// the width it needs does not truncate, it wraps — and squeezed far enough it
/// wraps a character at a time. This is the number the whole chart exists to show.
///
/// ═══ THE ALLOCATION, MADE ON INK ═══
///
/// #4373 asks for a decision rather than a nudge, because widening `Prob` takes
/// width directly from the participant name, which already truncates. Measured, it
/// turns out not to be a trade at all:
///
/// | at `.large`                    | today | measured |
/// |--------------------------------|-------|----------|
/// | `Prob` (bar + number)          | 50    | **49.5** (number alone, `100%` + gutter) |
/// | `24h`  (`-`, `+1.5%`)          | 50    | **~44**  (sized to the strings this render draws) |
///
/// **The 24pt mini bar was the entire defect and it is gone.** It was the cheapest
/// 24pt on the row: 24pt at full scale, so `14%` drew 3.4pt of colour, and its
/// colour is the series colour already carried by the dot at the head of the same
/// row. Removing it fits `100%` in full inside a cell NARROWER than the one that
/// could not fit `14%`, and on the board a reader actually meets the name comes out
/// AHEAD — which is why this needed measuring before it could be called a
/// trade-off.
///
/// ⚠️ One board does cost the name width: a leaderboard carrying both a settled
/// `100%` and a `-100.0%` collapse needs 109.6pt against the old 100, about half a
/// character. Bounded by `testTheExtremeBoardCostsTheNameUnderTenPoints` rather
/// than bought back by re-rounding `-100.0%` to `-100%`, because a wrap fix that
/// quietly changes a published number is two changes wearing one issue.
///
/// A real ladder — the bar behind the name, as other surfaces draw it — is the
/// option not taken. It is a better chart and a different row: it changes the
/// grammar of a card family that notice 35 says is shared, so it belongs to that
/// work and not to a wrap fix.
///
/// ═══ WHY THE COLUMNS ARE MEASURED AND NOT SET ═══
///
/// `CalibrationSourceTableGeometry` is the pattern and #3954 is the reason: a
/// hand-picked point count is a bound wearing a measurement's clothes, and it does
/// not track Dynamic Type, so every step above `.large` re-breaks the thing it was
/// chosen to protect. Sized against the strings THIS render will draw, a
/// leaderboard of `-` and `+1.5%` gives its spare width back to the names, and a
/// leaderboard holding `-100.0%` takes what it needs.
///
/// ⚠️ **AND THE COLUMNS GROW FASTER THAN THE ROW DOES.** Measured on worst-case
/// strings, the pair costs 109.6pt at `.large`, 148.9 at `.xxxLarge`, 175.5 at
/// `.accessibility1` and **329.8 at `.accessibility5`** — wider than an iPhone SE.
/// Above `.xxxLarge` there is no arrangement in which a name, a probability and a
/// 24-hour delta all fit on one 375pt row, so `24h` is dropped at accessibility
/// sizes and `Prob` keeps the space: at `.accessibility1` that is 76.1pt against
/// today's fixed 100, so the name is BETTER off than it is now at every
/// accessibility size but the last.
///
/// The delta is dropped from the DRAWING only. `EvolutionLeaderboardRow` states
/// the full row — rank, name, probability, 24-hour change — in one
/// `accessibilityLabel`, so the reader most likely to be at those sizes is the one
/// reader who never loses the number.
///
/// **What this does NOT fix, stated rather than hidden:** at `.accessibility5` the
/// `Prob` column alone is 142.3pt and the name is down to roughly three characters
/// on a 375pt phone. It was four before this change. That row needs to reflow —
/// the numbers under the name, not beside it — which is the same class as #4395
/// and is filed there, not bodged here with a `minimumScaleFactor` that would
/// shrink six names to half-rescue a seventh (#3954 measured that one and removed
/// it).
enum EvolutionLeaderboardGeometry {

    /// Kept between one column's ink and whatever is to its left, so trailing-aligned
    /// numbers never touch the value beside them.
    static let columnGutter: Double = 6

    /// The fixed pair this replaces: `Prob` and `24h` were both `.frame(width: 50)`.
    ///
    /// Here so the non-regression guard can be written as "the measured pair is no
    /// wider than the pair it replaces" instead of against a literal `100` that
    /// would keep passing after the view stopped drawing it.
    static let legacyColumnWidth: Double = 50
    static let legacyPairWidth: Double = legacyColumnWidth * 2

    // MARK: - The strings the row draws

    /// Both formatters live next to the measurement, and the view calls THESE.
    ///
    /// A column sized against `14%` while the row draws `14.0%` is the wrap all
    /// over again, one release later and harder to see; the only way that cannot
    /// happen is for the measured string and the drawn string to be the same call.
    static func probLabel(_ pct: Double) -> String {
        pct < 1 && pct > 0 ? String(format: "%.1f%%", pct) : "\(Int(pct.rounded()))%"
    }

    static func changeLabel(_ pct: Double) -> String {
        if pct > 0 { return "+\(String(format: "%.1f", pct))%" }
        if pct < 0 { return "\(String(format: "%.1f", pct))%" }
        return "-"
    }

    /// Spoken form of the same delta. `-` is a dash on screen and nothing at all in
    /// a sentence.
    static func spokenChange(_ pct: Double) -> String {
        pct == 0 ? "unchanged over 24 hours"
                 : "\(String(format: "%+.1f", pct))% over 24 hours"
    }

    // MARK: - Fonts

    /// Which face a cell is drawn in. A column must clear its HEADER as well as its
    /// values: `Prob` at `.caption2` is 24.5pt, wider than `8%`.
    enum CellFont {
        case header
        case probValue
        case changeValue

        #if canImport(UIKit)
        func uiFont(at typeSize: DynamicTypeSize) -> UIFont {
            let traits = UITraitCollection(
                preferredContentSizeCategory:
                    CalibrationSourceTableGeometry.CellFont.contentSizeCategory(typeSize))
            switch self {
            case .header:
                return UIFont.preferredFont(forTextStyle: .caption2, compatibleWith: traits)
            case .probValue:
                let base = UIFont.preferredFont(forTextStyle: .subheadline, compatibleWith: traits)
                return UIFont.monospacedDigitSystemFont(ofSize: base.pointSize, weight: .semibold)
            case .changeValue:
                let base = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: traits)
                return UIFont.monospacedDigitSystemFont(ofSize: base.pointSize, weight: .medium)
            }
        }
        #endif

        /// Per-character fallback for a platform that cannot measure text. Never used
        /// on iOS; see `textWidth`.
        var fallbackCharacterWidth: Double {
            switch self {
            case .header: return 6.5
            case .probValue: return 9.0
            case .changeValue: return 7.5
            }
        }
    }

    /// The ink a string actually occupies, MEASURED in the font it is drawn in.
    ///
    /// The size is threaded through rather than read from the process: SwiftUI
    /// resolves `.subheadline` against the view's `dynamicTypeSize`, and
    /// `UIFont.preferredFont` with no traits resolves against the app's. Measuring
    /// one while drawing the other is how a column ends up narrower than the number
    /// inside it (`HostedMeasurement` carries the full story).
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
        header: String, values: [String], font: CellFont,
        typeSize: DynamicTypeSize = .large
    ) -> Double {
        let headerInk = textWidth(header, font: .header, typeSize: typeSize)
        let valueInk = values.map { textWidth($0, font: font, typeSize: typeSize) }.max() ?? 0
        return max(headerInk, valueInk) + columnGutter
    }

    // MARK: - The two columns

    struct Columns: Equatable {
        let prob: Double
        /// `nil` when the column is not drawn at all — see `isAccessibilitySize`
        /// above. A width of zero would still cost the row its spacing.
        let change: Double?

        var drawsChange: Bool { change != nil }
        var total: Double { prob + (change ?? 0) }
    }

    /// Both columns, sized against the strings this render will draw.
    static func columns(
        probs: [String], changes: [String], typeSize: DynamicTypeSize = .large
    ) -> Columns {
        Columns(
            prob: columnWidth(
                header: "Prob", values: probs, font: .probValue, typeSize: typeSize),
            change: typeSize.isAccessibilitySize
                ? nil
                : columnWidth(
                    header: "24h", values: changes, font: .changeValue, typeSize: typeSize))
    }

    /// The same thing from the model the view holds, so the header, the rows and
    /// the suite all size against one list of outcomes.
    static func columns(
        for outcomes: [TimelineOutcomeMeta], at typeSize: DynamicTypeSize = .large
    ) -> Columns {
        columns(
            probs: outcomes.map { probLabel(($0.currentProbability ?? 0) * 100) },
            changes: outcomes.map { changeLabel(($0.probabilityChange24h ?? 0) * 100) },
            typeSize: typeSize)
    }
}
