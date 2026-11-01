import SwiftUI

/// #10868 — THE SOCCER MATCH SCREEN'S HOST GLUE: what `EventDetailView` would
/// mount for a soccer match, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: a soccer event page opens on the three
/// named outcomes, the win probability history and the stories its phase
/// offers — before kickoff the total goal outlook and the exact-score map;
/// during play and after the final the goal, both-teams, first-team and
/// half-by-half stories — and every full-size card, the All props catalogue
/// and an original's Details open over it and close back to the same place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held, which milestone or outcome each story is on, the
/// exact-score map's held scope and held score per scope, the held original and
/// the timing disclosures. It builds the page input from the
/// values the page already holds — passed in; it reads no view model, opens no
/// network, subscribes to nothing, runs no timer and ranks nothing.
///
/// The input is recomputed from those values on every body pass. No owner
/// supplies a revision that covers every value the adapters read (served odds,
/// pre-match readings, score and clock, history rows, markets and matrix), and
/// a partial memo would hold a changed score or chance on screen, so none is
/// kept here; any cache needs that complete owner revision first (performance
/// work, routed) — Design's HOST-COMPLETE-INPUT-INVALIDATION rule.
///
/// Proposed mount (NOT applied — `EventDetailView` is Native's). The switch
/// below does NOT exist: `ReleaseSurfaces` (Utilities/ReleaseSurfaces.swift) is
/// the project's per-surface gate, and adding `soccerMatchPageEnabled` to it is
/// Native's call. The story markets are the owner's admission and are still
/// owed (see `SoccerPropReadingAdapter10868.Markets`): no owner types them yet,
/// so a host without it passes none and the page shows its headline, history
/// and All props with no prop stories. The same admission carries the
/// exact-score descriptor and the goal rows' own-clock proof
/// (`Markets.exactScore`, `Markets.ownClockGoals`) — both still owed, both
/// accepted the moment an owner supplies them. Every card follows the approved
/// route-phase membership by default (`SoccerPageInputAdapter10868.routeCards`:
/// before kickoff the goal outlook and the exact-score map only); the journey
/// and replay hosts pass `halvesAdmission: .explicit`, and any other
/// owner-supplied context may pass `admittedCards` — context, not a rank.
/// ```swift
/// if ReleaseSurfaces.soccerMatchPageEnabled, SoccerEventPageHost10868.applies(event) {
///     SoccerEventPageHost10868(
///         event: vm.headline(event), history: vm.history, markets: vm.gameMarkets,
///         admitted: /* the owner's typed story markets, exact-score descriptor
///                      and goal own-clock proof — still owed */ .init(),
///         // halvesAdmission: .explicit — journey and replay routes only
///         // admittedCards: [...] — other owner-supplied context only
///         probabilityObservedAt: vm.displayedProbabilityObservedAt(event),
///         deliveryInterrupted: vm.liveUpdateStatus == .interrupted,
///         ladderHome: vm.history?.pmSpreadData?.projectedFinal?.homeScore,
///         ladderAway: vm.history?.pmSpreadData?.projectedFinal?.awayScore,
///         now: now,
///         onInteraction: { /* the page's existing reader hold */ })
/// }
/// ```
/// Backout is that switch off; no data or route is touched by either state.
///
/// Without a history response (not arrived, or failed) the page still shows its
/// three outcomes, stories and All props; only the chart slot says "History
/// unavailable" (`SoccerHistoryAdapter10868.unavailable`), with no working chart
/// control and no retry. The real load/error/retry contract is Native's.
///
/// Controls: Full chart opens the full-size history; Details and Inspect on the
/// history are offered unavailable until their owner contracts exist. The
/// presenter has no About content mode, so `onAbout` is nil (no button that
/// does nothing). A card's own Details — goal milestones, both teams, first
/// team, half by half and the exact-score map — open that row's exact original
/// in the page's existing Details (`SoccerCardOriginalsAdapter10868`): offered
/// only where this pass's mounted card and the owner's typed admission
/// establish it, held as the typed origin plus the exact selection, and shown
/// only while that origin still revalidates; otherwise the Details' own
/// unavailable view. Every original stays reachable through All props. The
/// exact-score map's scope and score choices hold the reader's place; its
/// recovery is offered only when the selected scope has a score to recover to.
///
/// Layers: one sheet. A card's Details open over its full-size card (the sheet
/// keeps that card's identity, so it is never presented again) and Done returns
/// to the same card; Details opened from a card on the page return to the page
/// with Done; an interactive dismissal returns to the page. The card path never
/// writes the story, outcome, exact-scope or score choices, the All props
/// selection or a timing disclosure. Holds: in the compact stream the card's
/// activation has already asked the stream's hold, so the host adds none; in
/// full-size content the host asks `onInteraction` exactly once, before the
/// Details open. Still owed, not claimed here: the full-size card's scroll
/// position and VoiceOver focus after Done.
struct SoccerEventPageHost10868: View {
    typealias Cards = SoccerCardOriginalsAdapter10868

