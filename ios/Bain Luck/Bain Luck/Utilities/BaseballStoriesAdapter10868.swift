import SwiftUI

/// #10868 — THE BASEBALL GAME SCREEN'S PRODUCTION ADAPTER, PART FOUR: THE
/// FINAL STORIES AND THE ASSOCIATED SERIES.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: after an MLB game the screen's stories
/// are exactly the cards the finished MLB page already deals — home runs
/// against their pregame chances, the strikeout ladder against its pregame
/// chances, the final total against every offered run line — drawn by the
/// accepted comparison leaves; and in every phase the associated series' own
/// markets, each outcome with its pregame chance and the producer's result.
///
/// It decides nothing the app does not already decide:
///
///   - the final cards   `MLBFinalDeck11284.cards` — the production deal, with
///                       the page's own printed-score gate
///                       (`EventDetailView.showsScore`), exactly as
///                       `EventDetailView.mlbFinalCards` builds it. Each slot is
///                       fenced to THIS event by the deck itself; an upcoming or
///                       live game deals none. Home runs, strikeouts and run
///                       totals are taken from it unchanged.
///   - the series        `MLBSeriesCard11284.build` on the related-futures
///                       series matrix, fenced to THIS event as the deck fences
///                       it. The builder takes no phase: the series is separate
///                       from this game and settled only by its producer.
///   - defaults          the production views' own: the strikeout target
///                       `MLBMilestoneCard11284.defaultIndex` (the priced line
///                       nearest even odds), the run line
///                       `MLBTotalsCard11284.defaultIndex` (the highest line the
///                       final total cleared, else the lowest), the series market
///                       the producer's first; no series outcome by default. A
///                       held selection always wins and is passed through
///                       unchanged — one the card no longer carries is the
///                       leaf's own "unavailable in this update", never another.
///   - colours, names    `TeamTextContrast.cardColors`; the strikeout ladder in
///                       its pitcher's side colour (`PlayerPropsTeam.color`); the
///                       series and run lines as the production cards colour
///                       them; `TeamShortName.shortPair` for the run-line card's
///                       spoken team words.
///
/// The extra-innings slot the deck also deals is not a story here (it is not
/// one of the route's required cards and its production view needs the deck's
/// shared state object); its originals stay in All props.
///
/// Before first pitch and during play there is no accepted baseball leaf for
/// home runs or the strikeout ladder (both accepted comparisons are pregame
/// chance beside the official final, and no in-game prop history is
/// delivered — `MLBFinalReader11284`), so neither story is offered then; the
/// originals stay in All props. Nothing here fetches.
enum BaseballStoriesAdapter10868 {

    /// The host's held selections, passed through unchanged.
    struct Selections: Equatable {
        /// A strikeout target's `rowID`.
        var strikeout: String? = nil
        /// A run line's option key — the same identity as a run milestone's id.
        var total: String? = nil
        /// A series market's `questionKey`.
        var seriesQuestion: String? = nil
        /// A series outcome's `optionKey`, inside `seriesQuestion`.
        var seriesOption: String? = nil
    }

    /// The final MLB deal, as the event page builds it.
    static func finalCards(_ event: EventDetail, markets: GameMarketsResponse?,
                           related: RelatedFuturesResponse?) -> [MLBFinalCard11284] {
        let hasScore = EventDetailView.showsScore(status: event.status, away: event.awayScore, home: event.homeScore)
        return MLBFinalDeck11284.cards(MLBFinalDeckInput11284(
            eventID: event.id, sportKey: event.sport, status: event.status,
            homeTeam: event.homeTeam, awayTeam: event.awayTeam,
            homeScore: hasScore ? event.homeScore : nil, awayScore: hasScore ? event.awayScore : nil,
            gameMarkets: markets, relatedFutures: related))
    }

