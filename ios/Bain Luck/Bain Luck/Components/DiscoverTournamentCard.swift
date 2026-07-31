import SwiftUI

struct NativeTournamentDiscoverCard: View {
    let data: FeedTournamentData
    let feedContext: String?
    @Binding var navigationPath: NavigationPath

    private var gradient: (Color, Color) {
        sportCategoryGradients["golf"] ?? sportDefaultGradient
    }

    /// True only in the T+36h post-settlement WHAT-HIT window. L2-224: the field was
    /// being dropped at decode, so a finished marquee rendered here with full live
    /// framing — a hero win probability plus a "+Npp today" movement line — for a
    /// tournament that was over ("settled means settled"). This mirrors the web
    /// treatment field for field (`TournamentCard.tsx`): a FINAL chip, a WON chip on
    /// the leader, the "Champion" label, and no live movement once settled.
    private var whatHit: Bool { data.marqueeWhathit == true }

    private var leader: FeedTournamentGolfer? {
        data.golfers?.first
    }

    private var leaderProbability: Double {
        (leader?.probability ?? 0) / 100.0
    }

    private var tourBadge: String {
        if data.isMajor == true { return "MAJOR" }
        guard let raw = data.tourLabel ?? data.tour, !raw.isEmpty else { return "GOLF" }
        // Map raw enum ("korn_ferry") to a display name, then uppercase for the
        // badge treatment ("KORN FERRY TOUR") — never leak the underscore enum.
        return golfTourDisplayName(for: raw).uppercased()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .topLeading) {
                LinearGradient(
                    colors: [gradient.0, gradient.1],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(tourBadge)
                            .font(.caption2.bold())
                            .foregroundStyle(.white.opacity(0.7))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(.white.opacity(0.15))
                            .clipShape(RoundedRectangle(cornerRadius: 4))

                        if whatHit {
                            Text("🏁 FINAL")
                                .font(.caption2.bold())
                                .foregroundStyle(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(.white.opacity(0.2))
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                        }

                        Spacer()

                        if let venue = data.venue {
                            Text(venue)
                                .font(.caption2)
                                .foregroundStyle(.white.opacity(0.6))
                                .lineLimit(1)
                        }
                    }

                    Text(properTitleCase(data.name))
                        .font(.headline.bold())
                        .foregroundStyle(.white)
                        .lineLimit(2)

                    if let leader {
                        HStack(spacing: 8) {
                            Text("\(Int(leader.probability.rounded()))%")
                                .font(.title.bold())
                                .foregroundStyle(.white)

                            VStack(alignment: .leading, spacing: 1) {
                                HStack(spacing: 6) {
                                    Text(leader.name)
                                        .font(.subheadline.bold())
                                        .foregroundStyle(.white)
                                    if whatHit {
                                        Text("WON")
                                            .font(.caption2.bold())
                                            .foregroundStyle(.white)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(.white.opacity(0.22))
                                            .clipShape(RoundedRectangle(cornerRadius: 4))
                                    }
                                }
                                if whatHit {
                                    Text("Champion")
                                        .font(.caption2)
                                        .foregroundStyle(.white.opacity(0.75))
                                } else if let move = leader.movement24h, abs(move) >= 0.5 {
                                    // No live "% today" movement once settled — the
                                    // result is fixed (mirrors TournamentCard.tsx:128).
                                    Text(move > 0 ? "+\(String(format: "%.1f", move))pp today" : "\(String(format: "%.1f", move))pp today")
                                        .font(.caption2)
                                        .foregroundStyle(move > 0 ? .green : .red)
                                }
                            }
                        }
                    }

                    if let golfers = data.golfers, golfers.count > 1 {
                        HStack(spacing: 12) {
                            ForEach(golfers.dropFirst().prefix(3)) { golfer in
                                HStack(spacing: 3) {
                                    Text("\(Int(golfer.probability.rounded()))%")
                                        .font(.caption.bold())
                                        .foregroundStyle(.white.opacity(0.9))
                                    Text(golfer.name.components(separatedBy: " ").last ?? golfer.name)
                                        .font(.caption)
                                        .foregroundStyle(.white.opacity(0.7))
                                        .lineLimit(1)
                                }
                            }
                        }
                    }
                }
                .padding(14)
            }

            if let context = feedContext, !context.isEmpty {
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
        .onTapGesture {
            navigationPath.append(Route.sportCategory(key: "golf", name: "Golf"))
        }
    }
}
