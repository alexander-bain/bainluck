import SwiftUI

// MARK: - League Info

private struct LeagueInfo: Identifiable {
    let slug: String
    let label: String
    let fullName: String
    let icon: String
    let group: String

    var id: String { slug }
}

private let allLeagues: [LeagueInfo] = [
    LeagueInfo(slug: "nba", label: "NBA", fullName: "National Basketball Association", icon: "basketball.fill", group: "Major US Leagues"),
    LeagueInfo(slug: "nfl", label: "NFL", fullName: "National Football League", icon: "football.fill", group: "Major US Leagues"),
    LeagueInfo(slug: "mlb", label: "MLB", fullName: "Major League Baseball", icon: "baseball.fill", group: "Major US Leagues"),
    LeagueInfo(slug: "nhl", label: "NHL", fullName: "National Hockey League", icon: "hockey.puck.fill", group: "Major US Leagues"),
    LeagueInfo(slug: "ncaa-basketball", label: "NCAAB", fullName: "NCAA Men's Basketball", icon: "basketball.fill", group: "College"),
    LeagueInfo(slug: "ncaa-women-basketball", label: "WNCAAB", fullName: "NCAA Women's Basketball", icon: "basketball.fill", group: "College"),
    LeagueInfo(slug: "ncaa-football", label: "NCAAF", fullName: "NCAA Football", icon: "football.fill", group: "College"),
    LeagueInfo(slug: "wnba", label: "WNBA", fullName: "Women's NBA", icon: "basketball.fill", group: "Other US Leagues"),
    LeagueInfo(slug: "mls", label: "MLS", fullName: "Major League Soccer", icon: "soccerball", group: "Other US Leagues"),
    LeagueInfo(slug: "epl", label: "EPL", fullName: "English Premier League", icon: "soccerball", group: "Soccer"),
    LeagueInfo(slug: "la-liga", label: "La Liga", fullName: "Spanish La Liga", icon: "soccerball", group: "Soccer"),
    LeagueInfo(slug: "champions-league", label: "UCL", fullName: "UEFA Champions League", icon: "soccerball", group: "Soccer"),
    LeagueInfo(slug: "bundesliga", label: "Bundesliga", fullName: "German Bundesliga", icon: "soccerball", group: "Soccer"),
    LeagueInfo(slug: "golf", label: "Golf", fullName: "PGA Tour & Majors", icon: "figure.golf", group: "Individual"),
]

private let groupOrder = ["Major US Leagues", "College", "Other US Leagues", "Soccer", "Individual"]

private struct CategoryLink: Identifiable {
    let id: String
    let label: String
    let desc: String
    let icon: String
    let color: Color
    let route: Route
}

private let categoryLinks: [CategoryLink] = [
    CategoryLink(id: "politics", label: "Politics", desc: "Elections, policy, geopolitics", icon: "building.columns.fill", color: .indigo, route: .politics),
    CategoryLink(id: "entertainment", label: "Entertainment", desc: "Awards, box office, culture", icon: "film.fill", color: .pink, route: .entertainment),
    CategoryLink(id: "economics", label: "Economics", desc: "Fed rates, inflation, GDP", icon: "chart.bar.fill", color: .purple, route: .economics),
    CategoryLink(id: "weather", label: "Weather", desc: "Temperature, rainfall, storms", icon: "cloud.sun.fill", color: .orange, route: .weather),
]

// MARK: - View

struct LeaguesView: View {
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            List {
                Section("Explore") {
                    NavigationLink(value: Route.futuresList) {
                        HStack(spacing: 12) {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .font(.body)
                                .foregroundStyle(.white)
                                .frame(width: 32, height: 32)
                                .background(Color.indigo, in: RoundedRectangle(cornerRadius: 8))
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Futures Markets")
                                    .font(.subheadline.weight(.semibold))
                                Text("Browse all prediction markets")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    NavigationLink(value: Route.calibration) {
                        HStack(spacing: 12) {
                            Image(systemName: "chart.dots.scatter")
                                .font(.body)
                                .foregroundStyle(.white)
                                .frame(width: 32, height: 32)
                                .background(Color.teal, in: RoundedRectangle(cornerRadius: 8))
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Calibration")
                                    .font(.subheadline.weight(.semibold))
                                Text("Do markets predict?")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    NavigationLink(value: Route.dailyChallenge) {
                        HStack(spacing: 12) {
                            Image(systemName: "flame.fill")
                                .font(.body)
                                .foregroundStyle(.white)
                                .frame(width: 32, height: 32)
                                .background(Color.orange, in: RoundedRectangle(cornerRadius: 8))
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Daily Challenge")
                                    .font(.subheadline.weight(.semibold))
                                Text("5 questions, track your streak")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    NavigationLink(value: Route.about) {
                        HStack(spacing: 12) {
                            Image(systemName: "info.circle")
                                .font(.body)
                                .foregroundStyle(.white)
                                .frame(width: 32, height: 32)
                                .background(Color.gray, in: RoundedRectangle(cornerRadius: 8))
                            VStack(alignment: .leading, spacing: 2) {
                                Text("About Bain Luck")
                                    .font(.subheadline.weight(.semibold))
                                Text("Sources, methodology, philosophy")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                }

                Section("Prediction Markets") {
                    ForEach(categoryLinks) { cat in
                        NavigationLink(value: cat.route) {
                            HStack(spacing: 12) {
                                Image(systemName: cat.icon)
                                    .font(.body)
                                    .foregroundStyle(.white)
                                    .frame(width: 32, height: 32)
                                    .background(cat.color, in: RoundedRectangle(cornerRadius: 8))
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(cat.label)
                                        .font(.subheadline.weight(.semibold))
                                    Text(cat.desc)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .padding(.vertical, 2)
                        }
                    }
                }

                ForEach(groupOrder, id: \.self) { group in
                    let leagues = allLeagues.filter { $0.group == group }
                    if !leagues.isEmpty {
                        Section(group) {
                            ForEach(leagues) { league in
                                NavigationLink(value: league.slug == "golf" ? Route.golfCategory : Route.leagueGrid(slug: league.slug)) {
                                    HStack(spacing: 12) {
                                        Image(systemName: league.icon)
                                            .font(.body)
                                            .foregroundStyle(.white)
                                            .frame(width: 32, height: 32)
                                            .background(Color.secondary.opacity(0.6), in: RoundedRectangle(cornerRadius: 8))
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(league.label)
                                                .font(.subheadline)
                                                .fontWeight(.semibold)
                                            Text(league.fullName)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                    .padding(.vertical, 2)
                                }
                            }
                        }
                    }
                }
            }
            #if os(iOS)
            .listStyle(.insetGrouped)
            #endif
            .navigationTitle("Browse")
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
            .onAppear {
                AnalyticsService.trackScreen(name: "leagues", type: "leagues_index")
            }
        }
    }
}
