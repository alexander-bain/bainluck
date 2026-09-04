import SwiftUI

// MARK: - League Info

private struct LeagueInfo: Identifiable {
    let slug: String
    let label: String
    let fullName: String
    let icon: String
    let group: String
    /// Where the tile navigates. Defaults to the championship-grid page, which is
    /// the right surface for a league of TEAMS chasing one trophy. Individual
    /// sports have no such grid — golf has always overridden this, and tennis
    /// (#2560's native sibling) does the same.
    let route: Route?

    init(slug: String, label: String, fullName: String, icon: String, group: String, route: Route? = nil) {
        self.slug = slug
        self.label = label
        self.fullName = fullName
        self.icon = icon
        self.group = group
        self.route = route
    }

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
    LeagueInfo(slug: "golf", label: "Golf", fullName: "PGA Tour & Majors", icon: "figure.golf", group: "Individual",
               route: .golfCategory),
    // Tennis had NO row here at all, so `/api/leagues/tennis_atp` — 156 markets,
    // 130 of them matches, as served on 2026-09-03 — was unreachable from the app
    // while the same data renders on the web. Alex found it by looking for the US
    // Open on his phone and not finding it.
    //
    // Pointed at the TOUR keys, never the `tennis` umbrella: the umbrella answers
    // 200 with `total_markets: 0`, so a row wired to it would look like a working
    // link to an empty page — the worst of the three outcomes.
    LeagueInfo(slug: "tennis_atp", label: "ATP", fullName: "Men's Tennis Tour", icon: "figure.tennis",
               group: "Individual", route: .sportCategory(key: "tennis_atp", name: "ATP Tennis")),
    LeagueInfo(slug: "tennis_wta", label: "WTA", fullName: "Women's Tennis Tour", icon: "figure.tennis",
               group: "Individual", route: .sportCategory(key: "tennis_wta", name: "WTA Tennis")),
]

private let groupOrder = ["Major US Leagues", "College", "Other US Leagues", "Soccer", "Individual"]

// MARK: - Featured tournament hubs

private struct FeaturedTournament: Identifiable {
    let slug: String
    let title: String
    let subtitle: String
    let icon: String

    var id: String { slug }
}

