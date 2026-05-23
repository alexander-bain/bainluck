import SwiftUI

// MARK: - Design System Colors (from Claude Design handoff)

enum DS {
    static let surface = Color(red: 0.96, green: 0.96, blue: 0.97)       // #F5F5F7
    static let cardBg = Color.white
    static let border = Color(red: 0.90, green: 0.91, blue: 0.92)        // #E5E7EB
    static let textPrimary = Color(red: 0.07, green: 0.09, blue: 0.15)   // #111827
    static let textSecondary = Color(red: 0.42, green: 0.44, blue: 0.50) // #6B7280
    static let textMuted = Color(red: 0.61, green: 0.64, blue: 0.69)     // #9CA3AF
    static let emerald = Color(red: 0.06, green: 0.73, blue: 0.51)       // #10B981
    static let emeraldDark = Color(red: 0.02, green: 0.59, blue: 0.40)   // #059669
    static let blue = Color(red: 0.23, green: 0.51, blue: 0.96)          // #3B82F6
    static let kalshiGreen = Color(red: 0.13, green: 0.77, blue: 0.37)   // #22C55E
    static let purple = Color(red: 0.55, green: 0.36, blue: 0.96)        // #8B5CF6
    static let amber = Color(red: 0.96, green: 0.62, blue: 0.04)         // #F59E0B
    static let danger = Color(red: 0.94, green: 0.27, blue: 0.27)        // #EF4444
    static let trackBg = Color(red: 0.95, green: 0.96, blue: 0.96)       // #F3F4F6

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

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 1) {
            Text("\(Int(value.rounded()))")
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

    private var config: (color: Color, label: String, bg: Color) {
        switch source.lowercased() {
        case "kalshi": return (DS.kalshiGreen, "Kalshi", DS.kalshiGreen.opacity(0.08))
        case "polymarket": return (DS.blue, "Polymarket", DS.blue.opacity(0.08))
        case "cross", "merged": return (DS.textSecondary, "Cross-Source", DS.trackBg)
        default: return (DS.textMuted, source.capitalized, DS.trackBg)
        }
    }

    var body: some View {
        let c = config
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
                SourceChip(source: source)
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
        .foregroundStyle(correct ? Color(red: 0.08, green: 0.50, blue: 0.24) : DS.danger)
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
