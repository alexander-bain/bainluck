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

    /// Seed `items` without a network call, so the section partition (#1471)
    /// can be tested on a captured production payload. Test-only by
    /// convention — `items` stays `private(set)` for every other caller.
    func setItemsForTesting(_ newItems: [FeedItem]) {
        items = newItems
        loading = false
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

    /// live/048 + CERT-786 — the three buckets read ONE ladder
    /// (`EventState.section`). Written as three independent comparisons they
    /// were never a partition: `suspended` matched none of them, so the match
    /// did not land in the wrong section, it landed in no section and left the
    /// screen. The one place that shows is a bug report saying "my match is
    /// gone", which is a harder thing to notice than a wrong badge.
    var liveNow: [FeedItem] {
        items.filter { EventState.section($0.event?.status) == .live }
    }

    /// True when the live bucket is holding a match nobody is watching, so the
    /// section header can say so instead of claiming "Live Now" over it.
    var liveNowHasSuspended: Bool {
        liveNow.contains { EventState.isSuspended($0.event?.status) }
    }

    var justHappened: [FeedItem] {
        items.filter { EventState.section($0.event?.status) == .finished }
    }

    var upcoming: [FeedItem] {
        items.filter {
            guard $0.type == "event" else { return false }
            return EventState.section($0.event?.status) == .upcoming
        }
    }

    var topMarkets: [FeedItem] {
        items.filter { $0.type == "futures" }
    }

    /// Is this item drawn by one of the four sections above? (#1471)
    ///
    /// The four are `liveNow` / `justHappened` / `upcoming`, all keyed on
    /// `event`, and `topMarkets`, keyed on `futures`. Nothing else has ever had
    /// a home here, and the feed has served `concept` and `tournament` items on
    /// this endpoint for months.
    private static func isPlacedByGameOrMarketSection(_ item: FeedItem) -> Bool {
        item.event != nil || item.type == "futures"
    }

    /// Everything the four sections above cannot place — event concepts (a UFC
    /// fight night, a Grand Prix) and tournaments (#1471).
    ///
    /// These fell through every section into an empty `List`, which draws as
    /// WHITE. That is Alex's 2026-09-15 report: "Tapping into a UFC card brought
    /// up a blank white screen, with no loading indicator of any kind… Tapping
    /// the golf card did the same thing." Measured the same day on the iPhone 17
    /// simulator: `sport=ufc` served 25 items and the page drew 0 rows, because
    /// the server's seen-filter had suppressed all 16 futures (it suppresses
    /// only `event` and `futures`, never `concept` or `tournament`) and the 9
    /// concepts it left behind had nowhere to go.
    ///
    /// Defined as the COMPLEMENT of what the sections place, not as an
    /// allowlist of the two types known today: the next type the backend adds
    /// must land here rather than re-open the white page.
    var otherEvents: [FeedItem] {
        items.filter { !Self.isPlacedByGameOrMarketSection($0) }
    }

    /// Would the list draw a single row? (#1471)
    ///
    /// The view picks its empty terminal on `items.isEmpty`, which asks whether
    /// the PAYLOAD was empty — a different question from whether the page has
    /// anything to show, and the gap between them is the blank screen. A page
    /// that can draw nothing must say so.
    var drawsNoRows: Bool {
        liveNow.isEmpty && justHappened.isEmpty && upcoming.isEmpty
            && topMarkets.isEmpty && otherEvents.isEmpty
            && (leagueMarkets?.sections.values.allSatisfy(\.isEmpty) ?? true)
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
