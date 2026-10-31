import Foundation

/// #10868 — THE FOOTBALL SCREEN'S PRODUCTION ADAPTER, PART TWO: THE EXISTING NFL
/// DECK — TOTAL AND MARGIN, AND THE PLAYER MILESTONES.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: the football screen's projected-finish
/// card and player milestone cards are the very cards the event page deals
/// today, from the same bodies, so the new screen and the current page can
/// never print two different forecasts, chances or grades.
///
/// It adds no data and decides nothing. It is `EventDetailView.nflCardDeck`
/// (private), rebuilt from the same public calls in the same order:
///
///   - projected input  `ProjectedFinalPointsMount.input` with the history and
///                      the clock it arrived on (`vm.historyArrivedAt`) — the
///                      page's ONE projected-points admission
///                      (`EventDetailView.projectedPointsInput`).
///   - finish           `NFLFinishCard9483.build`, comparing a finished game with
///                      the headline's own qualified forecast
///                      (`EventDetailView.qualifiedFinalForecast11296`) and a live
///                      one with the live headline's admitted retained pair —
///                      `EventDetailView.liveCardBaseline11296` (private), which is
///                      `LivePregameComparison11296.servedHalves` over
///                      `EventDetailView.liveForecast11296` on the event the
///                      headline prints.
///   - milestones       `NFLMilestoneCard9483.cards` on `/game-markets`' player
///                      props, with the event's status, start and teams.
///   - deck             `NFLEventCardDeck9483.cards` (finish first, then at most
///                      two milestone cards — production's fixed order), each
///                      card `current(at:)` the host's now, the rule the deck
///                      view applies every minute (a pregame price no longer
///                      observed loses its number).
///
/// NFL only (`NFLRecognizablePage9483.isNFL`); the NBA ladders and MLB stories
/// the same deck carries for other sports are not this screen's. The host passes
/// the event the headline prints (`vm.headline(event)`), the history, the game
/// markets, the clock the history arrived on and now.
/// Nothing here fetches, subscribes or schedules.
///
/// IDENTITY: `ProjectedFinalPointsMount.input` takes a sport, a status and a
/// history but no expected event, and `NFLMilestoneCard9483.cards` takes bare
/// props, so each entry point below scopes its own payload first
/// (`FootballInputIdentityAdapter10868`): another game's history draws no
/// projected finish, and another game's markets deal no milestone card. The
/// ladders' pair the live forecast reads comes from this event's own history,
/// never from a number handed in beside it. A foreign history leaves the
/// milestones standing, and foreign markets leave the projected finish.
enum FootballDeckAdapter10868 {

    /// What the host already holds, passed in unchanged.
    struct Host {
        /// `vm.historyArrivedAt` — the reader's clock when the history arrived.
        /// Nil keeps the projected points to a finished page, as production does.
        let historyArrivedAt: Date?
        let now: Date

        init(historyArrivedAt: Date?, now: Date = Date()) {
            self.historyArrivedAt = historyArrivedAt
            self.now = now
        }
    }

    /// The deck for this event, or empty to draw none.
    static func deck(_ event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                     host: Host) -> [NFLEventCard9483] {
        guard NFLRecognizablePage9483.isNFL(sportKey: event.sport) else { return [] }
        let cards = NFLEventCardDeck9483.cards(
            sportKey: event.sport,
            finish: finish(event, history: history, host: host),
            milestones: milestones(event, markets: markets, host: host))
        return cards.map { $0.current(at: host.now) }
    }

    /// `EventDetailView.projectedPointsInput`, on this event's own history only.
    static func projectedInput(_ event: EventDetail, history: EventHistoryResponse?,
                               host: Host) -> ProjectedFinalPointsSeries.Input? {
        guard let history = FootballInputIdentityAdapter10868.history(history, for: event) else { return nil }
        return ProjectedFinalPointsMount.input(
            sportKey: event.sport, eventStatus: event.status, history: history,
            finalHome: event.homeScore, finalAway: event.awayScore, asOf: host.historyArrivedAt)
    }

    /// The projected finish, as `nflCardDeck` builds it.
    static func finish(_ event: EventDetail, history: EventHistoryResponse?, host: Host) -> NFLFinishCard9483? {
        NFLFinishCard9483.build(
            projectedInput(event, history: history, host: host),
            finalBaseline: EventDetailView.qualifiedFinalForecast11296(event).map { (away: $0.away, home: $0.home) },
            liveBaseline: liveBaseline(event, history: history, host: host))
    }

    /// `EventDetailView.liveCardBaseline11296`: the live headline's admitted
    /// retained pair, its served halves unrounded, or nil. The ladders' pair is
    /// this event's own history's.
    static func liveBaseline(_ event: EventDetail, history: EventHistoryResponse?,
                             host: Host) -> (away: Double, home: Double)? {
        let hasScore = EventDetailView.showsScore(status: event.status, away: event.awayScore, home: event.homeScore)
        let ladder = FootballInputIdentityAdapter10868.ladder(history, for: event)
        let headline = EventDetailView.liveForecast11296(
            event, ladderHome: ladder.home, ladderAway: ladder.away, hasScore: hasScore, now: host.now)
        return LivePregameComparison11296.servedHalves(headline, projection: event.pregameProjection)
    }

    /// The player milestone cards, as `nflCardDeck` builds them, from this
    /// event's own markets only.
    static func milestones(_ event: EventDetail, markets: GameMarketsResponse?, host: Host) -> [NFLMilestoneCard9483] {
        guard let markets = FootballInputIdentityAdapter10868.markets(markets, for: event) else { return [] }
        return NFLMilestoneCard9483.cards(
            props: markets.playerProps ?? [], eventStatus: event.status,
            commenceTime: event.commenceTime?.asDate,
            homeTeam: event.homeTeam, awayTeam: event.awayTeam, now: host.now)
    }

    /// The deck's milestone cards, in its order.
    static func milestoneCards(_ deck: [NFLEventCard9483]) -> [NFLMilestoneCard9483] {
        deck.compactMap { card in
            if case .milestone(let milestone) = card { return milestone }
            return nil
        }
    }

    /// The deck's projected finish, or nil.
    static func finishCard(_ deck: [NFLEventCard9483]) -> NFLFinishCard9483? {
        for card in deck {
            if case .finish(let finish) = card { return finish }
        }
        return nil
    }
}
