import Foundation

/// Team identity is always the API's numeric ID, never a name search. Briefs
/// provide destinations only: readings and their clocks come from exact detail.
nonisolated struct WatchMyStuffTeamPage: Decodable, Sendable {
    struct Team: Decodable, Sendable { let id: Int; let name: String }
    struct Game: Decodable, Identifiable, Sendable {
        let id: Int; let homeTeam: String; let awayTeam: String
    }
    struct Market: Decodable, Sendable {
        let marketId: Int; let marketName: String
    }
    let team: Team
    let upcomingEvents: [Game]
    let recentEvents: [Game]
    let futures: [Market]
    var games: [Game] {
        var seen = Set<Int>()
        return (upcomingEvents + recentEvents).filter { $0.id > 0 && seen.insert($0.id).inserted }
    }
    var questions: [Market] {
        var seen = Set<Int>()
        return futures.filter { $0.marketId > 0 && seen.insert($0.marketId).inserted }
    }
}

/// Failed refreshes retain the saved heading in the view, never actionable
/// destinations from an earlier response. Only the exact team can publish rows.
nonisolated struct WatchMyStuffTeamState {
    private(set) var page: WatchMyStuffTeamPage?
    private(set) var error: String?

    mutating func beginRefresh() {
        page = nil
        error = nil
    }

    mutating func receive(_ data: Data, expectedTeamID: Int) {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard expectedTeamID > 0,
              let value = try? decoder.decode(WatchMyStuffTeamPage.self, from: data),
              value.team.id == expectedTeamID else {
            fail("Couldn't verify this team. Try again.")
            return
        }
        page = value
        error = nil
    }

    mutating func fail(_ message: String) {
        page = nil
        error = message
    }
}
