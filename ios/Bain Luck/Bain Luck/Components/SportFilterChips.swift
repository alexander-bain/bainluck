import SwiftUI

/// #13001 — Shared Upcoming cutoff across every Sports-tab pill (`All`, league
/// grids, and category pills such as `Tennis`): a non-live match whose start is
/// more than `12 hours` behind `now` is dropped from `Upcoming` (and has no
/// result to show under `Just Happened`), while same-day rain delays and late
/// session carry-overs (`<= 12h`) stay visible.
enum SportsUpcomingCutoff13001 {
    nonisolated static let maxPastStartAge: TimeInterval = 12 * 3600

    nonisolated static func admitsUpcoming(_ event: FeedEventData?, now: Date) -> Bool {
        guard let event, EventState.section(of: event, now: now) == .upcoming else { return false }
        guard let start = event.commenceTime?.asDate else { return true }
        return now.timeIntervalSince(start) <= maxPastStartAge
    }
}

// MARK: - Sport Category Model

struct SportCategory: Identifiable, Hashable {
    let id: String
    let name: String
    let sportPrefixes: [String]
    let futuresCategories: [String]
    let route: Route?

    func matches(_ item: FeedItem) -> Bool {
        if id == "all" { return true }
        if let event = item.event, let sport = event.sport {
            if sportPrefixes.contains(where: { sport.hasPrefix($0) }) { return true }
        }
        if let futures = item.futures, let cat = futures.llmSportCategory?.lowercased() {
            if futuresCategories.contains(cat) { return true }
        }
        return false
    }
}

/// #13013 (`246: A`) — Wrap-aware calendar season windows matching
/// `backend/app/utils/season_windows.py` so out-of-season leagues with no game
/// on today sit at the end of the Sports pill bar even before or after load.
enum SportPillSeason13013 {
    nonisolated struct MonthDay: Comparable {
        let month: Int
        let day: Int

        nonisolated static func < (lhs: MonthDay, rhs: MonthDay) -> Bool {
            if lhs.month != rhs.month { return lhs.month < rhs.month }
            return lhs.day < rhs.day
        }
    }

    nonisolated private static func inWindow(_ md: MonthDay, start: MonthDay, end: MonthDay) -> Bool {
        if start <= end {
            return md >= start && md <= end
        }
        return md >= start || md <= end
    }

    nonisolated static func isInSeason(
        categoryId: String,
        now: Date,
        calendar: Calendar = Calendar(identifier: .gregorian)
    ) -> Bool {
        let comps = calendar.dateComponents([.month, .day], from: now)
        let md = MonthDay(month: comps.month ?? 1, day: comps.day ?? 1)
        switch categoryId {
        case "baseball":
            return inWindow(md, start: .init(month: 3, day: 20), end: .init(month: 11, day: 5))
        case "football":
            return inWindow(md, start: .init(month: 9, day: 4), end: .init(month: 2, day: 12))
        case "ncaaf":
            return inWindow(md, start: .init(month: 8, day: 22), end: .init(month: 1, day: 25))
        case "basketball":
            return inWindow(md, start: .init(month: 10, day: 20), end: .init(month: 6, day: 25))
        case "ncaab":
            return inWindow(md, start: .init(month: 11, day: 2), end: .init(month: 4, day: 10))
        case "hockey":
            return inWindow(md, start: .init(month: 10, day: 4), end: .init(month: 6, day: 25))
        default:
            // All, Soccer, Tennis, and Golf run continuously across global tours/leagues.
            return true
        }
    }
}

/// #13013 (`246: A` + `264: A`) — Fixed league order inside each activity group:
/// `All` pinned first, then `NFL → NBA → MLB → NHL → NCAAF → NCAAB → Soccer → Tennis → Golf`.
let sportCategories: [SportCategory] = [
    .init(id: "all", name: "All", sportPrefixes: [], futuresCategories: [], route: nil),
    .init(id: "football", name: "NFL", sportPrefixes: ["americanfootball_nfl"], futuresCategories: ["football"], route: .leagueGrid(slug: "nfl")),
    .init(id: "basketball", name: "NBA", sportPrefixes: ["basketball_nba", "basketball_wnba"], futuresCategories: ["basketball"], route: .leagueGrid(slug: "nba")),
    .init(id: "baseball", name: "MLB", sportPrefixes: ["baseball"], futuresCategories: ["baseball"], route: .leagueGrid(slug: "mlb")),
    .init(id: "hockey", name: "NHL", sportPrefixes: ["icehockey"], futuresCategories: ["hockey"], route: .leagueGrid(slug: "nhl")),
    .init(id: "ncaaf", name: "NCAAF", sportPrefixes: ["americanfootball_ncaaf"], futuresCategories: ["ncaaf", "college_football"], route: .leagueGrid(slug: "ncaa-football")),
    .init(id: "ncaab", name: "NCAAB", sportPrefixes: ["basketball_ncaab", "basketball_wncaab"], futuresCategories: ["ncaab", "college_basketball"], route: .leagueGrid(slug: "ncaa-basketball")),
    .init(id: "soccer", name: "Soccer", sportPrefixes: ["soccer"], futuresCategories: ["soccer"], route: .leagueGrid(slug: "epl")),
    // Tennis routes to the CATEGORY, not a league grid: `/api/leagues/tennis` answers 200 with
    // `total_markets: 0`, while `SportCategoryView(key: "tennis")` merges ATP + WTA matches and
    // Slam futures (`tennis_atp` alone drops the WTA half).
    .init(id: "tennis", name: "Tennis", sportPrefixes: ["tennis"], futuresCategories: ["tennis"], route: .sportCategory(key: "tennis", name: "Tennis")),
    .init(id: "golf", name: "Golf", sportPrefixes: ["golf"], futuresCategories: ["golf"], route: .golfCategory),
]

