import Foundation

/// #10868 — THE FOOTBALL SCREEN'S WHOLE-INPUT EVENT IDENTITY: every payload the
/// screen reads is this game's, by its exact served id, or it is not read.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: another game's history can never draw
/// this game's chart or projected finish, and another game's markets can never
/// deal this game's player, team, combined or quarter stories, its originals or
/// a milestone line's Details — while this game's own headline and every part
/// whose payload IS this game's keep showing.
///
/// Why here: the shared production helpers the football parts call take no
/// expected event — `ProjectedFinalPointsMount.input` reads a sport, a status
/// and a history; `NFLMilestoneCard9483.cards` reads a list of props — so a
/// same-sport, same-status payload from another game would pass straight
/// through them. Those helpers are not changed; the football boundary scopes
/// what reaches them.
///
/// The rule is exact identity only: `EventHistoryResponse.eventId` and
/// `GameMarketsResponse.eventId` (both served, non-optional) must equal
/// `EventDetail.id`. Same teams, sport, status or start never stand in for it.
/// Each payload is judged on its own: a foreign history leaves the markets'
/// parts standing, and foreign markets leave the history's.
///
/// The host scopes once (`scoped`) before any part is built; each wrapper that
/// takes a raw payload also scopes it itself, so a direct caller is guarded too.
enum FootballInputIdentityAdapter10868 {

    /// The payloads that belong to this event. A nil member was absent or foreign.
    struct Scoped {
        let history: EventHistoryResponse?
        let markets: GameMarketsResponse?
        /// A history was supplied and refused as another event's.
        let historyRefused: Bool
        /// Markets were supplied and refused as another event's.
        let marketsRefused: Bool
    }

    static func scoped(_ event: EventDetail, history: EventHistoryResponse?,
                       markets: GameMarketsResponse?) -> Scoped {
        let ownHistory = self.history(history, for: event)
        let ownMarkets = self.markets(markets, for: event)
        return Scoped(history: ownHistory, markets: ownMarkets,
                      historyRefused: history != nil && ownHistory == nil,
                      marketsRefused: markets != nil && ownMarkets == nil)
    }

    /// The history, only when it is this event's by its served id.
    static func history(_ response: EventHistoryResponse?, for event: EventDetail) -> EventHistoryResponse? {
        response.flatMap { $0.eventId == event.id ? $0 : nil }
    }

    /// The game markets, only when they are this event's by their served id.
    static func markets(_ response: GameMarketsResponse?, for event: EventDetail) -> GameMarketsResponse? {
        response.flatMap { $0.eventId == event.id ? $0 : nil }
    }

    /// The ladders' projected-final pair production reads
    /// (`vm.history?.pmSpreadData?.projectedFinal`), from this event's own
    /// history only; a foreign or absent history gives none.
    static func ladder(_ response: EventHistoryResponse?, for event: EventDetail) -> (home: Double?, away: Double?) {
        let projected = history(response, for: event)?.pmSpreadData?.projectedFinal
        return (projected?.homeScore, projected?.awayScore)
    }
}
