import Foundation

// App only: the game page fetches the Live Activity's crests (GameActivityCrests).
#if os(iOS)
extension EventDetailView {
    /// The page's own crest (the served small logo), else the ESPN crest the
    /// page falls back to.
    nonisolated static func activityCrestURL(served: String?, team: String) -> URL? {
        if let served, let url = URL(string: served), url.scheme == "https" { return url }
        return espnTeamLogoURL(for: team).flatMap(URL.init(string:))
    }

    static func prefetchActivityCrests(_ event: EventDetail) async {
        await GameActivityCrests.prefetch(
            eventID: event.id,
            away: activityCrestURL(served: event.awayTeamData?.logoSmall, team: event.awayTeam),
            home: activityCrestURL(served: event.homeTeamData?.logoSmall, team: event.homeTeam))
    }
}
#endif
