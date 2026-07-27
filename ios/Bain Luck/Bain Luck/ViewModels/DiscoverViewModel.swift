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

    private var nextOffset = 0
    private let client: DiscoverFeedProviding

    /// Upper bound on how many consecutive duplicate-only / ineligible server
    /// pages a single loadMore pass will scan before surfacing a retryable
    /// error instead of spinning forever (L2-192 Item 2). Each page is up to
    /// `limit` rows, so this is a wide-but-finite forward window.
    private static let maxPageScans = 6

    init(client: DiscoverFeedProviding = APIClient.shared) {
        self.client = client
    }

    private static let sportsCategories: Set<String> = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
        "americanfootball", "icehockey", "olympics",
    ]

    @MainActor
    func load() async {
        if items.isEmpty {
            loading = true
            error = nil
        }
        for attempt in 1...3 {
            do {
                let response = try await client.fetchDiscoverFeed(limit: 200, offset: 0, eventPct: 0.15, cacheTTL: nil)
                let renderable = response.items.filter { $0.event != nil || $0.futures != nil || $0.tournament != nil || $0.concept != nil }

                if renderable.count < 10 {
                    let fallback = try await client.fetchDiscoverFeed(limit: 200, offset: 0, eventPct: nil, cacheTTL: nil)
                    let fallbackRenderable = fallback.items.filter { $0.event != nil || $0.futures != nil || $0.tournament != nil || $0.concept != nil }
                    items = Self.interleave(fallbackRenderable)
                    hasMore = fallback.hasMore
                    nextOffset = fallback.offset + fallback.items.count
                } else {
                    items = Self.interleave(renderable)
                    hasMore = response.hasMore
                    nextOffset = response.offset + response.items.count
                }

                error = nil
                loading = false
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
        if items.isEmpty {
            error = "Couldn't load feed"
        }
        loading = false
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

            // Advance by the server page boundary FIRST so a page that adds no
            // new renderable IDs can never be refetched at the same offset.
            let pageEnd = response.offset + response.items.count
            let advanced = pageEnd > nextOffset
            nextOffset = max(nextOffset, pageEnd)

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

            // No new IDs this page. If the server has nothing more, or the page
            // was decoded-empty (offset couldn't advance), stop honestly.
            if !response.hasMore || !advanced {
                hasMore = false
                error = nil
                return
            }

            // Duplicate-only page but the offset advanced and the server claims
            // more — keep scanning forward, bounded by maxPageScans.
            hasMore = response.hasMore
        }

        // Exhausted the scan budget while the server still claims more but keeps
        // returning nothing new: surface a retry instead of spinning forever.
        if hasMore {
            self.error = "Couldn't find fresh markets"
        }
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
    /// `fetchFeed` surface (L2-192). Keeps production behavior identical while
    /// letting tests inject a deterministic fake.
    nonisolated func fetchDiscoverFeed(
        limit: Int,
        offset: Int,
        eventPct: Double?,
        cacheTTL: TimeInterval?
    ) async throws -> FeedResponse {
        try await fetchFeed(limit: limit, offset: offset, eventPct: eventPct, cacheTTL: cacheTTL)
    }
}
