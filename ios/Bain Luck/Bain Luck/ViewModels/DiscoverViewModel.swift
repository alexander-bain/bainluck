import Combine
import Foundation

/// Narrow feed-fetch seam so `DiscoverViewModel` pagination can be exercised by
/// a deterministic fake client in tests (L2-192 Item 2). `APIClient` (an actor)
/// conforms via the extension at the bottom of this file; the default init arg
/// keeps production wiring unchanged.
protocol DiscoverFeedProviding: Sendable {
    nonisolated func fetchDiscoverFeed(
        limit: Int,
        offset: Int,
        eventPct: Double?,
        cacheTTL: TimeInterval?
    ) async throws -> FeedResponse
}

final class DiscoverViewModel: ObservableObject {
    @Published private(set) var items: [FeedItem] = [] {
        didSet { itemsVersion &+= 1 }
    }

    /// Monotonic version bumped on every `items` reassignment (L2-202 / C42 P2).
    /// The feed only ever replaces `items` wholesale — cold load, cache seed,
    /// pull-to-refresh, account switch, pagination merge — so a counter is a
    /// cheaper, more reliable "did the feed change" signal than diffing the array.
    /// `DiscoverView` folds this into its presentation memo signature so the
    /// interleave+group pipeline rebuilds when the feed actually changes, not on
    /// every SwiftUI body pass. Not `@Published`: it always changes in lockstep
    /// with `items`, whose publish already re-runs any dependent view body.
    private(set) var itemsVersion = 0

    @Published private(set) var loading = true
    @Published private(set) var error: String?
    @Published private(set) var loadingMore = false
    /// Exposed so the feed can show an honest end-of-feed card once pagination
    /// is exhausted (#902 item 9). Stays true until loadMoreIfNeeded confirms
    /// the API has no more pages.
    @Published private(set) var hasMore = true

    /// True while the currently rendered `items` came from the last-good disk
    /// cache and have not yet been replaced by a fresh server response (#1465).
    /// Lets the view stay honest that content is being revalidated.
    @Published private(set) var isShowingCachedContent = false

    /// True when a revalidation failed while last-good content is still on screen
    /// (#1465). The view surfaces a small, honest "showing recent — couldn't
    /// refresh" banner instead of silently presenting stale data as current.
    @Published private(set) var refreshFailedShowingCache = false

    /// When the currently shown last-good payload was stored, for honest staleness
    /// framing. Nil once fresh content replaces the cache.
    @Published private(set) var lastGoodStoredAt: Date?

    private var nextOffset = 0
    private let client: DiscoverFeedProviding
    /// Read seam for the last-good disk cache (#1465). Nil in tests that only
    /// exercise pagination so those stay hermetic and network-only.
    private let lastGood: DiscoverLastGoodReading?
    /// Sink for stale-while-revalidate telemetry (#1465). Defaults to Firebase;
    /// injectable so tests can assert emitted events deterministically.
    private let telemetry: (@Sendable (DiscoverFeedTelemetry) -> Void)?

    /// Total wall-clock budget for transient retries of the initial load
    /// (L2-201 / #1472). One budget across ALL retries — NOT a fresh timeout per
    /// attempt — so a slow/timing-out request that consumes the budget yields a
    /// single attempt rather than multiplying one load into many long requests
    /// (C42 P3). Injectable so tests drive it deterministically.
    private let retryBudget: TimeInterval
    /// Backoff between transient retries, clamped to the remaining budget.
    private let retryBackoff: TimeInterval

    /// Monotonic load identity (L2-201 / #1472). Each `load()` claims the next
    /// value; a load whose generation is superseded by a newer `load()` (pull to
    /// refresh, account switch, rapid re-entry) discards its late response instead
    /// of overwriting the current session's feed. Prevents a stale in-flight
    /// response from one identity clobbering another's.
    private var loadGeneration = 0

