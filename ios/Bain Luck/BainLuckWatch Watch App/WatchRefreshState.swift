import Foundation

/// #1739 — what a watch list knows about how fresh it is.
///
/// Home, Live and Trending each used to build an "Xs ago" string once, inside
/// the success branch, and never again. A refresh that failed left "Just now"
/// on screen over data of any age, and the string never counted up while the
/// screen sat open. This keeps the two facts the line is made of — when the
/// data on screen was fetched, and whether the latest attempt to replace it
/// failed — and renders the line from them at read time.
///
/// Foundation only, so it compiles into the iOS test bundle (like
/// `WatchMarquee.swift`) and the rule is tested without WatchKit.
nonisolated struct WatchRefreshState: Equatable, Sendable {
    /// When the data on screen was fetched. A failed refresh never moves it.
    private(set) var shownDataFetchedAt: Date?
    /// The latest refresh failed, so the screen is showing older data.
    private(set) var lastRefreshFailed = false

    mutating func recordSuccess(fetchedAt: Date) {
        shownDataFetchedAt = fetchedAt
        lastRefreshFailed = false
    }

    mutating func recordFailure() {
        lastRefreshFailed = true
    }

    /// The small line under the list, read at `now`. Nil until data is shown.
    func ageLine(now: Date) -> String? {
        guard let at = shownDataFetchedAt else { return nil }
        let age = Self.ageText(seconds: now.timeIntervalSince(at))
        return lastRefreshFailed ? "Couldn't refresh · \(age)" : age
    }

    static func ageText(seconds: TimeInterval) -> String {
        let s = max(0, Int(seconds))
        if s < 5 { return "Just now" }
        if s < 60 { return "\(s)s ago" }
        if s < 3600 { return "\(s / 60)m ago" }
        return "\(s / 3600)h ago"
    }
}

nonisolated struct WatchLiveGame: Identifiable, Equatable, Sendable {
    let id: Int
    let homeAbbrev: String
    let awayAbbrev: String
    let homeProb: Int
    let awayProb: Int
    let homeScore: Int?
    let awayScore: Int?
    let homeColor: String?
    let awayColor: String?
    let gameClock: String?
    let sportLabel: String
}

/// #1739 — the Live tab's list and its freshness, moved out of the view model
/// so the refresh rule is testable.
///
/// A refresh REPLACES the list, including with nothing. The old rule kept the
/// last non-empty list whenever a refresh came back with no live game, so once
/// a slate ended the tab showed finished games under its "Live" title, stamped
/// "Just now", and its own "No live games" state was unreachable. Home and
/// Trending never had that guard; Live now matches them.
nonisolated struct WatchLiveList: Equatable, Sendable {
    private(set) var games: [WatchLiveGame] = []
    private(set) var refresh = WatchRefreshState()

    mutating func apply(_ items: [WatchFeedItem], fetchedAt: Date) {
        games = Self.liveGames(in: items)
        refresh.recordSuccess(fetchedAt: fetchedAt)
    }

    /// A failed refresh keeps what is on screen and says so in the age line.
    mutating func applyFailure() {
        refresh.recordFailure()
    }

    static func liveGames(in items: [WatchFeedItem]) -> [WatchLiveGame] {
        items.compactMap { item -> WatchLiveGame? in
            guard let e = item.event, e.status == "live",
                  let homeProb = e.currentOdds?.homeProbability else { return nil }
            let homeTeam = e.homeTeam ?? "Home"
            let awayTeam = e.awayTeam ?? "Away"
            let awayProb = 1.0 - homeProb
            let homeAbbrev = e.homeTeamData?.abbreviation ?? String(homeTeam.split(separator: " ").last ?? "")
            let awayAbbrev = e.awayTeamData?.abbreviation ?? String(awayTeam.split(separator: " ").last ?? "")
            // #4880 — see `PeriodLabel.liveStatusText`.
            let clockText = PeriodLabel.liveStatusText(
                period: e.espn?.period, gameClock: e.espn?.gameClock)
            return WatchLiveGame(
                id: e.id,
                homeAbbrev: homeAbbrev,
                awayAbbrev: awayAbbrev,
                homeProb: Int((homeProb * 100).rounded()),
                awayProb: Int((awayProb * 100).rounded()),
                homeScore: e.homeScore,
                awayScore: e.awayScore,
                homeColor: e.homeTeamData?.primaryColor,
                awayColor: e.awayTeamData?.primaryColor,
                gameClock: clockText,
                sportLabel: e.sportName ?? e.sport ?? ""
            )
        }
    }
}
