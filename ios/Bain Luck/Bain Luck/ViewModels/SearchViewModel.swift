import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "search")

final class SearchViewModel: ObservableObject {
    @Published var query = ""
    @Published var suggestions: [TypeaheadSuggestion] = []
    @Published var didYouMean: String?
    @Published var results: SearchResponse?
    @Published private(set) var loading = false
    @Published private(set) var error: String?
    @Published var selectedSport = ""
    @Published var recentSearches: [String] = []
    @Published private(set) var trendingSearches: [TrendingQuery] = []

    private var debounceTask: Task<Void, Never>?
    // Full-search stale-response guard (L2-198). Every search() bumps the
    // generation; a response whose generation is no longer current is dropped so
    // an older/slower query can't overwrite a newer one, a cleared field, or a
    // surface the user has left. Mirrors FuturesListViewModel.loadGeneration.
    private var searchGeneration = 0

    // Injectable full-search transport so the stale-response race is
    // deterministically testable (default preserves production behavior).
    typealias SearchFetching = (_ query: String, _ sport: String?) async throws -> SearchResponse
    private let searchFetch: SearchFetching

    init(
        searchFetch: @escaping SearchFetching = { query, sport in
            try await APIClient.shared.fetchSearch(query: query, sport: sport)
        }
    ) {
        self.searchFetch = searchFetch
        recentSearches = RecentSearches.load()
    }

    @MainActor
    func loadTrending() async {
        do {
            let response = try await APIClient.shared.fetchTrendingSearches()
            trendingSearches = response.trending
        } catch {
            trendingSearches = []
        }
    }

    @MainActor
    func onQueryChange() {
        debounceTask?.cancel()

        let trimmed = query.trimmingCharacters(in: .whitespaces)
        if trimmed.count < 2 {
            suggestions = []
            results = nil
            return
        }

        debounceTask = Task {
            try? await Task.sleep(nanoseconds: 200_000_000) // 200ms
            guard !Task.isCancelled else { return }
            await fetchTypeahead(trimmed)
        }
    }

    @MainActor
    func search() async {
        debounceTask?.cancel()
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard trimmed.count >= 2 else { return }

        searchGeneration &+= 1
        let generation = searchGeneration
        let sport = selectedSport.isEmpty ? nil : selectedSport

        loading = true
        do {
            let response = try await searchFetch(trimmed, sport)
            // Stale-response guard (L2-198): only the latest search generation may
            // publish. A slower older query, a cleared field, or a surface the
            // user has navigated away from (all bump/invalidate the generation)
            // can never overwrite the newest results.
            guard generation == searchGeneration else { return }
            results = response
            suggestions = []
            error = nil
            loading = false
            let totalResults = response.results.count + response.futures.count
            AnalyticsService.trackSearch(query: trimmed, resultsCount: totalResults)

            // Save to recent searches
            RecentSearches.save(trimmed)
            recentSearches = RecentSearches.load()
        } catch {
            // A superseded search must not publish its error/spinner either.
            guard generation == searchGeneration else { return }
            self.error = error.localizedDescription
            loading = false
            logger.error("Search failed: \(error)")
        }
    }

    /// Invalidate any in-flight typeahead and full search — for a cleared field
    /// or when the search surface disappears — so a late response cannot publish
    /// onto a stale/absent surface (L2-198).
    @MainActor
    func cancelInFlightWork() {
        debounceTask?.cancel()
        searchGeneration &+= 1
        loading = false
    }

    @MainActor
    func onSportFilterChange() {
        // Re-search with new sport filter if we have results
        if results != nil {
            Task { await search() }
        }
    }

    func removeRecentSearch(_ query: String) {
        RecentSearches.remove(query)
        recentSearches = RecentSearches.load()
    }

    func clearRecentSearches() {
        RecentSearches.clear()
        recentSearches = []
    }

    @MainActor
    private func fetchTypeahead(_ q: String) async {
        do {
            let response = try await APIClient.shared.fetchTypeahead(query: q)
            guard !Task.isCancelled else { return }
            suggestions = response.suggestions
            didYouMean = response.didYouMean
        } catch {
            logger.error("Typeahead failed: \(error)")
        }
    }
}
