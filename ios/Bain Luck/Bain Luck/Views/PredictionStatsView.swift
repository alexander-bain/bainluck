import SwiftUI

struct PredictionStatsView: View {
    @State private var stats: DetailedPredictionStats? = nil
    @State private var loading = true
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var contentMaxWidth: CGFloat {
        #if os(macOS)
        return 700
        #else
        return sizeClass == .regular ? 700 : .infinity
        #endif
    }

    var body: some View {
        ScrollView {
            if loading {
                ProgressView()
                    .padding(.top, 60)
            } else if let stats {
                VStack(spacing: 20) {
                    heroSection(stats)
                    streakSection(stats)
                    if !stats.byCategory.isEmpty {
                        categoryBreakdown(stats)
                    }
                    badgesSection(stats)
                }
                .padding()
                .frame(maxWidth: contentMaxWidth)
                .frame(maxWidth: .infinity)
            } else {
                VStack(spacing: 12) {
                    Text("🎯")
                        .font(.system(size: 48))
                    Text("No predictions yet")
                        .font(.headline)
                    Text("Play Higher/Lower in Discover to start tracking your accuracy!")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding(.top, 60)
                .padding(.horizontal, 40)
            }
        }
        .navigationTitle("Prediction Stats")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .onAppear { AnalyticsService.trackScreen(name: "prediction_stats", type: "prediction_stats") }
        .task { await loadStats() }
        .refreshable { await loadStats() }
    }

    @MainActor
    private func loadStats() async {
        loading = true
        do {
            stats = try await APIClient.shared.fetchDetailedPredictionStats()
        } catch { }
        loading = false
    }

    private func heroSection(_ stats: DetailedPredictionStats) -> some View {
        VStack(spacing: 8) {
            Text("\(Int(stats.accuracy * 100))%")
                .font(.system(size: 64, weight: .black, design: .rounded).monospacedDigit())
                .foregroundStyle(stats.accuracy >= 0.6 ? .green : stats.accuracy >= 0.45 ? .primary : .red)

            Text("Accuracy")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            HStack(spacing: 24) {
                statPill(value: "\(stats.total)", label: "Total")
                statPill(value: "\(stats.correct)", label: "Correct")
                statPill(value: "\(stats.total - stats.correct)", label: "Wrong")
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func statPill(value: String, label: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.title3.weight(.bold).monospacedDigit())
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private func streakSection(_ stats: DetailedPredictionStats) -> some View {
        HStack(spacing: 16) {
            VStack(spacing: 4) {
                Text("🔥")
                    .font(.system(size: 28))
                Text("\(stats.currentStreak)")
                    .font(.title.weight(.black).monospacedDigit())
                Text("Current Streak")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))

            VStack(spacing: 4) {
                Text("⭐")
                    .font(.system(size: 28))
                Text("\(stats.bestStreak)")
                    .font(.title.weight(.black).monospacedDigit())
                Text("Best Streak")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
    }

    private func categoryBreakdown(_ stats: DetailedPredictionStats) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("By Category")
                .font(.headline)

            ForEach(stats.byCategory.sorted(by: { $0.value.total > $1.value.total }), id: \.key) { cat, data in
                HStack {
                    Text(categoryEmoji(cat))
                        .font(.system(size: 14))
                    Text(cat.capitalized)
                        .font(.subheadline)
                    Spacer()
                    Text("\(data.correct)/\(data.total)")
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(.secondary)
                    Text("\(Int(data.accuracy * 100))%")
                        .font(.subheadline.weight(.bold).monospacedDigit())
                        .foregroundStyle(data.accuracy >= 0.6 ? .green : data.accuracy >= 0.45 ? .primary : .red)
                        .frame(width: 40, alignment: .trailing)
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func badgesSection(_ stats: DetailedPredictionStats) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Badges")
                .font(.headline)

            if stats.badges.isEmpty {
                Text("Keep playing to earn badges!")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 100))], spacing: 12) {
                    ForEach(stats.badges, id: \.id) { badge in
                        VStack(spacing: 4) {
                            Text(badge.emoji)
                                .font(.system(size: 28))
                            Text(badge.name)
                                .font(.caption2.weight(.semibold))
                                .lineLimit(1)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(8)
                        .background(Color.cardBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.orange.opacity(0.3)))
                    }
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func categoryEmoji(_ cat: String) -> String {
        switch cat.lowercased() {
        case "basketball": return "🏀"
        case "football", "americanfootball": return "🏈"
        case "baseball": return "⚾"
        case "hockey", "icehockey": return "🏒"
        case "soccer": return "⚽"
        case "golf": return "⛳"
        case "mma": return "🥊"
        case "tennis": return "🎾"
        case "politics": return "🏛"
        case "economics": return "📈"
        case "tech": return "💻"
        case "weather": return "🌤"
        default: return "📊"
        }
    }
}
