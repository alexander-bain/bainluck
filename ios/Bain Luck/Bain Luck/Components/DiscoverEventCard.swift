import SwiftUI

// MARK: - Sport Emoji (shared)

func sportEmoji(for sport: String?) -> String {
    switch sport?.lowercased().split(separator: "_").first.map(String.init) {
    case "basketball": return "🏀"
    case "football", "americanfootball": return "🏈"
    case "baseball": return "⚾"
    case "hockey", "icehockey": return "🏒"
    case "soccer": return "⚽"
    case "golf": return "⛳"
    case "mma", "boxing": return "🥊"
    case "tennis": return "🎾"
    case "cricket": return "🏏"
    case "motorsports": return "🏎"
    case "olympics": return "🏅"
    default: return "🍀"
    }
}

// MARK: - Event Card

struct NativeEventDiscoverCard: View {
    let event: FeedEventData
    let feedContext: String?
    let expandedContext: String?
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil
    var onContextExpand: (() -> Void)? = nil
    var onContextCollapse: (() -> Void)? = nil

    private var awayColor: Color {
        Color(hex: event.awayTeamData?.primaryColor ?? "#64748b")
    }

    private var homeColor: Color {
        Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")
    }

    private var sportKey: String {
        event.sport?.split(separator: "_").first.map(String.init)?.lowercased() ?? "sports"
    }

    private var gradient: (Color, Color) {
        sportCategoryGradients[sportKey] ?? sportDefaultGradient
    }

    private var isLive: Bool {
        event.status == "live"
    }

    private var isDone: Bool {
        event.status == "completed" || event.status == "closed"
    }

    private var sportLabel: String {
        sportCategoryDisplayName(event.sportName ?? event.sport).uppercased()
    }

    private var statusText: String {
        if isLive { return event.espn?.period ?? "LIVE" }
        if isDone {
            if let a = event.awayScore, let h = event.homeScore {
                return "\(a) - \(h)"
            }
            return "Final"
        }
        return "vs"
    }

    private var contextText: String? {
        if let feedContext, !feedContext.isEmpty { return feedContext }
        if let label = event.highlight?.label, !label.isEmpty { return label }
        if let ei = event.ei, let score = ei.score, score >= 60, let label = ei.label {
            return "Excitement Index \(score): \(label)"
        }
        if isLive { return "Live probability is moving now" }
        return nil
    }

    private var shareURL: URL {
        URL(string: eventShareURL(event.id, style: .nativeCard)) ?? bainLuckFallbackURL
    }

    private var shareMessage: String {
        if let prob = event.currentOdds?.homeProbability {
            return "\(event.awayTeam) vs \(event.homeTeam) — \(Int((prob * 100).rounded()))% on Bain Luck"
        }
        return "\(event.awayTeam) vs \(event.homeTeam) on Bain Luck"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Hero section with gradient background
            ZStack {
                LinearGradient(
                    colors: [gradient.0, gradient.1],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .overlay(
                    Text(sportEmoji(for: event.sport))
                        .font(.system(size: 96))
                        .opacity(0.08)
                )

                VStack(spacing: 0) {
                    // Top row: sport label + live badge
                    HStack {
                        Text(sportLabel)
                            .font(.system(size: 9, weight: .heavy))
                            .tracking(0.8)
                            .foregroundStyle(.white.opacity(0.78))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.black.opacity(0.24), in: Capsule())

                        Spacer()

                        if isLive {
                            HStack(spacing: 4) {
                                Circle()
                                    .fill(.white)
                                    .frame(width: 5, height: 5)
                                Text("LIVE")
                                    .font(.system(size: 9, weight: .heavy))
                            }
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.red.opacity(0.85), in: Capsule())
                        } else if isDone {
                            Text("FINAL")
                                .font(.system(size: 9, weight: .heavy))
                                .foregroundStyle(.white.opacity(0.78))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(.black.opacity(0.24), in: Capsule())
                        }
                    }

                    Spacer(minLength: 10)

                    // Matchup row
                    HStack(alignment: .center, spacing: 0) {
                        heroTeam(
                            name: event.awayTeam,
                            logo: event.awayTeamData?.logoSmall,
                            color: awayColor,
                            score: event.awayScore,
                            alignment: .leading
                        )

                        VStack(spacing: 2) {
                            Text(statusText)
                                .font(.system(size: isLive ? 11 : 13, weight: .heavy).monospacedDigit())
                                .foregroundStyle(.white.opacity(0.7))
                        }
                        .frame(width: 50)

                        heroTeam(
                            name: event.homeTeam,
                            logo: event.homeTeamData?.logoSmall,
                            color: homeColor,
                            score: event.homeScore,
                            alignment: .trailing
                        )
                    }
                }
                .padding(14)
            }
            .frame(height: 160)
            .clipShape(UnevenRoundedRectangle(topLeadingRadius: 18, topTrailingRadius: 18))

