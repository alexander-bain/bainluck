import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "futuresDetail")

// MARK: - ViewModel

final class FuturesDetailViewModel: ObservableObject {
    @Published var market: FuturesMarketDetail?
    @Published var loading = true
    @Published var error: String?

    let marketId: Int

    init(marketId: Int) {
        self.marketId = marketId
    }

    @MainActor
    func load() async {
        loading = market == nil
        do {
            market = try await APIClient.shared.fetchFuturesDetail(id: marketId)
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Failed to load futures \(self.marketId): \(error)")
        }
    }
}

// MARK: - View

struct FuturesDetailView: View {
    let marketId: Int
    @StateObject private var vm: FuturesDetailViewModel

    init(marketId: Int) {
        self.marketId = marketId
        _vm = StateObject(wrappedValue: FuturesDetailViewModel(marketId: marketId))
    }

    var body: some View {
        Group {
            if vm.loading {
                ProgressView()
            } else if let error = vm.error, vm.market == nil {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if let market = vm.market {
                ScrollView {
                    VStack(spacing: 16) {
                        headerSection(market)
                        outcomesSection(market)
                    }
                    .padding()
                    .frame(maxWidth: 700)
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .navigationTitle("Market Details")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                PinButton(type: "future", id: marketId)
            }
        }
        .task {
            await vm.load()
        }
        .refreshable {
            await vm.load()
        }
    }

    // MARK: - Header

    private func headerSection(_ market: FuturesMarketDetail) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                if let category = market.llmSportCategory {
                    Text(category.capitalized)
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(categoryColor(market).opacity(0.9))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(categoryColor(market).opacity(0.1))
                        .clipShape(Capsule())
                }
                Spacer()
                if let source = market.source {
                    sourceBadge(source)
                }
            }

            Text(market.name)
                .font(.title3)
                .fontWeight(.semibold)

            HStack(spacing: 12) {
                if let status = market.status {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(status == "active" ? .green : .secondary)
                            .frame(width: 6, height: 6)
                        Text(status.capitalized)
                            .font(.caption2)
                            .fontWeight(.medium)
                    }
                    .foregroundStyle(status == "active" ? .green : .secondary)
                }
                HStack(spacing: 4) {
                    Image(systemName: "list.bullet")
                        .font(.system(size: 9))
                    Text("\(market.outcomes.count) outcomes")
                        .font(.caption2)
                }
                .foregroundStyle(.secondary)
                if let date = market.resolutionDate {
                    RelativeTimeText(dateString: date)
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Source Badge

    private func sourceBadge(_ source: String) -> some View {
        let label: String
        let color: Color
        switch source {
        case "polymarket":
            label = "Polymarket"
            color = .blue
        case "kalshi":
            label = "Kalshi"
            color = Color(hex: "#22c55e")
        case "odds_api":
            label = "Sportsbooks"
            color = Color(hex: "#d97706")
        default:
            label = source.capitalized
            color = .gray
        }
        return Text(label)
            .font(.system(size: 10, weight: .medium))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.12))
            .clipShape(Capsule())
    }

    // MARK: - Category Color

    private func categoryColor(_ market: FuturesMarketDetail) -> Color {
        switch market.llmSportCategory?.lowercased() {
        case "basketball": return .orange
        case "football": return .brown
        case "baseball": return .red
        case "hockey": return .cyan
        case "soccer": return .green
        case "golf": return .mint
        case "tennis": return .yellow
        case "mma", "boxing": return .red
        case "politics": return .purple
        case "entertainment": return .pink
        case "crypto": return Color(hex: "#f59e0b")
        default: return .blue
        }
    }

    // MARK: - Outcomes

    private func outcomesSection(_ market: FuturesMarketDetail) -> some View {
        let color = categoryColor(market)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "chart.bar.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                Text("All Outcomes")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                Text("\(market.outcomes.count)")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }

            ForEach(market.outcomes) { outcome in
                outcomeRow(outcome, color: color)
                if outcome.id != market.outcomes.last?.id {
                    Divider()
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func outcomeRow(_ outcome: FuturesOutcome, color: Color) -> some View {
        VStack(spacing: 4) {
            HStack(alignment: .top) {
                if let rank = outcome.rank {
                    Text("#\(rank)")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                        .frame(width: 28, alignment: .leading)
                }

                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(outcome.name)
                            .font(.subheadline)
                            .fontWeight(.medium)
                        if outcome.isWinner == true {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption)
                                .foregroundStyle(.green)
                        }
                    }

                    HStack(spacing: 8) {
                        if let odds = outcome.americanOdds {
                            Text(odds > 0 ? "+\(odds)" : "\(odds)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        changeIndicator(outcome)
                        if let opening = outcome.openingProbability, let current = outcome.probability {
                            let diff = current - opening
                            if abs(diff) >= 0.005 {
                                Text("from \(formatProbability(opening))")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                }

                Spacer()

                if let prob = outcome.probability {
                    Text(formatProbability(prob))
                        .font(.title3)
                        .fontWeight(.semibold)
                        .monospacedDigit()
                }
            }

            // Mini probability bar
            if let prob = outcome.probability {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Color.barTrack)
                        Capsule()
                            .fill(color.opacity(0.5))
                            .frame(width: geo.size.width * prob)
                    }
                }
                .frame(height: 4)
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func changeIndicator(_ outcome: FuturesOutcome) -> some View {
        if let change = outcome.probabilityChange24h, abs(change) >= 0.005 {
            HStack(spacing: 1) {
                Image(systemName: change > 0 ? "arrow.up" : "arrow.down")
                    .font(.system(size: 8))
                Text(formatProbability(abs(change)))
                    .font(.caption2)
            }
            .foregroundStyle(change > 0 ? .green : .red)
        }
    }
}