/// Tournament hubs promoted to the top of Browse.
///
/// HAND-MAINTAINED, and that is the known limitation rather than the design:
/// `REGISTERED_TOURNAMENTS` lives on the server and is not exposed as a list, so
/// the phone cannot ask which hubs exist or which one is being played this week.
/// A slug listed here stays listed after its final — the hub itself degrades
/// honestly (it keeps serving results and the finished board), but Browse will
/// keep offering the US Open in March until either this list is edited or the
/// API grows an index. Tracked as a follow-up; not worth blocking the hub on.
private let featuredTournaments: [FeaturedTournament] = [
    FeaturedTournament(
        slug: "us-open",
        title: "US Open",
        subtitle: "Live matches, results, title odds",
        icon: "tennis.racket"
    ),
]

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
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    browseHeader
                    featuredGrid
                    // topicSection — hidden for v1 (prediction market category pages not ready)
                    leagueSections
                }
                .padding(.horizontal, 22)
                .padding(.vertical, 18)
                .frame(maxWidth: 1100, alignment: .leading)
            }
            .background(Color.groupedBackground.opacity(0.35))
            .navigationTitle("Browse")
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
            .onAppear {
                AnalyticsService.trackScreen(name: "leagues", type: "leagues_index")
            }
        }
    }

    /// Subtitle only. The word "Browse" is already the navigation title, and
    /// printing it again here rendered the tab's name twice, one line apart.
    private var browseHeader: some View {
        Text("Markets, sports, and tools")
            .font(.subheadline)
            .foregroundStyle(.secondary)
    }

    private var featuredGrid: some View {
        LazyVGrid(columns: adaptiveColumns(minimum: 230), spacing: 14) {
            ForEach(featuredTournaments) { tournament in
                BrowseFeatureCard(
                    title: tournament.title,
                    subtitle: tournament.subtitle,
                    icon: tournament.icon,
                    color: .yellow,
                    route: .tournamentHub(slug: tournament.slug, name: tournament.title)
                )
            }
            BrowseFeatureCard(
                title: "Futures Markets",
                subtitle: "All prediction markets",
                icon: "chart.line.uptrend.xyaxis",
                color: .indigo,
                route: .futuresList
            )
            BrowseFeatureCard(
                title: "Calibration",
                subtitle: "Market track record",
                icon: "chart.dots.scatter",
                color: .teal,
                route: .calibration
            )
            BrowseFeatureCard(
                title: "Daily Challenge",
                subtitle: "Five probability calls",
                icon: "flame.fill",
                color: .orange,
                route: .dailyChallenge
            )
            BrowseFeatureCard(
                title: "About Bain Luck",
                subtitle: "Sources and methodology",
                icon: "info.circle.fill",
                color: .gray,
                route: .about
            )
        }
    }

    private var topicSection: some View {
        BrowseSection(title: "Prediction Markets") {
            LazyVGrid(columns: adaptiveColumns(minimum: 190), spacing: 12) {
                ForEach(categoryLinks) { cat in
                    BrowseTopicCard(category: cat)
                }
            }
        }
    }

    private var leagueSections: some View {
        VStack(alignment: .leading, spacing: 24) {
            ForEach(groupOrder, id: \.self) { group in
                let leagues = allLeagues.filter { $0.group == group }
                if !leagues.isEmpty {
                    BrowseSection(title: group) {
                        LazyVGrid(columns: adaptiveColumns(minimum: 150), spacing: 10) {
                            ForEach(leagues) { league in
                                BrowseLeagueTile(
                                    league: league,
                                    color: leagueColor(league)
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    private func adaptiveColumns(minimum: CGFloat) -> [GridItem] {
        [GridItem(.adaptive(minimum: minimum, maximum: 320), spacing: 12)]
    }

    private func leagueColor(_ league: LeagueInfo) -> Color {
        switch league.slug {
        case "nba", "ncaa-basketball", "ncaa-women-basketball", "wnba": return .orange
        case "nfl", "ncaa-football": return .green
        case "mlb": return .red
        case "nhl": return .blue
        case "mls", "epl", "la-liga", "champions-league", "bundesliga": return .mint
        case "golf": return .teal
        case "tennis_atp", "tennis_wta": return .yellow
        default: return .secondary
        }
    }
}

private struct BrowseSection<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
                .textCase(.uppercase)
                .tracking(0.6)
            content
        }
    }
}

private struct BrowseFeatureCard: View {
    let title: String
    let subtitle: String
    let icon: String
    let color: Color
    let route: Route

    var body: some View {
        NavigationLink(value: route) {
            HStack(spacing: 13) {
                Image(systemName: icon)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white)
                    .frame(width: 44, height: 44)
                    .background(color.gradient, in: RoundedRectangle(cornerRadius: 10))

                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.primary)
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer(minLength: 4)

                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.tertiary)
            }
            .padding(14)
            .frame(minHeight: 76)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.35), lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }
}

private struct BrowseTopicCard: View {
    let category: CategoryLink

    var body: some View {
        NavigationLink(value: category.route) {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Image(systemName: category.icon)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.white)
                        .frame(width: 40, height: 40)
                        .background(category.color.gradient, in: RoundedRectangle(cornerRadius: 10))
                    Spacer()
                    Image(systemName: "arrow.up.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(category.color.opacity(0.75))
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(category.label)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(.primary)
                    Text(category.desc)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(15)
            .frame(maxWidth: .infinity, minHeight: 128, alignment: .leading)
            .background(category.color.opacity(0.08), in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(category.color.opacity(0.18), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

private struct BrowseLeagueTile: View {
    let league: LeagueInfo
    let color: Color

    var body: some View {
        NavigationLink(value: league.route ?? Route.leagueGrid(slug: league.slug)) {
            HStack(spacing: 10) {
                Image(systemName: league.icon)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(color)
                    .frame(width: 34, height: 34)
                    .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 9))

                VStack(alignment: .leading, spacing: 2) {
                    Text(league.label)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                    Text(league.fullName)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)
            }
            .padding(11)
            .frame(maxWidth: .infinity, minHeight: 58, alignment: .leading)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.barTrack.opacity(0.25), lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }
}
