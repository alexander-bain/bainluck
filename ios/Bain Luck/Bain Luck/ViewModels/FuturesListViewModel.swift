import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "futuresList")

/// Sort options for the futures browse list.
enum FuturesBrowseSortOption: String, CaseIterable, Identifiable {
    case soonest = "soonest"
    case trending = "trending"
    case newest = "newest"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .soonest: return "Soonest"
        case .trending: return "Trending"
        case .newest: return "Newest"
        }
    }

    var icon: String {
        switch self {
        case .soonest: return "clock"
        case .trending: return "flame"
        case .newest: return "sparkles"
        }
    }
}

final class FuturesListViewModel: ObservableObject {
    @Published private(set) var markets: [FacetedFuturesMarket] = []
    @Published private(set) var facets: [String: [FacetTag]] = [:]
    @Published private(set) var movers: [FuturesMover] = []
    @Published private(set) var loading = true
    @Published private(set) var loadingMore = false
    @Published private(set) var moversLoading = false
    @Published private(set) var error: String?
    @Published private(set) var loadMoreError: String?
    @Published var selectedCategory = ""
    @Published var searchText = ""
    @Published var sortOption: FuturesBrowseSortOption = .soonest
    @Published private(set) var page = 1
    @Published private(set) var hasMore = true

    private var totalCount = 0
    private var loadGeneration = 0
    private var searchDebounce: AnyCancellable?

    init() {
        // Debounce search input so we don't fire on every keystroke
        searchDebounce = $searchText
            .removeDuplicates()
            .debounce(for: .milliseconds(350), scheduler: DispatchQueue.main)
            .sink { [weak self] _ in
                guard let self else { return }
                Task { await self.load() }
            }
    }

    @MainActor
    func load() async {
        loadGeneration += 1
        let generation = loadGeneration
        let category = selectedCategory
        let search = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        let sort = sortOption

        loading = markets.isEmpty
        loadingMore = false
        loadMoreError = nil
        page = 1
        do {
            let tags = category.isEmpty ? [] : [category]
            let response = try await APIClient.shared.fetchFacetedFutures(
                tags: tags,
                page: 1,
                search: search.isEmpty ? nil : search,
                sort: sort.rawValue
            )
            guard shouldApplyLoadResult(generation: generation, category: category, search: search) else { return }
            markets = response.markets
            facets = response.facets
            totalCount = response.total
            hasMore = response.markets.count < response.total
            error = nil
            loading = false
        } catch {
            guard shouldApplyLoadResult(generation: generation, category: category, search: search) else { return }
            self.error = error.localizedDescription
            loading = false
            logger.error("Futures load failed: \(error)")
        }
    }

    @MainActor
    func loadMore() async {
        guard hasMore, !loading, !loadingMore else { return }
        let generation = loadGeneration
        let category = selectedCategory
        let search = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        let sort = sortOption
        let nextPage = page + 1
        loadingMore = true
        loadMoreError = nil
        do {
            let tags = category.isEmpty ? [] : [category]
            let response = try await APIClient.shared.fetchFacetedFutures(
                tags: tags,
                page: nextPage,
                search: search.isEmpty ? nil : search,
                sort: sort.rawValue
            )
            guard shouldApplyLoadResult(generation: generation, category: category, search: search) else {
                loadingMore = false
                return
            }
            markets.append(contentsOf: response.markets)
            page = nextPage
            hasMore = markets.count < response.total
            totalCount = response.total
            loadingMore = false
        } catch {
            guard shouldApplyLoadResult(generation: generation, category: category, search: search) else {
                loadingMore = false
                return
            }
            loadMoreError = error.localizedDescription
            loadingMore = false
            logger.error("Futures load more failed: \(error)")
        }
    }

    @MainActor
    func loadMovers() async {
        guard movers.isEmpty else { return }
        moversLoading = true
        do {
            let response = try await APIClient.shared.fetchFuturesMovers(hours: 24, limit: 10)
            movers = response.movers
            moversLoading = false
        } catch {
            moversLoading = false
            logger.error("Movers load failed: \(error)")
        }
    }

    @MainActor
    func onCategoryChange() {
        Task { await load() }
    }

    @MainActor
    func onSortChange() {
        Task { await load() }
    }

    /// Category facets sorted by count, excluding empty
    var categoryFacets: [FacetTag] {
        (facets["llm_sport_category"] ?? [])
            .filter { !$0.tag.isEmpty }
            .sorted { $0.count > $1.count }
    }

    @MainActor
    private func shouldApplyLoadResult(generation: Int, category: String, search: String) -> Bool {
        generation == loadGeneration
            && category == selectedCategory
            && search == searchText.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
