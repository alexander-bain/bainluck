import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "futuresDetail")

// MARK: - Sort

private enum FuturesSortField: String, CaseIterable {
    case probability = "Probability"
    case change = "24h Change"
    case name = "Name"
}

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
    @State private var sortField: FuturesSortField = .probability
    @State private var sortAscending = false
    @State private var showAllOutcomes = false

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

                        // Probability evolution chart
                        // Show for any market with outcomes (>= 1), including
                        // binary markets that have only a single "Yes" outcome
                        if market.outcomes.count >= 1 {
                            TournamentChartView(
                                marketId: marketId,
                                hours: 168,
                                tournamentStart: golfTournamentStart(market),
                                tournamentEnd: golfTournamentEnd(market)
                            )
                        }

                        leaderSection(market)
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
            ToolbarItem(placement: .confirmationAction) {
                HStack(spacing: 4) {
                    ShareLink(item: URL(string: "https://bainluck.com/futures/\(marketId)")!) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.system(size: 14))
                    }
                    PinButton(type: "future", id: marketId)
                }
            }
        }
        .task {
            await vm.load()
            if let market = vm.market {
                AnalyticsService.trackScreen(name: "futures_detail", type: "futures_detail")
                AnalyticsService.trackFuturesDetailView(marketId: marketId, category: market.category)
            }
        }
        .refreshable {
            await vm.load()
        }
    }

    // MARK: - Header

    private func headerSection(_ market: FuturesMarketDetail) -> some View {
        let isResolved = market.status == "resolved"

        return VStack(alignment: .leading, spacing: 10) {
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
                if isResolved {
                    Text("Resolved")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.secondary.opacity(0.1))
                        .clipShape(Capsule())
                }
                if let source = market.source {
                    sourceBadge(source)
                }
            }

            Text(market.name)
                .font(.title3)
                .fontWeight(.semibold)

            if let desc = market.description, !desc.isEmpty {
                Text(desc)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            // Info strip
            HStack(spacing: 12) {
                if let status = market.status, !isResolved {
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

                if let commence = market.commenceTime, let date = commence.asDate {
                    HStack(spacing: 3) {
                        Image(systemName: "calendar")
                            .font(.system(size: 9))
                        Text("Starts \(date, style: .date)")
                            .font(.caption2)
                    }
                    .foregroundStyle(.secondary)
                }

                if let resolution = market.resolutionDate {
                    RelativeTimeText(dateString: resolution)
                }
            }

            if let updatedAt = market.updatedAt, let date = updatedAt.asDate {
                Text("Updated \(date, format: .dateTime.month(.abbreviated).day().hour().minute())")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            // Bookmakers
            if let bookmakers = market.bookmakers, !bookmakers.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Divider()
                    Text("Probabilities from \(bookmakers.count) sportsbook\(bookmakers.count != 1 ? "s" : "")")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(bookmakers, id: \.self) { bk in
                                Text(formatBookmaker(bk))
                                    .font(.system(size: 10))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(Color.secondary.opacity(0.08))
                                    .clipShape(Capsule())
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Current Leader

    @ViewBuilder
    private func leaderSection(_ market: FuturesMarketDetail) -> some View {
        if let leader = market.outcomes.max(by: { ($0.probability ?? 0) < ($1.probability ?? 0) }),
           let prob = leader.probability {
            VStack(alignment: .leading, spacing: 8) {
                Text("Current Favorite")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack {
                    HStack(spacing: 8) {
                        Text("1")
                            .font(.caption)
                            .fontWeight(.bold)
                            .frame(width: 28, height: 28)
                            .background(Color.orange.opacity(0.15))
                            .foregroundStyle(.orange)
                            .clipShape(Circle())
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 4) {
                                Text(leader.name)
                                    .font(.headline)
                                    .fontWeight(.semibold)
                                if leader.isWinner == true {
                                    Text("Winner")
                                        .font(.caption2)
                                        .fontWeight(.medium)
                                        .foregroundStyle(.green)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(.green.opacity(0.12))
                                        .clipShape(Capsule())
                                }
                            }
                            if let odds = leader.americanOdds {
                                Text(odds > 0 ? "+\(odds)" : "\(odds)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .monospacedDigit()
                            }
                        }
                    }
                    Spacer()
                    Text(formatProbability(prob))
                        .font(.title2)
                        .fontWeight(.bold)
                        .monospacedDigit()
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
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
        let sorted = sortedOutcomes(market.outcomes)
        let displayed = showAllOutcomes ? sorted : Array(sorted.prefix(25))
        let hasMore = sorted.count > 25

        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "chart.bar.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                Text("All Outcomes")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                if hasMore {
                    Button(showAllOutcomes ? "Show less" : "Show all \(sorted.count)") {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showAllOutcomes.toggle()
                        }
                    }
                    .font(.caption2)
                    .foregroundStyle(.blue)
                }
            }

            // Sort controls
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(FuturesSortField.allCases, id: \.self) { field in
                        sortChip(field)
                    }
                }
            }

            ForEach(Array(displayed.enumerated()), id: \.element.id) { index, outcome in
                outcomeRow(outcome, rank: index + 1, color: color, leaderId: sorted.first?.id)
                if index < displayed.count - 1 {
                    Divider()
                }
            }

            if hasMore && !showAllOutcomes {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showAllOutcomes = true
                    }
                } label: {
                    Text("Show \(sorted.count - 25) more outcomes")
                        .font(.caption)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }
                .foregroundStyle(.secondary)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.2)))
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func sortChip(_ field: FuturesSortField) -> some View {
        let isActive = sortField == field
        return Button {
            if sortField == field {
                sortAscending.toggle()
            } else {
                sortField = field
                sortAscending = field == .name
            }
        } label: {
            HStack(spacing: 3) {
                Text(field.rawValue)
                    .font(.caption2)
                    .fontWeight(.medium)
                if isActive {
                    Image(systemName: sortAscending ? "chevron.up" : "chevron.down")
                        .font(.system(size: 8, weight: .bold))
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(isActive ? Color.primary.opacity(0.12) : Color.secondary.opacity(0.08))
            .foregroundStyle(isActive ? .primary : .secondary)
            .clipShape(Capsule())
        }
    }

    private func sortedOutcomes(_ outcomes: [FuturesOutcome]) -> [FuturesOutcome] {
        outcomes.sorted { a, b in
            let cmp: Bool
            switch sortField {
            case .probability:
                cmp = (a.probability ?? 0) > (b.probability ?? 0)
            case .change:
                cmp = (a.probabilityChange24h ?? 0) > (b.probabilityChange24h ?? 0)
            case .name:
                cmp = a.name.localizedCompare(b.name) == .orderedAscending
            }
            return sortAscending ? !cmp : cmp
        }
    }

    private func outcomeRow(_ outcome: FuturesOutcome, rank: Int, color: Color, leaderId: Int?) -> some View {
        let isLeader = outcome.id == leaderId

        return VStack(spacing: 4) {
            HStack(alignment: .top) {
                Text("#\(rank)")
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(isLeader ? .orange : .secondary)
                    .frame(width: 28, alignment: .leading)

                // Rank change indicator
                if let rankChange = outcome.rankChange24h, rankChange != 0 {
                    HStack(spacing: 1) {
                        Image(systemName: rankChange < 0 ? "arrow.up" : "arrow.down")
                            .font(.system(size: 7))
                        Text("\(abs(rankChange))")
                            .font(.system(size: 9))
                    }
                    .foregroundStyle(rankChange < 0 ? .green : .red)
                    .frame(width: 22, alignment: .leading)
                } else {
                    Spacer().frame(width: 22)
                }

                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(outcome.name)
                            .font(.subheadline)
                            .fontWeight(isLeader ? .semibold : .medium)
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
                            .fill(color.opacity(isLeader ? 0.7 : 0.4))
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

    // MARK: - Golf Tournament Dates

    /// Return commence_time as tournament start for golf markets (used for round markers).
    private func golfTournamentStart(_ market: FuturesMarketDetail) -> String? {
        guard market.llmSportCategory?.lowercased() == "golf" else { return nil }
        return market.commenceTime
    }

    /// Derive tournament end from commence_time + 4 days for golf.
    /// Returns nil for non-golf markets.
    private func golfTournamentEnd(_ market: FuturesMarketDetail) -> String? {
        guard market.llmSportCategory?.lowercased() == "golf",
              let startStr = market.commenceTime,
              let startDate = startStr.asDate else { return nil }
        let endDate = Calendar.current.date(byAdding: .day, value: 4, to: startDate)
        return endDate?.ISO8601Format()
    }

    // MARK: - Bookmaker Formatting

    private func formatBookmaker(_ key: String) -> String {
        let names: [String: String] = [
            "draftkings": "DraftKings",
            "fanduel": "FanDuel",
            "betmgm": "BetMGM",
            "caesars": "Caesars",
            "pointsbet": "PointsBet",
            "betrivers": "BetRivers",
            "bovada": "Bovada",
            "pinnacle": "Pinnacle",
            "espnbet": "ESPN BET",
            "betonlineag": "BetOnline",
            "superbook": "SuperBook",
            "williamhill_us": "Caesars",
            "fliff": "Fliff",
            "hardrockbet": "Hard Rock",
        ]
        return names[key] ?? key.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
