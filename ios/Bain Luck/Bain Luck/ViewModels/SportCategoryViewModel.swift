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
        let isInitial = items.isEmpty && leagueMarkets == nil
        if isInitial { loading = true }

        // #13001: publish whichever source arrives first so Tennis (`tennis_atp` + `tennis_wta`
        // in ~0.4s) draws matches immediately without waiting 4s+ on `/api/feed`, and use
        // `mode: "sports"` on the category feed.
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor [weak self] in
                guard let self else { return }
                await self.loadLeagueMarkets()
                if !self.drawsNoRows {
                    self.loading = false
                }
            }
            group.addTask { @MainActor [weak self] in
                guard let self else { return }
                do {
                    let feed = try await APIClient.shared.fetchFeed(
                        sport: self.categoryKey,
                        limit: self.pageSize,
                        offset: 0,
                        mode: "sports"
                    )
                    self.items = feed.items
                    self.hasMore = feed.hasMore
                    self.error = nil
                    self.loading = false
                    logger.info("Category \(self.categoryKey) loaded: \(self.items.count) items")
                } catch {
                    if isInitial && self.drawsNoRows {
                        self.error = error.localizedDescription
                    }
                    self.loading = false
                    logger.error("Category feed error: \(error)")
                }
            }
        }
        loading = false
    }

    /// Seed `items` without a network call, so the section partition (#1471)
    /// can be tested on a captured production payload. Test-only by
    /// convention — `items` stays `private(set)` for every other caller.
    func setItemsForTesting(_ newItems: [FeedItem], leagueMarkets: LeagueMarketsResponse? = nil) {
        items = newItems
        self.leagueMarkets = leagueMarkets
        loading = false
    }

    func loadMore() async {
        guard !loadingMore, hasMore else { return }
        loadingMore = true
        do {
            let feed = try await APIClient.shared.fetchFeed(
                sport: categoryKey,
                limit: pageSize,
                offset: items.count,
                mode: "sports"
            )
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
        items.filter { EventState.section(of: $0.event) == .live }
    }

    /// True when the live bucket is holding a match nobody is watching, so the
    /// section header can say so instead of claiming "Live Now" over it.
    var liveNowHasSuspended: Bool {
        liveNow.contains { EventState.isSuspended($0.event?.status) }
    }

    var justHappened: [FeedItem] {
        items.filter { EventState.section(of: $0.event) == .finished }
    }

    var upcoming: [FeedItem] {
        items.filter {
            guard $0.type == "event" else { return false }
            return EventState.section(of: $0.event) == .upcoming
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
    private var feedEventIDs: Set<Int> {
        Set(items.compactMap { $0.event?.id })
    }

    var leagueLiveGames: [FeedEventData] {
        let seen = feedEventIDs
        return (leagueMarkets?.allGames ?? []).filter {
            !seen.contains($0.id) && EventState.section(of: $0) == .live
        }
    }

    var leagueLiveHasSuspended: Bool {
        liveNowHasSuspended || leagueLiveGames.contains { EventState.isSuspended($0.status) }
    }

    var leagueUpcomingGames: [FeedEventData] {
        let seen = feedEventIDs
        return (leagueMarkets?.allGames ?? []).filter {
            !seen.contains($0.id) && EventState.section(of: $0) == .upcoming
        }
    }

    var leagueRecentGames: [FeedEventData] {
        let seen = feedEventIDs
        return (leagueMarkets?.allGames ?? []).filter {
            !seen.contains($0.id) && EventState.section(of: $0) == .finished
        }
    }

    var drawsNoRows: Bool {
        liveNow.isEmpty && justHappened.isEmpty && upcoming.isEmpty
            && leagueLiveGames.isEmpty && leagueUpcomingGames.isEmpty && leagueRecentGames.isEmpty
            && topMarkets.isEmpty && otherEvents.isEmpty
            && (leagueMarkets?.sections.values.allSatisfy(\.isEmpty) ?? true)
    }

    static func mergeTourLeagueResponses(_ responses: [LeagueMarketsResponse], sportKey: String = "tennis") -> LeagueMarketsResponse {
        var mergedSections: [String: [LeagueMarketItem]] = [:]
        var seenMarketIDs = Set<Int>()
        for r in responses {
            for (k, rows) in r.sections {
                for row in rows where seenMarketIDs.insert(row.id).inserted {
                    mergedSections[k, default: []].append(row)
                }
            }
        }
        var seenUpcoming = Set<Int>()
        let upcoming = responses
            .flatMap(\.upcomingGames)
            .filter { seenUpcoming.insert($0.id).inserted }
            .sorted { ($0.commenceTime ?? "") < ($1.commenceTime ?? "") }

        var seenRecent = Set<Int>()
        let recent = responses
            .flatMap(\.recentResults)
            .filter { !seenUpcoming.contains($0.id) && seenRecent.insert($0.id).inserted }
            .sorted { ($0.commenceTime ?? "") > ($1.commenceTime ?? "") }

        let total = mergedSections.values.reduce(0) { $0 + $1.count }
        let dropped = responses.reduce(0) { $0 + $1.droppedMarkets }
        return LeagueMarketsResponse(
            sportKey: sportKey,
            sections: mergedSections,
            totalMarkets: total,
            droppedMarkets: dropped,
            upcomingGames: upcoming,
            recentResults: recent
        )
    }

    private func loadLeagueMarkets() async {
        if categoryKey == "tennis" {
            async let atpTask = try? APIClient.shared.fetchLeagueMarkets(sportKey: "tennis_atp")
            async let wtaTask = try? APIClient.shared.fetchLeagueMarkets(sportKey: "tennis_wta")
            let parts = await [atpTask, wtaTask].compactMap { $0 }
            if !parts.isEmpty {
                let merged = Self.mergeTourLeagueResponses(parts, sportKey: "tennis")
                leagueMarkets = merged
                logger.info("Tennis tour markets merged: \(merged.totalMarkets) markets, \(merged.allGames.count) matches")
            }
            return
        }
        do {
            leagueMarkets = try await APIClient.shared.fetchLeagueMarkets(sportKey: categoryKey)
            logger.info("League markets for \(self.categoryKey): \(self.leagueMarkets?.totalMarkets ?? 0) total")
        } catch {
            logger.debug("League markets not available for \(self.categoryKey): \(error)")
        }
    }
}
