import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "futuresList")

// MARK: - ViewModel

final class FuturesListViewModel: ObservableObject {
    @Published var markets: [FacetedFuturesMarket] = []
    @Published var facets: [String: [FacetTag]] = [:]
    @Published var loading = true
    @Published var error: String?
    @Published var selectedCategory = ""
    @Published var page = 1
    @Published var hasMore = true

    private var totalCount = 0

    @MainActor
    func load() async {
        loading = markets.isEmpty
        page = 1
        do {
            let tags = selectedCategory.isEmpty ? [] : [selectedCategory]
            let response = try await APIClient.shared.fetchFacetedFutures(tags: tags, page: 1)
            markets = response.markets
            facets = response.facets
            totalCount = response.total
            hasMore = response.markets.count < response.total
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Futures load failed: \(error)")
        }
    }

    @MainActor
    func loadMore() async {
        guard hasMore, !loading else { return }
        let nextPage = page + 1
        do {
            let tags = selectedCategory.isEmpty ? [] : [selectedCategory]
            let response = try await APIClient.shared.fetchFacetedFutures(tags: tags, page: nextPage)
            markets.append(contentsOf: response.markets)
            page = nextPage
            hasMore = markets.count < response.total
        } catch {
            logger.error("Futures load more failed: \(error)")
        }
    }

    @MainActor
    func onCategoryChange() {
        Task { await load() }
    }

    /// Category facets sorted by count, excluding empty
    var categoryFacets: [FacetTag] {
        (facets["llm_sport_category"] ?? [])
            .filter { !$0.tag.isEmpty }
            .sorted { $0.count > $1.count }
    }
}

// MARK: - View

struct FuturesListView: View {
    @StateObject private var vm = FuturesListViewModel()
    @State private var path = NavigationPath()
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                categoryChips
                    .padding(.vertical, 8)

                if vm.loading {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else if let error = vm.error, vm.markets.isEmpty {
                    ContentUnavailableView(
                        "Couldn't Load Futures",
                        systemImage: "wifi.exclamationmark",
                        description: Text(error)
                    )
                } else if vm.markets.isEmpty {
                    ContentUnavailableView(
                        "No Futures",
                        systemImage: "chart.line.uptrend.xyaxis",
                        description: Text("No futures markets found for this category.")
                    )
                } else {
                    marketList
                }
            }
            .navigationTitle("Futures")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
        }
        .task {
            await vm.load()
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "futures_list", type: "futures_list")
        }
    }

    // MARK: - Category Chips

    private var categoryChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                categoryChip(tag: "", label: "All", icon: nil)
                ForEach(vm.categoryFacets, id: \.tag) { facet in
                    categoryChip(
                        tag: facet.tag,
                        label: facet.tag.capitalized,
                        icon: categoryIcon(for: facet.tag),
                        count: facet.count
                    )
                }
            }
            .padding(.horizontal)
        }
    }

    private func categoryChip(tag: String, label: String, icon: String?, count: Int? = nil) -> some View {
        let isSelected = vm.selectedCategory == tag
        return Button {
            withAnimation(.easeInOut(duration: 0.2)) {
                vm.selectedCategory = tag
            }
            vm.onCategoryChange()
        } label: {
            HStack(spacing: 4) {
                if let icon {
                    Image(systemName: icon)
                        .font(.system(size: 10))
                }
                Text(label)
                    .font(.caption)
                    .fontWeight(isSelected ? .semibold : .regular)
                if let count, !isSelected {
                    Text("\(count)")
                        .font(.system(size: 9))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(isSelected ? Color.purple.opacity(0.15) : Color.cardBackgroundDark)
            .foregroundStyle(isSelected ? .purple : .primary)
            .clipShape(Capsule())
        }
    }

    private func categoryIcon(for key: String) -> String {
        switch key.lowercased() {
        case "basketball": return "basketball.fill"
        case "football": return "football.fill"
        case "baseball": return "baseball.fill"
        case "hockey": return "hockey.puck.fill"
        case "soccer": return "soccerball"
        case "golf": return "figure.golf"
        case "tennis": return "tennis.racket"
        case "mma", "boxing": return "figure.boxing"
        case "politics": return "building.columns.fill"
        case "entertainment": return "star.fill"
        case "crypto": return "bitcoinsign.circle.fill"
        default: return "chart.bar.fill"
        }
    }

    // MARK: - Market List

    private var marketList: some View {
        List {
            ForEach(vm.markets) { market in
                NavigationLink(value: Route.futuresDetail(id: market.id)) {
                    futuresMarketRow(market)
                }
            }

            if vm.hasMore {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .listRowBackground(Color.clear)
                    .task {
                        await vm.loadMore()
                    }
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable {
            await vm.load()
        }
    }

    // MARK: - Market Row

    private func categoryEmoji(for key: String?) -> String {
        switch key?.lowercased() {
        case "basketball": return "🏀"
        case "football": return "🏈"
        case "baseball": return "⚾"
        case "hockey": return "🏒"
        case "soccer": return "⚽"
        case "golf": return "⛳"
        case "tennis": return "🎾"
        case "mma", "boxing": return "🥊"
        case "politics": return "🏛"
        case "economics": return "📈"
        case "weather": return "🌤"
        case "entertainment": return "🎬"
        case "culture": return "🎭"
        case "tech": return "💻"
        case "geopolitics": return "🌍"
        case "cricket": return "🏏"
        default: return "📊"
        }
    }

    private func futuresMarketRow(_ market: FacetedFuturesMarket) -> some View {
        HStack(alignment: .top, spacing: 12) {
            if let imageUrl = market.imageUrl, let url = URL(string: imageUrl) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().scaledToFill()
                    default:
                        Text(categoryEmoji(for: market.llmSportCategory))
                            .font(.title2)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .background(Color.secondary.opacity(0.08))
                    }
                }
                .frame(width: 48, height: 48)
                .clipShape(RoundedRectangle(cornerRadius: 10))
            } else {
                Text(categoryEmoji(for: market.llmSportCategory))
                    .font(.title2)
                    .frame(width: 48, height: 48)
                    .background(Color.secondary.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(market.name)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(2)

                HStack(spacing: 6) {
                    if let category = market.llmSportCategory {
                        Text(category.capitalized)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let source = market.source {
                        sourceBadge(source)
                    }
                    if let count = market.outcomeCount {
                        Text("\(count) outcomes")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }

            // Top outcomes preview
            if let outcomes = market.topOutcomes, !outcomes.isEmpty {
                HStack(spacing: 12) {
                    ForEach(outcomes.prefix(3)) { outcome in
                        HStack(spacing: 3) {
                            Text(outcome.name)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                            if let prob = outcome.probability {
                                Text(formatProbability(prob))
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                    .monospacedDigit()
                            }
                        }
                    }
                }
            }
        }
        }
        .padding(.vertical, 4)
    }

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
            .font(.system(size: 9, weight: .medium))
            .foregroundStyle(color)
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .background(color.opacity(0.12))
            .clipShape(Capsule())
    }
}
