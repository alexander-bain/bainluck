import SwiftUI

// MARK: - League Info

struct LeagueInfo: Identifiable {
    let slug: String
    let label: String
    let fullName: String
    let emoji: String
    let group: String

    var id: String { slug }
}

private let allLeagues: [LeagueInfo] = [
    LeagueInfo(slug: "nba", label: "NBA", fullName: "National Basketball Association", emoji: "\u{1F3C0}", group: "Major US Leagues"),
    LeagueInfo(slug: "nfl", label: "NFL", fullName: "National Football League", emoji: "\u{1F3C8}", group: "Major US Leagues"),
    LeagueInfo(slug: "mlb", label: "MLB", fullName: "Major League Baseball", emoji: "\u{26BE}", group: "Major US Leagues"),
    LeagueInfo(slug: "nhl", label: "NHL", fullName: "National Hockey League", emoji: "\u{1F3D2}", group: "Major US Leagues"),
    LeagueInfo(slug: "ncaa-basketball", label: "NCAAB", fullName: "NCAA Men's Basketball", emoji: "\u{1F3C0}", group: "College"),
    LeagueInfo(slug: "ncaa-women-basketball", label: "WNCAAB", fullName: "NCAA Women's Basketball", emoji: "\u{1F3C0}", group: "College"),
    LeagueInfo(slug: "ncaa-football", label: "NCAAF", fullName: "NCAA Football", emoji: "\u{1F3C8}", group: "College"),
    LeagueInfo(slug: "wnba", label: "WNBA", fullName: "Women's NBA", emoji: "\u{1F3C0}", group: "Other US Leagues"),
    LeagueInfo(slug: "mls", label: "MLS", fullName: "Major League Soccer", emoji: "\u{26BD}", group: "Other US Leagues"),
    LeagueInfo(slug: "epl", label: "EPL", fullName: "English Premier League", emoji: "\u{26BD}", group: "Soccer"),
    LeagueInfo(slug: "la-liga", label: "La Liga", fullName: "Spanish La Liga", emoji: "\u{26BD}", group: "Soccer"),
    LeagueInfo(slug: "champions-league", label: "UCL", fullName: "UEFA Champions League", emoji: "\u{26BD}", group: "Soccer"),
    LeagueInfo(slug: "bundesliga", label: "Bundesliga", fullName: "German Bundesliga", emoji: "\u{26BD}", group: "Soccer"),
    LeagueInfo(slug: "golf", label: "Golf", fullName: "PGA Tour & Majors", emoji: "\u{26F3}", group: "Individual"),
]

private let groupOrder = ["Major US Leagues", "College", "Other US Leagues", "Soccer", "Individual"]

// MARK: - View

struct LeaguesView: View {
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            List {
                ForEach(groupOrder, id: \.self) { group in
                    let leagues = allLeagues.filter { $0.group == group }
                    if !leagues.isEmpty {
                        Section(group) {
                            ForEach(leagues) { league in
                                NavigationLink(value: league.slug == "golf" ? Route.golfCategory : Route.leagueGrid(slug: league.slug)) {
                                    HStack(spacing: 12) {
                                        Text(league.emoji)
                                            .font(.title2)
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(league.label)
                                                .font(.subheadline)
                                                .fontWeight(.semibold)
                                            Text(league.fullName)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                    .padding(.vertical, 4)
                                }
                            }
                        }
                    }
                }
            }
            #if os(iOS)
            .listStyle(.insetGrouped)
            #endif
            .navigationTitle("Leagues")
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .leagueGrid(let slug):
                    LeagueGridView(slug: slug)
                case .eventDetail(let id):
                    EventDetailView(eventId: id)
                case .futuresDetail(let id):
                    FuturesDetailView(marketId: id)
                case .eiRankings:
                    EmptyView()
                case .preferences:
                    PreferencesView()
                case .sportCategory(let key, let name):
                    SportCategoryView(categoryKey: key, categoryName: name)
                case .golfCategory:
                    GolfCategoryView()
                case .golfLeaderboard:
                    GolfCategoryView()
                case .golfTournament(_, let name):
                    SportCategoryView(categoryKey: "golf", categoryName: name)
                case .futuresList:
                    FuturesListView()
                case .teamDetail(_):
                    Text("Team")
                case .predictionStats:
                    PredictionStatsView()
                case .weather:
                    WeatherView()
                case .economics:
                    EconomicsView()
                case .politics:
                    PoliticsView()
                case .entertainment:
                    EntertainmentView()
                case .about:
                    Text("About")
                }
            }
            .onAppear {
                AnalyticsService.trackScreen(name: "leagues", type: "leagues_index")
            }
        }
    }
}
