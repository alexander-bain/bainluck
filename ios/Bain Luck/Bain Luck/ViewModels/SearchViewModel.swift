import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "search")

final class SearchViewModel: ObservableObject {
    @Published var query = ""
    @Published var suggestions: [TypeaheadSuggestion] = []
    @Published var didYouMean: String?
    @Published var results: SearchResponse?
    @Published var loading = false
    @Published var error: String?
    @Published var selectedSport = ""
    @Published var recentSearches: [String] = []
    @Published var trendingSearches: [TrendingQuery] = []

    private var debounceTask: Task<Void, Never>?

    init() {
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

        loading = true
        do {
            let sport = selectedSport.isEmpty ? nil : selectedSport
            results = try await APIClient.shared.fetchSearch(query: trimmed, sport: sport)
            suggestions = []
            error = nil
            loading = false
            let totalResults = (results?.results.count ?? 0) + (results?.futures.count ?? 0)
            AnalyticsService.trackSearch(query: trimmed, resultsCount: totalResults)

            // Save to recent searches
            RecentSearches.save(trimmed)
            recentSearches = RecentSearches.load()
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Search failed: \(error)")
        }
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
