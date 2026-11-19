import SwiftUI
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

/// #12822 — Measured, zero-truncation column geometry for unified game headlines.
///
/// Rules (Fable, Mon Nov 16):
/// 1. Before kickoff (`phase == .before`), `Chance` prints whole percents (`58%`,
///    `100%`, `<1%`, `>99%`) on every surface; during play (`phase == .during`),
///    `Now` keeps its tenths (`76.5%`, `99.9%`, `<1%`, `>99%`).
/// 2. No headline number or column header ever truncates with `"…"`. Every cell
///    measures the longest value its column can print (plus the actual values on
///    the card) at the active scaled font size, stacks competitor names above the
///    number strip whenever the container is too narrow for one row, and shrinks
///    cleanly when even the stacked strip exceeds a narrow accessibility viewport.
nonisolated enum HeadlineCellFit12822 {

    struct ResolvedLayout: Equatable, Sendable {
        let stacksRowsVertically: Bool
        let columnWidths: [CGFloat]
        let columnSpacing: CGFloat
        let extraLeadingGaps: [CGFloat]
        let fontScale: CGFloat

        var totalColumnsWidth: CGFloat {
            let sum = columnWidths.reduce(0, +)
            let activeCount = columnWidths.filter { $0 > 0 }.count
            let gaps = CGFloat(max(activeCount - 1, 0)) * columnSpacing
            let extra = extraLeadingGaps.reduce(0, +)
            return sum + gaps + extra
        }
    }

    /// Longest possible formatted strings each headline column role can carry.
    static func longestTemplates(
        for role: EventSportHeadlines12472.ColumnRole,
        isManyColumnScoreboard: Bool,
        hasSuperscript: Bool
    ) -> [String] {
        switch role {
        case .setScore:
            return hasSuperscript ? ["7"] : ["7", "10"]
        case .gamePoints:
            return ["AD", "99"]
        case .score:
            return ["999"]
        case .projected:
            return ["999"]
        case .pregame:
            return ["100%", ">99%"]
        case .finalResult:
            return isManyColumnScoreboard ? ["99"] : ["999"]
        case .chance:
            return ["100%", ">99%"]
        case .now:
            return ["99.9%", ">99%"]
        }
    }

    static func resolve(
        model: EventSportHeadlines12472.Model,
        innerWidth: CGFloat,
        crestSize: CGFloat,
        isAccessibilitySize: Bool,
        nameFontSize: CGFloat = 15.5,
        nowFontSize: CGFloat,
        secondProminentFontSize: CGFloat,
        secondRegularFontSize: CGFloat,
        headerFontSize: CGFloat
    ) -> ResolvedLayout {
        let cols = model.columns
        guard !cols.isEmpty else {
            return ResolvedLayout(
                stacksRowsVertically: isAccessibilitySize,
                columnWidths: [],
                columnSpacing: 6,
                extraLeadingGaps: [],
                fontScale: 1.0
            )
        }

        let cappedNow = min(nowFontSize, 32)
        let cappedProminent = min(secondProminentFontSize, 28)
        let cappedRegular = min(secondRegularFontSize, 22)
        let cappedHeader = min(headerFontSize, 15)
        let manyCols = cols.count >= 5

        let isActiveCol: [Bool] = cols.enumerated().map { idx, col in
            !col.header.isEmpty || model.rows.contains { row in
                let hasText = idx < row.cells.count && !row.cells[idx].isEmpty
                let hasWinnerTick = col.role == .finalResult && row.won == true
                return hasText || hasWinnerTick
            }
        }
        let activeColCount = isActiveCol.filter { $0 }.count
        let firstActiveIdx = isActiveCol.firstIndex(of: true)

        let naturalSpacing: CGFloat = manyCols ? 4 : 6
        let naturalExtraGaps: [CGFloat] = cols.indices.map { idx in
            guard isActiveCol[idx], let firstActiveIdx, idx > firstActiveIdx, !manyCols else { return 0 }
            return cols[idx].role == .now ? 8 : 0
        }

        let naturalWidths: [CGFloat] = cols.enumerated().map { idx, col in
            guard isActiveCol[idx] else { return 0 }
            let hasSup = model.rows.contains { row in
                guard let s = row.cellSuperscripts[idx] else { return false }
                return !s.isEmpty
            }

            // 1. Header width (when non-empty)
            let headerW: CGFloat = col.header.isEmpty
                ? 0
                : measureWidth(col.header, fontSize: cappedHeader, weight: .bold, rounded: false, monospacedDigits: true)

            // 2. Actual cells + worst-case role templates
            var candidates = longestTemplates(
                for: col.role,
                isManyColumnScoreboard: manyCols,
                hasSuperscript: hasSup
            )
            for row in model.rows where idx < row.cells.count {
                let text = row.cells[idx]
                if !text.isEmpty {
                    candidates.append(text)
                }
            }

            let contentW: CGFloat = {
                switch col.role {
                case .now, .chance:
                    let maxCell = candidates.map {
                        measureWidth($0, fontSize: cappedNow, weight: .black, rounded: true, monospacedDigits: true)
                    }.max() ?? 0
                    return maxCell

                case .score, .projected, .pregame:
                    let maxCell = candidates.map {
                        measureWidth($0, fontSize: cappedRegular, weight: .semibold, rounded: true, monospacedDigits: true)
                    }.max() ?? 0
                    return maxCell

                case .setScore:
                    let setSize = cappedProminent * 0.84
                    let maxBase = candidates.map {
                        measureWidth($0, fontSize: max(setSize, cappedRegular), weight: .heavy, rounded: true, monospacedDigits: true)
                    }.max() ?? 0
                    if hasSup {
                        let supCandidates: [String] = ["99"] + model.rows.compactMap { $0.cellSuperscripts[idx] }
                        let maxSup = supCandidates.map {
                            measureWidth($0, fontSize: cappedHeader * 0.90, weight: .bold, rounded: false, monospacedDigits: true)
                        }.max() ?? 0
                        return maxBase + 1 + maxSup
                    }
                    return maxBase

                case .gamePoints:
                    let gpSize = cappedRegular * 0.85
                    let maxCell = candidates.map {
                        measureWidth($0, fontSize: gpSize, weight: .semibold, rounded: true, monospacedDigits: true) + 10
                    }.max() ?? 0
                    return maxCell

                case .finalResult:
                    let maxCell = candidates.map {
                        measureWidth($0, fontSize: cappedProminent, weight: .heavy, rounded: true, monospacedDigits: true)
                    }.max() ?? 0
                    return maxCell
                }
            }()

            return ceil(max(headerW, contentW))
        }

        let naturalSum = naturalWidths.reduce(0, +)
        let naturalGaps = CGFloat(max(activeColCount - 1, 0)) * naturalSpacing + naturalExtraGaps.reduce(0, +)
        let naturalTotal = naturalSum + naturalGaps

        let usableWidth = max(innerWidth, 160)
        // Require every competitor short name to fit whole on one line above its 0.80 minimumScaleFactor
        // alongside the crest (6pt gap), optional winner tick after name, Spacer(minLength: 4), and measured columns.
        let minReadableNamePt = max(16, min(nameFontSize, 20) * 0.82)
        let widestNameAtReadable = model.rows
            .map { measureWidth($0.shortName, fontSize: minReadableNamePt, weight: .bold, rounded: false, monospacedDigits: false) }
            .max() ?? 68
        let nameTickReserve: CGFloat = model.rows.contains(where: { $0.won == true })
            ? (4 + measureWidth("\u{2713}", fontSize: min(nameFontSize, 20) * 0.85, weight: .heavy, rounded: true, monospacedDigits: false))
            : 0
        let minIdentityReservation: CGFloat = crestSize + 16 + max(widestNameAtReadable + nameTickReserve, 64)
        let stacksVertically = isAccessibilitySize || (minIdentityReservation + naturalTotal > usableWidth)

        let columnRowBudget: CGFloat = stacksVertically
            ? usableWidth
            : max(usableWidth - minIdentityReservation, 100)

        if naturalTotal <= columnRowBudget {
            return ResolvedLayout(
                stacksRowsVertically: stacksVertically,
                columnWidths: naturalWidths,
                columnSpacing: naturalSpacing,
                extraLeadingGaps: naturalExtraGaps,
                fontScale: 1.0
            )
        }

        // First compress inter-column gaps before scaling font/column widths.
        let tightSpacing: CGFloat = activeColCount > 1 ? 3 : 0
        let tightExtraGaps: [CGFloat] = cols.indices.map { idx in
            guard isActiveCol[idx], let firstActiveIdx, idx > firstActiveIdx, !manyCols else { return 0 }
            return cols[idx].role == .now ? 3 : 0
        }
        let tightGapsTotal = CGFloat(max(activeColCount - 1, 0)) * tightSpacing + tightExtraGaps.reduce(0, +)
        if naturalSum + tightGapsTotal <= columnRowBudget {
            return ResolvedLayout(
                stacksRowsVertically: stacksVertically,
                columnWidths: naturalWidths,
                columnSpacing: tightSpacing,
                extraLeadingGaps: tightExtraGaps,
                fontScale: 1.0
            )
        }

        // Proportionally compress column widths and font scale so every cell shrinks cleanly without ellipsis.
        let availableForCells = max(columnRowBudget - tightGapsTotal, CGFloat(max(activeColCount, 1)) * 18)
        let ratio = min(1.0, max(0.38, availableForCells / max(naturalSum, 1)))
        let scaledWidths = naturalWidths.map { floor($0 * ratio * 2) / 2 }
        return ResolvedLayout(
            stacksRowsVertically: stacksVertically,
            columnWidths: scaledWidths,
            columnSpacing: tightSpacing,
            extraLeadingGaps: tightExtraGaps,
            fontScale: ratio
        )
    }

    static func measureWidth(
        _ text: String,
        fontSize: CGFloat,
        weight: Font.Weight,
        rounded: Bool,
        monospacedDigits: Bool
    ) -> CGFloat {
        guard !text.isEmpty else { return 0 }
        #if canImport(UIKit)
        let uiWeight = uiFontWeight(weight)
        let baseFont: UIFont = {
            if monospacedDigits {
                let mono = UIFont.monospacedDigitSystemFont(ofSize: fontSize, weight: uiWeight)
                if rounded, let desc = mono.fontDescriptor.withDesign(.rounded) {
                    return UIFont(descriptor: desc, size: fontSize)
                }
                return mono
            } else {
                let sys = UIFont.systemFont(ofSize: fontSize, weight: uiWeight)
                if rounded, let desc = sys.fontDescriptor.withDesign(.rounded) {
                    return UIFont(descriptor: desc, size: fontSize)
                }
                return sys
            }
        }()
        let measured = (text as NSString).size(withAttributes: [.font: baseFont]).width
        // +5 pt safety headroom for SwiftUI rounded-glyph side bearings so Text never triggers tail ellipsis.
        return ceil(measured) + 5
        #elseif canImport(AppKit)
        let nsWeight = nsFontWeight(weight)
        let baseFont = monospacedDigits
            ? NSFont.monospacedDigitSystemFont(ofSize: fontSize, weight: nsWeight)
            : NSFont.systemFont(ofSize: fontSize, weight: nsWeight)
        let measured = (text as NSString).size(withAttributes: [.font: baseFont]).width
        return ceil(measured) + 5
        #else
        return ceil(CGFloat(text.count) * fontSize * 0.66) + 5
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
    #elseif canImport(AppKit)
    private static func nsFontWeight(_ weight: Font.Weight) -> NSFont.Weight {
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
