import SwiftUI
#if os(iOS)
import UIKit
#elseif os(macOS)
import AppKit
#endif

// MARK: - Design System Colors (Light + Adaptive Dark Mode)

enum DS {
    private struct RGB {
        let r: Double
        let g: Double
        let b: Double
    }

    private static func adaptive(light: RGB, dark: RGB) -> Color {
        #if os(iOS)
        Color(uiColor: UIColor { traits in
            let c = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: c.r, green: c.g, blue: c.b, alpha: 1)
        })
        #elseif os(macOS)
        Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            let c = isDark ? dark : light
            return NSColor(srgbRed: c.r, green: c.g, blue: c.b, alpha: 1)
        })
        #else
        Color(red: light.r, green: light.g, blue: light.b)
        #endif
    }

    static let surface = adaptive(
        light: RGB(r: 0.96, g: 0.96, b: 0.97),       // #F5F5F7
        dark: RGB(r: 0.059, g: 0.067, b: 0.082)      // #0F1115
    )
    static let cardBg = adaptive(
        light: RGB(r: 1.0, g: 1.0, b: 1.0),          // #FFFFFF
        dark: RGB(r: 0.102, g: 0.114, b: 0.141)      // #1A1D24
    )
    static let border = adaptive(
        light: RGB(r: 0.90, g: 0.91, b: 0.92),       // #E5E7EB
        dark: RGB(r: 0.173, g: 0.192, b: 0.235)      // #2C313C
    )
    static let textPrimary = adaptive(
        light: RGB(r: 0.07, g: 0.09, b: 0.15),       // #111827
        dark: RGB(r: 0.953, g: 0.957, b: 0.965)      // #F3F4F6
    )
    static let textSecondary = adaptive(
        light: RGB(r: 0.42, g: 0.44, b: 0.50),       // #6B7280
        dark: RGB(r: 0.612, g: 0.639, b: 0.686)      // #9CA3AF
    )
    static let textMuted = adaptive(
        light: RGB(r: 0.61, g: 0.64, b: 0.69),       // #9CA3AF
        dark: RGB(r: 0.520, g: 0.550, b: 0.600)      // #858C99
    )
    static let emerald = Color(red: 0.06, green: 0.73, blue: 0.51)       // #10B981
    static let emeraldDark = adaptive(
        light: RGB(r: 0.02, g: 0.59, b: 0.40),       // #059669
        dark: RGB(r: 0.063, g: 0.725, b: 0.506)      // #10B981
    )
    static let blue = Color(red: 0.23, green: 0.51, blue: 0.96)          // #3B82F6
    static let kalshiGreen = Color(red: 0.13, green: 0.77, blue: 0.37)   // #22C55E
    static let purple = adaptive(
        light: RGB(r: 0.55, g: 0.36, b: 0.96),       // #8B5CF6
        dark: RGB(r: 0.655, g: 0.490, b: 0.980)      // #A77DF9
    )
    static let amber = Color(red: 0.96, green: 0.62, blue: 0.04)         // #F59E0B
    static let danger = adaptive(
        light: RGB(r: 0.94, g: 0.27, b: 0.27),       // #EF4444
        dark: RGB(r: 0.973, g: 0.443, b: 0.443)      // #F87171
    )
    static let trackBg = adaptive(
        light: RGB(r: 0.95, g: 0.96, b: 0.96),       // #F3F4F6
        dark: RGB(r: 0.141, g: 0.161, b: 0.200)      // #242933
    )
    /// #12364 — small grey text a reader can read: 6.0:1 on a white card and
    /// 5.6:1 on `surface`. Apple's accessibility audit wants 4.5:1 for small
    /// text; the system's secondary grey is about 3.4:1 and `textSecondary`
    /// 4.4:1 on `surface`. It replaces the system `.secondary` on the
    /// game page's small text.
    static let textSecondaryReadable = adaptive(
        light: RGB(r: 0.37, g: 0.39, b: 0.44),       // #5E6370
        dark: RGB(r: 0.690, g: 0.718, b: 0.765)      // #B0B7C3
    )
    /// #12364 — small blue text and links: 6.3:1 on white, 5.0:1 on its own
    /// 15% tint. The system blue is 4.0:1 and `blue` 3.7:1.
    static let blueReadable = adaptive(
        light: RGB(r: 0.00, g: 0.36, b: 0.76),       // #005CC2
        dark: RGB(r: 0.376, g: 0.647, b: 0.980)      // #60A5FA
    )
    /// #12364 — a won or hit mark in text: 5.5:1 on white. The system green is 2.2:1.
    static let greenReadable = adaptive(
        light: RGB(r: 0.02, g: 0.47, b: 0.34),       // #047857
        dark: RGB(r: 0.204, g: 0.827, b: 0.600)      // #34D399
    )

    static func probColor(_ value: Double) -> Color {
        if value >= 65 { return emerald }
        if value >= 35 { return amber }
        return textMuted
    }

    static func deltaColor(_ value: Double) -> Color {
        if value > 0 { return kalshiGreen }
        if value < 0 { return danger }
        return textMuted
    }
}