            // Bottom section
            VStack(alignment: .leading, spacing: 12) {
                // Team names
                Text("\(event.awayTeam) \(isDone ? "" : "@") \(event.homeTeam)")
                    .font(.headline.weight(.bold))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                // Probability bar — hidden once the game is done: a settled
                // game's "Win Probability" is stale/meaningless (the result is
                // the final score shown above), so we never surface a live-looking
                // split on a FINAL card (Queue #238 settled-state honesty).
                if !isDone,
                   let homeProbability = event.currentOdds?.homeProbability,
                   let awayProbability = event.currentOdds?.awayProbability {
                    VStack(spacing: 6) {
                        HStack {
                            Text(formatProbability(awayProbability))
                                .font(.title3.weight(.black).monospacedDigit())
                                .foregroundStyle(awayColor)
                            Spacer()
                            Text("Win Probability")
                                .font(.system(size: 9, weight: .medium))
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(formatProbability(homeProbability))
                                .font(.title3.weight(.black).monospacedDigit())
                                .foregroundStyle(homeColor)
                        }
                        probabilityBar(awayProbability: awayProbability, homeProbability: homeProbability)
                    }
                }

                // Context text
                if let contextText {
                    ExpandableNativeContextText(
                        text: contextText,
                        expandedText: expandedContext,
                        font: .caption,
                        onExpand: onContextExpand,
                        onCollapse: onContextCollapse
                    )
                }

                // Footer
                HStack {
                    Spacer()

                    // #490 / L2-184: confidence signal (1-3 bars) — renders nothing
                    // when absent. Same tier map + placement as the native
                    // multi-candidate kernels (Comparison/Distribution/HeatMap).
                    SignalBarsView(tier: event.confidenceTier)

                    ShareLink(
                        item: shareURL,
                        subject: Text("\(event.awayTeam) vs \(event.homeTeam)"),
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
            navigationPath.append(Route.eventDetail(id: event.id))
            onOpen?()
        }
    }

    private func heroTeam(
        name: String,
        logo: String?,
        color: Color,
        score: Int?,
        alignment: HorizontalAlignment
    ) -> some View {
        VStack(spacing: 6) {
            if let logo, let url = URL(string: logo) {
                AsyncImage(url: url) { img in
                    img.resizable().scaledToFit()
                } placeholder: { EmptyView() }
                .frame(width: 52, height: 52)
                .shadow(color: .black.opacity(0.3), radius: 6, x: 0, y: 2)
            } else {
                RoundedRectangle(cornerRadius: 12)
                    .fill(color)
                    .frame(width: 52, height: 52)
                    .shadow(color: .black.opacity(0.3), radius: 6, x: 0, y: 2)
                    .overlay(
                        Text(String(name.split(separator: " ").last ?? "").prefix(3).uppercased())
                            .font(.system(size: 12, weight: .heavy))
                            .foregroundStyle(.white)
                    )
            }

            Text(name.split(separator: " ").last.map(String.init) ?? name)
                .font(.caption.weight(.bold))
                .foregroundStyle(.white.opacity(0.92))
                .lineLimit(1)

            if let score, (isLive || isDone) {
                Text("\(score)")
                    .font(.title2.weight(.black).monospacedDigit())
                    .foregroundStyle(.white)
                    .shadow(color: .black.opacity(0.25), radius: 4, x: 0, y: 2)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func probabilityBar(awayProbability: Double, homeProbability: Double) -> some View {
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
        .frame(height: 8)
        .background(Color.barTrack.opacity(0.25), in: Capsule())
    }

    private func renderedShareImage() -> PlatformImage? {
        guard let homeProbability = event.currentOdds?.homeProbability,
              let awayProbability = event.currentOdds?.awayProbability else {
            return nil
        }
        return ShareCardRenderer.renderEventCard(
            homeTeam: event.homeTeam,
            awayTeam: event.awayTeam,
            homeProbability: homeProbability,
            awayProbability: awayProbability,
            sportName: event.sportName ?? event.sport ?? "Sports",
            homeColor: homeColor,
            awayColor: awayColor,
            status: event.status,
            homeScore: event.homeScore,
            awayScore: event.awayScore
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
}
