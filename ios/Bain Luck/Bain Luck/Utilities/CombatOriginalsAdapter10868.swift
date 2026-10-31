import SwiftUI

/// #10868 — THE COMBAT EVENT SCREEN'S PRODUCTION ADAPTER, PART FOUR: "ALL
/// PROPS", THE ORIGINAL CATALOGUE AND ITS DETAILS.
///
/// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: on an MMA or boxing event page
/// "All props" lists every original market outcome the page serves, once each,
/// in the page's own catalogue order, and each original's Details print its own
/// pre-match chance, its own later reading and its own venue grade — or that
/// slot's own words. On the retained UFC 332 body that is all 31 originals.
///
/// The catalogue MATCHING is the hockey screen's part four
/// (`HockeyJourneyOriginalsAdapter10868`), called, not copied — it is sport-free
/// and reads only production authorities:
///
///   - membership, order  `matched` → `QuestionCatalog9483.build`, mapped back to
///                        each served row by build's own keys, never a position.
///   - identity           `identity(of:)`: `(source, market, side)` from the row's
///                        served ids (source; `_market_id`; contributor outcome
///                        ids), never a title or a ticker.
///   - grade              `contractGrade`: after the final only, the row's own
///                        settlement (`is_winner` with an authoritative
///                        `resolution_source`, `OutcomeVerdict`), "Not yet
///                        confirmed" when none — unknown is not loss.
///   - about              `aboutSection`: venue through `SourceLabels`, "Rules
///                        unavailable", the served market and outcome ids, and
///                        during play the refused quote as the historical quote.
///   - absence words      `absenceWords` → `AllMarketsCatalogView9483.priceText`.
///
/// What is the combat screen's own:
///
///   - pre-match reading  before the start, the catalogue's own price on its own
///                        recent clock (`NFLMilestoneCard9483.isRecent`), as the
///                        hockey screen reads it. From the start on, the server's
///                        pin for THIS original (`NBALadderCard9483.pin` on the
///                        one matrix option whose contributor ids equal the row's
///                        — the comparison baseline or its own `pregame_reading`,
///                        #11125) — the channel the hockey screen leaves unread.
///                        No pin is "Pre-match chance not recorded": a current or
///                        settled price is never relabelled pre-match. (The
///                        retained body predates #11125: no option carries one.)
///   - later reading      during play only: the catalogue's price as the current
///                        chance only when dated, observed at or after the listed
///                        start, recent, and the fight is not suspended (the
///                        headline's rule: a started fight that is not live has no
///                        current chance). A refused quote keeps that rule's words
///                        and is the Details' historical quote, with its own clock
///                        and venue. A row the venue already settled shows "No
///                        current chance" and keeps no quote.
///   - labels             "<market> · <outcome>" — the catalogue's own two words,
///                        so a Yes and its No never share a card heading.
///   - categories, paging nil: which family a combat market belongs to (Winner,
///                        Finish method, Fighter rounds, Knockout chances, Fight
///                        length) is the same unproved membership part three
///                        names, so every original is listed at once.
///
/// The host passes the event, `/game-markets`, now, the reader's calendar, the
/// tint and its held selection, passed through unchanged for the leaf to
/// resolve by exact scope and identity. The held original's recorded history
/// (`OriginalMarketDetails9483.RecordedHistory`) is not built here: no owner
/// admits one for these originals yet. Nothing here fetches.
enum CombatOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    /// The sport-free catalogue matching this file calls.
    typealias Catalogue = HockeyJourneyOriginalsAdapter10868

    /// What the host already holds, passed in unchanged.
    struct Host {
        let now: Date
        let calendar: Calendar
        let locale: Locale

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }

        /// Part one's host, for its clock words only.
        var words: CombatBoutPageAdapter10868.Host {
            CombatBoutPageAdapter10868.Host(probabilityObservedAt: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    enum Words {
        static let heading = "All props"
        static let emptyWords = "No retained originals for this fight"
        static let unavailableChoice = "Unnamed original"
        static let noPreMatch = "Pre-match chance not recorded"
        static let lastBeforeStart = "Last recorded before start"
        static let recorded = "Recorded"
        static let noCurrentChance = "No current chance"
        static let inFightUnavailable = "In-fight chance unavailable"

        static func context(_ count: Int) -> String {
            count == 1 ? "1 original" : "\(count) originals"
        }
    }

    // MARK: - The page's originals

    /// The originals group for the page at `host.now`. No served outcome is no
    /// catalogue, which draws `emptyWords`.
    static func originals(_ event: EventDetail, markets: GameMarketsResponse?, host: Host, tint: Color,
                          selection: Details.Selection? = nil) -> CombatEventPageOriginals10868 {
        let phase = CombatBoutPageAdapter10868.phase(event, now: host.now)
        let started = HockeyJourneyContributionAdapter10868.hasStarted(event, now: host.now)
        let found = markets.map { Catalogue.matched($0, status: event.status, now: host.now) } ?? []
        let matrix = CombatStoryAdapter10868.matrix(markets)
        let built = found.map {
            original($0, event: event, phase: phase, started: started, matrix: matrix, host: host)
        }
        var labels: [Details.Identity: String] = [:]
        for (match, made) in zip(found, built) {
            labels[made.identity] = "\(match.group.question) · \(match.outcome.label)"
        }
        return CombatEventPageOriginals10868(
            catalogue: built.isEmpty ? nil : Details.Catalogue(scope: scope(event, phase: phase), originals: built),
            selection: selection,
            labels: labels,
            heading: Words.heading,
            context: built.isEmpty ? nil : Words.context(built.count),
            emptyWords: Words.emptyWords,
            unavailableChoice: Words.unavailableChoice,
            tint: tint)
    }

    /// One catalogue per event and phase.
    static func scope(_ event: EventDetail, phase: CombatEventPagePhase10868) -> String {
        "combat:\(event.id):\(phase.rawValue):originals"
    }

    // MARK: - One original

    static func original(_ match: Catalogue.Match, event: EventDetail, phase: CombatEventPagePhase10868,
                         started: Bool, matrix: EventQuestionMatrix?, host: Host) -> Details.Original {
        let mode: Details.Mode
        let later: Details.Reading?
        let grade: Details.Grade?
        let quote: Details.HistoricalQuote?
        switch phase {
        case .before:
            mode = .pregame
            later = nil
            grade = nil
            quote = nil
        case .during:
            let reading = laterReading(match, event: event, host: host)
            mode = reading.mode
            later = reading.later
            grade = nil
            quote = reading.quote
        case .final:
            mode = .result
            later = nil
            grade = Catalogue.contractGrade(match.source)
            quote = nil
        }
        return Details.Original(
            identity: Catalogue.identity(of: match.source), title: match.group.question, outcome: match.outcome.label,
            mode: mode, pregame: preMatchReading(match, started: started, event: event, matrix: matrix, host: host),
            later: later, grade: grade, about: Catalogue.aboutSection(match.source, historicalQuote: quote))
    }

    /// Before the start: the catalogue's own price on its own recent clock.
    /// From the start on: the server's pin for this original, or this slot's words.
    static func preMatchReading(_ match: Catalogue.Match, started: Bool, event: EventDetail,
                                matrix: EventQuestionMatrix?, host: Host) -> Details.Reading {
        let venue = SourceLabels.label(for: match.source.row.source)
        if started {
            guard let served = Self.option(for: match.source, in: matrix), let pin = NBALadderCard9483.pin(served),
                  let at = pin.at.asDate
            else { return .missing(Words.noPreMatch) }
            return .value(formatProbability(pin.probability), placement: pin.probability,
                          provenance: joined([Words.lastBeforeStart, clock(at, host), venue]))
        }
        guard let price = admissible(match.outcome.probability) else {
            return .missing(Catalogue.absenceWords(match.outcome, status: event.status))
        }
        guard NFLMilestoneCard9483.isRecent(match.outcome.observedAt, now: host.now),
              let at = match.outcome.observedAt?.asDate
        else { return .missing(AllMarketsCatalogView9483.noRecentPrice) }
        return .value(formatProbability(price), placement: price,
                      provenance: joined(["\(Words.recorded) \(clock(at, host))", venue]))
    }

    /// The one matrix option whose contributor outcome ids are exactly this
    /// row's, inside a market the row names when it names one. Nil when none,
    /// or more than one, answers.
    static func option(for source: Catalogue.Source, in matrix: EventQuestionMatrix?) -> QuestionMatrixOption? {
        guard let matrix, let ids = source.outcomeIDs, !ids.isEmpty else { return nil }
        var found: [QuestionMatrixOption] = []
        for question in matrix.questions {
            for option in question.options where option.contributorOutcomeIds == ids {
                if let market = source.marketID, let markets = option.marketIds, !markets.contains(market) { continue }
                found.append(option)
            }
        }
        return found.count == 1 ? found[0] : nil
    }

    /// During play: the catalogue's price as the current chance only when the
    /// page would call it current. A refused quote is the historical quote.
    static func laterReading(_ match: Catalogue.Match, event: EventDetail, host: Host)
        -> (mode: Details.Mode, later: Details.Reading, quote: Details.HistoricalQuote?) {
        let venue = SourceLabels.label(for: match.source.row.source)
        let observed = match.outcome.observedAt
        let date = observed?.asDate
        // The catalogue's admitted price, else a stale one's at its own observation instant.
        var quoted = admissible(match.outcome.probability)
        if quoted == nil, match.outcome.absence == .stale, let date {
            quoted = admissible(QuestionCatalog9483.reading(match.source.row, status: event.status, now: date).probability)
        }
        guard let price = quoted else {
            return (.comparison(.current), .missing(Catalogue.absenceWords(match.outcome, status: event.status)), nil)
        }
        // A settled 1.0 / 0.0 is a result: never a chance, never a saved price.
        if Catalogue.settlement(isWinner: match.source.isWinner, resolutionSource: match.source.resolutionSource) != nil {
            return (.comparison(.current), .missing(Words.noCurrentChance), nil)
        }
        let quote = Details.HistoricalQuote(text: formatProbability(price),
                                            recorded: date.flatMap { joined([clock($0, host), venue]) })
        guard let at = date else {
            return (.comparison(.current), .missing(AllMarketsCatalogView9483.noRecentPrice), quote)
        }
        let start = event.commenceTime?.asDate
        if let start, at < start {
            return (.comparison(.current), .missing(Words.inFightUnavailable), quote)
        }
        if EventState.isSuspendedAndStarted(event.status, commenceTime: start, now: host.now) {
            return (.comparison(.current), .missing(Words.inFightUnavailable), quote)
        }
        guard match.outcome.absence != .stale, NFLMilestoneCard9483.isRecent(observed, now: host.now) else {
            return (.comparison(.current), .missing(AllMarketsCatalogView9483.noRecentPrice), quote)
        }
        return (.comparison(.current),
                .value(formatProbability(price), placement: price,
                       provenance: joined(["\(Words.recorded) \(clock(at, host))", venue])), nil)
    }

    // MARK: - Words

    private static func clock(_ date: Date, _ host: Host) -> String {
        CombatBoutPageAdapter10868.clockWords(date, host: host.words)
    }

    /// A finite probability in 0...1, or nil. A real 0 stays.
    private static func admissible(_ value: Double?) -> Double? {
        guard let value, value.isFinite, (0...1).contains(value) else { return nil }
        return value
    }

    private static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