// MARK: - Section Kicker

struct SectionKicker: View {
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 11, weight: .heavy))
            .tracking(1.3)
            .foregroundStyle(DS.emeraldDark)
    }
}

// MARK: - Section Title

struct SectionTitle: View {
    let title: String
    var count: Int?
    var action: String?
    var onAction: (() -> Void)?

    var body: some View {
        HStack(alignment: .lastTextBaseline) {
            Text(title)
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(DS.textPrimary)
                .tracking(-0.3)

            if let count {
                Text("\(count) active")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(DS.textSecondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(DS.trackBg)
                    .clipShape(Capsule())
            }

            Spacer()

            if let action {
                Button(action: { onAction?() }) {
                    Text(action)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(DS.emerald)
                }
            }
        }
    }
}

// MARK: - Probability Number

struct ProbabilityNumber: View {
    let value: Double
    var size: CGFloat = 36
    var color: Color?
    /// The card-level integer, when the caller has already decided the whole
    /// field together (#2060). Overrides the figure, never the `<1%` rule, and
    /// never the COLOUR — `DS.probColor` reads the probability, which is a
    /// property of the value rather than of the printed numeral.
    var renderedPercent: Int?

    /// `value` is percentage POINTS. The figure goes through `percentNumber` so a
    /// priced-but-tiny outcome reads `<1%` rather than `0%` (#5899) — the futures
    /// leader row drew `0%` directly above three `<1%` rows of the same list.
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 1) {
            Text(percentNumber(value, renderedPercent: renderedPercent))
                .font(.system(size: size, weight: .semibold, design: .monospaced))
                .foregroundStyle(color ?? DS.probColor(value))
                .tracking(-0.5)
            Text("%")
                .font(.system(size: size * 0.42, weight: .semibold, design: .monospaced))
                .foregroundStyle((color ?? DS.probColor(value)).opacity(0.7))
        }
    }
}

// MARK: - Probability Bar

struct DSProbabilityBar: View {
    let value: Double
    var maxValue: Double = 100
    var height: CGFloat = 6
    var color: Color?

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 999)
                    .fill(DS.trackBg)
                RoundedRectangle(cornerRadius: 999)
                    .fill(color ?? DS.probColor(value))
                    .frame(width: max(2, geo.size.width * min(value / maxValue, 1)))
            }
        }
        .frame(height: height)
    }
}

// MARK: - Delta Badge

struct DeltaBadge: View {
    let value: Double
    var unit: String = "pp"

    var body: some View {
        if value == 0 {
            Text("—")
                .font(.system(size: 10.5, design: .monospaced))
                .foregroundStyle(DS.textMuted)
        } else {
            HStack(spacing: 2) {
                Image(systemName: value > 0 ? "arrow.up.right" : "arrow.down.right")
                    .font(.system(size: 7, weight: .bold))
                Text("\(abs(value), specifier: "%.1f")\(unit)")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
            }
            .foregroundStyle(DS.deltaColor(value))
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(DS.deltaColor(value).opacity(0.08))
            .clipShape(Capsule())
        }
    }
}

// MARK: - Source Chip

struct SourceChip: View {
    let source: String
    var onCardFace: Bool = false

