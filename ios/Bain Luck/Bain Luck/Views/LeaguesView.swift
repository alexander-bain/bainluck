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

// MARK: - View

struct LeaguesView: View {
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var path = NavigationPath()
    private let previewDiscoveryService: (any ContainerDiscoveryLoading)?
    private let previewSets: [BrowsePublicSet402A]
    private let preloadedSetImages: [String: Image]

    init(
        previewDiscoveryService: (any ContainerDiscoveryLoading)? = nil,
        previewSets: [BrowsePublicSet402A] = [],
        preloadedSetImages: [String: Image] = [:]
    ) {
        self.previewDiscoveryService = previewDiscoveryService
        self.previewSets = previewSets
        self.preloadedSetImages = preloadedSetImages
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    browseHeader
                    if let previewDiscoveryService {
                        BrowseCollectionsView(
                            service: previewDiscoveryService,
                            previewSets: previewSets,
                            preloadedSetImages: preloadedSetImages
                        )
                    } else {
                        BrowseCollectionsView(
                            previewSets: previewSets,
                            preloadedSetImages: preloadedSetImages
                        )
                    }
                    topicSection
                    leagueSections
                    BrowseSection(title: "Explore") {
                        featuredGrid
                    }
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
            .onChange(of: navCoordinator.pendingRoute, initial: true) { _, _ in
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
        Text("Sets, categories, and leagues")
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
                title: CalibrationView.readerTitle,
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
            // Finished featured hubs (`hubs.trailing`, e.g. finished US Open) are no longer
            // promoted on Browse (#13662 item 8 / #13671); only live/active hubs appear above.
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

    private var topicSection: some View {
        let columns: [GridItem] = if dynamicTypeSize.isAccessibilitySize {
            [GridItem(.flexible())]
        } else if isRegularWidth {
            [GridItem(.adaptive(minimum: 190, maximum: 320), spacing: 12)]
        } else {
            [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]
        }
        return BrowseSection(title: "Categories") {
            LazyVGrid(columns: columns, spacing: 12) {
                ForEach(BrowseCategoryLink402A.orderedAll) { cat in
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
        if dynamicTypeSize.isAccessibilitySize {
            return [GridItem(.flexible())]
        }
        return [GridItem(
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
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        NavigationLink(value: route) {
            Group {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Image(systemName: icon)
                                .font(.title3.weight(.semibold))
                                .foregroundStyle(.white)
                                .frame(width: 44, height: 44)
                                .background(color.gradient, in: RoundedRectangle(cornerRadius: 10))
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(.tertiary)
                        }
                        VStack(alignment: .leading, spacing: 3) {
                            Text(title)
                                .font(.subheadline.weight(.bold))
                                .foregroundStyle(.primary)
                                .lineLimit(nil)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                            Text(subtitle)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(nil)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                } else {
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
                }
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
    let category: BrowseCategoryLink402A
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        NavigationLink(value: category.route) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: category.icon)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.white)
                        .frame(width: 38, height: 38)
                        .background(category.color.gradient, in: RoundedRectangle(cornerRadius: 10))
                    Spacer()
                    Image(systemName: "arrow.up.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(category.color.opacity(0.85))
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(category.label)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(.primary)
                        .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 2)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(category.desc)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 2)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 118, maxHeight: .infinity, alignment: .leading)
            .background(
                colorScheme == .dark ? Color.cardBackground : DS.cardBg,
                in: RoundedRectangle(cornerRadius: 14)
            )
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(category.color.opacity(0.32), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

private struct BrowseLeagueTile: View {
    let league: LeagueInfo
    let color: Color
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        NavigationLink(value: league.route ?? Route.leagueGrid(slug: league.slug)) {
            Group {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 8) {
                            Image(systemName: league.icon)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(color)
                            Text(league.label)
                                .font(.subheadline.weight(.bold))
                                .foregroundStyle(.primary)
                                .lineLimit(nil)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 0)
                        }
                        Text(league.fullName)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(nil)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                } else {
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
                            // #5788 — two lines, not one.
                            Text(league.fullName)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }

                        Spacer(minLength: 0)
                    }
                }
            }
            .padding(11)
            .frame(maxWidth: .infinity, minHeight: 58, maxHeight: .infinity, alignment: .leading)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.barTrack.opacity(0.25), lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }
}

extension LeaguesView {
    static func exploreSampleForTest() -> AnyView {
        AnyView(
            NavigationStack {
                VStack(alignment: .leading, spacing: 14) {
                    Text("EXPLORE")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                    LeaguesView().featuredGrid
                }
                .padding(.horizontal, 22)
                .padding(.vertical, 16)
            }
        )
    }

    static func leagueTilesSampleForTest() -> AnyView {
        let sampleSlugs = Set(["nba", "mlb", "nhl", "ncaa-women-basketball", "champions-league"])
        let picks = allLeagues.filter { sampleSlugs.contains($0.slug) }
        return AnyView(
            NavigationStack {
                VStack(alignment: .leading, spacing: 14) {
                    Text("LEAGUES")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                    LazyVGrid(columns: [GridItem(.flexible())], spacing: 10) {
                        ForEach(picks) { league in
                            BrowseLeagueTile(
                                league: league,
                                color: DS.emerald
                            )
                        }
                    }
                }
                .padding(.horizontal, 22)
                .padding(.vertical, 16)
            }
        )
    }
}
