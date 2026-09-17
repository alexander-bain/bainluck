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

// #5788 — `fullName` is a half-width caption2 under a bold acronym, and the
// tile allowed it ONE line, so eleven of the sixteen tiles printed a sentence
// fragment: "National Basket…", "NCAA Women's…", "UEFA Champion…". A truncated
// expansion is worse than no expansion — it spends a line to tell a reader
// nothing the acronym above it did not already say.
//
// So the subtitle answers the only question the acronym leaves open — what
// sport is this, or in the Soccer group, whose league is it — in as few words
// as will fit. The section header carries the rest: under COLLEGE, "Men's
// basketball" needs no "NCAA"; under SOCCER, "England" is the whole answer.
// Measured budget from the production screenshot (iPhone 17, 402pt):
// "Spanish La Liga" (15 characters) fits, everything from 16 up truncated —
// `BrowseLeagueTileLabelTests` holds that line, and the tile now wraps to two
// rather than truncating if a future string or text size overruns it anyway.
private let allLeagues: [LeagueInfo] = [
    LeagueInfo(slug: "nba", label: "NBA", fullName: "Basketball", icon: "basketball.fill", group: "Major US Leagues"),
    LeagueInfo(slug: "nfl", label: "NFL", fullName: "Football", icon: "football.fill", group: "Major US Leagues"),
    LeagueInfo(slug: "mlb", label: "MLB", fullName: "Baseball", icon: "baseball.fill", group: "Major US Leagues"),
    LeagueInfo(slug: "nhl", label: "NHL", fullName: "Hockey", icon: "hockey.puck.fill", group: "Major US Leagues"),
    LeagueInfo(slug: "ncaa-basketball", label: "NCAAB", fullName: "Men's basketball", icon: "basketball.fill", group: "College"),
    LeagueInfo(slug: "ncaa-women-basketball", label: "WNCAAB", fullName: "Women's basketball", icon: "basketball.fill", group: "College"),
    LeagueInfo(slug: "ncaa-football", label: "NCAAF", fullName: "Football", icon: "football.fill", group: "College"),
    LeagueInfo(slug: "wnba", label: "WNBA", fullName: "Women's NBA", icon: "basketball.fill", group: "Other US Leagues"),
    LeagueInfo(slug: "mls", label: "MLS", fullName: "Soccer", icon: "soccerball", group: "Other US Leagues"),
    LeagueInfo(slug: "epl", label: "EPL", fullName: "England", icon: "soccerball", group: "Soccer"),
    LeagueInfo(slug: "la-liga", label: "La Liga", fullName: "Spain", icon: "soccerball", group: "Soccer"),
    LeagueInfo(slug: "champions-league", label: "UCL", fullName: "Europe", icon: "soccerball", group: "Soccer"),
    LeagueInfo(slug: "bundesliga", label: "Bundesliga", fullName: "Germany", icon: "soccerball", group: "Soccer"),
    LeagueInfo(slug: "golf", label: "Golf", fullName: "PGA Tour", icon: "figure.golf", group: "Individual",
               route: .golfCategory),
    // Tennis had NO row here at all, so `/api/leagues/tennis_atp` — 156 markets,
    // 130 of them matches, as served on 2026-09-03 — was unreachable from the app
    // while the same data renders on the web. Alex found it by looking for the US
    // Open on his phone and not finding it.
    //
    // Pointed at the TOUR keys, never the `tennis` umbrella: the umbrella answers
    // 200 with `total_markets: 0`, so a row wired to it would look like a working
    // link to an empty page — the worst of the three outcomes.
    LeagueInfo(slug: "tennis_atp", label: "ATP", fullName: "Men's tennis", icon: "figure.tennis",
               group: "Individual", route: .sportCategory(key: "tennis_atp", name: "ATP Tennis")),
    LeagueInfo(slug: "tennis_wta", label: "WTA", fullName: "Women's tennis", icon: "figure.tennis",
               group: "Individual", route: .sportCategory(key: "tennis_wta", name: "WTA Tennis")),
]

private let groupOrder = ["Major US Leagues", "College", "Other US Leagues", "Soccer", "Individual"]

// Featured tournament hubs — `Utilities/FeaturedTournaments.swift`. Shared with
// Search, which offers the same hubs to a query that names one.