    static func homeRuns(_ cards: [MLBFinalCard11284], event: EventDetail) -> BaseballHomeRunsStory10868? {
        for card in cards {
            guard case .homeRuns(let homeRuns) = card else { continue }
            let tints = BaseballGamePageAdapter10868.tints(event)
            return BaseballHomeRunsStory10868(card: homeRuns, awayColor: tints.away, homeColor: tints.home)
        }
        return nil
    }

    static func strikeouts(_ cards: [MLBFinalCard11284], event: EventDetail,
                           selected: String?) -> BaseballStrikeoutsStory10868? {
        for card in cards {
            guard case .strikeouts(let ladder) = card else { continue }
            let tints = BaseballGamePageAdapter10868.tints(event)
            let fallback = ladder.defaultIndex.map { ladder.targets[$0].rowID }
            return BaseballStrikeoutsStory10868(
                card: ladder, selectedRowID: selected ?? fallback,
                color: PlayerPropsTeam.color(for: ladder.side, home: tints.home, away: tints.away))
        }
        return nil
    }

    static func finalTotals(_ cards: [MLBFinalCard11284], event: EventDetail,
                            selected: String?) -> BaseballFinalTotals10868? {
        for card in cards {
            guard case .totals(let totals) = card else { continue }
            let tints = BaseballGamePageAdapter10868.tints(event)
            let names = BaseballGamePageAdapter10868.names(event)
            let hasScore = EventDetailView.showsScore(status: event.status, away: event.awayScore,
                                                      home: event.homeScore)
            let fallback = totals.defaultIndex.map { totals.lines[$0].optionKey }
            return BaseballFinalTotals10868(
                card: totals, selectedOptionKey: selected ?? fallback,
                homeName: names.home, awayName: names.away,
                homeColor: tints.home, awayColor: tints.away,
                homeScore: hasScore ? event.homeScore : nil, awayScore: hasScore ? event.awayScore : nil)
        }
        return nil
    }

    /// In every phase: the series matrix of THIS event only.
    static func series(_ event: EventDetail, related: RelatedFuturesResponse?,
                       question: String?, option: String?) -> BaseballSeriesStory10868? {
        let matrix = related.flatMap { $0.eventId == event.id ? $0.seriesQuestionMatrix : nil }
        guard let card = MLBSeriesCard11284.build(matrix, eventID: event.id) else { return nil }
        let tints = BaseballGamePageAdapter10868.tints(event)
        return BaseballSeriesStory10868(card: card, selectedQuestionKey: question ?? card.questions.first?.questionKey,
                                        selectedOptionKey: option, color: tints.home)
    }

    /// The run totals story in its form for the phase: run milestones before
    /// and during play (part three), the final total against every line after.
    static func totals(_ event: EventDetail, markets: GameMarketsResponse?, cards: [MLBFinalCard11284],
                       selected: String?, host: BaseballRunMilestonesAdapter10868.Host) -> BaseballTotalsStory10868? {
        switch BaseballGamePageAdapter10868.phase(event, now: host.now) {
        case .before, .live:
            return BaseballRunMilestonesAdapter10868.input(event, markets: markets, host: host,
                                                           selectedMilestoneID: selected).map { .milestones($0) }
        case .final:
            return finalTotals(cards, event: event, selected: selected).map { .finalTargets($0) }
        }
    }

    /// The exact original a story's Details request names, from the stories
    /// the page holds — never the live payload — or nil.
    static func original(_ id: String, in input: BaseballEventPageInput10868) -> MLBOriginal11284? {
        var held: [MLBOriginal11284] = []
        held += input.homeRuns?.card.entries.map(\.original) ?? []
        held += input.strikeouts?.card.targets.map(\.original) ?? []
        if case .finalTargets(let totals)? = input.totals { held += totals.card.lines.map(\.original) }
        held += input.series?.card.questions.flatMap(\.options).map(\.original) ?? []
        let matches = held.filter { $0.id == id }
        return matches.count == 1 ? matches.first : nil
    }
}
