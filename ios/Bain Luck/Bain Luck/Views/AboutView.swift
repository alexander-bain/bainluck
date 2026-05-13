import SwiftUI

struct AboutView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                // Hero
                VStack(spacing: 12) {
                    Text("🍀")
                        .font(.system(size: 48))
                    Text("Bain Luck")
                        .font(.largeTitle).bold()
                    Text("The most engaging way to explore what the world thinks will happen.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)

                    HStack(spacing: 24) {
                        VStack {
                            Text("60%").font(.title).fontWeight(.black).monospacedDigit()
                            Text("Celtics").font(.caption2).foregroundStyle(.secondary)
                        }
                        Text("vs").font(.subheadline).foregroundStyle(.tertiary)
                        VStack {
                            Text("40%").font(.title).fontWeight(.black).monospacedDigit().foregroundStyle(.secondary)
                            Text("76ers").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    .padding()
                    .background(Color.cardBackgroundDark)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    Text("Not \"-150 / +130\" — just probabilities.")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity)
                .padding(.bottom, 8)

                // What You Can Explore
                VStack(alignment: .leading, spacing: 12) {
                    Text("What You Can Explore").font(.headline)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                        ForEach(categories, id: \.label) { cat in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(cat.emoji).font(.title2)
                                Text(cat.label).font(.caption).fontWeight(.semibold)
                                Text(cat.desc).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .background(Color.cardBackground)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                        }
                    }
                }

                // How It Works
                VStack(alignment: .leading, spacing: 12) {
                    Text("How It Works").font(.headline)
                    VStack(alignment: .leading, spacing: 8) {
                        Text("We ingest data from 8 sources — 20+ sportsbooks, Kalshi, Polymarket, ESPN, MLB Stats, DataGolf, and stat models — then blend them into a single probability.")
                            .font(.subheadline).foregroundStyle(.secondary)
                        Text("You see what the market as a whole thinks, not just one bookmaker's opinion.")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                    .padding()
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }

                // By the Numbers
                VStack(alignment: .leading, spacing: 12) {
                    Text("By the Numbers").font(.headline)
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        ForEach(stats, id: \.label) { stat in
                            VStack(spacing: 4) {
                                Text(stat.value).font(.title3).fontWeight(.black).monospacedDigit()
                                Text(stat.label).font(.caption2).foregroundStyle(.secondary).multilineTextAlignment(.center)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(Color.cardBackground)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                        }
                    }
                }

                // Philosophy
                VStack(alignment: .leading, spacing: 12) {
                    Text("Philosophy").font(.headline)
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(principles, id: \.title) { p in
                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: "checkmark")
                                    .font(.caption2).fontWeight(.bold)
                                    .foregroundStyle(.green)
                                    .frame(width: 16)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(p.title).font(.caption).fontWeight(.semibold)
                                    Text(p.desc).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                    .padding()
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }

                // Disclaimer
                VStack(alignment: .leading, spacing: 6) {
                    Text("Disclaimer").font(.caption).fontWeight(.semibold)
                    Text("Bain Luck is for informational and entertainment purposes only. We do not encourage or facilitate gambling. Win probabilities are derived from publicly available data and do not constitute betting advice.")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                .padding()
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                // Privacy Policy
                if let url = URL(string: "https://bainluck.com/privacy") {
                    Link(destination: url) {
                        HStack {
                            Image(systemName: "hand.raised.fill")
                                .foregroundStyle(.secondary)
                            Text("Privacy Policy")
                                .font(.subheadline).fontWeight(.semibold)
                            Spacer()
                            Image(systemName: "arrow.up.right")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding()
                        .background(Color.cardBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding()
        }
        .navigationTitle("About")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .onAppear { AnalyticsService.trackScreen(name: "about", type: "about") }
    }

    private let categories: [(emoji: String, label: String, desc: String)] = [
        ("🏀", "Sports", "NBA, NFL, MLB, NHL, Soccer, Golf, MMA"),
        ("📈", "Markets", "Kalshi + Polymarket, unified"),
        ("🌦️", "Weather", "Rainfall, temperature, tornado bets"),
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
        ("Probability-first", "Every number is a probability, not a moneyline"),
        ("Fans first", "Context for fans, not betting advice"),
        ("Source transparency", "See where every probability comes from"),
        ("Cross-source", "Aggregate across all markets"),
        ("No gambling", "Informational only, always"),
    ]
}