/// Where each featured hub belongs in Browse's grid, as of `now`.
///
/// Alex, 16 September: "Stale US Open leads." #6600 fixed the LINE under that
/// card — it reads "Results and title odds" now, which was the lie — but the
/// tournament whose final was played on 13 September still occupied the top of
/// the tab, above every destination that is worth reaching in an ordinary week.
/// A card can be honest and still be in the wrong place: leading the tab is
/// itself a claim that this is the thing to look at today.
///
/// So a hub LEADS only while its edition is being played, and otherwise moves
/// down. It is never dropped — the hub keeps the results and the title odds and
/// those are worth reaching all year, which is why `trailing` exists rather than
/// a `filter`. Catalog order is preserved inside each arm, and every hub lands
/// in exactly one of them: `leading + trailing` is the catalog, always.
///
/// The clock rule itself is `isBeingPlayed(asOf:)` and is deliberately NOT
/// re-implemented here — a second detector of one rule is how Browse came to
/// lead with a hub whose own header read "No match is being played right now".
/// It understates (an absent, unparsable or un-bumped date all read as not being
/// played), so the failure mode of this ordering is a live hub that sits low and
/// keeps its results, never a finished one back at the top.
nonisolated func browseFeaturedHubs(
    in catalog: [FeaturedTournament] = featuredTournaments,
    asOf now: Date = Date()
) -> (leading: [FeaturedTournament], trailing: [FeaturedTournament]) {
    (
        leading: catalog.filter { $0.isBeingPlayed(asOf: now) },
        trailing: catalog.filter { !$0.isBeingPlayed(asOf: now) }
    )
}

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
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
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
            // #2998 — Browse was the one tab `navigate(to:tab:)` could target and
            // could not receive. `bainluck://playoffs/<slug>` and `/calibration`
            // both switched to this tab and then silently dropped their route,
            // because nothing here ever read `pendingRoute`. Feed, Search and My
            // Stuff have always had this observer; Browse never did.
            .onChange(of: navCoordinator.pendingRoute) { _, _ in
                if navCoordinator.selectedTab == .leagues,
                   let route = navCoordinator.consumeRoute() {
                    path.append(route)
                }
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
        // ONE clock for the whole grid. Two `Date()` calls can straddle the
        // boundary, and a hub that led on the first and printed its resting line
        // on the second is the disagreement this pair exists to prevent, moved
        // inside a single render.
        let now = Date()
        let hubs = browseFeaturedHubs(asOf: now)

        return LazyVGrid(columns: adaptiveColumns(.featured), spacing: 14) {
            // A hub being played leads the tab. On an ordinary week there is no
            // such hub and this draws nothing, which is the common case.
            ForEach(hubs.leading) { tournament in
                featuredHubCard(tournament, asOf: now)
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
            // #6445 — the entry point that survived two sweeps of its own class.
            // #6445 gated Discover's challenge card and resolution digest and My
            // Stuff's summary; #6501 found the sign-in wall's perks and the
            // "Stats" toolbar button. All five navigate `Route.predictionStats`,
            // which is the one needle
            // `PredictionsExperienceIsGatedEverywhere6501Tests` scans for, in the
            // two views it reads. Browse's tile navigates `Route.dailyChallenge`
            // from a third file, so that scan was blind to it twice over — and
            // Alex found it on the phone on 16 September, a "Daily Challenge"
            // card still promoting a screen the same binary had switched off.
            //
            // Gated, not deleted: `Route.dailyChallenge` stays reachable and
            // flipping the flag restores this tile with the rest of the surface.
            if ReleaseSurfaces.predictionsExperienceEnabled {
                BrowseFeatureCard(
                    title: "Daily Challenge",
                    subtitle: "Five probability calls",
                    icon: "flame.fill",
                    color: .orange,
                    route: .dailyChallenge
                )
            }
            // A hub whose edition is over, or that nobody dated. It sits below
            // the destinations that are useful in any week and above "About",
            // which is the grid's footer rather than a place to go — a finished
            // tournament's results and title odds are still content, so last
            // place would be a demotion further than the defect warranted.
            ForEach(hubs.trailing) { tournament in
                featuredHubCard(tournament, asOf: now)
            }
            BrowseFeatureCard(
                title: "About Bain Luck",
                subtitle: "Sources and methodology",
                icon: "info.circle.fill",
                color: .gray,
                route: .about
            )
        }
    }

    /// One card, drawn identically wherever in the grid it lands — the position
    /// is the only thing the clock changes, and the reader who finds the US Open
    /// lower down gets the same tile they would have got at the top.
    private func featuredHubCard(_ tournament: FeaturedTournament, asOf now: Date) -> some View {
        BrowseFeatureCard(
            title: tournament.title,
            subtitle: tournament.subtitle(asOf: now),
            icon: tournament.icon,
            color: .yellow,
            route: .tournamentHub(slug: tournament.slug, name: tournament.title)
        )
    }

    /// Hidden for v1, so it is outside #5655 — which was measured off rasters of
    /// what the page actually draws. Its spec stays exactly as it was rather
    /// than inheriting a size-class rule nobody can photograph yet.
    private var topicSection: some View {
        BrowseSection(title: "Prediction Markets") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 190, maximum: 320), spacing: 12)], spacing: 12) {
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
                        LazyVGrid(columns: adaptiveColumns(.league), spacing: 10) {
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

    /// True when the page has a big canvas — any full-screen iPad, a Mac window,
    /// a Max-model phone in landscape. An iPad in a narrow split view is compact
    /// and is sized like a phone, which is what it is.
    private var isRegularWidth: Bool { horizontalSizeClass == .regular }

    /// #5655: the minimum has to grow with the canvas or `.adaptive` spends the
    /// extra width on more columns and draws each tile NARROWER than the phone
    /// does. `BrowseGridMetrics` carries the numbers and the measurements.
    private func adaptiveColumns(_ grid: BrowseGridMetrics.Grid) -> [GridItem] {
        [GridItem(
            .adaptive(
                minimum: BrowseGridMetrics.minimumTileWidth(grid, regularWidth: isRegularWidth),
                maximum: BrowseGridMetrics.maximumTileWidth
            ),
            spacing: BrowseGridMetrics.spacing
        )]
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
                    // #5788 — two lines, not one. The strings above are short
                    // enough to fit on one at the default text size; this is
                    // the net under the larger accessibility sizes and under
                    // the iPad, where `.adaptive` buys COLUMNS rather than
                    // width and a tile can be NARROWER than the iPhone's.
                    // Truncating here is the failure mode, not wrapping.
                    Text(league.fullName)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Spacer(minLength: 0)
            }
            .padding(11)
            // `maxHeight: .infinity` (#5788) so the two tiles in a row are the
            // same height when one of them wraps to a second line — without it
            // WNCAAB's "Women's basketball" grew its own card and left NCAAB
            // beside it visibly shorter.
            .frame(maxWidth: .infinity, minHeight: 58, maxHeight: .infinity, alignment: .leading)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.barTrack.opacity(0.25), lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }
}
