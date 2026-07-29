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
    /// Elapsed time from load start to this stage's DATA-ready — the moment the
    /// decoded model was assigned, NOT the on-screen render (L2-209 Item 2 / C68).
    /// The true first-card render is a separate, view-driven `sports_feed_first_render`
    /// event so a fast model assignment is never reported as a fast first paint and
    /// an empty-but-successful main never emits a bogus first-card time.
    let dataReadyMs: Double
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
    /// True when a NON-initial refresh's main request failed while existing content
    /// stayed on screen (L2-209 Item 2 / C68). Lets the view surface a small,
    /// non-blocking "couldn't refresh" state instead of silently presenting stale
    /// content as freshly loaded. Cleared on the next successful main response.
    @Published private(set) var refreshFailed = false

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

    /// Which sibling a task-group child resolved (L2-209 Item 1). Sendable so it can
    /// cross the group boundary; the optional payload is nil on failure/cancellation.
    private enum SiblingResult: Sendable {
        case backfill(FeedResponse?)
        case grouped(GroupedFeedResponse?)
    }

    @MainActor
    func load() async {
        // Claim a load identity so a superseded (older) load discards its late
        // responses instead of overwriting a newer session's feed (L2-207). The
        // owning view ALSO bumps this via `viewDidStop()` on disappear, so a
        // timer-driven refresh already in flight when the tab closes can never
        // mutate state afterward (L2-209 Item 1 / C68).
        loadGeneration &+= 1
        let generation = loadGeneration
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        let loadStart = clock()
        let client = self.client

        // === 1. Main feed — gates first paint ===
        do {
            let feed = try await client.fetchSportsFeed()
            guard generation == loadGeneration else { return }
            items = feed.items
            total = max(feed.total, items.count)
            error = nil
            refreshFailed = false
            loading = false
            liveCount = liveNow.count
            emit(.main, start: loadStart, count: items.count, success: true)
            // Arm auto-refresh IMMEDIATELY after the main publish (L2-209 Item 2 /
            // C68): a live game must have a refresh timer even while a slow or hung
            // 30/60s sibling is still loading — no longer deferred behind the
            // siblings. Recomputed once more after the merges below.
            configureAutoRefresh()
            logger.info("Sports main feed loaded: \(self.items.count) items")
        } catch {
            guard generation == loadGeneration else { return }
            // Cancellation (view disappeared / superseded) is not a transport
            // failure: abandon quietly, never surface it as an error or a failed
            // stage (L2-209 Item 1 / C68). No siblings were started yet.
            if error is CancellationError { return }
            loading = false
            if isInitial {
                // Cold load: nothing on screen → the error/retry screen.
                self.error = error.localizedDescription
            } else {
                // Refresh failure: keep existing content but tell the truth that the
                // refresh failed, so the UI is honestly retryable rather than
                // silently presenting stale content as fresh (L2-209 Item 2 / C68).
                refreshFailed = true
            }
            emit(.main, start: loadStart, count: items.count, success: false)
            logger.error("Sports main feed error: \(error)")
            return
        }

        // === 2 & 3. Siblings — STRUCTURED children of this load ===
        // Owned by a task group rather than detached `Task`s, so a superseded load
        // or a disappearing view cancels them instead of letting them outlive the
        // view and mutate state (L2-209 Item 1 / C68). Each result is applied as its
        // own child completes (`for await`), so grouped is never held behind a slow
        // 200-event backfill, and the generation guard drops any late/cancelled
        // child of a superseded load.
        await withTaskGroup(of: SiblingResult.self) { group in
            group.addTask {
                .backfill(await Self.optional {
                    try await client.fetchSportsEventBackfill(limit: Self.supplementalEventLimit)
                })
            }
            group.addTask {
                .grouped(await Self.optional {
                    try await client.fetchSportsGroupedFeed(limit: Self.groupedFeedLimit)
                })
            }
            for await result in group {
                guard generation == loadGeneration else { continue }
                switch result {
                case .backfill(let backfill): applyBackfill(backfill, start: loadStart)
                case .grouped(let grouped): applyGrouped(grouped, start: loadStart)
                }
            }
        }

        guard generation == loadGeneration else { return }
        // Recompute the refresh interval after the merges (belt-and-suspenders — the
        // backfill excludes live events, so the live set is already known from main).
        configureAutoRefresh()
    }

    /// Run an optional/non-fatal fetch, mapping ANY error — including cancellation —
    /// to nil (L2-209 Item 1). Cancellation is disambiguated at the merge site by the
    /// load-generation guard, so a superseded/cancelled child never emits a false
    /// failure stage. Nonisolated + Sendable so it runs off the main actor as a
    /// structured task-group child.
    private static func optional<T: Sendable>(_ op: @Sendable () async throws -> T) async -> T? {
        do { return try await op() } catch { return nil }
    }

    /// Merge the events-only backfill into the already-published main feed. Non-fatal:
    /// a miss is reported honestly and leaves the main feed intact. Only NEW non-live
    /// events are appended, in main order.
    @MainActor
    private func applyBackfill(_ backfill: FeedResponse?, start: Date) {
        if let backfill {
            items = mergeFeedItems(items, withNonLiveEventsFrom: backfill.items)
            total = max(total, items.count)
            liveCount = liveNow.count
            emit(.eventsBackfill, start: start, count: items.count, success: true)
        } else {
            emit(.eventsBackfill, start: start, count: items.count, success: false)
        }
    }

    /// Publish the grouped futures section. Honest + non-fatal: a failure leaves the
    /// section empty and the rest of the tab intact.
    @MainActor
    private func applyGrouped(_ grouped: GroupedFeedResponse?, start: Date) {
        if let grouped {
            groupedItems = grouped.feed
            emit(.grouped, start: start, count: grouped.feed.count, success: true)
            logger.info("Grouped feed loaded: \(grouped.feed.count) items")
        } else {
            emit(.grouped, start: start, count: groupedItems.count, success: false)
        }
    }

    private func emit(
        _ kind: SportsFeedStage.Kind,
        start: Date,
        count: Int,
        success: Bool
    ) {
        guard let telemetry else { return }
        let elapsedMs = clock().timeIntervalSince(start) * 1000
        telemetry(
            SportsFeedStage(
                kind: kind,
                dataReadyMs: elapsedMs,
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

    /// True while a live-game auto-refresh timer is armed. Observable so a test can
    /// prove refresh is active immediately after the main publish, even while a slow
    /// sibling is still loading (L2-209 Item 2 / C68).
    private(set) var refreshArmed = false

    private func configureAutoRefresh() {
        guard autoRefreshEnabled else { return }
        refreshTimer?.invalidate()
        guard hasLiveGames else { refreshArmed = false; return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.load()
            }
        }
        refreshArmed = true
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
        refreshArmed = false
    }

    /// Called when the owning Sports view stops (disappears) — L2-209 Item 1 / C68.
    /// Invalidates the current load generation so any request still in flight from a
    /// timer-driven refresh (which is NOT cancelled by the view's `.task`) can no
    /// longer mutate published state when it lands, then stops the refresh timer.
    @MainActor
    func viewDidStop() {
        loadGeneration &+= 1
        stopRefresh()
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
