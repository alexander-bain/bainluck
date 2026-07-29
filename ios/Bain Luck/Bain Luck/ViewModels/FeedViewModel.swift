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

    /// Immutable snapshot of the successful-main generation that FIRST became
    /// renderable this load (L2-211 Item 2 / C73). Stamped once at data-ready and
    /// frozen — the on-screen first-render telemetry reads THIS (its frozen count +
    /// provenance) instead of live `items`, so a later backfill merge, a superseding
    /// load, a same-card-ID row reuse, or a filter can never make the emitted event
    /// describe another generation. @Published so the view's generation-keyed
    /// `onChange` acknowledgement fires even when a same-id refresh retains its rows
    /// (SwiftUI does not re-run `onAppear` for retained IDs). Nil for an empty main.
    @Published private(set) var firstRenderGeneration: SportsRenderGeneration?

    static let supplementalEventLimit = 200
    static let groupedFeedLimit = 20
    private var refreshTimer: Timer?

    private let client: SportsFeedProviding
    private let telemetry: (@Sendable (SportsFeedStage) -> Void)?
    private let clock: @Sendable () -> Date
    private let autoRefreshEnabled: Bool
    /// Wall-clock bound on how long a load waits for its OPTIONAL siblings after the
    /// main has published (L2-211 Item 1 / C73). Once it elapses the merge is closed
    /// so a cancellation-IGNORING sibling can never keep the owned load task — and
    /// therefore the single-load rail — alive indefinitely. Injectable so tests drive
    /// the deadline_then_join path deterministically without real time.
    private let siblingDeadline: TimeInterval

    /// The single owned load task (L2-211 Item 1 / C73). Every entry point — the
    /// view's `.task`, pull-to-refresh, the Retry button, and the live auto-refresh
    /// timer — routes through `startLoad()`, which cancels AND joins this task before
    /// installing its replacement, so at most one owned load ever executes and a
    /// superseded load's work is actually TERMINATED (its main fetch + siblings
    /// cancelled), not merely discarded by the generation guard.
    private var loadTask: Task<Void, Never>?
    /// The current load's in-flight sibling tasks, held so a supersession or a view
    /// disappearance can cancel them (they are unstructured — not children of
    /// `loadTask` — so cancellation must be explicit).
    private var inFlightSiblings: [Task<Void, Never>] = []
    /// Set by `viewDidStop()` so a refresh-timer callback already queued at the
    /// moment the view disappeared cannot start a fresh owned load after teardown.
    /// Cleared by `viewDidStart()` on (re)appearance.
    private var isStopped = false

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
        autoRefreshEnabled: Bool = true,
        siblingDeadline: TimeInterval = 10
    ) {
        self.client = client
        self.telemetry = telemetry
        self.clock = clock
        self.autoRefreshEnabled = autoRefreshEnabled
        self.siblingDeadline = siblingDeadline
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

    /// The single owned-load entry point (L2-211 Item 1 / C73). Cancels the prior
    /// owned load and installs this one as the sole owner; the replacement JOINS the
    /// prior (awaits its termination) before running its body, so at most one load
    /// executes at a time and a superseded load's work is actually terminated rather
    /// than left running and merely discarded by the generation guard. The view's
    /// `.task`, `.refreshable`, the Retry button, and the live auto-refresh timer all
    /// route through here. The generation guard inside `load()` remains a publication
    /// backstop for any late child that outraces cancellation.
    @MainActor
    func startLoad() async {
        // A refresh-timer callback queued just as the view disappeared must not
        // resurrect a load after teardown (cancel_and_join_on_disappear).
        guard !isStopped else { return }
        let prior = loadTask
        prior?.cancel()
        // NOTE: no `await` between reading `loadTask` and reassigning it below — the
        // synchronous region is atomic on the main actor, so rapid re-entry can never
        // strand a newer owner. The join happens INSIDE the new task.
        let task = Task { @MainActor [weak self] in
            await prior?.value          // join prior ownership before replacement
            guard let self, !Task.isCancelled else { return }
            await self.load()
        }
        loadTask = task
        await task.value
    }

    /// Called by the owning view on (re)appearance so a load can begin again after a
    /// prior `viewDidStop()` (navigation away then back) — L2-211 Item 1 / C73.
    @MainActor
    func viewDidStart() {
        isStopped = false
    }

    @MainActor
    func load() async {
        // Cancel any siblings still in flight from a prior load body before this one
        // launches its own — they are unstructured, so a superseded body's children
        // are terminated here rather than left to race (L2-211 Item 1 / C73).
        cancelInFlightSiblings()
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
        // Re-arm the immutable render-generation token for this load (L2-211 Item 2):
        // the next successful non-empty main stamps it once, frozen for this load.
        firstRenderGeneration = nil

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
            // Stamp the immutable render token from THIS main response (L2-211 Item
            // 2 / C73): frozen generation + start + count, before any sibling merge
            // can change the live count. An empty main leaves it nil, so an
            // empty-but-successful main emits no on-screen first-card event.
            if !items.isEmpty {
                firstRenderGeneration = SportsRenderGeneration(
                    generation: generation,
                    startedAt: loadStart,
                    provenance: "network",
                    itemCount: items.count
                )
            }
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

        // === 2 & 3. Siblings — OWNED, cancellable, deadline-bounded ===
        // The two supplemental requests run as owned unstructured tasks (tracked in
        // `inFlightSiblings`) so a superseded load or a disappearing view cancels
        // them (L2-209 Item 1 / C68), and their results flow through a merge channel
        // rather than a structured task group. A structured group awaits ALL children
        // on scope exit, so a single sibling that IGNORES cancellation would keep the
        // whole owned-load rail alive forever; the channel + a wall-clock deadline
        // lets this load stop waiting (deadline_then_join) while a runaway sibling is
        // abandoned — its late delivery after `close()` is dropped, and the
        // generation guard is the second backstop. Grouped is still applied the
        // instant it arrives, so it is never held behind a slow 200-event backfill.
        let merge = SportsSiblingMerge<SiblingResult>()
        let backfillTask = Task { [merge] in
            let response = await Self.optional {
                try await client.fetchSportsEventBackfill(limit: Self.supplementalEventLimit)
            }
            merge.deliver(.backfill(response))
        }
        let groupedTask = Task { [merge] in
            let response = await Self.optional {
                try await client.fetchSportsGroupedFeed(limit: Self.groupedFeedLimit)
            }
            merge.deliver(.grouped(response))
        }
        inFlightSiblings = [backfillTask, groupedTask]
        let deadlineTask = Task { [merge, siblingDeadline] in
            try? await Task.sleep(nanoseconds: UInt64(max(0, siblingDeadline) * 1_000_000_000))
            merge.close()
        }

        // Consume sibling results as they arrive. Cancellation of this load (a
        // supersession or a view disappearance) closes the merge and cancels the
        // siblings AT ONCE — so the suspended `next()` wakes immediately and the load
        // terminates promptly rather than lingering until the deadline (L2-211 Item
        // 1). The deadline still bounds the NON-cancelled case where a
        // cancellation-ignoring sibling never returns.
        await withTaskCancellationHandler {
            var received = 0
            while received < 2 {
                guard let result = await merge.next() else { break }  // closed by deadline/cancel
                received += 1
                // Drop a late/cancelled child of a superseded (or stopped) load — the
                // generation guard is the publication backstop behind termination.
                guard generation == loadGeneration, !Task.isCancelled else { continue }
                switch result {
                case .backfill(let backfill): applyBackfill(backfill, start: loadStart)
                case .grouped(let grouped): applyGrouped(grouped, start: loadStart)
                }
            }
        } onCancel: {
            backfillTask.cancel()
            groupedTask.cancel()
            merge.close()
        }
        deadlineTask.cancel()
        inFlightSiblings = []

        guard generation == loadGeneration else { return }
        // Recompute the refresh interval after the merges (belt-and-suspenders — the
        // backfill excludes live events, so the live set is already known from main).
        configureAutoRefresh()
    }

    /// Cancel and drop any sibling tasks still in flight from a prior load body
    /// (L2-211 Item 1). They are unstructured, so termination must be explicit; a
    /// cooperative sibling ends promptly, and a cancellation-ignoring one is left to
    /// finish into a closed merge where its result is discarded.
    @MainActor
    private func cancelInFlightSiblings() {
        for task in inFlightSiblings { task.cancel() }
        inFlightSiblings = []
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
            // Route the timer through the single owned rail (L2-211 Item 1): the
            // refresh supersedes (cancels + joins) any prior owned load rather than
            // running as an overlapping concurrent load.
            Task { @MainActor in
                await self.startLoad()
            }
        }
        refreshArmed = true
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
        refreshArmed = false
    }

    /// Called when the owning Sports view stops (disappears) — L2-209 Item 1 / C68,
    /// hardened for L2-211 Item 1 / C73 (cancel_and_join_on_disappear). Terminates
    /// the owned load and its siblings — cancellation is real, not just a discard —
    /// stops the refresh timer, and invalidates the current generation as the
    /// publication backstop so any request that outraces cancellation can no longer
    /// mutate published state after the tab closes. `isStopped` blocks a refresh-timer
    /// callback that was already queued at teardown from starting a fresh load.
    @MainActor
    func viewDidStop() {
        isStopped = true
        loadGeneration &+= 1
        loadTask?.cancel()
        loadTask = nil
        cancelInFlightSiblings()
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
