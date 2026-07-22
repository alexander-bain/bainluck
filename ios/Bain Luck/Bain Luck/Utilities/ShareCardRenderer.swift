import SwiftUI

#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

// MARK: - Category Gradient Palette (shared with DiscoverFuturesCard)

private let shareCardGradients: [String: (Color, Color)] = [
    "basketball": (Color(red: 0.49, green: 0.18, blue: 0.07), Color(red: 0.76, green: 0.25, blue: 0.05)),
    "football": (Color(red: 0.08, green: 0.33, blue: 0.18), Color(red: 0.08, green: 0.50, blue: 0.24)),
    "baseball": (Color(red: 0.50, green: 0.11, blue: 0.11), Color(red: 0.73, green: 0.11, blue: 0.11)),
    "hockey": (Color(red: 0.12, green: 0.23, blue: 0.37), Color(red: 0.15, green: 0.39, blue: 0.92)),
    "soccer": (Color(red: 0.02, green: 0.31, blue: 0.23), Color(red: 0.02, green: 0.60, blue: 0.40)),
    "golf": (Color(red: 0.08, green: 0.33, blue: 0.18), Color(red: 0.09, green: 0.40, blue: 0.20)),
    "mma": (Color(red: 0.27, green: 0.04, blue: 0.04), Color(red: 0.60, green: 0.11, blue: 0.11)),
    "economics": (Color(red: 0.18, green: 0.06, blue: 0.40), Color(red: 0.49, green: 0.23, blue: 0.93)),
    "politics": (Color(red: 0.12, green: 0.11, blue: 0.29), Color(red: 0.26, green: 0.22, blue: 0.79)),
    "tech": (Color(red: 0.03, green: 0.20, blue: 0.27), Color(red: 0.03, green: 0.57, blue: 0.70)),
    "culture": (Color(red: 0.51, green: 0.09, blue: 0.26), Color(red: 0.86, green: 0.15, blue: 0.47)),
    "weather": (Color(red: 0.05, green: 0.29, blue: 0.43), Color(red: 0.01, green: 0.52, blue: 0.78)),
    "entertainment": (Color(red: 0.44, green: 0.10, blue: 0.46), Color(red: 0.75, green: 0.15, blue: 0.83)),
    "cricket": (Color(red: 0.07, green: 0.31, blue: 0.29), Color(red: 0.08, green: 0.72, blue: 0.65)),
    "olympics": (Color(red: 0.47, green: 0.21, blue: 0.06), Color(red: 0.85, green: 0.47, blue: 0.02)),
]

private let shareCardDefaultGradient: (Color, Color) = (
    Color(red: 0.06, green: 0.09, blue: 0.16),
    Color(red: 0.12, green: 0.16, blue: 0.24)
)

// MARK: - Shareable Card Views

/// A self-contained futures card view designed for image rendering and sharing.
/// Uses category gradients as background (no external image loading).
/// Fixed at 375x500pt for IG Story friendly aspect ratio.
struct ShareableFuturesCardView: View {
    let marketName: String
    let leaderName: String
    let probability: Double
    let category: String
    let hookDescription: String?
    let outcomes: [(name: String, probability: Double)]

    private var gradient: (Color, Color) {
        shareCardGradients[category.lowercased()] ?? shareCardDefaultGradient
    }

    private var categoryLabel: String {
        sportCategoryDisplayName(category).uppercased()
    }

    private var categoryEmoji: String {
        switch category.lowercased() {
        case "politics": return "🏛"
        case "geopolitics": return "🌍"
        case "economics": return "📈"
        case "tech": return "💻"
        case "entertainment": return "🎬"
        case "culture": return "🎭"
        case "weather": return "🌤"
        case "health": return "🏥"
        case "basketball": return "🏀"
        case "football": return "🏈"
        case "baseball": return "⚾"
        case "hockey": return "🏒"
        case "soccer": return "⚽"
        case "golf": return "⛳"
        case "mma": return "🥊"
        case "cricket": return "🏏"
        case "olympics": return "🏅"
        default: return "🍀"
        }
    }