    /// nil when the app cannot name the source — the chip renders nothing rather
    /// than title-casing a raw key onto the screen (#4135). "cross"/"merged" are
    /// this chip's own pseudo-sources for the comparison surfaces, not market
    /// sources, so they stay local to it. On card faces (`onCardFace == true`),
    /// single-venue Kalshi / Polymarket are omitted and multi-source says "2 sources".
    private var config: (color: Color, label: String, bg: Color)? {
        if onCardFace {
            guard let label = SourceLabels.cardFaceLabel(for: source) else { return nil }
            return (DS.textSecondary, label, DS.trackBg)
        }
        switch source.lowercased() {
        case "kalshi": return (DS.kalshiGreen, "Kalshi", DS.kalshiGreen.opacity(0.08))
        case "polymarket": return (DS.blue, "Polymarket", DS.blue.opacity(0.08))
        case "cross", "merged": return (DS.textSecondary, "Cross-Source", DS.trackBg)
        default:
            guard let label = SourceLabels.label(for: source.lowercased()) else { return nil }
            return (DS.textMuted, label, DS.trackBg)
        }
    }

    var body: some View {
        if let c = config {
            HStack(spacing: 5) {
                Circle()
                    .fill(c.color)
                    .frame(width: 5, height: 5)
                Text(c.label)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(c.color == DS.textSecondary ? DS.textPrimary : c.color)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(c.bg)
            .clipShape(Capsule())
        }
    }
}

// MARK: - Market Card

struct DSMarketCard: View {
    let question: String
    let probability: Double
    var source: String = "kalshi"
    var delta: Double?
    var resolved: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(question)
                .font(.subheadline)
                .fontWeight(.semibold)
                .lineLimit(2)
                .foregroundStyle(resolved ? DS.textMuted : DS.textPrimary)
                .strikethrough(resolved)

            Spacer(minLength: 0)

            HStack(spacing: 8) {
                DSProbabilityBar(value: probability, height: 6, color: DS.probColor(probability))
                Text(probability.truncatingRemainder(dividingBy: 1) == 0 ? "\(Int(probability))%" : String(format: "%.1f%%", probability))
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                    .monospacedDigit()
                    .foregroundStyle(probability > 50 ? DS.textPrimary : DS.textSecondary)
            }

            HStack(spacing: 6) {
                if let delta, abs(delta) >= 1 {
                    DeltaBadge(value: delta)
                }
                Spacer()
                SourceChip(source: source, onCardFace: true)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .frame(minHeight: 110)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(DS.border, lineWidth: 0.5))
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
    }
}

// MARK: - Resolved Badge

struct ResolvedBadge: View {
    var actual: String?
    var expected: String?
    var correct: Bool = true

    var body: some View {
        HStack(spacing: 6) {
            Text("RESOLVED")
                .font(.system(size: 9, weight: .heavy))
                .tracking(0.5)
            if let expected, let actual {
                HStack(spacing: 4) {
                    Text(expected)
                        .strikethrough()
                        .foregroundStyle(DS.textMuted)
                    Text("→")
                    Text(actual)
                }
                .font(.system(size: 10, weight: .medium, design: .monospaced))
            }
        }
        .foregroundStyle(correct ? DS.greenReadable : DS.danger)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(correct ? Color.green.opacity(0.08) : Color.red.opacity(0.08))
        .clipShape(Capsule())
        .overlay(Capsule().stroke(correct ? Color.green.opacity(0.2) : Color.red.opacity(0.2), lineWidth: 1))
    }
}

// MARK: - Section Card (container)

struct SectionCard<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            content
        }
        .padding(22)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(DS.border, lineWidth: 0.5))
    }
}

// MARK: - Footer Note

struct FooterNote: View {
    let left: String
    var right: String?

    var body: some View {
        HStack {
            Text(left)
            Spacer()
            if let right {
                Text(right)
                    .font(.system(size: 11, design: .monospaced))
            }
        }
        .font(.system(size: 11))
        .foregroundStyle(DS.textMuted)
        .padding(.top, 10)
        .overlay(alignment: .top) {
            Rectangle()
                .fill(DS.border)
                .frame(height: 0.5)
                .padding(.horizontal, -22)
        }
    }
}