// MARK: - Filter Chips View

struct SportFilterChips: View {
    @Binding var selectedCategory: String
    var items: [FeedItem] = []
    var now: Date = Date()
    var calendar: Calendar = .current
    var onNavigate: ((Route) -> Void)? = nil

    private var displayedCategories: [SportCategory] {
        Self.orderedCategories(items: items, now: now, calendar: calendar)
    }

    var body: some View {
        ZStack(alignment: .trailing) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(displayedCategories) { category in
                        chipButton(category)
                    }
                    Spacer().frame(width: 20)
                }
                .padding(.horizontal)
            }

            LinearGradient(
                colors: [
                    Color.groupedBackground.opacity(0),
                    Color.groupedBackground,
                ],
                startPoint: .leading,
                endPoint: .trailing
            )
            .frame(width: 32)
            .allowsHitTesting(false)
        }
    }

    /// #13013 (`246: A` + `264: A`) — Orders Sports tab pills into three groups with
    /// one fixed league order (`NFL, NBA, MLB, NHL, NCAAF, NCAAB, Soccer, Tennis, Golf`)
    /// inside each group:
    /// 1. `All` is pinned first.
    /// 2. Sports with a game/tournament today (live, scheduled today, or just finished).
    /// 3. In-season sports with nothing today.
    /// 4. Out-of-season sports.
    /// Never orders by live-game count, and a sport never moves when its game goes live.
    static func orderedCategories(
        from base: [SportCategory] = sportCategories,
        items: [FeedItem],
        now: Date = Date(),
        calendar: Calendar = .current
    ) -> [SportCategory] {
        let pinnedAll = base.filter { $0.id == "all" }
        let rest = base.enumerated().filter { $0.element.id != "all" }

        struct CategoryActivity {
            let category: SportCategory
            let baseIndex: Int
            let tier: Int
        }

        let justHappenedWindow: TimeInterval = 18 * 3600

        let scored: [CategoryActivity] = rest.map { baseIndex, category in
            var hasGameToday = false

            for item in items where !hasGameToday {
                if let event = item.event, category.matches(item) {
                    if event.status == "live" {
                        hasGameToday = true
                    } else if EventState.section(of: event, now: now) == .finished {
                        if let start = event.commenceTime?.asDate {
                            let age = now.timeIntervalSince(start)
                            if age <= justHappenedWindow || calendar.isDate(start, inSameDayAs: now) {
                                hasGameToday = true
                            }
                        } else {
                            hasGameToday = true
                        }
                    } else if SportsUpcomingCutoff13001.admitsUpcoming(event, now: now),
                              let start = event.commenceTime?.asDate,
                              calendar.isDate(start, inSameDayAs: now) {
                        hasGameToday = true
                    }
                } else if category.id == "golf", let tournament = item.tournament {
                    let status = (tournament.scheduleStatus ?? "").lowercased()
                    if status == "live" || status == "in_progress" || tournament.marqueeWhathit == true {
                        hasGameToday = true
                    } else if let start = (tournament.commenceTime ?? tournament.startDate)?.asDate,
                              calendar.isDate(start, inSameDayAs: now) {
                        hasGameToday = true
                    }
                }
            }

            let inSeason = SportPillSeason13013.isInSeason(categoryId: category.id, now: now, calendar: calendar)
            let tier: Int
            if hasGameToday {
                tier = 0
            } else if inSeason {
                tier = 1
            } else {
                tier = 2
            }

            return CategoryActivity(
                category: category,
                baseIndex: baseIndex,
                tier: tier
            )
        }

        let sortedRest = scored.sorted { lhs, rhs in
            if lhs.tier != rhs.tier { return lhs.tier < rhs.tier }
            return lhs.baseIndex < rhs.baseIndex
        }.map(\.category)

        return pinnedAll + sortedRest
    }

    private func chipButton(_ category: SportCategory) -> some View {
        let isAll = category.id == "all"
        let isSelected = selectedCategory == category.id
        return Button {
            if isAll {
                withAnimation(.easeInOut(duration: 0.2)) {
                    selectedCategory = "all"
                }
            } else if let route = category.route {
                onNavigate?(route)
            }
        } label: {
            HStack(spacing: 4) {
                if !isAll {
                    Image(systemName: Self.chipIcon(for: category.id))
                        .font(.system(size: 10))
                }
                Text(category.name)
                    .font(.caption)
                    .fontWeight(isSelected ? .semibold : .regular)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .background(isSelected ? Color.blue.opacity(0.15) : Color.secondary.opacity(0.08))
            .foregroundStyle(isSelected ? .blue : .primary)
            .clipShape(Capsule())
        }
    }

    /// Static so a guard test can assert every chip has its own case rather than
    /// silently rendering the generic `sportscourt` fallback (native/007).
    static func chipIcon(for key: String) -> String {
        switch key {
        case "basketball": return "basketball.fill"
        case "football": return "football.fill"
        case "ncaaf": return "football.circle.fill"
        case "ncaab": return "basketball.circle.fill"
        case "baseball": return "baseball.fill"
        case "hockey": return "hockey.puck.fill"
        case "soccer": return "soccerball"
        case "tennis": return "tennis.racket"
        case "golf": return "figure.golf"
        case "politics": return "building.columns.fill"
        case "entertainment": return "film.fill"
        case "economics": return "chart.bar.fill"
        case "weather": return "cloud.sun.fill"
        default: return "sportscourt"
        }
    }
}
