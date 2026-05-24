import Foundation
import SwiftUI

/// Navigation destinations for the app.
enum Route: Hashable {
    case eventDetail(id: Int)
    case futuresDetail(id: Int)
    case preferences
    case discoverLabeling
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
    case politics
    case entertainment
    case about
    case dailyChallenge
    case friendChallenge(code: String)
    case eventModels(id: Int)
    case calibration
}

struct RouteDestination: View {
    let route: Route

    var body: some View {
        switch route {
        case .eventDetail(let id): EventDetailView(eventId: id)
        case .futuresDetail(let id): FuturesDetailView(marketId: id)
        case .preferences: PreferencesView()
        case .discoverLabeling: DiscoverLabelingView()
        case .sportCategory(let key, let name): SportCategoryView(categoryKey: key, categoryName: name)
        case .leagueGrid(let slug): LeagueGridView(slug: slug)
        case .golfCategory: GolfCategoryView()
        case .golfLeaderboard: GolfCategoryView()
        case .golfTournament(_, let name): SportCategoryView(categoryKey: "golf", categoryName: name)
        case .futuresList: FuturesListView()
        case .teamDetail(let slug): TeamDetailView(slug: slug)
        case .predictionStats: PredictionStatsView()
        case .weather: WeatherView()
        case .economics: EconomicsView()
        case .politics: PoliticsView()
        case .entertainment: EntertainmentView()
        case .about: AboutView()
        case .dailyChallenge: DailyChallengeView()
        case .friendChallenge(let code): FriendChallengeView(challengeCode: code)
        case .eventModels(let id): EventModelsView(eventId: id)
        case .calibration: CalibrationView()
        }
    }
}
