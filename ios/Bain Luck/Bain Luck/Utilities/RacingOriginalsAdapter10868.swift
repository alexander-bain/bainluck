import SwiftUI

/// #10868 — THE RACING SCREEN'S PRODUCTION ADAPTER, PART THREE: "ALL PROPS",
/// THE ORIGINAL CATALOGUE AND ITS DETAILS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `racing-live` "All props" lists every
/// original outcome of the race markets the page holds, once each, in served
/// order, and each original's Details print its own recorded chance with its
/// own clock, or its own contract result — never an old price as today's, never
/// a settled 0% or 100% as a price.
///
/// It decides nothing the app does not already decide:
///
///   - membership      every outcome of every market body the host holds
///     and order       (`FuturesMarketDetail`), market by market in the host's
///                     order and outcome by outcome in served order. A market
///                     handed in twice is one set of originals (first kept).
///                     Today a race page holds ONE body — the market it opened —
///                     so the catalogue is that market's outcomes; the race's
///                     other markets (podium, matchups, fastest lap, red flag…)
///                     have no production owner that groups them (dependency in
///                     the return).
///   - identity        `(source, market id, outcome id)` — the served ids, through
///                     part one's `venueKey`. Never a ticker, a name or a position.
///   - what a row      part one's `reading` (`FuturesDetailRowValue.of`, the
///     says           Market Details row rule): per ROW, so a market the venue
///                     settled shows its result whatever the page's phase, and an
///                     open one never settles because a race ended.
///                     • a dated recent price — one reading, labelled "Recorded
///                       chance", with its own clock and venue;
///                     • a stale or undated price, or a resolved market's last
///                       ungraded price — the main slot says
///                       `AllMarketsCatalogView9483.noRecentPrice`, and the quote
///                       is kept, with its own clock, as the Details' historical
///                       quote (H4's rule);
///                     • a graded row — `.result`, with `OutcomeVerdict`'s words;
///                       its pre-race slot says it is unavailable (no start
///                       clock reaches the app), and the settled 0/1 is never a
///                       quote;
///                     • a settled row whose result is unknown
///                       (`SettledResultDisplay698`) — "Result unknown"; its last
///                       price is kept as a historical quote only when it is
///                       strictly between 0 and 1;
///                     • no price and no grade — the catalogue's own words.
///   - about           the venue through `SourceLabels.label`; no proved rule
///                     text is served on `/api/futures/{id}`, so rules read
///                     "Rules unavailable"; the served market and outcome ids.
///
/// The host passes the market bodies, now, the reader's calendar, the tint and
/// its held selection, which reaches the leaf unchanged. Nothing here fetches.
/// The owner's category / Show more controls are not built: no production owner
/// admits a race market's category (dependency in the return), so `controls` is nil.
enum RacingOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    typealias Page = RacingFieldPageAdapter10868

    enum Words {
        static let heading = "All props"
        static let emptyWords = "No original outcomes for this race"
        static let unavailableChoice = "Unnamed original"
        static let recordedChance = "Recorded chance"
        static let preRaceChance = "Pre-race chance"
        static let resultUnknown = Page.Words.resultUnknown
        static let rulesUnavailable = "Rules unavailable"
        static let marketID = "Market ID"
        static let outcomeID = "Outcome ID"
        static let settlement = "Settlement"

        static func context(_ count: Int) -> String {
            count == 1 ? "1 original outcome" : "\(count) original outcomes"
        }
    }

    // MARK: - The page's originals

    /// The originals group for the page at `host.now`. `race` is the page's own
    /// market; `markets` the other bodies the host holds for the same race (the
    /// race itself is always first). No outcome is no catalogue, which shows
    /// `emptyWords`.
    static func originals(race: FuturesMarketDetail, markets: [FuturesMarketDetail] = [], host: Page.Host,
                          tint: Color, selection: Details.Selection? = nil) -> RacingEventPageOriginals10868 {
        var built: [Details.Original] = []
        for market in held(race: race, markets: markets) {
            for outcome in market.outcomes {
                built.append(original(outcome, in: market, host: host))
            }
        }
        let catalogue: Details.Catalogue? = built.isEmpty ? nil : Details.Catalogue(scope: scope(race), originals: built)
        return RacingEventPageOriginals10868(
            catalogue: catalogue,
            selection: selection,
            heading: Words.heading,
            context: built.isEmpty ? nil : Words.context(built.count),
            emptyWords: Words.emptyWords,
            unavailableChoice: Words.unavailableChoice,
            tint: tint)
    }

    /// The race first, then each other held market once, in the host's order.
    static func held(race: FuturesMarketDetail, markets: [FuturesMarketDetail]) -> [FuturesMarketDetail] {
        var seen: Set<Int> = [race.id]
        var out: [FuturesMarketDetail] = [race]
        for market in markets where !seen.contains(market.id) {
            seen.insert(market.id)
            out.append(market)
        }
        return out
    }

    /// One catalogue per race market and phase.
    static func scope(_ race: FuturesMarketDetail) -> String {
        "racing:\(race.id):\(Page.phaseWord(Page.phase(race))):originals"
    }

    static func identity(_ outcome: FuturesOutcome, in market: FuturesMarketDetail) -> Details.Identity {
        Details.Identity(source: Page.venueKey(market), market: String(market.id), side: String(outcome.id))
    }

    // MARK: - One original

    static func original(_ outcome: FuturesOutcome, in market: FuturesMarketDetail, host: Page.Host) -> Details.Original {
        let venue = SourceLabels.label(for: market.source)
        let mode: Details.Mode
        let pregame: Details.Reading
        let grade: Details.Grade?
        let quote: Details.HistoricalQuote?
        let label: String
        switch Page.reading(outcome, in: market, host: host) {
        case .chance(let probability, let text, let detail):
            mode = .pregame
            pregame = .value(text, placement: probability, provenance: detail)
            grade = nil
            quote = nil
            label = Words.recordedChance
        case .stale(_, let text, let detail):
            mode = .pregame
            pregame = .missing(AllMarketsCatalogView9483.noRecentPrice)
            grade = nil
            quote = Details.HistoricalQuote(text: text, recorded: detail)
            label = Words.recordedChance
        case .unpriced:
            mode = .pregame
            pregame = .missing(AllMarketsCatalogView9483.unavailablePrice)
            grade = nil
            quote = nil
            label = Words.recordedChance
        case .settled(let verdict):
            mode = .result
            pregame = .missing(Page.Words.noPreRace)
            grade = Details.Grade(words: verdict.label, provenance: settledBy(venue))
            quote = nil
            label = Words.preRaceChance
        case .resultUnknown(let last):
            mode = .result
            pregame = .missing(Page.Words.noPreRace)
            grade = Details.Grade(words: Words.resultUnknown, provenance: settledBy(venue))
            quote = lastQuote(last, outcome: outcome, in: market, host: host)
            label = Words.preRaceChance
        }
        return Details.Original(
            identity: identity(outcome, in: market), title: market.name, outcome: outcome.name,
            mode: mode, pregame: pregame, later: nil, grade: grade,
            about: about(outcome, in: market, venue: venue, historicalQuote: quote),
            beforeLabel: label)
    }

    /// "Settled by Polymarket"; an unnamed venue is not guessed.
    static func settledBy(_ venue: String?) -> String {
        venue.map { "Settled by \($0)" } ?? Words.settlement
    }

    /// A settled-unknown row's last price, as history: only strictly between 0
    /// and 1, so a settled 0% or 100% is never kept as a price.
    static func lastQuote(_ last: Double?, outcome: FuturesOutcome, in market: FuturesMarketDetail,
                          host: Page.Host) -> Details.HistoricalQuote? {
        guard let last, last.isFinite, last > 0, last < 1 else { return nil }
        let percents = futuresDetailRenderedPercents(market.outcomes)
        let text = formatProbability(last, renderedPercent: percents[outcome.id])
        let clock = outcome.lastUpdated?.asDate.map { Page.clockWords($0, host: host) }
        return Details.HistoricalQuote(text: text, recorded: Page.joined([clock, SourceLabels.label(for: market.source)]))
    }

    static func about(_ outcome: FuturesOutcome, in market: FuturesMarketDetail, venue: String?,
                      historicalQuote: Details.HistoricalQuote?) -> Details.About {
        let rows: [Details.Row] = [
            Details.Row(label: Words.marketID, value: String(market.id)),
            Details.Row(label: Words.outcomeID, value: String(outcome.id)),
        ]
        return Details.About(source: venue, rules: .unavailable(Words.rulesUnavailable), provenance: rows,
                             historicalQuote: historicalQuote)
    }
}
