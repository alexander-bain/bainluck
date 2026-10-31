import SwiftUI

/// #10868 — THE FIELD SCREEN'S PRODUCTION ADAPTER, PART FOUR: "ALL PROPS",
/// THE ORIGINAL CATALOGUE AND ITS DETAILS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on a championship field page "All props"
/// lists every original outcome of the field once, in served order, and each
/// original's Details print its own recorded chance with its own clock, or its
/// own contract result — never an old reading as today's, never a settled 0% or
/// 100% as a chance.
///
/// It decides nothing the app does not already decide:
///
///   - membership      every outcome of the field's market body, in served order,
///     and order       then every outcome of each other body the host holds for
///                     the same field, market by market (a market handed in twice
///                     is one set of originals, first kept). Today a field page
///                     holds ONE body — the market it opened — so the catalogue
///                     is that market's outcomes.
///   - identity        `(source, market id, outcome id)` — the served ids, through
///                     part one's `venueKey`. Never a ticker, a name or a position.
///   - what a row      part one's row reading (`FuturesDetailRowValue.of`, the
///     says           Market Details row rule), per ROW:
///                     • a dated recent value — one reading, "Recorded chance",
///                       with its own clock and venue;
///                     • a stale or undated value, or a resolved market's last
///                       ungraded value — the slot says
///                       `AllMarketsCatalogView9483.noRecentPrice`, and the value is
///                       kept, with its own clock, as the Details' historical quote;
///                     • a graded row — `.result` with `OutcomeVerdict`'s words; its
///                       pre-event slot says it is unavailable (no start reaches the
///                       app), and the settled 0/1 is never a quote;
///                     • a settled row whose result is unknown
///                       (`SettledResultDisplay698`) — "Result unknown"; its last
///                       value is kept as a historical quote only when strictly
///                       between 0 and 1;
///                     • no value and no grade — the catalogue's own words.
///   - about           the venue through `SourceLabels.label`; no proved rule text
///                     is served on `/api/futures/{id}` (`description` is null on
///                     every retained field body), so rules read "Rules
///                     unavailable"; the served market and outcome ids.
///
/// The host passes the market bodies, now, the reader's calendar, the tint and
/// its held selection, which reaches the leaf unchanged. Nothing here fetches.
enum FieldEventOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    typealias Page = FieldEventPageAdapter10868

    enum Words {
        static let heading = "All props"
        static let emptyWords = "No original outcomes for this field"
        static let unavailableChoice = "Unnamed original"
        static let recordedChance = "Recorded chance"
        static let preEventChance = "Pre-event chance"
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

    /// The originals group for the page at `host.now`. `field` is the page's
    /// own market; `markets` the other bodies the host holds for the same
    /// field. No outcome is no catalogue, which shows `emptyWords`.
    static func originals(field: FuturesMarketDetail, markets: [FuturesMarketDetail] = [], host: Page.Host,
                          tint: Color, selection: Details.Selection? = nil) -> FieldEventPageOriginals10868 {
        var built: [Details.Original] = []
        for market in held(field: field, markets: markets) {
            for outcome in market.outcomes {
                built.append(original(outcome, in: market, host: host))
            }
        }
        let catalogue: Details.Catalogue? = built.isEmpty ? nil : Details.Catalogue(scope: scope(field), originals: built)
        return FieldEventPageOriginals10868(
            catalogue: catalogue,
            selection: selection,
            heading: Words.heading,
            context: built.isEmpty ? nil : Words.context(built.count),
            emptyWords: Words.emptyWords,
            unavailableChoice: Words.unavailableChoice,
            tint: tint)
    }

    /// The field first, then each other held market once, in the host's order.
    static func held(field: FuturesMarketDetail, markets: [FuturesMarketDetail]) -> [FuturesMarketDetail] {
        var seen: Set<Int> = [field.id]
        var out: [FuturesMarketDetail] = [field]
        for market in markets where !seen.contains(market.id) {
            seen.insert(market.id)
            out.append(market)
        }
        return out
    }

    /// One catalogue per field market and phase.
    static func scope(_ field: FuturesMarketDetail) -> String {
        "field:\(field.id):\(Page.phaseWord(Page.phase(field))):originals"
    }

    static func identity(_ outcome: FuturesOutcome, in market: FuturesMarketDetail) -> Details.Identity {
        Details.Identity(source: Page.venueKey(market), market: String(market.id), side: String(outcome.id))
    }

    /// The Details selection a field-card ref names: the same served market and
    /// outcome ids, in the catalogue's own scope. Nil when the ref names no
    /// held original — never the first or a neighbour.
    static func selection(for ref: FieldChooserOriginalRef10868, in originals: FieldEventPageOriginals10868) -> Details.Selection? {
        guard let catalogue = originals.catalogue else { return nil }
        let identity = Details.Identity(source: ref.source, market: ref.marketID, side: ref.outcomeID)
        guard catalogue.originals.filter({ $0.identity == identity }).count == 1 else { return nil }
        return Details.Selection(scope: catalogue.scope, identity: identity)
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
            pregame = .missing(Page.Words.noPreEvent)
            grade = Details.Grade(words: verdict.label, provenance: settledBy(venue))
            quote = nil
            label = Words.preEventChance
        case .resultUnknown(let last):
            mode = .result
            pregame = .missing(Page.Words.noPreEvent)
            grade = Details.Grade(words: Words.resultUnknown, provenance: settledBy(venue))
            quote = lastQuote(last, outcome: outcome, in: market, host: host)
            label = Words.preEventChance
        }
        return Details.Original(
            identity: identity(outcome, in: market), title: market.name, outcome: outcome.name,
            mode: mode, pregame: pregame, later: nil, grade: grade,
            about: about(outcome, in: market, venue: venue, historicalQuote: quote),
            beforeLabel: label)
    }

    /// "Settled by Kalshi"; an unnamed venue is not guessed.
    static func settledBy(_ venue: String?) -> String {
        venue.map { "Settled by \($0)" } ?? Words.settlement
    }

    /// A settled-unknown row's last value, as history: only strictly between 0
    /// and 1, so a settled 0% or 100% is never kept as a chance.
    static func lastQuote(_ last: Double?, outcome: FuturesOutcome, in market: FuturesMarketDetail,
                          host: Page.Host) -> Details.HistoricalQuote? {
        guard let last, last.isFinite, last > 0, last < 1 else { return nil }
        let percents = futuresDetailRenderedPercents(market.outcomes)
        let text = formatProbability(last, renderedPercent: percents[outcome.id])
        let clock = outcome.lastUpdated?.asDate.map { Page.clockWords($0, host: host) }
        let parts: [String] = [clock, SourceLabels.label(for: market.source)].compactMap { $0 }
        return Details.HistoricalQuote(text: text, recorded: parts.isEmpty ? nil : parts.joined(separator: " · "))
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
