import Foundation

/// WHAT THE MARKET GAVE EACH SIDE BEFORE THE GAME: the one number a finished
/// card and a settled hero print (#8622, the iPhone half of #8315).
///
/// The server resolves Alex's ladder (Kalshi, then Polymarket, then
/// sportsbooks) and serves the winner as `prematch_odds`. Its reason line
/// ("won as a 22% underdog") is written from that reading. The phone printed
/// `opening_odds`, the sportsbook median, so on every game the ladder answered
/// from a prediction market the card disagreed with its own line: Fernandez
/// 24% over "won as a 22% underdog", 2026-09-25.
///
/// This is the phone's copy of the web's `lib/prematchReading.ts`, and it has
/// to make the same decision: the served reading when it is usable, else
/// `opening_odds` (a cached payload older than the key). It does not re-derive
/// the ladder.
nonisolated struct PrematchReading: Equatable, Sendable {
    let awayProbability: Double
    let homeProbability: Double
    /// Whole percents `[away, home]`, rounded once as a pair. From the server
    /// on the served arm; locally on the fallback, which no serializer rounds.
    let percents: [Int?]
    /// The rung, `books` on the fallback.
    let source: String
    /// Whether this came from the server's ladder rather than the
    /// `opening_odds` fallback. Decides the settled hero's word: "Opened" is
    /// true of the fallback only.
    let isServed: Bool

    static let booksSource = "books"

    /// The word a caption puts before the pair. "Opened" is true of the
    /// `opening_odds` fallback only; the served rung is the last reading before
    /// the start, so it is "Pre-match".
    var captionWord: String { isServed ? "Pre-match" : "Opened" }

    /// Whether `awayProbability` is `1 − home` rather than a price the market
    /// gave the away side. On a two-way board the two are the same number; on
    /// a board that prices a draw the complement carries the draw too.
    let awayIsComplement: Bool

    static func resolve(prematch: PrematchOdds?, opening: OpeningOdds?) -> PrematchReading? {
        if let served = prematch, let home = usable(served.homeProbability) {
            let servedAway = usable(served.awayProbability)
            let away = servedAway ?? 1 - home
            return PrematchReading(
                awayProbability: away,
                homeProbability: home,
                // Both served values or neither (#2279).
                percents: duelPercents(
                    away: away, home: home,
                    servedAway: served.awayRenderedPercent,
                    servedHome: served.homeRenderedPercent
                ),
                source: served.source ?? booksSource,
                isServed: true,
                awayIsComplement: servedAway == nil
            )
        }
        guard let home = usable(opening?.homeProbability) else { return nil }
        let openingAway = usable(opening?.awayProbability)
        let away = openingAway ?? 1 - home
        return PrematchReading(
            awayProbability: away,
            homeProbability: home,
            percents: renderedDuelPercents(away: away, home: home),
            source: booksSource,
            isServed: false,
            awayIsComplement: openingAway == nil
        )
    }

    /// #9490 — whether the side that won was the market's underdog: priced
    /// BELOW the side it beat, on this same reading.
    ///
    /// The card used a fixed cut on the winner alone (`< 0.4`), which is only
    /// the right question on a two-way board, where the pair sums to one. On a
    /// board that prices a draw, 39.5% can be the favourite: Turkey 32.5% v
    /// Italy 39.5% (event 15304745) and the phone would have painted a home
    /// win at those prices as an upset. A draw or no result names no winner,
    /// and a draw-priced board whose away number is only the complement cannot
    /// answer, so both say false.
    func winnerWasUnderdog(homeWon: Bool, awayWon: Bool, pricesADraw: Bool) -> Bool {
        guard homeWon != awayWon else { return false }
        if pricesADraw && awayIsComplement { return false }
        return homeWon
            ? homeProbability < awayProbability
            : awayProbability < homeProbability
    }

    /// Rejects the endpoints as well as the out-of-range, as the web does: a
    /// pre-match 0 or 1 is a settled price leaking backwards past the server's
    /// clock filter, and it would print as the strongest claim on the card.
    private static func usable(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0, value < 1 else { return nil }
        return value
    }
}
