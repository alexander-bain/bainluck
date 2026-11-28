import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// 466: A (`PILLAR: FORMATTING`):
/// Computes width-safe, dynamically scaled font sizes, column widths, and stacked-vs-inline row
/// decisions for `EventCardView` when `dynamicTypeSize.isAccessibilitySize == true`.
///
/// At ordinary text sizes (`isAccessibilitySize == false`), `EventCardView` does not consult this
/// helper and remains 100% unchanged.
nonisolated struct GameCardAXLayout466A: Equatable, Sendable {
    let nameFontSize: CGFloat
    let scoreFontSize: CGFloat
    let nowFontSize: CGFloat
    let headerFontSize: CGFloat
    let pregameFontSize: CGFloat
    let mediumColWidth: CGFloat
    let projectedColWidth: CGFloat
    let largeColWidth: CGFloat
    let mediumToProjectedGap: CGFloat
    let largeLeadingGap: CGFloat
    let totalClusterWidth: CGFloat
    let usesStackedRow: Bool

    static func resolve(
        cardWidth: CGFloat,
        awayName: String,
        homeName: String,
        scaledNameSize: CGFloat,
        scaledScoreSize: CGFloat,
        scaledNowSize: CGFloat,
        scaledHeaderSize: CGFloat,
        scaledPregameSize: CGFloat,
        hasMedium: Bool,
        hasLiveProjected: Bool,
        hasLarge: Bool,
        isFinished: Bool,
        hasDrawRow: Bool,
        mediumHeaderText: String,
        projectedHeaderText: String,
        largeHeaderText: String,
        mediumSamples: [String],
        projectedSamples: [String],
        largeSamples: [String]
    ) -> GameCardAXLayout466A {
        // Conservative initial budget before SwiftUI's GeometryReader reports exact card width
        // (~232 pt matches the narrowest 320 pt insetGrouped List + disclosure chevron).
        let safeCardWidth = max(cardWidth > 0 ? cardWidth : 232, 140)

        let targetNow = max(scaledNowSize, HeadlineStyleTable199.nowBaseSize(.card))
        let targetScore = min(max(scaledScoreSize, HeadlineStyleTable199.secondNumberBaseSize(.card)), targetNow * 0.90)
        let targetPregame = min(max(scaledPregameSize, HeadlineStyleTable199.pregameNumberBaseSize(.card)), targetScore)
        let targetHeader = min(max(scaledHeaderSize, HeadlineStyleTable199.headerBaseSize(.card)), targetScore * 0.60)
        let targetNameBase = min(max(scaledNameSize, HeadlineStyleTable199.nameBaseSize(.card)), targetNow * 0.85)

        let rawMedW: CGFloat = hasMedium ? columnWidth(
            header: mediumHeaderText,
            headerFontSize: targetHeader,
            samples: mediumSamples,
            valueFontSize: targetScore,
            valueWeight: .semibold
        ) : 0
        let rawProjW: CGFloat = hasLiveProjected ? columnWidth(
            header: projectedHeaderText,
            headerFontSize: targetHeader,
            samples: projectedSamples,
            valueFontSize: targetScore,
            valueWeight: .semibold
        ) : 0
        let rawLargeW: CGFloat = hasLarge ? columnWidth(
            header: largeHeaderText,
            headerFontSize: targetHeader,
            samples: largeSamples,
            valueFontSize: targetNow,
            valueWeight: .heavy
        ) : 0

        let rawMedToProjGap: CGFloat = (hasMedium && hasLiveProjected) ? 10 : 0
        let rawLargeGap: CGFloat = (hasLarge && (hasMedium || hasLiveProjected)) ? 12 : 0
        let rawClusterW = rawMedW + rawMedToProjGap + rawProjW + rawLargeGap + rawLargeW

        let clusterScale: CGFloat
        if rawClusterW > safeCardWidth, rawClusterW > 0 {
            clusterScale = max(0.45, (safeCardWidth - 4) / rawClusterW)
        } else {
            clusterScale = 1.0
        }

        let nowFontSize = floor(targetNow * clusterScale * 2) / 2
        let scoreFontSize = floor(targetScore * clusterScale * 2) / 2
        let pregameFontSize = floor(targetPregame * clusterScale * 2) / 2
        let headerFontSize = floor(targetHeader * clusterScale * 2) / 2

        let mediumToProjectedGap = floor(rawMedToProjGap * clusterScale)
        let largeLeadingGap = floor(rawLargeGap * clusterScale)
        let mediumColWidth = hasMedium ? ceil(rawMedW * clusterScale) : 0
        let projectedColWidth = hasLiveProjected ? ceil(rawProjW * clusterScale) : 0
        let largeColWidth = hasLarge ? ceil(rawLargeW * clusterScale) : 0
        let totalClusterWidth = mediumColWidth
            + (hasLiveProjected ? mediumToProjectedGap + projectedColWidth : 0)
            + (hasLarge ? largeLeadingGap + largeColWidth : 0)

        let row1ChromeWidth: CGFloat = 28 + 6 + (isFinished ? 20 : 0)
        let stackedNameBudget = max(safeCardWidth - row1ChromeWidth, 80)
        let stackedNameSize = CardTeamNameSizing.sharedUnboundedWordSafeFontSize(
            names: hasDrawRow ? [awayName, homeName, "Draw"] : [awayName, homeName],
            baseSize: targetNameBase,
            weight: .bold,
            availableWidth: stackedNameBudget,
            minimumScale: 0.48
        )

        let inlineAvailableNameW = safeCardWidth - row1ChromeWidth - 10 - totalClusterWidth
        let inlineFitName = min(targetNameBase, stackedNameSize)
        let widestSingleLineName = [awayName, homeName]
            .map { measureSingleLine($0, fontSize: inlineFitName, weight: .bold, rounded: false) }
            .max() ?? 0
        let fitsInline = inlineAvailableNameW > 40 && widestSingleLineName <= inlineAvailableNameW

        return GameCardAXLayout466A(
            nameFontSize: stackedNameSize,
            scoreFontSize: scoreFontSize,
            nowFontSize: nowFontSize,
            headerFontSize: headerFontSize,
            pregameFontSize: pregameFontSize,
            mediumColWidth: mediumColWidth,
            projectedColWidth: projectedColWidth,
            largeColWidth: largeColWidth,
            mediumToProjectedGap: mediumToProjectedGap,
            largeLeadingGap: largeLeadingGap,
            totalClusterWidth: totalClusterWidth,
            usesStackedRow: !fitsInline
        )
    }

    private static func columnWidth(
        header: String,
        headerFontSize: CGFloat,
        samples: [String],
        valueFontSize: CGFloat,
        valueWeight: Font.Weight
    ) -> CGFloat {
        let hW = header.isEmpty ? 0 : measureSingleLine(header, fontSize: headerFontSize, weight: .semibold, rounded: false)
        let vW = (samples
            .filter { !$0.isEmpty }
            .map { measureSingleLine($0, fontSize: valueFontSize, weight: valueWeight, rounded: true) }
            .max() ?? 0) * 1.06
        return ceil(max(hW, vW)) + 8
    }

    private static func measureSingleLine(
        _ text: String,
        fontSize: CGFloat,
        weight: Font.Weight,
        rounded: Bool
    ) -> CGFloat {
        guard !text.isEmpty else { return 0 }
        #if canImport(UIKit)
        let baseFont = UIFont.systemFont(ofSize: max(fontSize, 8), weight: uiFontWeight(weight))
        let resolvedFont: UIFont
        if rounded, let desc = baseFont.fontDescriptor.withDesign(.rounded) {
            resolvedFont = UIFont(descriptor: desc, size: baseFont.pointSize)
        } else {
            resolvedFont = baseFont
        }
        let size = (text as NSString).size(withAttributes: [.font: resolvedFont])
        return ceil(size.width) + 2
        #else
        return CGFloat(text.count) * max(fontSize, 8) * (rounded ? 0.64 : 0.58) + 2
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
