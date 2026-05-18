import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "futuresList")

final class FuturesListViewModel: ObservableObject {
    @Published private(set) var markets: [FacetedFuturesMarket] = []
    @Published private(set) var facets: [String: [FacetTag]] = [:]
    @Published private(set) var loading = true
    @Published private(set) var error: String?
    @Published var selectedCategory = ""
    @Published private(set) var page = 1
    @Published private(set) var hasMore = true

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
