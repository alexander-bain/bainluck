import Combine
import SwiftUI

struct WatchGlancesView: View {
    @StateObject private var vm = WatchGlancesViewModel()

    var body: some View {
        ScrollView {
            if vm.loading {
                ProgressView()
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
                }
                .padding(.horizontal, 4)
            }
        }
        .navigationTitle("Following")
        .task { await vm.load() }
    }

    private func glanceRow(_ market: WatchMarket) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(market.dotColor)
                .frame(width: 6, height: 6)

            VStack(alignment: .leading, spacing: 1) {
                Text(market.name)
                    .font(.system(size: 12, weight: .semibold))
                    .lineLimit(1)
                Text(market.leader)
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 2)

            VStack(alignment: .trailing, spacing: 1) {
                Text("\(market.probability)%")
                    .font(.system(size: 13, weight: .bold, design: .rounded))

                if let movement = market.movement, movement != 0 {
                    HStack(spacing: 1) {
                        Image(systemName: movement > 0 ? "arrow.up" : "arrow.down")
                            .font(.system(size: 7, weight: .bold))
                        Text("\(abs(Int((movement * 100).rounded())))")
                            .font(.system(size: 9, weight: .semibold))
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

    func load() async {
        loading = true
        defer { loading = false }

        do {
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 20)
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
        } catch {
            markets = []
        }
    }
}
