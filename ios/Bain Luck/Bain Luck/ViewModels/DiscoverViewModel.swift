import Combine
import Foundation

final class DiscoverViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var loading = false
    @Published var error: String?
    @Published private(set) var loadingMore = false

    private var hasMore = true
    private var nextOffset = 0

    private static let sportsCategories: Set<String> = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
        "americanfootball", "icehockey", "olympics",
    ]

    @MainActor
    func load() async {
        loading = true
        error = nil
        do {
            let response = try await APIClient.shared.fetchFeed(limit: 200, eventPct: 0.15, cacheTTL: nil)
            items = Self.interleave(response.items)
            hasMore = response.hasMore
            nextOffset = response.offset + response.items.count
        } catch is CancellationError {
            return
        } catch let urlError as URLError where urlError.code == .cancelled {
            return
        } catch {
            print("DiscoverView load error: \(error)")
            if items.isEmpty {
                self.error = error.localizedDescription
            }
        }
        loading = false
    }

    @MainActor
    func loadMoreIfNeeded() async {
        guard hasMore, !loading, !loadingMore else { return }
        loadingMore = true
        defer { loadingMore = false }

        do {
            let loadedIds = Set(items.map(Self.itemKey))
            let offsets = Array(Set([0, nextOffset])).sorted()
            var sawMore = false

            for offset in offsets {
                let response = try await APIClient.shared.fetchFeed(
                    limit: 200,
                    offset: offset,
                    eventPct: 0.15,
                    cacheTTL: nil
                )
                sawMore = sawMore || response.hasMore
                let fresh = response.items.filter { !loadedIds.contains(Self.itemKey($0)) }
                if fresh.isEmpty { continue }

                items = Self.interleave(items + fresh)
                nextOffset = max(nextOffset, response.offset + response.items.count)
                hasMore = response.hasMore
                return
            }

            if !sawMore {
                hasMore = false
            }
        } catch {
            print("DiscoverView loadMore error: \(error)")
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
        return "other"
    }

    private static func itemKey(_ item: FeedItem) -> String {
        if let event = item.event { return "event-\(event.id)" }
        if let futures = item.futures { return "futures-\(futures.id)" }
        return item.id
    }
}
