import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "leagueGrid")

// Grid slug -> full sport key for league markets API
private let leagueGridSlugToSportKey: [String: String] = [
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "wnba": "basketball_wnba",
    "ncaa-basketball": "basketball_ncaab",
    "ncaa-women-basketball": "basketball_ncaab",
    "ncaa-football": "americanfootball_ncaaf",
    "epl": "soccer_epl",
    "mls": "soccer_usa_mls",
    "la-liga": "soccer_spain_la_liga",
    "champions-league": "soccer_uefa_champs_league",
    "bundesliga": "soccer_germany_bundesliga",
    "golf": "golf",
]

final class LeagueGridViewModel: ObservableObject {
    let slug: String
    @Published private(set) var grid: ChampionshipGridResponse?
    @Published private(set) var leagueMarkets: LeagueMarketsResponse?
    @Published private(set) var loading = true
    @Published private(set) var loadingMarkets = false
    @Published private(set) var error: String?
    @Published var conferenceFilter: String?

    private let isPreloadedForTest: Bool

    init(
        slug: String,
        preloadedGrid: ChampionshipGridResponse? = nil,
        preloadedMarkets: LeagueMarketsResponse? = nil
    ) {
        self.slug = slug
        self.grid = preloadedGrid
        self.leagueMarkets = preloadedMarkets
        self.isPreloadedForTest = (preloadedGrid != nil || preloadedMarkets != nil)
        if isPreloadedForTest {
            self.loading = false
        }
    }

    var displayName: String {
        grid?.name ?? slug.replacingOccurrences(of: "-", with: " ").uppercased()
    }

    var liveGames: [FeedEventData] {
        (leagueMarkets?.allGames ?? []).filter { EventState.section(of: $0) == .live }
    }

    var liveHasSuspended: Bool {
        liveGames.contains { EventState.isSuspended($0.status) }
    }

    var upcomingGames: [FeedEventData] {
        (leagueMarkets?.allGames ?? []).filter { EventState.section(of: $0) == .upcoming }
    }

    var recentGames: [FeedEventData] {
        (leagueMarkets?.allGames ?? []).filter { EventState.section(of: $0) == .finished }
    }

    var conferences: [String] {
        guard let grid else { return [] }
        if let grouped = grid.groupedTeams {
            return grouped.keys.sorted().filter { $0 != "Other" }
        }
        return []
    }

    var visibleTeams: [GridTeam] {
        guard let grid else { return [] }
        return GridLadderOrder.visibleTeams(in: grid, conferenceFilter: conferenceFilter)
    }

    /// The ranked ladder — the list whose index becomes the rank number on each card.
    func rankedTeams(_ columns: [GridColumn]) -> [GridTeam] {
        guard let grid else { return [] }
        return GridLadderOrder.ranked(
            visibleTeams,
            serverTeams: grid.teams,
            columns: columns
        )
    }

    /// In-memory cache shared across instances
    private static var cache: [String: (grid: ChampionshipGridResponse, date: Date)] = [:]
    private static var marketsCache: [String: (markets: LeagueMarketsResponse, date: Date)] = [:]

    @MainActor
    func load() async {
        guard !isPreloadedForTest else { return }

        let sportKey = leagueGridSlugToSportKey[slug] ?? slug
        if grid == nil, let cached = Self.cache[slug] {
            grid = cached.grid
        }
        if leagueMarkets == nil, let cachedM = Self.marketsCache[sportKey] {
            leagueMarkets = cachedM.markets
        }

        let gridFresh = Self.cache[slug].map { Date().timeIntervalSince($0.date) < 60 } ?? false
        let marketsFresh = Self.marketsCache[sportKey].map { Date().timeIntervalSince($0.date) < 60 } ?? false
        if gridFresh && marketsFresh {
            loading = false
            loadingMarkets = false
            return
        }

        if grid == nil && leagueMarkets == nil {
            loading = true
        }
        if !marketsFresh {
            loadingMarkets = (leagueMarkets == nil)
        }

        // #13001: publish whichever endpoint returns first instead of holding
        // `/api/playoffs/{slug}` (0.4s) hostage to `/api/leagues/{sport_key}` (2.8-5.7s).
        await withTaskGroup(of: Void.self) { group in
            if !gridFresh {
                group.addTask { @MainActor [weak self] in
                    guard let self else { return }
                    await self.loadGrid()
                }
            } else {
                loading = false
            }
            if !marketsFresh {
                group.addTask { @MainActor [weak self] in
                    guard let self else { return }
                    await self.loadLeagueMarkets()
                }
            }
        }
        loading = false
        loadingMarkets = false
    }

    @MainActor
    private func loadGrid() async {
        do {
            let freshGrid = try await APIClient.shared.fetchChampionshipGrid(slug: slug)
            grid = freshGrid
            Self.cache[slug] = (freshGrid, Date())
            error = nil
            loading = false
        } catch {
            if grid == nil && leagueMarkets == nil {
                self.error = error.localizedDescription
            }
            loading = false
            logger.error("Grid load failed for \(self.slug): \(error)")
        }
    }

    @MainActor
    private func loadLeagueMarkets() async {
        let sportKey = leagueGridSlugToSportKey[slug] ?? slug
        do {
            let fresh = try await APIClient.shared.fetchLeagueMarkets(sportKey: sportKey)
            leagueMarkets = fresh
            Self.marketsCache[sportKey] = (fresh, Date())
            loading = false
            loadingMarkets = false
            logger.info("League markets for \(self.slug): \(fresh.totalMarkets) total, \(fresh.allGames.count) games")
        } catch {
            loadingMarkets = false
            logger.debug("League markets not available for \(self.slug): \(error)")
        }
    }
}
