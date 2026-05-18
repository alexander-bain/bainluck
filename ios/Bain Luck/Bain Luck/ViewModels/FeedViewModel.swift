import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "feed")

final class FeedViewModel: ObservableObject {
    @Published private(set) var items: [FeedItem] = []
    @Published private(set) var groupedItems: [GroupedFeedItem] = []
    @Published private(set) var total = 0
    @Published private(set) var loading = true
    @Published private(set) var error: String?
    @Published private(set) var liveCount = 0

    private static let supplementalEventLimit = 200
    private var refreshTimer: Timer?

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

    var hasLiveGames: Bool { !liveNow.isEmpty }

    @MainActor
    func load() async {
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        do {
            // Fetch the ranked feed plus an event-only backfill so native Sports
            // still has recent/upcoming rows when live games dominate the first page.
            async let feedTask = APIClient.shared.fetchFeed()
            async let eventBackfillTask = APIClient.shared.fetchFeed(
                limit: Self.supplementalEventLimit,
                includeFutures: false
            )
            async let groupedTask = APIClient.shared.fetchGroupedFeed(limit: 20)

            let feed = try await feedTask
            let eventBackfill = try? await eventBackfillTask
            items = mergeFeedItems(feed.items, withNonLiveEventsFrom: eventBackfill?.items ?? [])
            total = max(feed.total, items.count)

            // Grouped feed is optional — don't fail if it errors
            if let grouped = try? await groupedTask {
                groupedItems = grouped.feed
                logger.info("Grouped feed loaded: \(grouped.feed.count) items")
            }

            error = nil
            loading = false
            liveCount = liveNow.count
            logger.info("Feed loaded: \(self.items.count) items")
            configureAutoRefresh()
        } catch {
            if isInitial {
                self.error = error.localizedDescription
            }
            loading = false
            logger.error("Feed error: \(error)")
        }
    }

    private func mergeFeedItems(_ rankedItems: [FeedItem], withNonLiveEventsFrom backfillItems: [FeedItem]) -> [FeedItem] {
        var merged = rankedItems
        var seen = Set(rankedItems.map(\.id))

        for item in backfillItems {
            guard item.type == "event", item.event?.status != "live", !seen.contains(item.id) else {
                continue
            }
            merged.append(item)
            seen.insert(item.id)
        }

        return merged
    }

    private func configureAutoRefresh() {
        refreshTimer?.invalidate()
        guard hasLiveGames else { return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.load()
            }
        }
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }

    // MARK: - Filtered accessors

    func filteredItems(for categoryID: String) -> [FeedItem] {
        guard categoryID != "all" else { return items }
        guard let category = sportCategories.first(where: { $0.id == categoryID }) else { return items }
        return items.filter { category.matches($0) }
    }

    func filteredLiveNow(for categoryID: String) -> [FeedItem] {
        filteredItems(for: categoryID).filter { $0.event?.status == "live" }
    }

    func filteredJustHappened(for categoryID: String) -> [FeedItem] {
        filteredItems(for: categoryID).filter {
            let s = $0.event?.status
            return s == "completed" || s == "closed"
        }
    }

    func filteredUpcoming(for categoryID: String) -> [FeedItem] {
        filteredItems(for: categoryID).filter {
            guard $0.type == "event" else { return false }
            let s = $0.event?.status
            return s == "scheduled" || s == nil
        }
    }

    func filteredTopMarkets(for categoryID: String) -> [FeedItem] {
        filteredItems(for: categoryID).filter { $0.type == "futures" }
    }
}
