import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// Shared team-name & record sizing across headlines and compact game cards:
/// 1. Both competitor names in one card always render at the **same** point size
///    (the smaller of the two fitting scales, never independent per-row scaling).
/// 2. A team's record (or secondary subline) is **never** larger than its name
///    (`recordSize <= floor(teamNameSize * 0.80 * 2) / 2`).
nonisolated enum CardTeamNameSizing {

    /// Returns one shared font size so every name in `names` fits on a single line
    /// within `availableWidth` (down to `baseSize * minimumScale`, rounded to 0.5 pt).
    static func sharedSingleLineFontSize(
        names: [String],
        baseSize: CGFloat,
        weight: Font.Weight = .bold,
        availableWidth: CGFloat,
        minimumScale: CGFloat = 0.58
    ) -> CGFloat {
        let clampedBase = max(baseSize, 10)
        let widthBudget = max(availableWidth, 36)
        let floorScale = min(max(minimumScale, 0.35), 1.0)

        var smallestScale: CGFloat = 1.0
        for raw in names {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { continue }
            let measured = singleLineWidth(trimmed, fontSize: clampedBase, weight: weight)
            if measured > widthBudget, measured > 0 {
                let scale = max(floorScale, widthBudget / ceil(measured))
                smallestScale = min(smallestScale, scale)
            }
        }
        return max(floor(clampedBase * floorScale * 2) / 2, floor(clampedBase * smallestScale * 2) / 2)
    }

    /// Returns one shared font size for compact cards where multi-word names may wrap
    /// across at most 2 word-broken lines while single-word names stay on 1 line.
    static func sharedWordSafeFontSize(
        names: [String],
        baseSize: CGFloat,
        weight: Font.Weight = .semibold,
        availableWidth: CGFloat,
        minimumScale: CGFloat = 0.72
    ) -> CGFloat {
        let clampedBase = max(baseSize, 10)
        let widthBudget = max(availableWidth, 36)
        let floorScale = min(max(minimumScale, 0.40), 1.0)

        var smallestScale: CGFloat = 1.0
        for raw in names {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { continue }
            let words = trimmed.split(whereSeparator: \.isWhitespace).map(String.init)
            let widestSpan: CGFloat
            if words.count <= 1 {
                widestSpan = singleLineWidth(trimmed, fontSize: clampedBase, weight: weight)
            } else {
                let maxWord = words.map { singleLineWidth($0, fontSize: clampedBase, weight: weight) }.max() ?? 0
                let fullLine = singleLineWidth(trimmed, fontSize: clampedBase, weight: weight)
                widestSpan = max(maxWord, fullLine * 0.56)
            }
            if widestSpan > widthBudget, widestSpan > 0 {
                let scale = max(floorScale, widthBudget / ceil(widestSpan))
                smallestScale = min(smallestScale, scale)
            }
        }
        return max(floor(clampedBase * floorScale * 2) / 2, floor(clampedBase * smallestScale * 2) / 2)
    }

    /// Guarantees a team's record / subline is strictly smaller than its name.
    static func cappedRecordFontSize(
        baseRecordSize: CGFloat,
        teamNameFontSize: CGFloat
    ) -> CGFloat {
        let maxAllowed = max(8.5, floor(teamNameFontSize * 0.80 * 2) / 2)
        return min(baseRecordSize, maxAllowed)
    }

    private static func singleLineWidth(
        _ text: String,
        fontSize: CGFloat,
        weight: Font.Weight
    ) -> CGFloat {
        #if canImport(UIKit)
        let uiFont = UIFont.systemFont(ofSize: fontSize, weight: uiFontWeight(weight))
        let size = (text as NSString).size(withAttributes: [.font: uiFont])
        return ceil(size.width) + 4
        #else
        return CGFloat(text.count) * fontSize * 0.58
        #endif
    }

    #if canImport(UIKit)
    private static func uiFontWeight(_ weight: Font.Weight) -> UIFont.Weight {
        switch weight {
        case .ultraLight: return .ultraLight
        case .thin: return .thin
        case .light: return .light
        case .regular: return .regular
        case .medium: return .medium
        case .semibold: return .semibold
        case .bold: return .bold
        case .heavy: return .heavy
        case .black: return .black
        default: return .semibold
        }
    }
    #endif
}
