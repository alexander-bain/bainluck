import SwiftUI

/// #10868 — THE FOOTBALL SCREEN'S HOST GLUE: what `EventDetailView` would mount
/// for an NFL game, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER / TRUTH. SHIP: an NFL event page opens on the
/// phase's comparison, the win probability history and the route's stories —
/// the projected finish, the final period winners (completed `nfl-live`), the
/// player milestones, the team sacks and field goals and combined yards, as the
/// route names them — and every full-size card, the All props catalogue and an
/// original's Details open over it and close back to the same place. Another
/// game's history or markets never supply any of it.
///
/// WHOLE-INPUT IDENTITY: `build` scopes the history and the game markets ONCE,
/// by exact served `eventId` against `EventDetail.id`
/// (`FootballInputIdentityAdapter10868.scoped`), before the chart, the projected
/// finish, the headline's ladder fallback, any milestone, team, combined or
/// period card, the originals and every Details lookup read them; the wrappers
/// also guard themselves for direct callers. Each payload is judged alone: a
/// foreign history leaves the markets' parts, and foreign markets the
/// history's; the headline is the event's own and always stays.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held, the milestone line each player card is on (the deck's
/// own `NFLCardDeckState9483`), which milestone each team card is on, and the
/// held original. It builds the page input from the values the page already
/// holds — passed in; it reads no view model, opens no network, subscribes to
/// nothing, runs no timer and ranks nothing.
///
/// The input is recomputed from those values on every body pass. No owner
/// supplies a revision that covers every value the adapters read (served odds,
/// pre-match readings, score and clock, history rows, markets, matrix and
/// projection), and a partial memo would hold a changed score or chance on
/// screen, so none is kept (Design's HOST-COMPLETE-INPUT-INVALIDATION rule).
/// `now` is the host's: the existing page re-reads each minute (the deck's own
/// `TimelineView`), which is what ages a pregame price out of a held card.
///
/// Proposed mount (NOT applied — `EventDetailView` is Native's). The switch
/// below does NOT exist: `ReleaseSurfaces` is the project's per-surface gate and
/// adding `footballEventPageEnabled` to it is Native's call. `route` is `.nfl`
/// on the ordinary event page; the other five routes are the same screen with
/// another card set.
/// ```swift
/// if ReleaseSurfaces.footballEventPageEnabled, FootballEventPageHost10868.applies(event) {
///     TimelineView(.periodic(from: .now, by: 60)) { tick in
///         FootballEventPageHost10868(
///             route: .nfl, event: vm.headline(event), history: vm.history,
///             historyArrivedAt: vm.historyArrivedAt, markets: vm.gameMarkets,
///             probabilityObservedAt: vm.displayedProbabilityObservedAt(event),
///             deliveryInterrupted: vm.liveUpdateStatus == .interrupted,
///             // periodBinding: owed — no owner binds the period winners yet
///             now: displayNow(tick.date),
///             onInteraction: { /* the page's existing reader hold */ })
///     }
/// }
/// ```
/// Backout is that switch off; no data or route is touched by either state.
///
/// Without a history response the page still shows its comparison, stories and
/// All props; only the chart slot says "History unavailable". The real
/// load/error/retry contract is Native's.
///
/// Controls: Full chart opens the full-size history; Details and Inspect on the
/// history stay offered unavailable until their owner contracts exist. A
/// headline forecast control opens the full-size projected finish. A milestone
/// card's Details (full size only) present the existing `NFLRowDetails9483` for
/// the exact served row; a team card's Details open that exact original's
/// catalogue Details; a team card's expand opens it full size. The presenter has
/// no About mode, so `onAbout` is nil, and the split leaf has no original route,
/// so its Details are nil. The period-winner card holds its own selected
/// original here (side kept across periods by the card's own rule); its Details
/// open that exact original's catalogue Details, which print the same admitted
/// pregame trade; its open control shows it full size.
///
/// The ladders' projected-final pair is no longer passed in beside the history:
/// it is read from the scoped history, so it can never be another game's.
struct FootballEventPageHost10868: View {
    var route: FootballRoute10868 = .nfl
    let event: EventDetail
    let history: EventHistoryResponse?
    /// `vm.historyArrivedAt`, the projected points' reader clock.
    var historyArrivedAt: Date? = nil
    let markets: GameMarketsResponse?
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    /// The owner's typed period-winner binding — production input debt; nil
    /// offers no period-winner story.
    var periodBinding: FootballPeriodWinnersAdapter10868.Binding? = nil
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any reader action the stream
    /// or a card starts. Appearance and reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// NFL games only — the one sport the production deck's player milestones
    /// and this screen's card families cover.
    static func applies(_ event: EventDetail) -> Bool {
        NFLRecognizablePage9483.isNFL(sportKey: event.sport)
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: FootballEventPageMode10868
        var id: String {
            switch mode {
            case .page: "page"
            case .reader(let card): "reader.\(card.key)"
            case .catalogue: "catalogue"
            case .original: "original"
            }
        }
    }

