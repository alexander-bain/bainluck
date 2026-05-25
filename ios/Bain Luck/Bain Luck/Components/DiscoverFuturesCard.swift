import SwiftUI

// MARK: - Category Gradients (shared with DiscoverEventCard)

let sportCategoryGradients: [String: (Color, Color)] = [
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

let sportDefaultGradient: (Color, Color) = (Color(red: 0.06, green: 0.09, blue: 0.16), Color(red: 0.12, green: 0.16, blue: 0.24))

// MARK: - Futures Card

struct NativeFuturesDiscoverCard: View {
    let data: FeedFuturesData
    let feedContext: String?
    let expandedContext: String?
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil
    var onContextExpand: (() -> Void)? = nil
    var onContextCollapse: (() -> Void)? = nil

    private var gradient: (Color, Color) {
        sportCategoryGradients[data.llmSportCategory?.lowercased() ?? ""] ?? sportDefaultGradient
    }

    private var categoryLabel: String {
        (data.sportName ?? data.llmSportCategory ?? "Market").uppercased()
    }

    private var leader: FeedFuturesOutcome? {
        data.topOutcomes?.first
    }

    private var leaderProbability: Double {
        leader?.probability ?? 0
    }

    private var shareURL: URL {
        URL(string: futuresShareURL(data.id, style: .nativeCard)) ?? bainLuckFallbackURL
    }

    private var shareMessage: String {
        if let leader, let prob = leader.probability {
            return "\(leader.name) at \(Int((prob * 100).rounded()))% — \(data.name) on Bain Luck"
        }
        return "\(data.name) on Bain Luck"
    }

    private var contextText: String? {
        if let feedContext, !feedContext.isEmpty { return feedContext }
        if let hook = data.hookDescription, !hook.isEmpty { return hook }
        return nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .bottomLeading) {
                heroBackground
                    .frame(height: 170)
                    .clipped()

                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text(categoryLabel)
                            .font(.system(size: 9, weight: .heavy))
                            .tracking(0.8)
                            .foregroundStyle(.white.opacity(0.78))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.black.opacity(0.24), in: Capsule())

                        Spacer()

                        if isTrending(data) {
                            Label("Trending", systemImage: "flame.fill")
                                .font(.system(size: 9, weight: .heavy))
                                .foregroundStyle(.orange)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(.black.opacity(0.24), in: Capsule())
                        }
                    }

                    Spacer(minLength: 16)

                    if let leader {
                        HStack(alignment: .bottom, spacing: 10) {
                            Text("\(Int((leaderProbability * 100).rounded()))%")
                                .font(.system(size: 52, weight: .black).monospacedDigit())
                                .minimumScaleFactor(0.76)
                                .foregroundStyle(.white)
                                .shadow(color: .black.opacity(0.25), radius: 8, x: 0, y: 3)

                            MovementBadge(movement: leader.movement)
                                .padding(.bottom, 8)
                        }

                        Text(leader.name)
                            .font(.headline.weight(.bold))
                            .foregroundStyle(.white.opacity(0.92))
                            .lineLimit(3)
                            .minimumScaleFactor(0.92)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(14)
            }
            .clipShape(UnevenRoundedRectangle(topLeadingRadius: 18, topTrailingRadius: 18))

            VStack(alignment: .leading, spacing: 12) {
                Text(data.name)
                    .font(.headline.weight(.bold))
                    .lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let contextText {
                    ExpandableNativeContextText(
                        text: contextText,
                        expandedText: expandedContext ?? data.hookDescription,
                        font: .subheadline,
                        onExpand: onContextExpand,
                        onCollapse: onContextCollapse
                    )
                }

                if let outcomes = data.topOutcomes, outcomes.count > 1 {
                    VStack(spacing: 7) {
                        ForEach(Array(outcomes.prefix(3).enumerated()), id: \.element.id) { idx, outcome in
                            outcomeRow(outcome, isLeader: idx == 0)
                        }
                    }
                }

                HStack(spacing: 8) {
                    if let sources = data.sources, sources.count > 1 {
                        Text(sources.map { $0.uppercased() }.joined(separator: " + "))
                            .font(.system(size: 9, weight: .heavy))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(Color.blue.opacity(0.10), in: Capsule())
                    } else if let src = data.source {
                        Text(src.uppercased())
                            .font(.system(size: 9, weight: .heavy))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(Color.blue.opacity(0.10), in: Capsule())
                    }

                    Spacer()

                    ShareLink(
                        item: shareURL,
                        subject: Text(data.name),
                        message: Text(shareMessage)
                    ) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundStyle(.secondary)
                            .padding(8)
                            .background(Color.secondary.opacity(0.10), in: Circle())
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .contextMenu {
                        Button(action: copyShareImage) {
                            Label("Copy Image", systemImage: "doc.on.doc")
                        }

                        #if os(iOS)
                        Button(action: saveShareImage) {
                            Label("Save Image", systemImage: "square.and.arrow.down")
                        }
                        #endif
                    }
                }
            }
            .padding(14)
        }
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.07), radius: 12, x: 0, y: 5)
        .contentShape(Rectangle())
        .onTapGesture {
            navigationPath.append(Route.futuresDetail(id: data.id))
            onOpen?()
        }
    }

    @ViewBuilder
    private var heroBackground: some View {
        LinearGradient(colors: [gradient.0, gradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
            .overlay(
                Text(categoryEmoji(data.llmSportCategory))
                    .font(.system(size: 96))
                    .opacity(0.10)
            )
    }

    private func outcomeRow(_ outcome: FeedFuturesOutcome, isLeader: Bool) -> some View {
        HStack(spacing: 8) {
            Text(outcome.name)
                .font(.caption.weight(isLeader ? .semibold : .regular))
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minWidth: 60, maxWidth: 140, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.12))
                    Capsule()
                        .fill(isLeader ? Color.blue : Color.secondary.opacity(0.35))
                        .frame(width: max(3, geo.size.width * (outcome.probability ?? 0)))
                }
            }
            .frame(height: 7)

            Text("\(Int(((outcome.probability ?? 0) * 100).rounded()))%")
                .font(.caption.weight(.bold).monospacedDigit())
                .frame(width: 34, alignment: .trailing)
        }
    }

    private func renderedShareImage() -> PlatformImage? {
        let outcomes: [(name: String, probability: Double)] = (data.topOutcomes ?? []).compactMap { outcome in
            guard let probability = outcome.probability else { return nil }
            return (outcome.name, probability)
        }
        return ShareCardRenderer.renderFuturesCard(
            marketName: data.name,
            leaderName: leader?.name ?? "",
            probability: leaderProbability,
            category: data.llmSportCategory ?? data.sportName ?? "Market",
            hookDescription: data.hookDescription,
            outcomes: outcomes
        )
    }

    private func copyShareImage() {
        if let image = renderedShareImage() {
            ShareCardRenderer.copyImageToClipboard(image)
        }
    }

    private func saveShareImage() {
        #if os(iOS)
        if let image = renderedShareImage() {
            ShareCardRenderer.saveImageToPhotos(image)
        }
        #endif
    }

    private func categoryEmoji(_ category: String?) -> String {
        switch category?.lowercased() {
        case "politics": return "🏛"
        case "geopolitics": return "🌍"
        case "economics": return "📈"
        case "tech": return "💻"
        case "entertainment": return "🎬"
        case "culture": return "🎭"
        case "weather": return "🌤"
        case "health": return "🏥"
        default: return "🍀"
        }
    }
}
