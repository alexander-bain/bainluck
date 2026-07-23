import SwiftUI

// #490 (L2-172 native half) — confidence signal bars.
// A cell-signal-style 1-3 bar glyph showing how much we trust a probability
// (sources + liquidity + freshness). Alex ruling 2026-07-23: signal bars.
//
// The native mirror of the web treatment:
//   glyph  -> frontend/components/discover/shared.tsx :: SignalBars
//   math   -> frontend/lib/confidence.ts  (== backend feed_market_quality.py)
// Feed cards get `confidence_tier` straight from the API; the event hero
// recomputes its tier locally from the win-prob source list (Confidence.fromSources).
// Renders nothing when the tier is absent (#490 "render-only-where-present").

// MARK: - Confidence math (mirror of lib/confidence.ts)

enum ConfidenceTier: String, CaseIterable {
    case high, moderate, low

    /// Number of filled bars (out of 3). Backend/web keep an identical map.
    var bars: Int {
        switch self {
        case .high: return 3
        case .moderate: return 2
        case .low: return 1
        }
    }

    /// Human label, used in the accessibility description.
    var label: String {
        switch self {
        case .high: return "High confidence"
        case .moderate: return "Moderate confidence"
        case .low: return "Low confidence"
        }
    }
}

enum Confidence {
    // Shown to screen readers so the glyph is never unexplained chrome.
    static let tooltip = "Signal strength: sources + liquidity + freshness"

    // Tier cut points and signal weights — MUST match lib/confidence.ts and
    // backend feed_market_quality.compute_confidence_score.
    private static let tierHigh = 0.70
    private static let tierModerate = 0.40
    private static let wSources = 0.45
    private static let wMovement = 0.25
    private static let wVolume = 0.15
    private static let wAgree = 0.15
    private static let sourceSaturation = 3.0

    /// Coerce an API `confidence_tier` string into a known tier, or nil.
    static func normalize(_ tier: String?) -> ConfidenceTier? {
        guard let tier = tier else { return nil }
        return ConfidenceTier(rawValue: tier)
    }

    static func scoreToTier(_ score: Double) -> ConfidenceTier {
        if score >= tierHigh { return .high }
        if score >= tierModerate { return .moderate }
        return .low
    }

    /// Compute a tier client-side from signals the hero already has (mirrors the
    /// web event hero). Returns nil when there's no source to count — render
    /// nothing rather than a misleading bar.
    static func fromSources(
        sourceCount: Int?,
        hasMovement: Bool = false,
        hasVolume: Bool = false,
        sourcesAgree: Bool? = nil
    ) -> ConfidenceTier? {
        let sc = max(0, sourceCount ?? 0)
        if sc == 0 { return nil }

        var components: [(Double, Double)] = [
            (min(Double(sc), sourceSaturation) / sourceSaturation, wSources),
            (hasMovement ? 1.0 : 0.0, wMovement),
            (hasVolume ? 1.0 : 0.0, wVolume),
        ]
        if let agree = sourcesAgree {
            components.append((agree ? 1.0 : 0.0, wAgree))
        }

        let totalWeight = components.reduce(0.0) { $0 + $1.1 }
        if totalWeight <= 0 { return nil }
        let raw = components.reduce(0.0) { $0 + $1.0 * $1.1 } / totalWeight
        return scoreToTier(min(1.0, max(0.0, raw)))
    }
}

// MARK: - Glyph

/// Three ascending bars; filled ones take the tier color, the rest sit muted.
/// Ships with its own accessibility label so it's never unexplained chrome.
struct SignalBarsView: View {
    /// Tier string ("high"/"moderate"/"low"). Cards pass the API's
    /// `confidenceTier`; the hero passes `Confidence.fromSources(...)?.rawValue`.
    let tier: String?

    private let heights: [CGFloat] = [5, 8, 11]

    var body: some View {
        if let t = Confidence.normalize(tier) {
            HStack(alignment: .bottom, spacing: 2) {
                ForEach(Array(heights.enumerated()), id: \.offset) { index, height in
                    RoundedRectangle(cornerRadius: 1, style: .continuous)
                        .fill(index < t.bars ? fill(t) : DS.border)
                        .frame(width: 3, height: height)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(t.label). \(Confidence.tooltip)")
        }
    }

    private func fill(_ tier: ConfidenceTier) -> Color {
        switch tier {
        case .high: return DS.emerald
        case .moderate: return DS.emerald.opacity(0.7)
        case .low: return DS.textMuted
        }
    }
}

#if DEBUG
#Preview {
    VStack(alignment: .leading, spacing: 16) {
        SignalBarsView(tier: "high")
        SignalBarsView(tier: "moderate")
        SignalBarsView(tier: "low")
        SignalBarsView(tier: nil) // renders nothing
    }
    .padding()
}
#endif
