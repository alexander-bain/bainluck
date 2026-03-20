import Foundation

/// Navigation destinations for the app.
enum Route: Hashable {
    case eventDetail(id: Int)
    case futuresDetail(id: Int)
    case eiRankings
    case preferences
    case sportCategory(key: String, name: String)
    case leagueGrid(slug: String)
}
