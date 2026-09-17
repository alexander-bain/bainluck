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
    /// One golf tournament — `/api/golf/tournaments/{slug}` (#1471).
    ///
    /// ⚠️ **NOT `tournamentHub`.** These two look interchangeable and are not:
    /// a golf slug sent to the registered hub is a guaranteed 404. See the
    /// destination switch below.
    case golfTournament(slug: String, name: String)
    /// A registered tournament hub — `/api/tournaments/{slug}`. **Tennis draws.**
    case tournamentHub(slug: String, name: String)
    /// One fight card — `/api/event/{key}`, the endpoint the web's
    /// `/event/<domain>/<slug>` page reads (#6667). `key` is the canonical
    /// `event:<domain>:<slug>` exactly as the feed served it.
    case conceptCard(key: String, name: String)
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
        // #1471. This read `SportCategoryView(categoryKey: "golf", …)` and
        // discarded the slug with `_`, so EVERY tournament row on the Golf page
        // led back to a golf-shaped list of the same cards — Alex's "duplicate
        // card", written literally in the route table. A slug is carried here
        // to be used; an empty one is the only case with nowhere to go, and it
        // falls back to the category rather than opening a screen that can only
        // fail.
        case .golfTournament(let slug, let name):
            if slug.isEmpty {
                GolfCategoryView()
            } else {
                GolfTournamentView(slug: slug, displayName: name)
            }
        case .tournamentHub(let slug, let name): TournamentHubView(slug: slug, displayName: name)
        case .conceptCard(let key, let name): ConceptCardView(key: key, displayName: name)
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
