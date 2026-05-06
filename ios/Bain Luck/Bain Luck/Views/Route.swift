import Foundation

/// Navigation destinations for the app.
enum Route: Hashable {
    case eventDetail(id: Int)
    case futuresDetail(id: Int)
    case eiRankings
    case preferences
    case sportCategory(key: String, name: String)
    case leagueGrid(slug: String)
    case golfCategory
    case golfLeaderboard
    case golfTournament(slug: String, name: String)
    case futuresList
    case teamDetail(slug: String)
    case predictionStats
    case weather
    case economics
    case about
}
