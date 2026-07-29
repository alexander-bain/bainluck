import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "feed")

/// Narrow fetch seam for the native **Sports** tab (L2-207 / #1480) so
/// `FeedViewModel`'s three independent requests can be driven by deterministic
/// (delayed) fakes in tests. `APIClient` conforms via the extension at the
/// bottom of this file; the default init arg keeps production wiring unchanged.
///
/// The Sports tab intentionally issues THREE requests:
/// - the main fast `mode=sports` feed (gates first paint),
/// - an events-only backfill (recent/upcoming rows when live games dominate),
/// - grouped futures (player props / playoff progressions).
protocol SportsFeedProviding: Sendable {
    /// The main Sports feed on the fast backend contract (`mode=sports`).
    nonisolated func fetchSportsFeed() async throws -> FeedResponse
    /// Events-only backfill (`include_futures=false`), served raw as today.
    nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse
    /// Grouped futures cards; optional/non-fatal.
    nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse
}

/// One progressive-load milestone for the native Sports tab (L2-207 / #1480).
/// Deliberately carries only opaque timings + counts — never an ID, token,
/// session, market text, or the raw query — so it is safe to emit through the
/// existing latency rail.
struct SportsFeedStage: Sendable {
    enum Kind: String, Sendable {
        case main = "sports_main"
        case eventsBackfill = "sports_events_backfill"
        case grouped = "sports_grouped"
    }
    let kind: Kind
    /// Elapsed time from load start to this stage's data-ready (model assignment).
    let dataReadyMs: Double
    /// Elapsed time from load start to the first renderable card being published.
    /// Only set on the `main` stage (the moment the skeleton is removed); nil for
    /// the siblings so a fast sibling can never be mistaken for first paint.
    let firstRealCardMs: Double?
    let itemCount: Int
    let success: Bool
}

final class FeedViewModel: ObservableObject {
    @Published private(set) var items: [FeedItem] = []
    @Published private(set) var groupedItems: [GroupedFeedItem] = []
    @Published private(set) var total = 0
    @Published private(set) var loading = true
    @Published private(set) var error: String?
    @Published private(set) var liveCount = 0

    static let supplementalEventLimit = 200
    static let groupedFeedLimit = 20
    private var refreshTimer: Timer?

    private let client: SportsFeedProviding
    private let telemetry: (@Sendable (SportsFeedStage) -> Void)?
    private let clock: @Sendable () -> Date
    private let autoRefreshEnabled: Bool

    /// Monotonic load identity (mirrors `DiscoverViewModel`, L2-201/L2-207). Each
    /// `load()` claims the next value; a load superseded by a newer `load()`
    /// (pull-to-refresh, the live auto-refresh timer, rapid re-entry) discards its
    /// late responses instead of overwriting the current session's feed. This is
    /// what makes progressive publication safe: three requests resolve out of
    /// order, and a stale in-flight response from a prior load can never clobber a
    /// newer one, blank visible cards, or reorder them.
    private var loadGeneration = 0