    /// Bounded first page (L2-201 / #1472). The initial load requests only enough
    /// cards for the first viewport so first paint no longer waits on the full
    /// former window to transfer/decode/interleave (C42 P1). The remaining pages
    /// load in the background through the existing scroll-driven
    /// `loadMoreIfNeeded` pagination/merge contract (DiscoverView prefetches ~3
    /// cards before the rendered window's end). The backend ranks the full
    /// candidate universe before slicing, so a 50-card first page returns the
    /// first 50 of the former 200 in the same order.
    static let firstPageLimit = 50

    /// Upper bound on how many consecutive duplicate-only / ineligible server
    /// pages a single loadMore pass will scan before surfacing a retryable
    /// error instead of spinning forever (L2-192 Item 2). Each page is up to
    /// `limit` rows, so this is a wide-but-finite forward window.
    private static let maxPageScans = 6

    init(
        client: DiscoverFeedProviding = APIClient.shared,
        lastGood: DiscoverLastGoodReading? = APIClient.shared,
        telemetry: (@Sendable (DiscoverFeedTelemetry) -> Void)? = { AnalyticsService.trackDiscoverFeedCache($0) },
        retryBudget: TimeInterval = 6,
        retryBackoff: TimeInterval = 1
    ) {
        self.client = client
        self.lastGood = lastGood
        self.telemetry = telemetry
        self.retryBudget = retryBudget
        self.retryBackoff = retryBackoff
    }

