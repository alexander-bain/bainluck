import SwiftUI

/// #10868 — THE SOCCER MATCH SCREEN'S HOST GLUE: what `EventDetailView` would
/// mount for a soccer match, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: a soccer event page opens on the three
/// named outcomes, the win probability history and the goal, both-teams,
/// first-team and half-by-half stories the match has content for, and every
/// full-size card, the All props catalogue and an original's Details open over
/// it and close back to the same place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held, which milestone or outcome each story is on, the held
/// original and the timing disclosures. It builds the page input from the
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
/// and All props with no prop stories.
/// ```swift
/// if ReleaseSurfaces.soccerMatchPageEnabled, SoccerEventPageHost10868.applies(event) {
///     SoccerEventPageHost10868(
///         event: vm.headline(event), history: vm.history, markets: vm.gameMarkets,
///         admitted: /* the owner's typed story markets — still owed */ .init(),
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
/// does nothing). The cards' own Details callbacks are nil until a card-to-
/// original route exists; every original is reachable through All props.
struct SoccerEventPageHost10868: View {
    let event: EventDetail
    let history: EventHistoryResponse?
    let markets: GameMarketsResponse?
    /// The owner's typed story markets. Empty: no prop story is offered.
    var admitted: SoccerPropReadingAdapter10868.Markets = .init()
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
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var story: SoccerEventPageCard10868? = nil
        var goal: String? = nil
        var both: String? = nil
        var first: String? = nil
        var half: String? = nil
        var selection: OriginalMarketDetails9483.Selection? = nil
        var readerOpen = false
        var wide = false
    }

    @State private var presented: Presented?
    @State private var story: SoccerEventPageCard10868?
    @State private var goal: String?
    @State private var both: String?
    @State private var first: String?
    @State private var half: String?
    @State private var selection: OriginalMarketDetails9483.Selection?
    @State private var goalTiming = false
    @State private var bothTiming = false
    @State private var firstTiming = false
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        page(make(), mode: .page)
        .sheet(item: $presented) { shown in
            NavigationStack {
                ScrollView {
                    page(make(), mode: shown.mode).padding(.horizontal, 16)
                }
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { presented = nil }
                    }
                }
            }
        }
    }

    private func page(_ built: Built, mode: SoccerEventPageMode10868) -> SoccerEventPagePresentation10868 {
        SoccerEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
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
            onGoalDetails: nil,
            onBothSelect: { both = $0.outcomeID },
            onBothDetails: nil,
            onFirstSelect: { first = $0 },
            onFirstDetails: nil,
            onHalfSelect: { half = $0 },
            onHalfDetails: nil,
            goalTimingExpanded: $goalTiming,
            bothTimingExpanded: $bothTiming,
            firstTimingExpanded: $firstTiming)
    }

    /// The hold first, then the exact mode — never the reverse.
    private func open(_ mode: SoccerEventPageMode10868) {
        onInteraction?()
        presented = Presented(mode: mode)
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
                   probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
                   ladderHome: ladderHome, ladderAway: ladderAway, now: now,
                   reading: Reading(story: story, goal: goal, both: both, first: first, half: half,
                                    selection: selection, readerOpen: presented != nil,
                                    wide: sizeClass == .regular))
    }

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. A missing
    /// history response leaves only the chart slot unavailable.
    static func build(event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                      admitted: SoccerPropReadingAdapter10868.Markets, probabilityObservedAt: Date?,
                      deliveryInterrupted: Bool = false, ladderHome: Double? = nil, ladderAway: Double? = nil,
                      now: Date, reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
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
        let goals = SoccerGoalsAdapter10868.input(event, markets: markets, admitted: admitted.goals, host: props,
                                                  selectedMilestoneID: reading.goal)
        let both = SoccerBothTeamsAdapter10868.input(event, markets: markets, admitted: admitted.both, host: props,
                                                     selectedOutcomeID: reading.both)
        let first = SoccerFirstTeamAdapter10868.input(event, markets: markets, history: history,
                                                      admitted: admitted.first, host: props, selectedID: reading.first)
        let halves = SoccerHalvesAdapter10868.input(event, markets: markets, admitted: admitted.halves, host: props,
                                                    selectedSeriesID: reading.half)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let originals = SoccerOriginalsAdapter10868.originals(event, markets: markets, host: props, tint: tints.home,
                                                              selection: reading.selection)
        let input = SoccerPageInputAdapter10868.input(
            event, history: historyInput, goals: goals, both: both, first: first, halves: halves,
            originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals)
    }
}