    init(
        client: SportsFeedProviding = APIClient.shared,
        telemetry: (@Sendable (SportsFeedStage) -> Void)? = { AnalyticsService.trackSportsFeedStage($0) },
        clock: @escaping @Sendable () -> Date = { Date() },
        autoRefreshEnabled: Bool = true
    ) {
        self.client = client
        self.telemetry = telemetry
        self.clock = clock
        self.autoRefreshEnabled = autoRefreshEnabled
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

    var hasLiveGames: Bool { !liveNow.isEmpty }

    @MainActor
    func load() async {
        // Claim a load identity so a superseded (older) load discards its late
        // responses instead of overwriting a newer session's feed (L2-207).
        loadGeneration &+= 1
        let generation = loadGeneration
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        let loadStart = clock()

        // Fire all three requests concurrently. First paint is gated on the MAIN
        // fast (`mode=sports`) response ONLY — the events backfill and grouped
        // futures merge in independently, each on its OWN completion, so the
        // skeleton no longer waits on the slowest of the three (the L2-207 defect)
        // and the (bottom-of-page) grouped section is never held hostage behind
        // the heavy 200-event backfill.
        async let mainTask = client.fetchSportsFeed()
        let backfillTask = Task { [client] in
            try? await client.fetchSportsEventBackfill(limit: Self.supplementalEventLimit)
        }
        let groupedTask = Task { [client] in
            try? await client.fetchSportsGroupedFeed(limit: Self.groupedFeedLimit)
        }

        // === 1. Main feed — gates first paint ===
        do {
            let feed = try await mainTask
            guard generation == loadGeneration else {
                // Superseded by a newer load: abandon and cancel siblings so a stale
                // response can never clobber, blank, or reorder the newer feed.
                backfillTask.cancel()
                groupedTask.cancel()
                return
            }
            items = feed.items
            total = max(feed.total, items.count)
            error = nil
            loading = false
            liveCount = liveNow.count
            emit(.main, start: loadStart, isFirstCard: true, count: items.count, success: true)
            logger.info("Sports main feed loaded: \(self.items.count) items")
        } catch {
            guard generation == loadGeneration else { return }
            // Main failure stays retryable and must NOT publish sibling content as
            // a false full-success state: the siblings alone are not a complete
            // Sports tab. Cancel them, leave items untouched (empty on a cold load →
            // the error/retry screen; existing on a refresh → prior content kept),
            // and abandon this load.
            backfillTask.cancel()
            groupedTask.cancel()
            if isInitial { self.error = error.localizedDescription }
            loading = false
            emit(.main, start: loadStart, isFirstCard: true, count: items.count, success: false)
            logger.error("Sports main feed error: \(error)")
            return
        }

        // === 2 & 3. Siblings merge independently, each on its own completion ===
        // Both requests are already in flight (started above, concurrent with the
        // main feed). Publishing each in its own child task means grouped can land
        // before a slow backfill, and neither blanks nor reorders the main cards.
        async let backfillPublished: Void = mergeBackfill(backfillTask, generation: generation, start: loadStart)
        async let groupedPublished: Void = mergeGrouped(groupedTask, generation: generation, start: loadStart)
        _ = await (backfillPublished, groupedPublished)

        guard generation == loadGeneration else { return }
        configureAutoRefresh()
    }

    /// Merges the events-only backfill into the already-published main feed as soon
    /// as the backfill completes. Non-fatal: a miss is reported honestly and leaves
    /// the main feed intact. Only NEW non-live events are appended, in main order.
    @MainActor
    private func mergeBackfill(
        _ task: Task<FeedResponse?, Never>,
        generation: Int,
        start: Date
    ) async {
        let backfill = await task.value
        guard generation == loadGeneration else { return }
        if let backfill {
            items = mergeFeedItems(items, withNonLiveEventsFrom: backfill.items)
            total = max(total, items.count)
            liveCount = liveNow.count
            emit(.eventsBackfill, start: start, isFirstCard: false, count: items.count, success: true)
        } else {
            emit(.eventsBackfill, start: start, isFirstCard: false, count: items.count, success: false)
        }
    }

    /// Publishes the grouped futures section as soon as it completes. Honest +
    /// non-fatal: a failure leaves the section empty and the rest of the tab intact.
    @MainActor
    private func mergeGrouped(
        _ task: Task<GroupedFeedResponse?, Never>,
        generation: Int,
        start: Date
    ) async {
        let grouped = await task.value
        guard generation == loadGeneration else { return }
        if let grouped {
            groupedItems = grouped.feed
            emit(.grouped, start: start, isFirstCard: false, count: grouped.feed.count, success: true)
            logger.info("Grouped feed loaded: \(grouped.feed.count) items")
        } else {
            emit(.grouped, start: start, isFirstCard: false, count: groupedItems.count, success: false)
        }
    }

    private func emit(
        _ kind: SportsFeedStage.Kind,
        start: Date,
        isFirstCard: Bool,
        count: Int,
        success: Bool
    ) {
        guard let telemetry else { return }
        let elapsedMs = clock().timeIntervalSince(start) * 1000
        telemetry(
            SportsFeedStage(
                kind: kind,
                dataReadyMs: elapsedMs,
                firstRealCardMs: isFirstCard ? elapsedMs : nil,
                itemCount: count,
                success: success
            )
        )
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
        guard autoRefreshEnabled else { return }
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

// MARK: - Production fetch conformance

extension APIClient: SportsFeedProviding {
    /// Main Sports feed on the fast backend contract (L2-207 / #1480): the native
    /// Sports tab requests `mode=sports` so the backend runs
    /// `_score_sports_mode_futures` (a single top-sports-futures query) instead of
    /// the full editorial Discover pipeline the Discover-default guard would
    /// otherwise force on an unparameterized request.
    nonisolated func fetchSportsFeed() async throws -> FeedResponse {
        try await fetchFeed(mode: "sports")
    }

    /// Events-only backfill, served raw as today (`include_futures=false` opts it
    /// out of the Discover-default guard). No `mode`: the guard only rewrites
    /// futures-carrying main requests, so this stays the same events-only response
    /// that powers Live Now / Just Happened / Upcoming.
    nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
        try await fetchFeed(limit: limit, includeFutures: false)
    }

    nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse {
        try await fetchGroupedFeed(limit: limit)
    }
}
