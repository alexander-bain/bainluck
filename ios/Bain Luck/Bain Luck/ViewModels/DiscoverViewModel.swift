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
    @Published private(set) var items: [FeedItem] = []
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

    /// Upper bound on how many consecutive duplicate-only / ineligible server
    /// pages a single loadMore pass will scan before surfacing a retryable
    /// error instead of spinning forever (L2-192 Item 2). Each page is up to
    /// `limit` rows, so this is a wide-but-finite forward window.
    private static let maxPageScans = 6

    init(
        client: DiscoverFeedProviding = APIClient.shared,
        lastGood: DiscoverLastGoodReading? = APIClient.shared,
        telemetry: (@Sendable (DiscoverFeedTelemetry) -> Void)? = { AnalyticsService.trackDiscoverFeedCache($0) }
    ) {
        self.client = client
        self.lastGood = lastGood
        self.telemetry = telemetry
    }

    private static let sportsCategories: Set<String> = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
        "americanfootball", "icehockey", "olympics",
    ]

    @MainActor
    func load() async {
        // Stale-while-revalidate (#1465): on a cold view model, seed the last
        // successful payload from disk so a first card renders immediately instead
        // of blocking on the 9–13s cold `/api/feed` miss (#1459). The view re-runs
        // its `now`-relative eligibility gate on this content, so nothing here
        // extends how long a settled/aged card may survive.
        if items.isEmpty, let lastGood {
            let t0 = Date()
            if let cached = await lastGood.loadLastGoodFeed() {
                let renderable = Self.renderable(cached.response.items)
                if renderable.isEmpty {
                    telemetry?(DiscoverFeedTelemetry(
                        outcome: .cacheMiss, cacheDecodeMs: Self.elapsedMs(since: t0),
                        networkMs: nil, itemCount: 0, cacheAgeSeconds: nil))
                } else {
                    items = Self.interleave(renderable)
                    hasMore = cached.response.hasMore
                    nextOffset = Self.pageBoundary(cached.response, from: 0)
                    loading = false
                    error = nil
                    isShowingCachedContent = true
                    refreshFailedShowingCache = false
                    lastGoodStoredAt = cached.storedAt
                    telemetry?(DiscoverFeedTelemetry(
                        outcome: .cacheHitServed, cacheDecodeMs: Self.elapsedMs(since: t0),
                        networkMs: nil, itemCount: renderable.count,
                        cacheAgeSeconds: cached.age(now: Date())))
                }
            } else {
                telemetry?(DiscoverFeedTelemetry(
                    outcome: .cacheMiss, cacheDecodeMs: Self.elapsedMs(since: t0),
                    networkMs: nil, itemCount: 0, cacheAgeSeconds: nil))
            }
        }

        // Only show the blocking loading state when there is nothing to render.
        // When last-good seeded content, revalidation happens silently behind it.
        if items.isEmpty {
            loading = true
            error = nil
        }

        let netStart = Date()
        for attempt in 1...3 {
            do {
                let response = try await client.fetchDiscoverFeed(limit: 200, offset: 0, eventPct: 0.15, cacheTTL: nil)
                let renderable = Self.renderable(response.items)

                if renderable.count < 10 {
                    let fallback = try await client.fetchDiscoverFeed(limit: 200, offset: 0, eventPct: nil, cacheTTL: nil)
                    let fallbackRenderable = Self.renderable(fallback.items)
                    items = Self.interleave(fallbackRenderable)
                    hasMore = fallback.hasMore
                    // Advance by the SERVER page boundary (offset + limit), not the
                    // decoded item count — the tolerant decoder drops malformed rows,
                    // so initial and incremental loads must share one contract (C29).
                    nextOffset = Self.pageBoundary(fallback, from: 0)
                } else {
                    items = Self.interleave(renderable)
                    hasMore = response.hasMore
                    nextOffset = Self.pageBoundary(response, from: 0)
                }

                // Fresh server content replaces last-good without blanking or a
                // local reorder — the server order is preserved as decoded (#1465).
                error = nil
                loading = false
                isShowingCachedContent = false
                refreshFailedShowingCache = false
                lastGoodStoredAt = nil
                telemetry?(DiscoverFeedTelemetry(
                    outcome: .revalidateSuccess, cacheDecodeMs: nil,
                    networkMs: Self.elapsedMs(since: netStart), itemCount: items.count,
                    cacheAgeSeconds: nil))
                return
            } catch is CancellationError {
                loading = false
                return
            } catch let urlError as URLError where urlError.code == .cancelled {
                loading = false
                return
            } catch {
                print("DiscoverView load error (attempt \(attempt)/3): \(error)")
                if attempt < 3 {
                    try? await Task.sleep(for: .seconds(1.5))
                }
            }
        }

        // All network attempts failed. Never blank last-good content — keep it and
        // tell the truth that the refresh failed (#1465). With nothing cached, fall
        // to the honest error state exactly as before.
        loading = false
        if !items.isEmpty {
            refreshFailedShowingCache = true
            error = "Showing recent markets — couldn't refresh"
            telemetry?(DiscoverFeedTelemetry(
                outcome: .revalidateFailedKeptCache, cacheDecodeMs: nil,
                networkMs: Self.elapsedMs(since: netStart), itemCount: items.count,
                cacheAgeSeconds: lastGoodStoredAt.map { Date().timeIntervalSince($0) }))
        } else {
            error = "Couldn't load feed"
            telemetry?(DiscoverFeedTelemetry(
                outcome: .revalidateFailedNoCache, cacheDecodeMs: nil,
                networkMs: Self.elapsedMs(since: netStart), itemCount: 0, cacheAgeSeconds: nil))
        }
    }

    /// Cards the feed can actually render (event / futures / tournament / concept).
    private static func renderable(_ items: [FeedItem]) -> [FeedItem] {
        items.filter { $0.event != nil || $0.futures != nil || $0.tournament != nil || $0.concept != nil }
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

    private static func interleave(_ items: [FeedItem]) -> [FeedItem] {
        var sports = items.filter { sportsCategories.contains(category(for: $0)) }
        var nonSports = items.filter { !sportsCategories.contains(category(for: $0)) }
        if nonSports.isEmpty { return items }

        var result: [FeedItem] = []
        var lastCategory = ""
        var sportsSince = 0
        let maxSportsRun = nonSports.count >= 4 ? 2 : 3

        while !sports.isEmpty || !nonSports.isEmpty {
            if !nonSports.isEmpty && (sportsSince >= maxSportsRun || sports.isEmpty) {
                let item = nonSports.removeFirst()
                result.append(item)
                sportsSince = 0
                lastCategory = category(for: item)
            } else if !sports.isEmpty {
                if category(for: sports[0]) == lastCategory,
                   let swapIdx = sports.prefix(5).firstIndex(where: { category(for: $0) != lastCategory }) {
                    sports.swapAt(0, swapIdx)
                }
                let item = sports.removeFirst()
                result.append(item)
                sportsSince += 1
                lastCategory = category(for: item)
            } else {
                break
            }
        }
        return result
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
