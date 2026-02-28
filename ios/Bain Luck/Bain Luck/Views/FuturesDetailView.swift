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
                }
            }
        }
        .navigationTitle("Market Details")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            await vm.load()
        }
        .refreshable {
            await vm.load()
        }
    }

    // MARK: - Header

    private func headerSection(_ market: FuturesMarketDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(market.llmSportCategory?.capitalized ?? "Futures")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                if let source = market.source {
                    Text(source.capitalized)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Text(market.name)
                .font(.title3)
                .fontWeight(.semibold)

            HStack(spacing: 12) {
                if let status = market.status {
                    Label(status.capitalized, systemImage: "circle.fill")
                        .font(.caption2)
                        .foregroundStyle(status == "active" ? .green : .secondary)
                }
                Label("\(market.outcomes.count) outcomes", systemImage: "list.bullet")
                    .font(.caption2)
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

    // MARK: - Outcomes

    private func outcomesSection(_ market: FuturesMarketDetail) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("All Outcomes")
                .font(.subheadline)
                .fontWeight(.medium)

            ForEach(market.outcomes) { outcome in
                outcomeRow(outcome)
                if outcome.id != market.outcomes.last?.id {
                    Divider()
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func outcomeRow(_ outcome: FuturesOutcome) -> some View {
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
                            .fill(.blue.opacity(0.6))
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
