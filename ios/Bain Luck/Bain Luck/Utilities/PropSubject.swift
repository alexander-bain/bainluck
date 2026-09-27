import Foundation

/// #9148 — the name a prop card prints for the subject of a prop.
///
/// Kalshi names a team defense `<ABBR> <Nickname> D/ST` ("SEA Seahawks D/ST",
/// "WAS Commanders D/ST"). `/api/events/14781702/game-markets` serves exactly
/// those strings before the colon of `outcome_name`, and the Player Props card
/// printed them verbatim: the team named twice, once as a ticker the rest of
/// the page does not use (it says WSH, not WAS). The nickname alone names the
/// unit and stays unique where a city is shared (NY Jets / NY Giants).
///
/// Only that exact shape is touched: a leading run of 2–3 capitals, at least
/// one more word, and a trailing `D/ST`. A player, a "Team" row, and any
/// subject with no ticker come back unchanged. Same rule as the web's
/// `propSubjectDisplay` (`frontend/lib/playerPropsGrouping.ts`).
nonisolated enum PropSubject {

    static func display(_ subject: String) -> String {
        guard let match = subject.wholeMatch(of: #/[A-Z]{2,3}\s+(\S.*\sD\/ST)/#) else { return subject }
        return String(match.1)
    }
}
