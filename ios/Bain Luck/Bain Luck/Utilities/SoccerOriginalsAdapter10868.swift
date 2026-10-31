import SwiftUI

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART EIGHT: "ALL
/// PROPS", THE ORIGINAL CATALOGUE AND ITS DETAILS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: "All props" lists every original market
/// outcome the match page serves, once each, in the page's own catalogue order,
/// and each original's Details print its own pre-match chance, its own later
/// reading and its own venue grade — or that slot's own words — so an old quote
/// is never sold as today's chance.
///
/// Membership, order, identity, About and the grade are the accepted hockey
/// originals adapter's (H4, `HockeyJourneyOriginalsAdapter10868`), called rather
/// than copied: `matched` (`QuestionCatalog9483.build` mapped back to served
/// rows by build's own keys), `identity(of:)`, `aboutSection`, `absenceWords`,
/// `settlement`, `contractGrade` and `label`. Two readings are soccer's own,
/// both by H4's own rules:
///
///   - pre-match     before the start, the catalogue's price on its own recent
///                   clock (H4). Once started, H4 had no stored pre-match value
///                   for a non-prop row; soccer has one: the production pin
///                   helper on the matrix option for the same market and
///                   contributor outcomes, in an admitted 10238.v1 game-scope
///                   matrix only, kept when observed before the listed start
///                   (`SoccerPropReadingAdapter10868.pin`). Otherwise "Pre-match
///                   chance not recorded" only on the producer's own
///                   `no_pregame_pin` statement, else "Pre-match chance
///                   unavailable" (`SoccerPropReadingAdapter10868.preMatchAbsence`).
///                   An unsupported matrix reads no metadata; every served
///                   original is still listed.
///   - later         during play, H4's admission (dated, at or after the listed
///                   start, recent; a settled row has no chance), plus the
///                   refusal H4 asks for by name: a row from a
///                   `GameMarketOutcome` array (game lines, team scoring,
///                   periods) can carry a sibling's clock (served
///                   `observed_at_basis: "capped_to_sibling"`, not decoded), so
///                   its quote is never the current chance. A refused quote is
///                   the Details' historical quote with its own clock and venue,
///                   exactly as H4 keeps it — never the card figure.
///   - period rows   (Design, wave-1 review 2026-10-31) a row of a market the
///                   owner admitted as one half (`periodMarketIDs`, from
///                   `SoccerPropReadingAdapter10868.Markets.halves`) is never the
///                   current chance during play: no decoded field proves its half
///                   is still being played (part three's header, `period rows`,
///                   names every field checked and the missing owner input). Its
///                   quote is kept only as the historical quote dated by its
///                   own clock — an undated one, or one on a sibling's clock,
///                   keeps none — and the later slot says "In-play chance
///                   unavailable". After the final its grade is H4's, as
///                   for every row; until then the result is unknown. Rows of the
///                   `GameMarketOutcome` period arrays are already refused above.
///
/// The host passes the event, `/game-markets`, now, the reader's calendar, the
/// tint, its held selection (passed through unchanged for the leaf to resolve by
/// exact scope and identity) and the admitted half markets. Nothing here fetches.
enum SoccerOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    typealias H4 = HockeyJourneyOriginalsAdapter10868
    typealias R = SoccerPropReadingAdapter10868

    enum Words {
        static let heading = "All props"
        static let emptyWords = "No original props recorded for this match"
        static let unavailableChoice = "Unnamed original"
        static let preMatchNotRecorded = R.Words.preMatchNotRecorded
        static let preMatchUnavailable = R.Words.preMatchUnavailable
        static let savedBeforeStart = "Saved before kickoff"
        static let recorded = "Recorded"
        static let settledNoChance = R.Words.settledNoChance
        static let inPlayUnavailable = R.Words.inPlayUnavailable

        static func context(_ count: Int) -> String {
            count == 1 ? "1 original" : "\(count) originals"
        }
    }

    // MARK: - The page's originals

    /// The originals group for the page at `host.now`. No served outcome is no
    /// catalogue, which draws `emptyWords`. `periodMarketIDs` are the owner's
    /// admitted half markets; none admitted is none treated as a period.
    static func originals(_ event: EventDetail, markets: GameMarketsResponse?, host: R.Host, tint: Color,
                          selection: Details.Selection? = nil,
                          periodMarketIDs: Set<Int> = []) -> SoccerEventPageOriginals10868 {
        let phase = SoccerMatchPageAdapter10868.phase(event, now: host.now)
        let started = HockeyJourneyContributionAdapter10868.hasStarted(event, now: host.now)
        let found = markets.map { H4.matched($0, status: event.status, now: host.now) } ?? []
        let matrix = markets?.gameQuestionMatrix
        let built = found.map {
            original($0, event: event, phase: phase, started: started, matrix: matrix, host: host,
                     period: isPeriod($0.source, admitted: periodMarketIDs))
        }
        var labels: [Details.Identity: String] = [:]
        for (match, made) in zip(found, built) {
            labels[made.identity] = H4.label(match.source, event: event)
        }
        return SoccerEventPageOriginals10868(
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
    static func scope(_ event: EventDetail, phase: SoccerEventPagePhase10868) -> String {
        "soccer:\(event.id):\(phase):originals"
    }

    // MARK: - One original

    /// Whether the row belongs to a market the owner admitted as one half — by
    /// exact market id, never by its title.
    static func isPeriod(_ source: H4.Source, admitted: Set<Int>) -> Bool {
        if let id = source.marketID, admitted.contains(id) { return true }
        return (source.marketIDs ?? []).contains { admitted.contains($0) }
    }

    static func original(_ match: H4.Match, event: EventDetail, phase: SoccerEventPagePhase10868, started: Bool,
                         matrix: EventQuestionMatrix?, host: R.Host, period: Bool = false) -> Details.Original {
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
        case .live:
            let reading = laterReading(match, event: event, host: host, period: period)
            mode = .comparison(.current)
            later = reading.later
            grade = nil
            quote = reading.quote
        case .final:
            mode = .result
            later = nil
            grade = H4.contractGrade(match.source)
            quote = nil
        }
        return Details.Original(
            identity: H4.identity(of: match.source), title: match.group.question, outcome: match.outcome.label,
            mode: mode,
            pregame: pregameReading(match, started: started, event: event, matrix: matrix, host: host),
            later: later, grade: grade, about: H4.aboutSection(match.source, historicalQuote: quote))
    }

    /// Whether this row's clock is its own: rows the catalogue reads from the
    /// `GameMarketOutcome` arrays can carry a sibling's clock.
    static func clockIsOwn(_ source: H4.Source) -> Bool {
        switch source.family {
        case .playerProps, .matchups, .other: true
        case .gameLines, .teamScoring, .periods: false
        }
    }

    /// Before the start: the catalogue's own price on its own recent clock.
    /// Once started: the stored pre-match pin for the same original, or its absence.
    static func pregameReading(_ match: H4.Match, started: Bool, event: EventDetail,
                               matrix: EventQuestionMatrix?, host: R.Host) -> Details.Reading {
        let venue = SourceLabels.label(for: match.source.row.source)
        if started {
            let market = match.source.marketID ?? match.source.marketIDs?.first
            let option = market.flatMap { R.option($0, contributors: match.source.outcomeIDs ?? [], in: matrix) }
            guard let pin = R.pin(option, start: event.commenceTime?.asDate) else {
                return .missing(R.preMatchAbsence(option))
            }
            let clock = "\(Words.savedBeforeStart) \(clockWords(pin.observedAt, host))"
            return .value(formatProbability(pin.probability), placement: pin.probability,
                          provenance: SoccerMatchPageAdapter10868.joined([clock, venue]))
        }
        guard let price = R.admissible(match.outcome.probability) else {
            return .missing(H4.absenceWords(match.outcome, status: event.status))
        }
        guard clockIsOwn(match.source), NFLMilestoneCard9483.isRecent(match.outcome.observedAt, now: host.now),
              let at = match.outcome.observedAt?.asDate
        else { return .missing(AllMarketsCatalogView9483.noRecentPrice) }
        return .value(formatProbability(price), placement: price,
                      provenance: SoccerMatchPageAdapter10868.joined(["\(Words.recorded) \(clockWords(at, host))", venue]))
    }

    /// During play: the catalogue's price as the current chance only as H4
    /// admits it, and only on a row whose clock is its own. A refused quote
    /// keeps the slot's words and becomes the historical quote; a settled row
    /// shows no chance and keeps no quote. A `period` row (an admitted half) is
    /// never admitted: its quote stays historical, and only when dated by its
    /// own clock.
    static func laterReading(_ match: H4.Match, event: EventDetail, host: R.Host, period: Bool = false)
        -> (later: Details.Reading, quote: Details.HistoricalQuote?) {
        let venue = SourceLabels.label(for: match.source.row.source)
        let observed = match.outcome.observedAt
        let date = observed?.asDate
        // The catalogue's admitted price, else a stale one's at its own observation instant.
        var quoted = R.admissible(match.outcome.probability)
        if quoted == nil, match.outcome.absence == .stale, let date {
            quoted = R.admissible(QuestionCatalog9483.reading(match.source.row, status: event.status, now: date).probability)
        }
        guard let price = quoted else {
            return (.missing(H4.absenceWords(match.outcome, status: event.status)), nil)
        }
        // A settled 1.0 / 0.0 is a result: never a chance, never a saved price.
        if H4.settlement(isWinner: match.source.isWinner, resolutionSource: match.source.resolutionSource) != nil {
            return (.missing(Words.settledNoChance), nil)
        }
        let quote = Details.HistoricalQuote(
            text: formatProbability(price),
            recorded: date.flatMap { SoccerMatchPageAdapter10868.joined([clockWords($0, host), venue]) })
        guard clockIsOwn(match.source), let at = date else {
            // A period row's quote is shown only when dated by its own clock.
            return (.missing(AllMarketsCatalogView9483.noRecentPrice), period ? nil : quote)
        }
        if let start = event.commenceTime?.asDate, at < start {
            return (.missing(Words.inPlayUnavailable), quote)
        }
        // No decoded field proves this half is still being played, so a recent
        // price alone never makes its quote the current chance.
        if period { return (.missing(Words.inPlayUnavailable), quote) }
        guard match.outcome.absence != .stale, NFLMilestoneCard9483.isRecent(observed, now: host.now) else {
            return (.missing(AllMarketsCatalogView9483.noRecentPrice), quote)
        }
        return (.value(formatProbability(price), placement: price,
                       provenance: SoccerMatchPageAdapter10868.joined(["\(Words.recorded) \(clockWords(at, host))", venue])),
                nil)
    }

    private static func clockWords(_ date: Date, _ host: R.Host) -> String {
        SoccerMatchPageAdapter10868.clockWords(date, host: host.words)
    }
}
