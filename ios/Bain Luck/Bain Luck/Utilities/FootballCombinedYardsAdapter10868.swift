import Foundation

/// #10868 — THE FOOTBALL SCREEN'S PRODUCTION ADAPTER, PART FOUR: COMBINED
/// RUSHING + RECEIVING YARDS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `nfl-combined` (and the routes that
/// carry combined yards) a fan sees each player's chances on the combined
/// rushing + receiving contract — the same milestone card the event page
/// already deals — beside the signed ground + air split leaf, which says
/// plainly that the split is unavailable rather than inventing one.
///
/// It decides nothing the app does not already decide:
///
///   - which rows   the venue's own stat words, read as the props card reads them
///                  (`PlayerPropsStatLabel.display` + `PlayerPropsFamily.name`):
///                  "Rushing + Receiving Yards" (the combined Kalshi contract in
///                  the retained Bears–Eagles capture), the same way H3 picks
///                  its points and assists ladders.
///   - the card     `NFLMilestoneCard9483.cards` over those rows only — the
///                  production builder's grouping, bases, admission, ranking and
///                  two-card cap — and never a card the deck already deals (a
///                  combined ladder the deck chose stays in the deck).
///   - the split    `AdditiveStatSplitPresentation10868` (624b18f9). Production
///                  serves NO combined-to-component association and NO sporting
///                  actual clock (`GameMarketPlayerProp.actual` is a graded
///                  final with no membership; `AfterPlayerProps` counts are
///                  non-negative integers and cannot carry −2), so:
///                    · before play the leaf hides every actual itself;
///                    · during play there is no clocked actual-so-far channel —
///                      "Actual so far unavailable";
///                    · after the final the combined total is the card's own
///                      graded actual (`NFLMilestoneCard9483.actual`, printed by
///                      `NFLFinishCardView9483.points` as the card prints it), and
///                      the split stays unavailable — no ground or air figure is
///                      ever joined by name, subtracted or assumed 0.
///   - the axis     `NFLMilestoneCard9483.statDomain` over the card's own profile
///                  domain and actual — the card's own stat axis.
///
/// Dependency, named: a typed combined → component membership and a signed,
/// clocked actual channel (Native/shared-data owners, #10236 / #10237; backend
/// `event_props_matrix` STAT_TABLE admits neither rushing nor receiving yards).
/// Nothing here fetches, subscribes or schedules.
enum FootballCombinedYardsAdapter10868 {

    enum Words {
        /// The venue's combined stat words after the matchup.
        static let statWords = "Rushing + Receiving Yards"
        static let totalName = "Combined"
        static let unit = "yards"
        static let splitUnavailable = "Ground and air split unavailable"
        static let soFarUnavailable = "Actual so far unavailable"
        static let finalUnavailable = "Final actual unavailable"
        static let finalProvenance = "Graded after the final"
    }

    /// The combined stories for this page, at most production's two, none the
    /// deck already deals.
    static func stories(_ event: EventDetail, markets: GameMarketsResponse?, deck: [NFLEventCard9483],
                        now: Date) -> [FootballCombinedStory10868] {
        let dealt = Set(FootballDeckAdapter10868.milestoneCards(deck).map(\.id))
        let phase = FootballEventPageAdapter10868.phase(event, now: now)
        return cards(event, markets: markets, now: now)
            .filter { !dealt.contains($0.id) }
            .map { FootballCombinedStory10868(card: $0, split: split($0, phase: phase)) }
    }

    /// `NFLMilestoneCard9483.cards` over the combined contract's rows only, each
    /// `current(at:)` now.
    static func cards(_ event: EventDetail, markets: GameMarketsResponse?, now: Date) -> [NFLMilestoneCard9483] {
        // This event's own markets only (`FootballInputIdentityAdapter10868`).
        let own = FootballInputIdentityAdapter10868.markets(markets, for: event)
        let rows = (own?.playerProps ?? []).filter { isCombined($0, event: event) }
        guard !rows.isEmpty else { return [] }
        return NFLMilestoneCard9483.cards(
            props: rows, eventStatus: event.status, commenceTime: event.commenceTime?.asDate,
            homeTeam: event.homeTeam, awayTeam: event.awayTeam, now: now)
            .map { $0.current(at: now) }
    }

    static func isCombined(_ prop: GameMarketPlayerProp, event: EventDetail) -> Bool {
        let subject = HockeyJourneyContributionAdapter10868.subject(prop)
        let label = PlayerPropsStatLabel.display(marketName: prop.marketName, homeTeam: event.homeTeam,
                                                 awayTeam: event.awayTeam, player: subject)
        return PlayerPropsFamily.name(statLabel: label).caseInsensitiveCompare(Words.statWords) == .orderedSame
    }

    /// The split leaf's input for one card at the page's phase.
    static func split(_ card: NFLMilestoneCard9483, phase: FootballEventPagePhase10868) -> AdditiveStatSplitInput10868 {
        let actual: AdditiveStatSplitActual10868
        switch phase {
        case .before, .live:
            // Before play the leaf hides every actual itself; during play no
            // clocked actual-so-far channel exists. Nothing is carried.
            actual = .absent(Words.soFarUnavailable)
        case .final:
            if let total = card.actual, total.isFinite {
                let figure = AdditiveStatSplitFigure10868(text: NFLFinishCardView9483.points(total), unit: Words.unit,
                                                          provenance: Words.finalProvenance)
                actual = .final(AdditiveStatSplitReading10868(total: .value(figure),
                                                              split: .unavailable(Words.splitUnavailable)))
            } else {
                actual = .absent(Words.finalUnavailable)
            }
        }
        return AdditiveStatSplitInput10868(
            subject: card.player, totalName: Words.totalName, phase: phase.splitPhase,
            actual: actual, axis: axis(card), detailsID: nil)
    }

    /// The card's own stat axis; empty ticks (the leaf places none it is not given).
    static func axis(_ card: NFLMilestoneCard9483) -> AdditiveStatSplitAxis10868 {
        let thresholds = card.rungs.map(\.threshold)
        let base: ClosedRange<Double> = card.profile?.domain
            ?? ((thresholds.min() ?? 0)...(thresholds.max() ?? 1))
        let domain = NFLMilestoneCard9483.statDomain(base, actual: card.actual)
        return AdditiveStatSplitAxis10868(lower: domain.lowerBound, upper: domain.upperBound, ticks: [],
                                          unit: Words.unit)
    }
}