    private var heroOutcomeLabel: String {
        let trimmed = leaderName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "Market probability" }
        if trimmed.count > 44 || trimmed == marketName {
            return "Leading outcome"
        }
        return trimmed
    }

    private var hookLineLimit: Int {
        outcomes.count > 1 ? 4 : 8
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Hero section with gradient background
            ZStack(alignment: .bottomLeading) {
                LinearGradient(
                    colors: [gradient.0, gradient.1],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .overlay(
                    Text(categoryEmoji)
                        .font(.system(size: 120))
                        .opacity(0.08)
                        .offset(x: 100, y: -20)
                )

                VStack(alignment: .leading, spacing: 12) {
                    Text(categoryLabel)
                        .font(.system(size: 11, weight: .heavy))
                        .tracking(1.0)
                        .foregroundStyle(.white.opacity(0.78))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(.black.opacity(0.24), in: Capsule())

                    Spacer(minLength: 16)

                    Text("\(Int((probability * 100).rounded()))%")
                        .font(.system(size: 64, weight: .black).monospacedDigit())
                        .foregroundStyle(.white)
                        .shadow(color: .black.opacity(0.30), radius: 10, x: 0, y: 4)

                    Text(heroOutcomeLabel)
                        .font(.system(size: 20, weight: .bold))
                        .foregroundStyle(.white.opacity(0.92))
                        .lineLimit(2)
                        .minimumScaleFactor(0.82)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(18)
            }
            .frame(height: 220)
            .clipped()

            // Content section with white/light background
            VStack(alignment: .leading, spacing: 14) {
                Text(marketName)
                    .font(.system(size: 18, weight: .bold))
                    .lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true)
                    .foregroundStyle(Color(red: 0.10, green: 0.10, blue: 0.12))

                if let hook = hookDescription, !hook.isEmpty {
                    Text(hook)
                        .font(.system(size: 14))
                        .foregroundStyle(Color(red: 0.35, green: 0.35, blue: 0.40))
                        .lineLimit(hookLineLimit)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if outcomes.count > 1 {
                    VStack(spacing: 8) {
                        ForEach(Array(outcomes.prefix(3).enumerated()), id: \.offset) { idx, outcome in
                            shareableOutcomeRow(
                                name: outcome.name,
                                probability: outcome.probability,
                                isLeader: idx == 0
                            )
                        }
                    }
                }

                Spacer(minLength: 0)

                // Watermark
                HStack {
                    Spacer()
                    Text("bainluck.com")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.60))
                    Text("🍀")
                        .font(.system(size: 12))
                }
            }
            .padding(18)
        }
        .frame(width: 375, height: 500)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 22))
    }

    private func shareableOutcomeRow(name: String, probability: Double, isLeader: Bool) -> some View {
        HStack(spacing: 8) {
            Text(name)
                .font(.system(size: 13, weight: isLeader ? .semibold : .regular))
                .lineLimit(2)
                .foregroundStyle(Color(red: 0.15, green: 0.15, blue: 0.18))
                .frame(width: 130, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color(red: 0.90, green: 0.90, blue: 0.92))
                    Capsule()
                        .fill(isLeader
                              ? Color(red: 0.20, green: 0.40, blue: 0.85)
                              : Color(red: 0.70, green: 0.70, blue: 0.75))
                        .frame(width: max(3, geo.size.width * probability))
                }
            }
            .frame(height: 7)

            Text("\(Int((probability * 100).rounded()))%")
                .font(.system(size: 13, weight: .bold).monospacedDigit())
                .foregroundStyle(Color(red: 0.15, green: 0.15, blue: 0.18))
                .frame(width: 36, alignment: .trailing)
        }
    }
}

/// A self-contained event card view designed for image rendering and sharing.
/// Uses team colors as visual anchors on a clean white background.
struct ShareableEventCardView: View {
    let homeTeam: String
    let awayTeam: String
    let homeProbability: Double
    let awayProbability: Double
    let sportName: String
    let homeColor: Color
    let awayColor: Color
    let status: String?
    let homeScore: Int?
    let awayScore: Int?

    private var eyebrow: String {
        if status == "live" { return "LIVE" }
        if status == "completed" || status == "closed" { return "FINAL" }
        return sportName.uppercased()
    }

