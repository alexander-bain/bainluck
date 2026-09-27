import Foundation

/// #9170 — a Kalshi matchup title printed the way the rest of the page names teams.
///
/// Kalshi titles some game markets `<ABBR> <Nickname> vs <ABBR> <Nickname>: …`
/// and names the legs the same way. `/api/events/14781702/related-futures`
/// serves "SEA Seahawks vs WAS Commanders: 4th Quarter Spread" with legs
/// "SEA Seahawks wins 4Q by over 2.5 points", so the Novelty card named each
/// team twice, once as a ticker the page does not use (the header says WSH).
/// Same shape as #9148's `SEA Seahawks D/ST` (`PropSubject`).
///
/// Only that exact matchup shape is touched: two `<2–3 capitals> <name>` teams
/// joined by `vs`/`vs.`, up to the first colon. The tickers it finds there are
/// the only ones removed from the legs, and only where the same nickname follows
/// — so "US Open", "NBA Finals" or a player named after a team are never cut.
nonisolated enum TickerMatchupName {

    /// The (ticker-prefixed, nickname) pairs a matchup title names, or empty
    /// when the title is not that shape.
    static func pairs(in title: String) -> [(prefixed: String, nickname: String)] {
        let head = title.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
            .first.map(String.init) ?? title
        guard let m = head.trimmingCharacters(in: .whitespaces)
            .wholeMatch(of: #/([A-Z]{2,3})\s+(\S.*?)\s+vs\.?\s+([A-Z]{2,3})\s+(\S.*?)/#)
        else { return [] }
        // "USA Basketball vs CAN Basketball" would print one name twice: keep the tickers.
        guard m.2 != m.4 else { return [] }
        return [
            ("\(m.1) \(m.2)", String(m.2)),
            ("\(m.3) \(m.4)", String(m.4)),
        ]
    }

    /// `text` with each ticker-prefixed team from `title`'s matchup reduced to
    /// its nickname. Unchanged when `title` is not a matchup of that shape.
    static func display(_ text: String, matchup title: String) -> String {
        var out = text
        for pair in pairs(in: title) {
            out = out.replacingOccurrences(of: pair.prefixed, with: pair.nickname)
        }
        return out
    }

    /// The title itself, printed with nicknames only.
    static func display(_ title: String) -> String {
        display(title, matchup: title)
    }
}
