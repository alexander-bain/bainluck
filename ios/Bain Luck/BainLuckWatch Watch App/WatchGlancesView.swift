import Combine
import os.log
import SwiftUI
import WatchKit

private let logger = Logger(subsystem: "com.bainluck.watch", category: "Glances")

struct WatchGlancesView: View {
    @StateObject private var vm = WatchGlancesViewModel()

    var body: some View {
        ScrollView {
            if vm.loading && vm.markets.isEmpty {
                ProgressView()
                    .padding(.top, 20)
            } else if let error = vm.error, vm.markets.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.title3)
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button("Retry") { Task { await vm.load(force: true) } }
                        .font(.caption2)
                }
                .padding(.top, 20)
            } else if vm.markets.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                    Text("No markets yet")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)
            } else {
                LazyVStack(spacing: 4) {
                    ForEach(vm.markets) { market in
                        glanceRow(market)
                    }
                    if let ago = vm.lastUpdated {
                        Text(ago)
                            .font(.system(size: 9))
                            .foregroundStyle(.tertiary)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 4)
                    }
                }
                .padding(.horizontal, 4)
            }
        }
        .navigationTitle("Trending")
        .task { await vm.load() }
    }

    private func glanceRow(_ market: WatchMarket) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(market.dotColor)
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 1) {
                Text(market.name)
                    .font(.system(size: 14, weight: .semibold))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Text(market.leader)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 2)

            VStack(alignment: .trailing, spacing: 1) {
                Text("\(market.probability)%")
                    .font(.system(size: 17, weight: .bold, design: .rounded))

                if let movement = market.movement, movement != 0 {
                    HStack(spacing: 1) {
                        Image(systemName: movement > 0 ? "arrow.up" : "arrow.down")
                            .font(.system(size: 10, weight: .bold))
                        Text("\(abs(Int((movement * 100).rounded())))")
                            .font(.system(size: 11, weight: .semibold))
                    }
                    .foregroundStyle(movement > 0 ? .green : .red)
                }
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 8)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

struct WatchMarket: Identifiable {
    let id: Int
    let name: String
    let leader: String
    let probability: Int
    let movement: Double?
    let category: String?

    var dotColor: Color {
        switch category?.lowercased() {
        case "basketball", "football", "baseball", "hockey": return .green
        case "politics", "geopolitics": return .purple
        case "economics": return .blue
        case "weather": return .cyan
        case "entertainment": return .orange
        default: return .gray
        }
    }
}

@MainActor
final class WatchGlancesViewModel: ObservableObject {
    @Published var markets: [WatchMarket] = []
    @Published var loading = true
    @Published var error: String?
    @Published var lastUpdated: String?

    func load(force: Bool = false) async {
        logger.info("Glances load started (force=\(force), existing=\(self.markets.count))")
        if markets.isEmpty { loading = true }
        error = nil
        defer { loading = false }

        do {
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 5, forceRefresh: force)
            logger.info("Glances feed received: \(feed.items.count) items")
            markets = feed.items.compactMap { item -> WatchMarket? in
                guard let f = item.futures,
                      let leader = f.topOutcomes?.first,
                      let prob = leader.probability else { return nil }
                return WatchMarket(
                    id: f.id,
                    name: f.name,
                    leader: leader.name,
                    probability: Int((prob * 100).rounded()),
                    movement: leader.movement,
                    category: f.llmSportCategory
                )
            }
            logger.info("Glances: \(self.markets.count) markets from \(feed.items.count) items")
            if let t = await WatchAPIClient.shared.lastFetchTime {
                let ago = Int(Date().timeIntervalSince(t))
                lastUpdated = ago < 5 ? "Just now" : "\(ago)s ago"
            }
            WKInterfaceDevice.current().play(.click)
        } catch {
            logger.error("Glances load failed: \(error.localizedDescription)")
            if markets.isEmpty {
                self.error = "Couldn't load"
            }
        }
    }
}
