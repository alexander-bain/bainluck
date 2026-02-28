import SwiftUI
import os

private let logger = Logger(subsystem: "com.bainluck", category: "feed")

struct ContentView: View {
    @State private var items: [FeedItem] = []
    @State private var total = 0
    @State private var error: String?
    @State private var loading = true

    var body: some View {
        NavigationStack {
            Group {
                if loading {
                    ProgressView("Loading feed...")
                } else if let error {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.largeTitle)
                            .foregroundStyle(.red)
                        Text(error)
                            .font(.caption)
                            .multilineTextAlignment(.center)
                    }
                    .padding()
                } else {
                    List {
                        Section("Feed (\(total) items)") {
                            ForEach(items) { item in
                                feedRow(item)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Bain Luck")
        }
        .task {
            await loadFeed()
        }
    }

    @ViewBuilder
    private func feedRow(_ item: FeedItem) -> some View {
        if item.type == "event", let e = item.event {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(e.sportName ?? e.sport ?? "")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(e.status ?? "")
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(statusColor(e.status).opacity(0.2))
                        .clipShape(Capsule())
                }
                Text("\(e.awayTeam) @ \(e.homeTeam)")
                    .font(.headline)
                if let odds = e.currentOdds,
                   let away = odds.awayProbability,
                   let home = odds.homeProbability {
                    HStack {
                        Text("\(Int(away * 100))%")
                        GeometryReader { geo in
                            HStack(spacing: 0) {
                                Rectangle()
                                    .fill(Color(hex: e.awayTeamData?.primaryColor ?? "#888"))
                                    .frame(width: geo.size.width * away)
                                Rectangle()
                                    .fill(Color(hex: e.homeTeamData?.primaryColor ?? "#888"))
                                    .frame(width: geo.size.width * home)
                            }
                            .clipShape(Capsule())
                        }
                        .frame(height: 8)
                        Text("\(Int(home * 100))%")
                    }
                    .font(.caption)
                }
                if let reason = item.reason, !reason.isEmpty {
                    Text(reason)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 4)
        } else if item.type == "futures", let f = item.futures {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(f.llmSportCategory ?? "futures")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(f.source ?? "")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Text(f.name)
                    .font(.headline)
                if let outcomes = f.topOutcomes?.prefix(3) {
                    ForEach(Array(outcomes)) { o in
                        HStack {
                            Text(o.name)
                                .font(.caption)
                            Spacer()
                            if let p = o.probability {
                                Text("\(Int(p * 100))%")
                                    .font(.caption)
                                    .fontWeight(.medium)
                            }
                        }
                    }
                }
            }
            .padding(.vertical, 4)
        }
    }

    private func statusColor(_ status: String?) -> Color {
        switch status {
        case "live": return .green
        case "completed", "closed": return .gray
        default: return .blue
        }
    }

    private func loadFeed() async {
        do {
            let feed = try await APIClient.shared.fetchFeed(limit: 10)
            items = feed.items
            total = feed.total
            loading = false
            logger.info("Feed loaded: \(feed.items.count) items, \(feed.total) total")
            for (i, item) in feed.items.prefix(5).enumerated() {
                if let e = item.event {
                    logger.info("  [\(i)] EVENT: \(e.awayTeam) @ \(e.homeTeam) (\(e.status ?? "?")) colors=\(e.homeTeamData?.primaryColor ?? "nil")")
                } else if let f = item.futures {
                    logger.info("  [\(i)] FUTURES: \(f.name) (\(f.topOutcomes?.count ?? 0) outcomes)")
                }
            }
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Feed error: \(error)")
        }
    }
}

// MARK: - Color Hex Extension

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var rgb: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }
}