    let event: EventDetail
    let history: EventHistoryResponse?
    let markets: GameMarketsResponse?
    /// The owner's typed story markets. Empty: no prop story is offered.
    var admitted: SoccerPropReadingAdapter10868.Markets = .init()
    /// Where the half-by-half card may be offered: the approved default is
    /// after the final only; the journey and replay hosts pass `.explicit`.
    var halvesAdmission: SoccerPageInputAdapter10868.HalvesAdmission = .routeDefault
    /// Other cards the owner admits beyond the route's own. Empty: the approved
    /// membership alone.
    var admittedCards: Set<SoccerEventPageCard10868> = []
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    var ladderHome: Double? = nil
    var ladderAway: Double? = nil
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any reader action the stream
    /// or a card starts. Appearance and reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// Soccer matches only — the one sport `SportVocab` declares draw-priced.
    /// Which soccer matches get this screen is the adopting owner's call.
    static func applies(_ event: EventDetail) -> Bool {
        (event.sport ?? "").lowercased().hasPrefix("soccer_") && DrawPricedWinner.sportPricesADraw(event.sport)
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: SoccerEventPageMode10868
        var id: String {
            switch mode {
            case .page: "page"
            case .reader(let card): "reader.\(card.rawValue)"
            case .catalogue: "catalogue"
            case .original: "original"
            }
        }
    }

    struct Built {
        let input: SoccerEventPageInput10868
        let originals: SoccerEventPageOriginals10868
        /// This pass's card-Details values and lookups, built once from the
        /// same values as `input` and `originals`.
        let pass: SoccerCardOriginalsAdapter10868.Pass
        /// The originals a card's Details show on this pass: the held origin's
        /// exact selection only while it revalidates, else none (the Details'
        /// own unavailable view).
        let cardDetailsOriginals: SoccerEventPageOriginals10868
    }

    /// The sheet's layers. One sheet: a card's Details open over the full-size
    /// card they came from, or over the page.
    struct Session: Equatable {
        /// The full-size card, All props, or All props' Details; never `.page`.
        var base: SoccerEventPageMode10868? = nil
        /// A card's Details, over `base` when one is open, else over the page.
        var cardDetails: SoccerCardOriginalsAdapter10868.Opened? = nil

        /// The sheet's identity: the base layer's, or the page's under Details
        /// opened from the page. It does not change while a card's Details open
        /// or close over that card, so the card's sheet is never presented again.
        var presented: Presented? {
            if let base { return Presented(mode: base) }
            return cardDetails == nil ? nil : Presented(mode: .page)
        }

        mutating func open(_ mode: SoccerEventPageMode10868) {
            base = mode == .page ? nil : mode
            cardDetails = nil
        }

        mutating func openCardDetails(_ opened: SoccerCardOriginalsAdapter10868.Opened) {
            cardDetails = opened
        }

        /// Done: a card's Details return to the card or page they were opened
        /// over; anything else returns to the page.
        mutating func close() {
            if cardDetails != nil {
                cardDetails = nil
            } else {
                base = nil
            }
        }

        /// The sheet was dismissed interactively: the page.
        mutating func dismiss() {
            cardDetails = nil
            base = nil
        }
    }

    /// The hold a card's Details tap asks for itself: none on the page, whose
    /// cards sit in the stream and already asked through its activation; the
    /// page's hold in full-size content, which has no activation.
    static func detailsHold(_ mode: SoccerEventPageMode10868, _ hold: (() -> Void)?) -> (() -> Void)? {
        mode == .page ? nil : hold
    }

    /// Cards render only on the page and in full-size content; All props and
    /// Details show none, so no card Details callback is built for them.
    static func showsCards(_ mode: SoccerEventPageMode10868) -> Bool {
        switch mode {
        case .page, .reader: true
        case .catalogue, .original: false
        }
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var story: SoccerEventPageCard10868? = nil
        var goal: String? = nil
        var both: String? = nil
        var first: String? = nil
        var half: String? = nil
        /// The exact-score map's held scope id; nil shows the owner's first scope.
        var exactScope: String? = nil
        /// The exact-score map's held original id, per scope id.
        var exactOriginals: [String: String] = [:]
        var selection: OriginalMarketDetails9483.Selection? = nil
        var readerOpen = false
        var wide = false
        /// A card's open Details; nil: none.
        var cardDetails: SoccerCardOriginalsAdapter10868.Opened? = nil
    }

