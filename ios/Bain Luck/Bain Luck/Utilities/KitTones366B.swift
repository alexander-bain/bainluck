import SwiftUI

/// Ruling 366: B / #13551 — Light and Dark semantic tokens for Kit v1 cards and marks.
///
/// Reuses `DS`, `HeadlineStyleTable199`, `TeamTextContrast`, and `ProbabilityBarPalette` so
/// Light/Dark contrast floors match existing native Discover cards.
enum KitTones366B {

    // MARK: - Contrast Floor Constants (WCAG AA: 4.5:1 text, 3.0:1 marks/bars)

    /// Exact card, elevated, and bar-track sRGB hexes used for WCAG 2.1 verification in Light & Dark.
    static let lightCardHex = "#FFFFFF"
    static let lightElevatedHex = "#F5F5F7"
    static let lightTrackHex = "#F3F4F6"
    static let darkCardHex = "#1C1C1E"
    static let darkElevatedHex = "#2C2C2E"
    /// `Color.white.opacity(0.11)` over `#1C1C1E`.
    static let darkTrackHex = "#353537"

    static let lightMutedHex = "#59606D"     // 6.33:1 on #FFFFFF, 5.81:1 on #F5F5F7
    static let darkMutedHex = "#9CA4B2"      // 6.55:1 on #1C1C1E, 5.32:1 on #2C2C2E
    static let lightWarnHex = "#9A4D00"      // 6.11:1 on #FFFFFF, 5.61:1 on #F5F5F7
    static let darkWarnHex = "#FBBF24"       // 9.86:1 on #1C1C1E, 8.00:1 on #2C2C2E

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

    // MARK: - Text Tones (all >= 4.5:1 on card & elevated surfaces)

    static func textColor(for tone: KitV1Tone?, scheme: ColorScheme) -> Color {
        Color(hex: textHex(for: tone, scheme: scheme))
    }

    static func textHex(for tone: KitV1Tone?, scheme: ColorScheme) -> String {
        switch tone ?? .primary {
        case .primary:
            return scheme == .dark ? "#F3F4F6" : "#111827"
        case .secondary:
            return scheme == .dark ? "#B0B7C3" : "#5E6370"
        case .muted:
            return scheme == .dark ? darkMutedHex : lightMutedHex
        case .accent:
            return scheme == .dark ? "#10B981" : "#047857"
        case .warn:
            return scheme == .dark ? darkWarnHex : lightWarnHex
        }
    }

    // MARK: - Palette c2..c6 (contrast-checked >= 3.0:1 against card & track surfaces)

    static let fallbackHexLight: [String] = [
        "#047857", // accent
        "#005CC2", // c2 blue
        "#7C3AED", // c3 purple
        "#B45309", // c4 amber (4.56:1 on light track)
        "#0891B2", // c5 cyan
        "#DC2626", // c6 red
    ]

    static let fallbackHexDark: [String] = [
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
    /// - Uses `darkHex` verbatim on Dark mode when present and readable against card & track.
    /// - Adapts raw hex colors to clear `>= 3.05:1` against BOTH card and track surfaces.
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
               let canonical = TeamTextContrast.canonicalHex(explicitDark) {
                return ensureMarkContrast(canonical, scheme: .dark)
            }
            if let lightHex = hex,
               let adapted = TeamTextContrast.usableOnDarkSurface(
                   primaryHex: lightHex,
                   surfaceLuminance: TeamTextContrast.darkSurfaceLuminance
               ) {
                return ensureMarkContrast(adapted, scheme: .dark)
            }
            return seriesHex(at: fallbackIndex, scheme: .dark)
        }
        if let raw = hex, let canonical = TeamTextContrast.canonicalHex(raw) {
            return ensureMarkContrast(canonical, scheme: .light)
        }
        return seriesHex(at: fallbackIndex, scheme: .light)
    }

    /// Clamps any parsed sRGB hex so its contrast against BOTH `cardBackground` and `trackBackground`
    /// is at least `minRatio` (default `3.05:1`), preserving hue cleanly.
    static func ensureMarkContrast(_ hex: String, scheme: ColorScheme, minRatio: Double = 3.05) -> String {
        guard let rgb = ProbabilityBarPalette.rgb(hex) else {
            return seriesHex(at: 0, scheme: scheme)
        }
        let cardHex = scheme == .dark ? darkCardHex : lightCardHex
        let trackHex = scheme == .dark ? darkTrackHex : lightTrackHex
        func passes(_ candidate: String) -> Bool {
            guard let c1 = contrastRatio(candidate, against: cardHex),
                  let c2 = contrastRatio(candidate, against: trackHex) else {
                return false
            }
            return min(c1, c2) >= minRatio
        }
        if passes(hex) { return hex }
        let target: (r: Double, g: Double, b: Double) = scheme == .dark ? (255, 255, 255) : (0, 0, 0)
        for step in 1...40 {
            let t = Double(step) / 40.0
            let r = Int((Double(rgb.r) * (1 - t) + target.r * t).rounded())
            let g = Int((Double(rgb.g) * (1 - t) + target.g * t).rounded())
            let b = Int((Double(rgb.b) * (1 - t) + target.b * t).rounded())
            let cand = String(format: "#%02X%02X%02X", min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)))
            if passes(cand) { return cand }
        }
        return seriesHex(at: 0, scheme: scheme)
    }

    static func contrastRatio(_ fgHex: String, against bgHex: String) -> Double? {
        guard let l1 = TeamTextContrast.relativeLuminance(fgHex),
              let l2 = TeamTextContrast.relativeLuminance(bgHex) else {
            return nil
        }
        return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
    }

    /// Resolves a paired two-segment split bar using the repo's hue-separation & contrast rules,
    /// flooring both sides cleanly to `>= 3.05:1` against card and track surfaces.
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
            let hexes = TeamTextContrast.surfaceColorHexes(
                awayHex: leftHex,
                homeHex: rightHex,
                colorScheme: scheme
            )
            return (
                left: Color(hex: ensureMarkContrast(hexes.away, scheme: scheme)),
                right: Color(hex: ensureMarkContrast(hexes.home, scheme: scheme))
            )
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
                foreground: textColor(for: .muted, scheme: scheme),
                secondaryForeground: textColor(for: .muted, scheme: scheme)
            )
        }
        let accent = brandAccent(for: scheme)
        if highlightRole == .dayPeak || shade >= 0.6 {
            return TilePalette(
                background: accent,
                border: accent,
                foreground: scheme == .dark ? Color(hex: "#0B0E11") : .white,
                secondaryForeground: scheme == .dark ? Color(hex: "#111827") : .white
            )
        }
        if shade >= 0.3 {
            return TilePalette(
                background: accent.opacity(scheme == .dark ? 0.24 : 0.18),
                border: accent.opacity(0.65),
                foreground: textColor(for: .primary, scheme: scheme),
                secondaryForeground: textColor(for: .secondary, scheme: scheme)
            )
        }
        if shade >= 0.12 {
            return TilePalette(
                background: accent.opacity(scheme == .dark ? 0.14 : 0.10),
                border: accent.opacity(0.45),
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