    /// The exact served row behind a milestone line's Details.
    struct DetailsRow: Identifiable, Equatable {
        let id: String
    }

    struct Built {
        let input: FootballEventPageInput10868
        let originals: FootballEventPageOriginals10868
        /// The history and markets every part read — this event's, or nil.
        let scoped: FootballInputIdentityAdapter10868.Scoped
        /// The period-winner originals as admitted, for its Details lookup.
        let periodWinners: [FootballPeriodWinnersAdapter10868.Admitted]
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var story: FootballEventPageCard10868? = nil
        var sacksGroup: String? = nil
        var fieldGoalGroup: String? = nil
        var selection: OriginalMarketDetails9483.Selection? = nil
        var readerOpen = false
        var wide = false
        /// The period-winner card's held original id.
        var periodSelection: String? = nil
    }

    @StateObject private var cardState = NFLCardDeckState9483()
    @State private var presented: Presented?
    @State private var story: FootballEventPageCard10868?
    @State private var sacksGroup: String?
    @State private var fieldGoalGroup: String?
    @State private var selection: OriginalMarketDetails9483.Selection?
    @State private var periodSelection: String?
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        page(make(), mode: .page)
            .sheet(item: $presented) { shown in
                let built = make()
                NavigationStack {
                    ScrollView {
                        page(built, mode: shown.mode).padding(.horizontal, 16)
                    }
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Done") { presented = nil }
                        }
                    }
                }
                .sheet(item: detailsRow) { row in
                    NFLRowDetails9483(prop: Self.rows(built.input, event: event, markets: built.scoped.markets)[row.id])
                }
            }
    }

    /// The deck state's Details row, as a sheet item.
    private var detailsRow: Binding<DetailsRow?> {
        Binding(get: { cardState.detailsRowID.map(DetailsRow.init) },
                set: { cardState.detailsRowID = $0?.id })
    }

    private func page(_ built: Built, mode: FootballEventPageMode10868) -> FootballEventPagePresentation10868 {
        FootballEventPagePresentation10868(
            input: built.input, cardState: cardState, mode: mode, originals: built.originals,
            showsMilestoneDetails: true,
            onAbout: nil,
            onAllProps: { open(.catalogue) },
            onOriginalSelect: { chosen in
                selection = chosen
                open(.original)
            },
            onOriginalHistory: nil,
            onStoryIntent: { intent in handle(intent, input: built.input) },
            onHistoryAction: { id in
                if id == HockeyJourneyHistoryAdapter10868.expandActionID { open(.reader(.history)) }
            },
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onForecastInspection: { _ in open(.reader(.finish)) },
            onTeamMilestoneSelect: { card, id in
                if card == .teamSacks { sacksGroup = id } else { fieldGoalGroup = id }
            },
            onTeamMilestoneDetails: { _, id in
                guard let chosen = Self.teamOriginal(id, event: event, markets: built.scoped.markets, now: now,
                                                     scope: built.originals)
                else { return }
                selection = chosen
                open(.original)
            },
            onTeamMilestoneExpand: { card, _ in open(.reader(card)) },
            onSplitDetails: nil,
            onPeriodSelect: { id in periodSelection = id },
            onPeriodDetails: { id in
                guard let chosen = Self.periodOriginal(id, admitted: built.periodWinners, scope: built.originals)
                else { return }
                selection = chosen
                open(.original)
            },
            onPeriodExpand: { open(.reader(.periodWinners)) })
    }

    /// The hold first, then the exact mode — never the reverse.
    private func open(_ mode: FootballEventPageMode10868) {
        onInteraction?()
        presented = Presented(mode: mode)
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent, input: FootballEventPageInput10868) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse(_, let target):
            guard target.scope == input.stream.scope else { return }
            story = Self.card(target.id, in: input.stories)
        case .open(let target):
            guard target.scope == input.stream.scope else { return }
            if let card = Self.card(target.id, in: input.stories) { open(.reader(card)) }
        case .pause, .resume, .applyUpdates:
            break // the manual stream offers none of these controls
        }
    }

    private func make() -> Built {
        Self.build(route: route, event: event, history: history, historyArrivedAt: historyArrivedAt,
                   markets: markets, probabilityObservedAt: probabilityObservedAt,
                   deliveryInterrupted: deliveryInterrupted, periodBinding: periodBinding,
                   now: now,
                   reading: Reading(story: story, sacksGroup: sacksGroup, fieldGoalGroup: fieldGoalGroup,
                                    selection: selection, readerOpen: presented != nil,
                                    wide: sizeClass == .regular, periodSelection: periodSelection))
    }

    // MARK: - Pure parts

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. The history and
    /// markets are scoped to this event ONCE, before any part reads them. A
    /// missing or foreign history leaves only the chart slot unavailable and
    /// the projected finish undealt; missing or foreign markets leave every
    /// market-fed story and All props out; the headline always stays.
    static func build(route: FootballRoute10868, event: EventDetail, history: EventHistoryResponse?,
                      historyArrivedAt: Date?, markets: GameMarketsResponse?, probabilityObservedAt: Date?,
                      deliveryInterrupted: Bool = false,
                      periodBinding: FootballPeriodWinnersAdapter10868.Binding? = nil,
                      now: Date, reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        let scoped = FootballInputIdentityAdapter10868.scoped(event, history: history, markets: markets)
        let host = FootballEventPageAdapter10868.Host(
            probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
            history: scoped.history, now: now, calendar: calendar, locale: locale)
        let phase = FootballEventPageAdapter10868.phase(event, now: now)
        let historyInput = scoped.history.map {
            FootballHistoryAdapter10868.history(
                $0, event: event, phase: phase,
                host: FootballHistoryAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        } ?? FootballHistoryAdapter10868.unavailable(event: event, phase: phase)
        let deck = FootballDeckAdapter10868.deck(
            event, history: scoped.history, markets: scoped.markets,
            host: FootballDeckAdapter10868.Host(historyArrivedAt: historyArrivedAt, now: now))
        let team = FootballTeamMilestonesAdapter10868.Host(now: now, calendar: calendar, locale: locale)
        let sacks = FootballTeamMilestonesAdapter10868.input(.sacks, event: event, markets: scoped.markets,
                                                             host: team, selectedGroupID: reading.sacksGroup)
        let fieldGoals = FootballTeamMilestonesAdapter10868.input(.fieldGoals, event: event, markets: scoped.markets,
                                                                  host: team, selectedGroupID: reading.fieldGoalGroup)
        let combined = FootballCombinedYardsAdapter10868.stories(event, markets: scoped.markets, deck: deck, now: now)
        let periodHost = FootballPeriodWinnersAdapter10868.Host(now: now, calendar: calendar, locale: locale)
        let periodWinners = FootballPeriodWinnersAdapter10868.admitted(event, markets: scoped.markets,
                                                                       binding: periodBinding, host: periodHost)
        let periodCard = FootballPeriodWinnersAdapter10868.input(event, markets: scoped.markets, binding: periodBinding,
                                                                 selectedID: reading.periodSelection, host: periodHost)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let originals = FootballOriginalsAdapter10868.originals(
            event, markets: scoped.markets,
            host: FootballOriginalsAdapter10868.Host(now: now, calendar: calendar, locale: locale),
            tint: tints.home, selection: reading.selection, periodWinners: periodWinners)
        let input = FootballPageInputAdapter10868.input(
            event, route: route, history: historyInput, deck: deck, teamSacks: sacks, teamFieldGoals: fieldGoals,
            combined: combined, periodWinners: periodCard, originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals, scoped: scoped, periodWinners: periodWinners)
    }

    /// The card a stream id names: exactly one link, else none.
    static func card(_ id: String, in stories: [FootballEventPageStory10868]) -> FootballEventPageCard10868? {
        let links = stories.filter { $0.cardID == id }
        return links.count == 1 ? links.first?.card : nil
    }

    /// The served rows a milestone line's Details can name, by row id — the
    /// production reader's own resolution (`NFLCardReaderHold9483.rows`) over
    /// the deck's player milestones and the combined-yards cards, which draw
    /// through the same milestone card and write the same deck state.
    /// Only this event's own markets are read: another game's rows can never
    /// answer a line's Details, even under the same market and outcome names.
    static func rows(_ input: FootballEventPageInput10868, event: EventDetail,
                     markets: GameMarketsResponse?) -> [String: GameMarketPlayerProp] {
        let cards = input.deck + input.combined.map { NFLEventCard9483.milestone($0.card) }
        let own = FootballInputIdentityAdapter10868.markets(markets, for: event)
        return NFLCardReaderHold9483.rows(for: cards, in: own?.playerProps ?? [])
    }

    /// The catalogue selection for a period-winner original's card id: the
    /// admitted original it names exactly once, and the one catalogue entry
    /// with its identity, in the originals' own scope. Otherwise nil.
    static func periodOriginal(_ cellID: String, admitted: [FootballPeriodWinnersAdapter10868.Admitted],
                               scope originals: FootballEventPageOriginals10868) -> OriginalMarketDetails9483.Selection? {
        guard let catalogue = originals.catalogue,
              let one = FootballPeriodWinnersAdapter10868.admitted(cellID: cellID, in: admitted),
              catalogue.originals.filter({ $0.identity == one.identity }).count == 1 else { return nil }
        return OriginalMarketDetails9483.Selection(scope: catalogue.scope, identity: one.identity)
    }

    /// The catalogue selection for a team card's exact original (its
    /// `HockeyJourneyContributionAdapter10868.milestoneID`): the one catalogue
    /// entry built from that same served row, in the originals' own scope.
    /// Nil when it is not exactly one listed original.
    static func teamOriginal(_ originalID: String, event: EventDetail, markets: GameMarketsResponse?, now: Date,
                             scope originals: FootballEventPageOriginals10868) -> OriginalMarketDetails9483.Selection? {
        guard let markets = FootballInputIdentityAdapter10868.markets(markets, for: event),
              let catalogue = originals.catalogue else { return nil }
        let matches = HockeyJourneyOriginalsAdapter10868.matched(markets, status: event.status, now: now)
            .filter { match in
                guard let prop = match.source.prop else { return false }
                return HockeyJourneyContributionAdapter10868.milestoneID(prop) == originalID
            }
        guard matches.count == 1, let match = matches.first else { return nil }
        let identity = HockeyJourneyOriginalsAdapter10868.identity(of: match.source)
        guard catalogue.originals.filter({ $0.identity == identity }).count == 1 else { return nil }
        return OriginalMarketDetails9483.Selection(scope: catalogue.scope, identity: identity)
    }
}