    var body: some View {
        VStack(spacing: 0) {
            // Dark header band
            HStack {
                if status == "live" {
                    Circle()
                        .fill(Color.red)
                        .frame(width: 8, height: 8)
                }
                Text(eyebrow)
                    .font(.system(size: 11, weight: .heavy))
                    .tracking(1.0)
                    .foregroundStyle(status == "live" ? .red : .white.opacity(0.7))
                Spacer()
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 14)
            .background(Color(red: 0.08, green: 0.08, blue: 0.12))

            // Teams section
            VStack(spacing: 24) {
                Spacer(minLength: 12)

                HStack(alignment: .center, spacing: 0) {
                    // Away team
                    VStack(spacing: 10) {
                        RoundedRectangle(cornerRadius: 14)
                            .fill(awayColor)
                            .frame(width: 56, height: 56)
                            .overlay(
                                Text(String(awayTeam.split(separator: " ").last ?? "").prefix(3).uppercased())
                                    .font(.system(size: 12, weight: .heavy))
                                    .foregroundStyle(.white)
                            )
                        Text(awayTeam)
                            .font(.system(size: 15, weight: .bold))
                            .multilineTextAlignment(.center)
                            .lineLimit(3)
                            .foregroundStyle(Color(red: 0.10, green: 0.10, blue: 0.12))
                        Text(formatProbability(awayProbability))
                            .font(.system(size: 32, weight: .black).monospacedDigit())
                            .foregroundStyle(awayColor)
                        if let score = awayScore {
                            Text("\(score)")
                                .font(.system(size: 14, weight: .heavy).monospacedDigit())
                                .foregroundStyle(Color(red: 0.45, green: 0.45, blue: 0.50))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color(red: 0.92, green: 0.92, blue: 0.94))
                                .clipShape(Capsule())
                        }
                    }
                    .frame(maxWidth: .infinity)

                    Text("vs")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.60))
                        .frame(width: 36)

                    // Home team
                    VStack(spacing: 10) {
                        RoundedRectangle(cornerRadius: 14)
                            .fill(homeColor)
                            .frame(width: 56, height: 56)
                            .overlay(
                                Text(String(homeTeam.split(separator: " ").last ?? "").prefix(3).uppercased())
                                    .font(.system(size: 12, weight: .heavy))
                                    .foregroundStyle(.white)
                            )
                        Text(homeTeam)
                            .font(.system(size: 15, weight: .bold))
                            .multilineTextAlignment(.center)
                            .lineLimit(3)
                            .foregroundStyle(Color(red: 0.10, green: 0.10, blue: 0.12))
                        Text(formatProbability(homeProbability))
                            .font(.system(size: 32, weight: .black).monospacedDigit())
                            .foregroundStyle(homeColor)
                        if let score = homeScore {
                            Text("\(score)")
                                .font(.system(size: 14, weight: .heavy).monospacedDigit())
                                .foregroundStyle(Color(red: 0.45, green: 0.45, blue: 0.50))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color(red: 0.92, green: 0.92, blue: 0.94))
                                .clipShape(Capsule())
                        }
                    }
                    .frame(maxWidth: .infinity)
                }

                // Probability bar
                GeometryReader { geo in
                    HStack(spacing: 0) {
                        Rectangle()
                            .fill(awayColor)
                            .frame(width: max(3, geo.size.width * awayProbability))
                        Rectangle()
                            .fill(homeColor)
                            .frame(width: max(3, geo.size.width * homeProbability))
                    }
                    .clipShape(Capsule())
                }
                .frame(height: 10)
                .padding(.horizontal, 4)

                Spacer(minLength: 0)

                // Watermark
                HStack {
                    Spacer()
                    Text("bainluck.com")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.60))
                    Text("🍀")
                        .font(.system(size: 12))
                }
            }
            .padding(22)
        }
        .frame(width: 375, height: 500)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 22))
    }
}

// MARK: - Share Card Renderer

@MainActor
enum ShareCardRenderer {

    /// Render a futures Discover card as a shareable image.
    static func renderFuturesCard(
        marketName: String,
        leaderName: String,
        probability: Double,
        category: String,
        hookDescription: String?,
        outcomes: [(name: String, probability: Double)] = []
    ) -> PlatformImage? {
        let view = ShareableFuturesCardView(
            marketName: marketName,
            leaderName: leaderName,
            probability: probability,
            category: category,
            hookDescription: hookDescription,
            outcomes: outcomes
        )
        let renderer = ImageRenderer(content: view)
        #if canImport(UIKit)
        renderer.scale = UIScreen.main.scale
        return renderer.uiImage
        #elseif canImport(AppKit)
        renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
        return renderer.nsImage
        #endif
    }

    /// Render an event Discover card as a shareable image.
    static func renderEventCard(
        homeTeam: String,
        awayTeam: String,
        homeProbability: Double,
        awayProbability: Double,
        sportName: String,
        homeColor: Color,
        awayColor: Color,
        status: String?,
        homeScore: Int?,
        awayScore: Int?
    ) -> PlatformImage? {
        let view = ShareableEventCardView(
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeProbability: homeProbability,
            awayProbability: awayProbability,
            sportName: sportName,
            homeColor: homeColor,
            awayColor: awayColor,
            status: status,
            homeScore: homeScore,
            awayScore: awayScore
        )
        let renderer = ImageRenderer(content: view)
        #if canImport(UIKit)
        renderer.scale = UIScreen.main.scale
        return renderer.uiImage
        #elseif canImport(AppKit)
        renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
        return renderer.nsImage
        #endif
    }

    /// Copy a rendered image to the system clipboard.
    static func copyImageToClipboard(_ image: PlatformImage) {
        #if canImport(UIKit)
        UIPasteboard.general.image = image
        #elseif canImport(AppKit)
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.writeObjects([image])
        #endif
    }

    /// Save a rendered image to the photo library (iOS only).
    static func saveImageToPhotos(_ image: PlatformImage) {
        #if canImport(UIKit)
        UIImageWriteToSavedPhotosAlbum(image, nil, nil, nil)
        #endif
    }
}
