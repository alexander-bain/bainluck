import Combine
import SwiftUI

struct AboutView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                // Hero
                VStack(spacing: 4) {
                    HStack(spacing: 8) {
                        Text("🍀").font(.system(size: 24))
                        Text("Bain Luck").font(.title2.bold())
                    }
                    Text("The most engaging way to explore what the world thinks will happen.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)

                    HStack(spacing: 16) {
                        HStack(spacing: 2) {
                            Text("60%").font(.callout).fontWeight(.black).monospacedDigit()
                            Text("Celtics").font(.caption2).foregroundStyle(.secondary)
                        }
                        Text("vs").font(.caption2).foregroundStyle(.tertiary)
                        HStack(spacing: 2) {
                            Text("40%").font(.callout).fontWeight(.black).monospacedDigit().foregroundStyle(.secondary)
                            Text("76ers").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 6).padding(.horizontal, 12)
                    .background(Color.cardBackgroundDark)
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                    Text("Not \"-150 / +130\" — just probabilities.")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity)

                // What You Can Explore
                VStack(alignment: .leading, spacing: 6) {
                    Text("What You Can Explore").font(.subheadline.weight(.semibold))
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 6)], spacing: 6) {
                        ForEach(categories, id: \.label) { cat in
                            HStack(spacing: 6) {
                                Text(cat.emoji).font(.callout)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(cat.label).font(.caption2).fontWeight(.semibold)
                                    Text(cat.desc).font(.system(size: 9)).foregroundStyle(.secondary).lineLimit(1)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(8)
                            .background(Color.cardBackground)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                    }
                }

                // How It Works + By the Numbers side by side
                HStack(alignment: .top, spacing: 8) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("How It Works").font(.subheadline.weight(.semibold))
                        Text("8 sources — 20+ sportsbooks, Kalshi, Polymarket, ESPN, stat models — blended into one probability.")
                            .font(.system(size: 9)).foregroundStyle(.secondary)
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 4) {
                        ForEach(stats, id: \.label) { stat in
                            VStack(spacing: 1) {
                                Text(stat.value).font(.caption).fontWeight(.black).monospacedDigit()
                                Text(stat.label).font(.system(size: 8)).foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                            .background(Color.cardBackground)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                        }
                    }
                    .frame(maxWidth: 120)
                }

                // Philosophy
                VStack(alignment: .leading, spacing: 6) {
                    Text("Philosophy").font(.subheadline.weight(.semibold))
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(principles, id: \.title) { p in
                            HStack(alignment: .center, spacing: 6) {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 7, weight: .bold))
                                    .foregroundStyle(.green)
                                HStack(spacing: 0) {
                                    Text(p.title)
                                        .font(.caption2)
                                        .fontWeight(.semibold)
                                    Text(" — \(p.desc)")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                    .padding(8)
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }

                // Disclaimer
                VStack(alignment: .leading, spacing: 2) {
                    Text("Disclaimer").font(.caption2).fontWeight(.semibold)
                    Text("Bain Luck shows prediction market probabilities for informational and entertainment purposes only. No betting, wagering, or real-money transactions are facilitated through this app.")
                        .font(.system(size: 9)).foregroundStyle(.secondary)
                }
                .padding(8)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 8))

                // Need Help?
                VStack(alignment: .leading, spacing: 6) {
                    Text("Need Help?").font(.subheadline.weight(.semibold))
                    Text("Questions, feedback, or bug reports? Reach out and we'll get back to you within 24 hours.")
                        .font(.system(size: 9)).foregroundStyle(.secondary)
                    if let mailURL = URL(string: "mailto:bugs@bainluck.com") {
                        Link(destination: mailURL) {
                            HStack(spacing: 4) {
                                Image(systemName: "envelope.fill").font(.caption2)
                                Text("bugs@bainluck.com").font(.caption2).fontWeight(.semibold)
                            }
                            .foregroundStyle(.blue)
                        }
                        .buttonStyle(.plain)
                    }
                    Text("You can also shake your device to send a bug report with a screenshot directly to our team.")
                        .font(.system(size: 9)).foregroundStyle(.tertiary)
                }
                .padding(8)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 8))

                // Privacy Policy
                if let url = URL(string: "https://bainluck.com/privacy") {
                    Link(destination: url) {
                        HStack {
                            Image(systemName: "hand.raised.fill").font(.caption2).foregroundStyle(.secondary)
                            Text("Privacy Policy").font(.caption).fontWeight(.semibold)
                            Spacer()
                            Image(systemName: "arrow.up.right").font(.system(size: 9)).foregroundStyle(.secondary)
                        }
                        .padding(10)
                        .background(Color.cardBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal).padding(.bottom, 16)
        }
        .navigationTitle("About")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .onAppear { AnalyticsService.trackScreen(name: "about", type: "about") }
    }

    private let categories: [(emoji: String, label: String, desc: String)] = [
        ("🏀", "Sports", "NBA, NFL, MLB, NHL, Soccer, Golf, MMA"),
        ("📈", "Markets", "Kalshi + Polymarket, unified"),
        ("🌦️", "Weather", "Rainfall, temperature, tornado"),
        ("💰", "Economics", "Fed rates, GDP, inflation"),
        ("🗳️", "Politics", "Elections, policy, geopolitics"),
        ("🎬", "Entertainment", "Awards, box office, culture"),
    ]

    private let stats: [(value: String, label: String)] = [
        ("8", "Sources"),
        ("130K+", "Markets"),
        ("20+", "Books"),
        ("~32s", "Live"),
    ]

    private let principles: [(title: String, desc: String)] = [
        ("Probability-first", "probabilities, not moneylines"),
        ("Fans first", "context, not financial advice"),
        ("Source transparency", "see where every number comes from"),
        ("Cross-source", "aggregate across all markets"),
        ("No gambling", "informational only, always"),
    ]
}
