import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "sportCategory")

@MainActor
final class SportCategoryViewModel: ObservableObject {
    @Published private(set) var items: [FeedItem] = []
    @Published private(set) var loading = true
    @Published private(set) var error: String?
    @Published private(set) var loadingMore = false
    @Published private(set) var hasMore = true
    @Published private(set) var leagueMarkets: LeagueMarketsResponse?

    let categoryKey: String
    private let pageSize = 50

    init(categoryKey: String) {
        self.categoryKey = categoryKey
    }

    func load() async {
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        do {
            async let feedTask = APIClient.shared.fetchFeed(sport: categoryKey, limit: pageSize, offset: 0)
            async let marketsTask = loadLeagueMarkets()
            let feed = try await feedTask
            _ = await marketsTask
            items = feed.items
            hasMore = feed.hasMore
            error = nil
            loading = false
            logger.info("Category \(self.categoryKey) loaded: \(self.items.count) items")
        } catch {
            if isInitial {
                self.error = error.localizedDescription
            }
            loading = false
            logger.error("Category feed error: \(error)")
        }
    }

    func loadMore() async {
        guard !loadingMore, hasMore else { return }
        loadingMore = true
        do {
            let feed = try await APIClient.shared.fetchFeed(sport: categoryKey, limit: pageSize, offset: items.count)
            items.append(contentsOf: feed.items)
            hasMore = feed.hasMore
            logger.info("Category \(self.categoryKey) loaded more: +\(feed.items.count), total \(self.items.count)")
        } catch {
            logger.error("Category load more error: \(error)")
        }
        loadingMore = false
    }

    var liveNow: [FeedItem] {
        items.filter { $0.event?.status == "live" }
    }

    var justHappened: [FeedItem] {
        items.filter {
            let s = $0.event?.status
            return s == "completed" || s == "closed"
        }
    }

    var upcoming: [FeedItem] {
        items.filter {
            guard $0.type == "event" else { return false }
            let s = $0.event?.status
            return s == "scheduled" || s == nil
        }
    }

    var topMarkets: [FeedItem] {
        items.filter { $0.type == "futures" }
    }

    private func loadLeagueMarkets() async {
        do {
            leagueMarkets = try await APIClient.shared.fetchLeagueMarkets(sportKey: categoryKey)
            logger.info("League markets for \(self.categoryKey): \(self.leagueMarkets?.totalMarkets ?? 0) total")
        } catch {
            logger.debug("League markets not available for \(self.categoryKey): \(error)")
        }
    }
}