    @State private var session = Session()
    @State private var story: SoccerEventPageCard10868?
    @State private var goal: String?
    @State private var both: String?
    @State private var first: String?
    @State private var half: String?
    @State private var exactScope: String?
    @State private var exactOriginals: [String: String] = [:]
    @State private var selection: OriginalMarketDetails9483.Selection?
    @State private var goalTiming = false
    @State private var bothTiming = false
    @State private var firstTiming = false
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        page(make(), mode: .page)
        .sheet(item: Binding(get: { session.presented },
                             set: { shown in if shown == nil { session.dismiss() } })) { shown in
            NavigationStack {
                ScrollView {
                    sheetContent(shown).padding(.horizontal, 16)
                }
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { session.close() }
                    }
                }
            }
        }
    }

    /// A card's Details over the card or page they came from, else the base
    /// layer — each over THIS pass's input and originals.
    private func sheetContent(_ shown: Presented) -> SoccerEventPagePresentation10868 {
        let built = make()
        return session.cardDetails == nil
            ? page(built, mode: shown.mode)
            : page(built, mode: .original, originals: built.cardDetailsOriginals)
    }

    private func page(_ built: Built, mode: SoccerEventPageMode10868,
                      originals: SoccerEventPageOriginals10868? = nil) -> SoccerEventPagePresentation10868 {
        // A card's Details: offered from this pass's lookups, asking the hold
        // only in full-size content, opening over the card or page they came from.
        let hold = Self.detailsHold(mode, onInteraction)
        let pass: Cards.Pass? = Self.showsCards(mode) ? built.pass : nil
        let show: (Cards.Opened) -> Void = { session.openCardDetails($0) }
        let goalDetails = pass.flatMap { Cards.goalDetails(in: $0, hold: hold, show: show) }
        let bothDetails = pass.flatMap { Cards.bothDetails(in: $0, hold: hold, show: show) }
        let firstDetails = pass.flatMap { Cards.firstDetails(in: $0, hold: hold, show: show) }
        let halfDetails = pass.flatMap { Cards.halfDetails(in: $0, hold: hold, show: show) }
        let exactDetails = pass.flatMap { Cards.exactDetails(in: $0, hold: hold, show: show) }
        return SoccerEventPagePresentation10868(
            input: built.input, mode: mode, originals: originals ?? built.originals,
            onAbout: nil,
            onAllProps: { open(.catalogue) },
            onOriginalSelect: { chosen in
                selection = chosen
                open(.original)
            },
            onOriginalHistory: nil,
            onStoryIntent: { intent in handle(intent) },
            onHistoryAction: { id in
                if id == HockeyJourneyHistoryAdapter10868.expandActionID { open(.reader(.history)) }
            },
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onGoalSelect: { goal = $0 },
            onGoalDetails: goalDetails,
            onBothSelect: { both = $0.outcomeID },
            onBothDetails: bothDetails,
            onFirstSelect: { first = $0 },
            onFirstDetails: firstDetails,
            onHalfSelect: { half = $0 },
            onHalfDetails: halfDetails,
            onExactSelectScope: { exactScope = $0 },
            onExactSelectOriginal: { scope, original in
                exactScope = scope
                exactOriginals[scope] = original
            },
            onExactDetails: exactDetails,
            onExactRecover: Self.recovery(built.input.exact).map { target -> () -> Void in
                { exactOriginals[target.scope] = target.original }
            },
            goalTimingExpanded: $goalTiming,
            bothTimingExpanded: $bothTiming,
            firstTimingExpanded: $firstTiming)
    }

    /// The score the map's recovery selects: the selected scope's first
    /// original an action can name, in the owner's order — only while no held
    /// score resolves there. Nil: no recovery control.
    static func recovery(_ map: ExactScoreMapInput10868?) -> (scope: String, original: String)? {
        guard let map, let scope = map.scopeSelection.scope, map.originalSelection(in: scope).original == nil,
              let first = map.actionableIDs(in: scope).first else { return nil }
        return (scope.id, first)
    }

    /// The hold first, then the exact mode — never the reverse. A card's
    /// Details never come through here.
    private func open(_ mode: SoccerEventPageMode10868) {
        onInteraction?()
        session.open(mode)
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse(_, let target):
            story = SoccerEventPageCard10868(rawValue: target.id)
        case .open(let target):
            if let card = SoccerEventPageCard10868(rawValue: target.id) { open(.reader(card)) }
        case .pause, .resume, .applyUpdates:
            break // the manual stream offers none of these controls
        }
    }

    private func make() -> Built {
        Self.build(event: event, history: history, markets: markets, admitted: admitted,
                   halvesAdmission: halvesAdmission, admittedCards: admittedCards,
                   probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
                   ladderHome: ladderHome, ladderAway: ladderAway, now: now,
                   reading: Reading(story: story, goal: goal, both: both, first: first, half: half,
                                    exactScope: exactScope, exactOriginals: exactOriginals,
                                    selection: selection, readerOpen: session.presented != nil,
                                    wide: sizeClass == .regular, cardDetails: session.cardDetails))
    }

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. A missing
    /// history response leaves only the chart slot unavailable. The admitted
    /// half markets, and the descriptor's period exact-score markets, also tell
    /// All props which rows are about one half.
    static func build(event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                      admitted: SoccerPropReadingAdapter10868.Markets,
                      halvesAdmission: SoccerPageInputAdapter10868.HalvesAdmission = .routeDefault,
                      admittedCards: Set<SoccerEventPageCard10868> = [],
                      probabilityObservedAt: Date?,
                      deliveryInterrupted: Bool = false, ladderHome: Double? = nil, ladderAway: Double? = nil,
                      now: Date, reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        // Another event's payload never reaches this page: history and markets
        // count only when served under this event's own id. A foreign part reads
        // exactly like a missing one; the event's own parts still compose.
        let history = history.flatMap { $0.eventId == event.id ? $0 : nil }
        let markets = markets.flatMap { $0.eventId == event.id ? $0 : nil }
        let host = SoccerMatchPageAdapter10868.Host(
            probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
            ladderHome: ladderHome, ladderAway: ladderAway, now: now, calendar: calendar, locale: locale)
        let phase = SoccerMatchPageAdapter10868.phase(event, now: now)
        let historyInput = history.map {
            SoccerHistoryAdapter10868.history(
                $0, event: event, phase: phase,
                host: SoccerHistoryAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        } ?? SoccerHistoryAdapter10868.unavailable(event: event, phase: phase)
        let props = SoccerPropReadingAdapter10868.Host(now: now, calendar: calendar, locale: locale)
        let goals = SoccerGoalsAdapter10868.input(event, markets: markets, admitted: admitted.goals,
                                                  ownClock: admitted.ownClockGoals, host: props,
                                                  selectedMilestoneID: reading.goal)
        let exact = SoccerExactScoreAdapter10868.input(event, markets: markets, descriptor: admitted.exactScore,
                                                       host: props, selectedScopeID: reading.exactScope,
                                                       selectedOriginals: reading.exactOriginals)
        let both = SoccerBothTeamsAdapter10868.input(event, markets: markets, admitted: admitted.both, host: props,
                                                     selectedOutcomeID: reading.both)
        let first = SoccerFirstTeamAdapter10868.input(event, markets: markets, history: history,
                                                      admitted: admitted.first, host: props, selectedID: reading.first)
        let halves = SoccerHalvesAdapter10868.input(event, markets: markets, admitted: admitted.halves, host: props,
                                                    selectedSeriesID: reading.half)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let originals = SoccerOriginalsAdapter10868.originals(
            event, markets: markets, host: props, tint: tints.home, selection: reading.selection,
            periodMarketIDs: Set(admitted.halves.map(\.marketID))
                .union(admitted.exactScore?.periodMarketIDs(for: event) ?? []))
        let input = SoccerPageInputAdapter10868.input(
            event, history: historyInput, goals: goals, both: both, first: first, halves: halves, exact: exact,
            halvesAdmission: halvesAdmission, admittedCards: admittedCards,
            originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        // A card's Details: this pass's lookups, built once, and the held
        // origin's selection only while it revalidates on this pass.
        let pass = Cards.Pass(event: event, markets: markets, admitted: admitted, host: props, input: input,
                              catalogue: originals.catalogue)
        let cardDetails = Cards.originals(originals, showing: reading.cardDetails.flatMap { Cards.shown($0, in: pass) })
        return Built(input: input, originals: originals, pass: pass, cardDetailsOriginals: cardDetails)
    }
}
