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
    @Published var grid: ChampionshipGridResponse?
    @Published var leagueMarkets: LeagueMarketsResponse?
    @Published var loading = true
    @Published var error: String?
    @Published var conferenceFilter: String?

    init(slug: String) {
        self.slug = slug
    }

    var displayName: String {
        grid?.name ?? slug.replacingOccurrences(of: "-", with: " ").uppercased()
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
        if let grouped = grid.groupedTeams {
            if let filter = conferenceFilter {
                return grouped[filter] ?? []
            }
            return grouped.values.flatMap { $0 }
        }
        if let filter = conferenceFilter {
            return grid.teams.filter { $0.conference == filter }
        }
        return grid.teams
    }

    /// In-memory cache shared across instances
    private static var cache: [String: (grid: ChampionshipGridResponse, date: Date)] = [:]

    @MainActor
    func load() async {
        // Show cached data immediately while refreshing in background
        if grid == nil, let cached = Self.cache[slug] {
            grid = cached.grid
            // If cache is fresh enough (<60s), skip network
            if Date().timeIntervalSince(cached.date) < 60 {
                await loadLeagueMarkets()
                return
            }
        }

        loading = true
        do {
            async let gridTask = APIClient.shared.fetchChampionshipGrid(slug: slug)
            async let marketsTask = loadLeagueMarkets()
            let freshGrid = try await gridTask
            _ = await marketsTask
            grid = freshGrid
            Self.cache[slug] = (freshGrid, Date())
            error = nil
        } catch {
            // Only show error if we have no cached data
            if grid == nil {
                self.error = error.localizedDescription
            }
            logger.error("Grid load failed for \(self.slug): \(error)")
        }
        loading = false
    }

    @MainActor
    private func loadLeagueMarkets() async {
        let sportKey = leagueGridSlugToSportKey[slug] ?? slug
        do {
            leagueMarkets = try await APIClient.shared.fetchLeagueMarkets(sportKey: sportKey)
            logger.info("League markets for \(self.slug): \(self.leagueMarkets?.totalMarkets ?? 0) total")
        } catch {
            logger.debug("League markets not available for \(self.slug): \(error)")
        }
    }
}
