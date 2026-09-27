import Foundation

/// Whether a futures market's `commence_time` may be printed as "Starts" — #9107.
///
/// Found on a D48 walk (native, 2026-09-27): Market Details for "Brazil
/// Presidential election winner?" (futures 109952, Kalshi `KXBRPRES-26`) read
/// **"Starts Oct 25, 2027"** directly above **"Resolves Oct 25, 2026"**. The wire
/// carries `commence_time 2027-10-25T14:00Z` and `resolution_date 2026-10-25T14:00Z`:
/// for Kalshi, `commence_time` is a venue close/expiration stamp, not a start
/// (gotcha #14). The stored field is #2644's; this file only decides what the
/// phone is willing to say about it.
///
/// Measured on production 2026-09-27 over open futures with both dates: Kalshi
/// **4,700 of 13,422** have start AFTER resolve and **4,939** have start EQUAL to
/// resolve (the row printed the resolve date twice, once under the wrong word).
/// Polymarket and DataGolf: 0 after. Web's futures page prints no start row at all.
///
/// ## THE RULE
///
/// A start is shown only when it is strictly BEFORE the resolve instant. A start
/// on or after the moment the question is answered cannot be a start. No resolve
/// date (or an unparseable one) is no evidence against the start, so it is kept:
/// that is the pre-#9107 behaviour, unchanged.
///
/// Instants, not calendar days: a game-shaped market that starts at 7pm and
/// resolves at 11pm the same day is a true "Starts Oct 25 / Resolves Oct 25" and
/// keeps its row. A day-level compare would drop it.
nonisolated enum FuturesStartDate {
    static func shown(commenceTime: String?, resolutionDate: String?) -> Date? {
        guard let start = commenceTime?.asDate else { return nil }
        guard let resolves = resolutionDate?.asDate else { return start }
        return start < resolves ? start : nil
    }
}
