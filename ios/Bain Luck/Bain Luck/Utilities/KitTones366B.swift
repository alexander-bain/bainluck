import SwiftUI

/// Ruling 366: B / #13551 — Light and Dark semantic tokens for Kit v1 cards and marks.
///
/// Reuses `DS`, `HeadlineStyleTable199`, `TeamTextContrast`, and `ProbabilityBarPalette` so
/// Light/Dark contrast floors match existing native Discover cards.
enum KitTones366B {

    // MARK: - Surfaces & Chrome

    static func cardBackground(for scheme: ColorScheme) -> Color {
        scheme == .dark ? Color.cardBackground : DS.cardBg
    }

    static func elevatedBackground(for scheme: ColorScheme) -> Color {
        scheme == .dark ? Color.cardBackgroundDark : DS.surface
    }

    static func cardBorder(for scheme: ColorScheme) -> Color {
        scheme == .dark ? HeadlineStyleTable199.cardBorderInk : DS.border
    }

    static func divider(for scheme: ColorScheme) -> Color {
        scheme == .dark ? Color.white.opacity(0.09) : DS.border.opacity(0.75)
    }

    static func trackBackground(for scheme: ColorScheme) -> Color {
        scheme == .dark ? Color.white.opacity(0.11) : DS.trackBg
    }

    static func brandAccent(for scheme: ColorScheme) -> Color {
        scheme == .dark ? DS.emerald : DS.greenReadable
    }

    // MARK: - Text Tones

    static func textColor(for tone: KitV1Tone?, scheme: ColorScheme) -> Color {
        switch tone ?? .primary {
        case .primary:
            return scheme == .dark ? DS.textPrimary : DS.textPrimary
        case .secondary:
            return DS.textSecondaryReadable
        case .muted:
            return DS.textMuted
        case .accent:
            return brandAccent(for: scheme)
        case .warn:
            return DS.amber
        }
    }

    // MARK: - Palette c2..c6 (contrast-checked fallbacks for multi-series marks)

    private static let fallbackHexLight: [String] = [
        "#047857", // accent
        "#005CC2", // c2 blue
        "#7C3AED", // c3 purple
        "#D97706", // c4 amber
        "#0891B2", // c5 cyan
        "#DC2626", // c6 red
    ]

    private static let fallbackHexDark: [String] = [
        "#34D399", // accent
        "#60A5FA", // c2 blue
        "#A78BFA", // c3 purple
        "#FBBF24", // c4 amber
        "#22D3EE", // c5 cyan
        "#F87171", // c6 red
    ]

    static func seriesHex(at index: Int, scheme: ColorScheme) -> String {
        let palette = scheme == .dark ? fallbackHexDark : fallbackHexLight
        return palette[abs(index) % palette.count]
    }

    /// Resolves a bar or series color for Light or Dark mode:
    /// - Uses `darkHex` verbatim on Dark mode when present and readable.
    /// - Lightens dark raw team colors on Dark mode via `TeamTextContrast.lightenedForDarkSurface`
    ///   so dark navy/purple hexes (`#0a2240`, `#29127a`, `#1d428a`) stay distinct on dark cards.
    static func barColor(
        hex: String?,
        darkHex: String? = nil,
        fallbackIndex: Int = 0,
        scheme: ColorScheme
    ) -> Color {
        Color(hex: barHex(hex: hex, darkHex: darkHex, fallbackIndex: fallbackIndex, scheme: scheme))
    }

    static func barHex(
        hex: String?,
        darkHex: String? = nil,
        fallbackIndex: Int = 0,
        scheme: ColorScheme
    ) -> String {
        if scheme == .dark {
            if let explicitDark = darkHex,
               TeamTextContrast.readableOnSurface(explicitDark, surfaceLuminance: TeamTextContrast.darkSurfaceLuminance) {
                return TeamTextContrast.canonicalHex(explicitDark) ?? explicitDark
            }
            if let lightHex = hex,
               let adapted = TeamTextContrast.usableOnDarkSurface(
                   primaryHex: lightHex,
                   surfaceLuminance: TeamTextContrast.darkSurfaceLuminance
               ) {
                return adapted
            }
            return seriesHex(at: fallbackIndex, scheme: .dark)
        }
        if let raw = hex, let canonical = TeamTextContrast.canonicalHex(raw) {
            return canonical
        }
        return seriesHex(at: fallbackIndex, scheme: .light)
    }

    /// Resolves a paired two-segment split bar using the repo's hue-separation & contrast rules.
    static func splitBarColors(
        leftHex: String?,
        leftDarkHex: String?,
        rightHex: String?,
        rightDarkHex: String?,
        scheme: ColorScheme
    ) -> (left: Color, right: Color) {
        if scheme == .dark && (leftDarkHex != nil || rightDarkHex != nil) {
            let l = barColor(hex: leftHex, darkHex: leftDarkHex, fallbackIndex: 0, scheme: .dark)
            let r = barColor(hex: rightHex, darkHex: rightDarkHex, fallbackIndex: 1, scheme: .dark)
            return (l, r)
        }
        if let leftHex, let rightHex {
            let pair = TeamTextContrast.surfaceColors(
                awayHex: leftHex,
                homeHex: rightHex,
                colorScheme: scheme
            )
            return (left: pair.away, right: pair.home)
        }
        return (
            barColor(hex: leftHex, darkHex: leftDarkHex, fallbackIndex: 0, scheme: scheme),
            barColor(hex: rightHex, darkHex: rightDarkHex, fallbackIndex: 1, scheme: scheme)
        )
    }

    // MARK: - Tile Tones

    struct TilePalette {
        let background: Color
        let border: Color
        let foreground: Color
        let secondaryForeground: Color
    }

    static func tilePalette(
        shade: Double,
        highlightRole: KitV1TileMark.HighlightRole?,
        muted: Bool,
        scheme: ColorScheme
    ) -> TilePalette {
        if muted {
            return TilePalette(
                background: elevatedBackground(for: scheme),
                border: cardBorder(for: scheme),
                foreground: DS.textMuted,
                secondaryForeground: DS.textMuted
            )
        }
        let accent = brandAccent(for: scheme)
        if highlightRole == .dayPeak || shade >= 0.6 {
            return TilePalette(
                background: accent,
                border: accent,
                foreground: scheme == .dark ? Color.black.opacity(0.92) : .white,
                secondaryForeground: scheme == .dark ? Color.black.opacity(0.75) : .white.opacity(0.9)
            )
        }
        if shade >= 0.3 {
            return TilePalette(
                background: accent.opacity(scheme == .dark ? 0.24 : 0.18),
                border: accent.opacity(0.45),
                foreground: textColor(for: .primary, scheme: scheme),
                secondaryForeground: textColor(for: .secondary, scheme: scheme)
            )
        }
        if shade >= 0.12 {
            return TilePalette(
                background: accent.opacity(scheme == .dark ? 0.14 : 0.10),
                border: accent.opacity(0.30),
                foreground: textColor(for: .primary, scheme: scheme),
                secondaryForeground: textColor(for: .secondary, scheme: scheme)
            )
        }
        return TilePalette(
            background: elevatedBackground(for: scheme),
            border: cardBorder(for: scheme),
            foreground: textColor(for: .secondary, scheme: scheme),
            secondaryForeground: textColor(for: .muted, scheme: scheme)
        )
    }
}