    private static let sportsCategories: Set<String> = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
        "americanfootball", "icehockey", "olympics",
    ]

    @MainActor
    func load() async {
        // Claim a load identity so a superseded (older) load discards its late
        // response instead of overwriting a newer session's feed (L2-201 / #1472).
        loadGeneration &+= 1
        let generation = loadGeneration
        let loadStart = Date()

        // Stale-while-revalidate (#1465): on a cold view model, seed the last
        // successful payload from disk so a first card renders immediately instead
        // of blocking on the 9–13s cold `/api/feed` miss (#1459). The view re-runs
        // its `now`-relative eligibility gate on this content, so nothing here
        // extends how long a settled/aged card may survive.
        if items.isEmpty, let lastGood {
            let t0 = Date()
            let cached = await lastGood.loadLastGoodFeed()
            // A newer load() started while we read the disk cache — its identity
            // owns the feed now; do not seed stale content over it.
            guard generation == loadGeneration else { return }
            if let cached {
                let renderable = Self.renderable(cached.response.items)
                if renderable.isEmpty {
                    telemetry?(DiscoverFeedTelemetry(
                        outcome: .cacheMiss, cacheDecodeMs: Self.elapsedMs(since: t0),
                        itemCount: 0))
                } else {
                    let mergeStart = Date()
                    items = Self.interleave(renderable)
                    let mergeMs = Self.elapsedMs(since: mergeStart)
                    hasMore = cached.response.hasMore
                    nextOffset = Self.pageBoundary(cached.response, from: 0)
                    loading = false
                    error = nil
                    isShowingCachedContent = true
                    refreshFailedShowingCache = false
                    lastGoodStoredAt = cached.storedAt
                    telemetry?(DiscoverFeedTelemetry(
                        outcome: .cacheHitServed, cacheDecodeMs: Self.elapsedMs(since: t0),
                        itemCount: renderable.count,
                        cacheAgeSeconds: cached.age(now: Date()),
                        mergeMs: mergeMs,
                        dataReadyMs: Self.elapsedMs(since: loadStart)))
                }
            } else {
                telemetry?(DiscoverFeedTelemetry(
                    outcome: .cacheMiss, cacheDecodeMs: Self.elapsedMs(since: t0),
                    itemCount: 0))
            }
        }

        // Only show the blocking loading state when there is nothing to render.
        // When last-good seeded content, revalidation happens silently behind it.
        if items.isEmpty {
            loading = true
            error = nil
        }
        // Whether a first card is already on screen from the cache seed. When
        // false, the network success below is what makes the data ready, so its
        // `dataReadyMs` is the cold time-to-data-ready (the on-screen first render
        // is tracked separately by the view — L2-206 Item 3).
        let seededFromCache = !items.isEmpty

        // One bounded first-page fetch with deadline-aware, classified retries
        // (L2-201 / #1472). The prior code re-issued a normalized-identical
        // `event_pct: nil` fallback (a no-op the backend collapses to the same
        // Discover page) and retried EVERY error — decode/4xx included — up to a
        // six-request ceiling. This makes a single attempt, retries only transient
        // transport / 5xx / 429 failures, and only while one shared budget remains.
        let netStart = Date()
        let deadline = Date().addingTimeInterval(retryBudget)
        while true {
            do {
                // One REAL cancellable deadline for the whole initial load (L2-206
                // Item 2). The bare `fetchDiscoverFeed` is only bounded by
                // URLSession's 30/60s timeouts, so a suspended request would hang
                // far past the nominal budget. Racing it against the remaining
                // budget cancels a stuck request AT the budget — and because each
                // attempt is bounded by the time LEFT (not a fresh per-attempt
                // timeout), a slow request that burns the budget yields no retry.
                let response = try await fetchWithinDeadline(deadline: deadline)
                // A newer load() superseded this one mid-flight (refresh / account
                // switch) — drop this response rather than overwrite (C42, races).
                guard generation == loadGeneration else { return }

                let renderable = Self.renderable(response.items)
                let mergeStart = Date()
                items = Self.interleave(renderable)
                let mergeMs = Self.elapsedMs(since: mergeStart)
                hasMore = response.hasMore
                // Advance by the SERVER page boundary (offset + limit), not the
                // decoded item count — the tolerant decoder drops malformed rows,
                // so initial and incremental loads must share one contract (C29).
                nextOffset = Self.pageBoundary(response, from: 0)

                // Fresh server content replaces last-good without blanking or a
                // local reorder — the server order is preserved as decoded (#1465).
                error = nil
                loading = false
                isShowingCachedContent = false
                refreshFailedShowingCache = false
                lastGoodStoredAt = nil
                telemetry?(DiscoverFeedTelemetry(
                    outcome: .revalidateSuccess,
                    networkMs: Self.elapsedMs(since: netStart), itemCount: items.count,
                    mergeMs: mergeMs,
                    dataReadyMs: seededFromCache ? nil : Self.elapsedMs(since: loadStart)))
                return
            } catch is CancellationError {
                loading = false
                return
            } catch let urlError as URLError where urlError.code == .cancelled {
                loading = false
                return
            } catch {
                // A newer load() owns the feed — stop silently, let it drive state.
                guard generation == loadGeneration else { return }
                print("DiscoverView load error: \(error)")
                // Only transient transport / 5xx / 429 self-heal; decode and
                // non-retryable 4xx cannot, so never spend a retry on them. And a
                // retry happens only while the ONE shared budget still has time —
                // a request that itself burned the budget yields no further attempt.
                let remaining = deadline.timeIntervalSinceNow
                guard Self.isRetryable(error), remaining > 0 else { break }
                try? await Task.sleep(for: .seconds(min(retryBackoff, remaining)))
                guard generation == loadGeneration else { return }
            }
        }

        // All network attempts failed. Never blank last-good content — keep it and
        // tell the truth that the refresh failed (#1465). With nothing cached, fall
        // to the honest error state exactly as before.
        guard generation == loadGeneration else { return }
        loading = false
        if !items.isEmpty {
            refreshFailedShowingCache = true
            error = "Showing recent markets — couldn't refresh"
            telemetry?(DiscoverFeedTelemetry(
                outcome: .revalidateFailedKeptCache,
                networkMs: Self.elapsedMs(since: netStart), itemCount: items.count,
                cacheAgeSeconds: lastGoodStoredAt.map { Date().timeIntervalSince($0) }))
        } else {
            error = "Couldn't load feed"
            telemetry?(DiscoverFeedTelemetry(
                outcome: .revalidateFailedNoCache,
                networkMs: Self.elapsedMs(since: netStart), itemCount: 0))
        }
    }

    /// Whether a failed fetch should be retried (L2-201 / #1472). Only transient
    /// transport failures, 5xx, and 429 can self-heal; decoding/schema failures,
    /// non-retryable 4xx, invalid URLs, and cancellation cannot, so retrying them
    /// only multiplies work (C42 P3). Handles both `APIError` (production) and the
    /// raw `URLError`/`CancellationError` deterministic fakes throw in tests.
    static func isRetryable(_ error: Error) -> Bool {
        if error is CancellationError { return false }
        if let api = error as? APIError {
            switch api {
            case .networkError:
                return !api.isCancellation
            case .httpError(let code, _):
                return code == 429 || (500...599).contains(code)
            case .decodingError, .invalidURL:
                return false
            }
        }
        if let url = error as? URLError {
            return url.code != .cancelled
        }
        if error is DeadlineExceededError { return false }
        return false
    }

    /// Thrown when the total initial-load budget elapses before a response
    /// arrives (L2-206 Item 2). Non-retryable: the deadline is the whole-load
    /// budget, so once it fires there is no time left to retry.
    struct DeadlineExceededError: Error {}

    /// Run one bounded fetch of the offset-0 first page, cancelled at `deadline`
    /// (L2-206 Item 2). The bare fetch is only bounded by URLSession's 30/60s
    /// timeouts; racing it against the remaining budget makes the six-second
    /// deadline REAL — a suspended request is cancelled at the budget instead of
    /// hanging, and because the sleep uses the time LEFT (not a fresh per-attempt
    /// timeout) the total load can never exceed the budget across retries.
    private func fetchWithinDeadline(deadline: Date) async throws -> FeedResponse {
        let remaining = deadline.timeIntervalSinceNow
        let client = self.client
        // Degenerate/exhausted budget: make a single UNBOUNDED attempt rather than
        // refuse to try — an attempt is not a retry, and the loop's own
        // `remaining > 0` check already prevents any RETRY after exhaustion, so this
        // never multiplies into many requests. A real hanging request under the real
        // production budget never reaches here: the budget starts positive, so the
        // bounded race below is what actually cancels a stuck request at the deadline.
        guard remaining > 0 else {
            return try await client.fetchDiscoverFeed(
                limit: Self.firstPageLimit, offset: 0, eventPct: 0.15, cacheTTL: nil)
        }
        return try await withThrowingTaskGroup(of: FeedResponse.self) { group in
            group.addTask {
                try await client.fetchDiscoverFeed(
                    limit: Self.firstPageLimit, offset: 0, eventPct: 0.15, cacheTTL: nil)
            }
            group.addTask {
                try await Task.sleep(for: .seconds(remaining))
                throw DeadlineExceededError()
            }
            // Cancel the loser on exit: when the deadline wins, cancelAll() cancels
            // the stuck fetch (its URLSession task is cancelled); when the fetch
            // wins, it cancels the pending sleep.
            defer { group.cancelAll() }
            guard let first = try await group.next() else { throw DeadlineExceededError() }
            return first
        }
    }

    /// Rebind the feed to a NEW auth identity (login, logout, account switch, or a
    /// failed restore that drops back to anonymous) — L2-206 Item 1. The caller
    /// (DiscoverView) has already rebound `APIClient`'s cache namespace; this
    /// clears the prior identity's in-memory cards and resets load state BEFORE
    /// reloading, so another account's items are never presented under the new
    /// identity. `load()` then claims a fresh generation (superseding any in-flight
    /// load — its late response is discarded, never overwriting the new identity)
    /// and seeds the new identity's own last-good cache.
    @MainActor
    func rebindForIdentityChange() async {
        items = []
        nextOffset = 0
        hasMore = true
        isShowingCachedContent = false
        refreshFailedShowingCache = false
        lastGoodStoredAt = nil
        error = nil
        loading = true
        await load()
    }

    /// Cards the feed can actually render, admitted through ONE shared
    /// predicate (L2-201 / #1472 — C42 P1). Previously this dropped `bundle`
    /// cards even though `DiscoverView` has a full comparison-bundle render path,
    /// so feed-driven bundles were silently discarded from the initial page AND
    /// dragged the renderable count below the old fallback threshold. A bundle is
    /// admitted only when it carries at least one renderable child; an empty /
    /// all-ineligible bundle contributes no card (matching DiscoverView's bundle
    /// sanitization) and must not seed a first card or inflate the page.
    private static func renderable(_ items: [FeedItem]) -> [FeedItem] {
        items.filter(isRenderable)
    }

    private static func isRenderable(_ item: FeedItem) -> Bool {
        if item.event != nil || item.futures != nil || item.tournament != nil || item.concept != nil {
            return true
        }
        if let bundle = item.bundle {
            return bundle.items.contains(where: isRenderable)
        }
        return false
    }

    private static func elapsedMs(since start: Date) -> Double {
        Date().timeIntervalSince(start) * 1000
    }

    /// Advance pagination toward fresh content, always terminating in one of
    /// three honest states: new cards appended, honest exhaustion (`hasMore =
    /// false`), or a retryable `error`. Never spins on a duplicate-only or
    /// decoded-empty page (C26 P2): the offset advances by the server's page
    /// boundary even when a page yields no new IDs, so the loop can never refetch
    /// the same page forever, and a bounded scan surfaces a retry rather than an
    /// indefinite "Finding fresh markets…" spinner.
    @MainActor
    func loadMoreIfNeeded() async {
        guard hasMore, !loading, !loadingMore else { return }
        loadingMore = true
        defer { loadingMore = false }

        var scans = 0
        while hasMore, scans < Self.maxPageScans {
            scans += 1

            let response: FeedResponse
            do {
                response = try await client.fetchDiscoverFeed(
                    limit: 200,
                    offset: nextOffset,
                    eventPct: 0.15,
                    cacheTTL: nil
                )
            } catch is CancellationError {
                return
            } catch let urlError as URLError where urlError.code == .cancelled {
                return
            } catch {
                // Surface a retryable error instead of swallowing it into a
                // permanent progress state (C26 P2). The view offers a retry
                // control that calls back into loadMoreIfNeeded.
                print("DiscoverView loadMore error: \(error)")
                self.error = "Couldn't load more markets"
                return
            }

            // Advance by the SERVER page boundary FIRST, not the decoded item
            // count. The tolerant FeedResponse decoder silently drops malformed
            // rows (FeedModels), so `items.count` is NOT the number of server
            // slots consumed (C29 P1) — the backend paginates
            // `feed_items[offset : offset + limit]` with
            // `has_more = (offset + limit) < total`, so the next page always
            // begins at `offset + limit`. Advancing by decoded count would
            // overlap the prior server page on a partially-malformed page
            // (burning the scan budget on duplicates) or, on a
            // fully-malformed/decoded-empty page, fail to advance and falsely
            // declare exhaustion while later pages still exist.
            let pageEnd = Self.pageBoundary(response, from: nextOffset)
            let advanced = pageEnd > nextOffset
            nextOffset = pageEnd

            let loadedIds = Set(items.map(Self.itemKey))
            let fresh = response.items.filter { !loadedIds.contains(Self.itemKey($0)) }

            if !fresh.isEmpty {
                // Real new content (may be lifecycle-stale — the view's stale
                // gate filters it and, if the whole page was rot, re-triggers
                // this method because items.count changed). Either way this is a
                // terminating, honest step forward.
                items = Self.interleave(items + fresh)
                hasMore = response.hasMore
                error = nil
                return
            }

            // No new IDs this page (duplicate-only, decoded-empty, or fully
            // malformed). Only the SERVER's own signal ends the feed.
            if !response.hasMore {
                hasMore = false
                error = nil
                return
            }

            // Defensive: the server claims more but the offset could not advance
            // (a misbehaving `limit <= 0` AND a decoded-empty page). Stop rather
            // than refetch the same page forever; treat as caught-up.
            if !advanced {
                hasMore = false
                error = nil
                return
            }

            // The server claims more and the offset advanced past this page —
            // even a fully-malformed/decoded-empty page. Keep scanning FORWARD
            // (bounded by maxPageScans) toward the next server page instead of
            // falsely ending the feed on decode loss (C29 P1).
            hasMore = response.hasMore
        }

        // Exhausted the scan budget while the server still claims more but keeps
        // returning nothing new: surface a retry instead of spinning forever.
        if hasMore {
            self.error = "Couldn't find fresh markets"
        }
    }

    /// The offset the NEXT server page begins at, given a decoded response and
    /// the current monotonic offset floor (C29 P1). The server page boundary is
    /// `response.offset + response.limit` — the contract the backend paginates on
    /// (`feed_items[offset : offset + limit]`). Decoded item count is used only
    /// as a floor so a misbehaving server that under-reports `limit` still can't
    /// stall behind a nonempty decoded page, and the result never regresses below
    /// the current offset (monotonic guarantee).
    private static func pageBoundary(_ response: FeedResponse, from currentOffset: Int) -> Int {
        let serverPageEnd = response.offset + response.limit
        let decodedPageEnd = response.offset + response.items.count
        return max(currentOffset, serverPageEnd, decodedPageEnd)
    }

    /// Page-merge interleave (L2-202): delegates to the shared linear-traversal
    /// core so the O(n²) `removeFirst()` drain is gone here and in the view's two
    /// interleave paths, with byte-for-byte identical order. This call site keeps
    /// its historical lack of a small-input guard — the core handles 0/1/2 items
    /// the same way the old inline loop did.
    private static func interleave(_ items: [FeedItem]) -> [FeedItem] {
        FeedInterleave.byCategory(items, sportsCategories: sportsCategories, category: category(for:))
    }

    private static func category(for item: FeedItem) -> String {
        if let f = item.futures { return f.llmSportCategory?.lowercased() ?? "other" }
        if let e = item.event { return e.sport?.split(separator: "_").first.map(String.init) ?? "other" }
        if let c = item.concept { return c.domain?.lowercased() ?? "other" }
        return "other"
    }

    private static func itemKey(_ item: FeedItem) -> String {
        if let event = item.event { return "event-\(event.id)" }
        if let futures = item.futures { return "futures-\(futures.id)" }
        // Bundles dedup on their stable bundle id so a comparison card cannot
        // duplicate across pages (matches DiscoverView's key) — L2-201 / #1472.
        if let bundle = item.bundle { return "bundle-\(bundle.id)" }
        // tournament/concept fall through to FeedItem.id ("tournament-<key>" /
        // "concept-<key>"), which is already stable and unique.
        return item.id
    }
}

// MARK: - Production feed-fetch conformance

extension APIClient: DiscoverFeedProviding {
    /// Thin adapter mapping the narrow Discover pagination seam onto the full
    /// feed surface (L2-192). The offset-0 page routes through
    /// `fetchFeedPersistingLastGood` so its raw body is cached as last-good for
    /// the next launch (#1465); pagination pages stay transient. Production
    /// behavior is otherwise identical, and tests inject a deterministic fake.
    nonisolated func fetchDiscoverFeed(
        limit: Int,
        offset: Int,
        eventPct: Double?,
        cacheTTL: TimeInterval?
    ) async throws -> FeedResponse {
        try await fetchFeedPersistingLastGood(limit: limit, offset: offset, eventPct: eventPct, cacheTTL: cacheTTL)
    }
}

// MARK: - Last-good read conformance (#1465)

extension APIClient: DiscoverLastGoodReading {}
