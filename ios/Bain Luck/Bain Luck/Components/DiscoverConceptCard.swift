import SwiftUI

/// Native Discover card for an event-concept marquee hub — Tour de France, FIFA
/// World Cup, a UFC fight card, an awards ceremony. Concept cards are hubs, not
/// single markets, so this card is probability-free: it leads with the marquee
/// name and (post-settlement) the graded champion, mirroring the web
/// `ConceptFeedCard` treatment (FeedCard.tsx).
///
/// L2-179: before this card existed, the native decode path silently discarded
/// every `concept`-type feed item, which is why the marquee never appeared on
/// device. See FeedModels.swift `FeedItem.init(from:)`.
struct NativeConceptDiscoverCard: View {
    let data: FeedConceptData
    let headline: String?
    let feedContext: String?
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)?

    private var gradient: (Color, Color) {
        sportCategoryGradients[data.domain?.lowercased() ?? ""] ?? sportDefaultGradient
    }

    /// True only in the post-settlement WHAT-HIT window — the result is the story
    /// (settled-means-settled grammar). Wins over any live framing.
    private var whatHit: Bool { data.marqueeWhathit == true }
    private var isLive: Bool { !whatHit && data.status == "live" }
    private var winner: String? {
        guard let w = data.winner?.trimmingCharacters(in: .whitespacesAndNewlines), !w.isEmpty else { return nil }
        return w
    }
    private var resultSummary: String? {
        guard let s = data.resultSummary?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty else { return nil }
        return s
    }
    private var isMarquee: Bool { data.isMajor == true || data.isMarquee == true }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .topLeading) {
                LinearGradient(
                    colors: [gradient.0, gradient.1],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                VStack(alignment: .leading, spacing: 8) {
                    // Badge row: FINAL / LIVE / Marquee + domain label.
                    HStack(spacing: 6) {
                        if whatHit {
                            badge("🏁 FINAL", background: .white.opacity(0.2))
                        } else if isLive {
                            HStack(spacing: 4) {
                                Circle()
                                    .fill(Color.red)
                                    .frame(width: 6, height: 6)
                                Text("LIVE")
                                    .font(.caption2.bold())
                            }
                            .foregroundStyle(.white)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(.white.opacity(0.18))
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                        }

                        if isMarquee {
                            badge("MARQUEE", background: .white.opacity(0.15))
                        }

                        // The countdown/live headline is suppressed once settled —
                        // the result carries the card instead.
                        if let headline, !headline.isEmpty, !isLive, !whatHit {
                            badge(headline, background: .white.opacity(0.15))
                        }

                        Spacer(minLength: 0)

                        if let domain = data.domain, !domain.isEmpty {
                            Text(domain.uppercased())
                                .font(.caption2.bold())
                                .foregroundStyle(.white.opacity(0.7))
                                .lineLimit(1)
                        }
                    }

                    Text(properTitleCase(data.name))
                        .font(.headline.bold())
                        .foregroundStyle(.white)
                        .lineLimit(2)

                    if whatHit {
                        // Result-first: champion + "WON" chip where present, else an
                        // honest settled line. Never fabricated.
                        if let winner {
                            HStack(spacing: 6) {
                                Text(winner)
                                    .font(.subheadline.bold())
                                    .foregroundStyle(.white)
                                    .lineLimit(1)
                                Text("WON")
                                    .font(.caption2.bold())
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(.white.opacity(0.22))
                                    .clipShape(RoundedRectangle(cornerRadius: 4))
                                if let resultSummary {
                                    Text(resultSummary)
                                        .font(.caption)
                                        .foregroundStyle(.white.opacity(0.75))
                                        .lineLimit(1)
                                }
                            }
                        } else {
                            Text(resultSummary ?? "Final result — see the recap")
                                .font(.caption)
                                .foregroundStyle(.white.opacity(0.8))
                                .lineLimit(2)
                        }
                    }
                }
                .padding(14)
            }

            if let context = feedContext, !context.isEmpty, !whatHit {
                Text(context)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.systemBackground)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.08), radius: 8, y: 4)
        .contentShape(Rectangle())
        .onTapGesture { navigate() }
    }

    @ViewBuilder
    private func badge(_ text: String, background: Color) -> some View {
        Text(text)
            .font(.caption2.bold())
            .foregroundStyle(.white)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(background)
            .clipShape(RoundedRectangle(cornerRadius: 4))
    }

    private func navigate() {
        onOpen?()
        // No native concept-hub view exists yet (web opens /event/{key}); land on
        // the closest existing surface — the sport category for the concept's
        // domain — mirroring the tournament card's category landing.
        guard let domain = data.domain?.lowercased(), !domain.isEmpty else { return }
        if domain == "golf" {
            navigationPath.append(Route.golfCategory)
        } else {
            navigationPath.append(Route.sportCategory(key: domain, name: properTitleCase(domain)))
        }
    }
}
