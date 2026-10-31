import SwiftUI

/// #10868 — THE BASEBALL GAME SCREEN'S HOST GLUE: what `EventDetailView` would
/// mount for an MLB game, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: an MLB event page opens on both
/// teams' chances and runs, the win probability history and the stories the
/// game has content for in its phase — run milestones and the series before
/// and during play; home runs, the strikeout ladder, the final total against
/// every offered run line and the series after the final — and every
/// full-size card, the All props catalogue, an original's Details and each
/// story original's Details open over it and close back to the same place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held, which strikeout target, run line and series market and
/// outcome each story is on, the held original, the run milestones' timing
/// disclosure and the story original on show. It builds the page input from the
/// values the page already holds — passed in; it reads no view model, opens no
/// network, subscribes to nothing, runs no timer and ranks nothing.
///
/// The input is recomputed from those values on every body pass. No owner
/// supplies a revision that covers every value the adapters read (served odds,
/// pre-match readings, score and inning, history rows, markets, matrices and
/// the series), and a partial memo would hold a changed score or chance on
/// screen, so none is kept here; any cache needs that complete owner revision
/// first (performance work, routed) — Design's HOST-COMPLETE-INPUT-INVALIDATION
/// rule.
///
/// Proposed mount (NOT applied — `EventDetailView` is Native's). The switch
/// below does NOT exist: `ReleaseSurfaces` (Utilities/ReleaseSurfaces.swift) is
/// the project's per-surface gate, and adding `mlbGamePageEnabled` to it is
/// Native's call. Mounted, this screen would take the place of the adopted
/// paired headline, the chart and the MLB final deck for an MLB game; the
/// page's other sections (score by inning, Live Activity, the After grid,
/// game info) stay where they are, and that composition is Native's to decide.
/// ```swift
/// if ReleaseSurfaces.mlbGamePageEnabled, BaseballEventPageHost10868.applies(event) {
///     BaseballEventPageHost10868(
///         event: vm.headline(event), history: vm.history, markets: vm.gameMarkets,
///         related: vm.relatedFutures,
///         probabilityObservedAt: vm.displayedProbabilityObservedAt(event),
///         deliveryInterrupted: vm.liveUpdateStatus == .interrupted,
///         now: now,
///         onInteraction: { /* the page's existing reader hold */ })
/// }
/// ```
/// Backout is that switch off; no data or route is touched by either state.
///
/// Without a history response (not arrived, or failed) the page still shows its
/// matrix, stories and All props; only the chart slot says "History
/// unavailable" (`BaseballHistoryAdapter10868.unavailable`), with no working
/// chart control and no retry. The real load/error/retry contract is Native's.
///
/// Controls: Full chart opens the full-size history; Details and Inspect on the
/// history are offered unavailable until their owner contracts exist. A
/// story's Details opens that story original's existing Details
/// (`MLBOriginalDetails11284`), frozen as it was on screen; a run milestone
/// has no Details route yet (nil — no button), and every original stays
/// reachable through All props.
struct BaseballEventPageHost10868: View {
    let event: EventDetail
    let history: EventHistoryResponse?
    let markets: GameMarketsResponse?
    let related: RelatedFuturesResponse?
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any reader action the stream
    /// or a card starts. Appearance and reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// MLB games only (part one's rule).
    static func applies(_ event: EventDetail) -> Bool {
        BaseballGamePageAdapter10868.applies(event)
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: BaseballEventPageMode10868
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
        let input: BaseballEventPageInput10868
        let originals: BaseballEventPageOriginals10868
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var story: BaseballEventPageCard10868? = nil
        var selections = BaseballStoriesAdapter10868.Selections()
        var selection: OriginalMarketDetails9483.Selection? = nil
        var readerOpen = false
        var wide = false
    }

    @State private var presented: Presented?
    @State private var story: BaseballEventPageCard10868?
    @State private var selections = BaseballStoriesAdapter10868.Selections()
    @State private var selection: OriginalMarketDetails9483.Selection?
    @State private var totalTiming = false
    /// A story original's Details over the page, and over a full-size reader.
    @State private var pageStoryOriginal: MLBOriginal11284?
    @State private var readerStoryOriginal: MLBOriginal11284?
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        page(make(), mode: .page)
            .sheet(item: $pageStoryOriginal) { original in
                MLBOriginalDetails11284(original: original)
            }
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
                .sheet(item: $readerStoryOriginal) { original in
                    MLBOriginalDetails11284(original: original)
                }
            }
    }

    private func page(_ built: Built, mode: BaseballEventPageMode10868) -> BaseballEventPagePresentation10868 {
        BaseballEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
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
            onHomeRunDetails: { showStoryOriginal($0) },
            onStrikeoutSelect: { selections.strikeout = $0 },
            onStrikeoutDetails: { showStoryOriginal($0) },
            onTotalSelect: { selections.total = $0 },
            onTotalMilestoneDetails: nil,
            onTotalLineDetails: { showStoryOriginal($0) },
            onSeriesMarket: { question in
                // A market change resets the outcome: an outcome belongs to one market.
                selections.seriesQuestion = question
                selections.seriesOption = nil
            },
            onSeriesOption: { question, option in
                selections.seriesQuestion = question
                selections.seriesOption = option
            },
            onSeriesDetails: { showStoryOriginal($0) },
            totalTimingExpanded: $totalTiming)
    }

    /// The hold first, then the exact mode — never the reverse.
    private func open(_ mode: BaseballEventPageMode10868) {
        onInteraction?()
        presented = Presented(mode: mode)
    }

    /// The exact original the held stories carry, frozen as shown, over the
    /// page or over the full-size reader the request came from.
    private func showStoryOriginal(_ id: String) {
        guard let original = BaseballStoriesAdapter10868.original(id, in: make().input) else { return }
        onInteraction?()
        if presented == nil {
            pageStoryOriginal = original
        } else {
            readerStoryOriginal = original
        }
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse(_, let target):
            story = BaseballEventPageCard10868(rawValue: target.id)
        case .open(let target):
            if let card = BaseballEventPageCard10868(rawValue: target.id) { open(.reader(card)) }
        case .pause, .resume, .applyUpdates:
            break // the manual stream offers none of these controls
        }
    }

    private func make() -> Built {
        Self.build(event: event, history: history, markets: markets, related: related,
                   probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
                   now: now,
                   reading: Reading(story: story, selections: selections, selection: selection,
                                    readerOpen: presented != nil, wide: sizeClass == .regular))
    }

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. A missing (or
    /// another event's) history response leaves only the chart slot
    /// unavailable.
    static func build(event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                      related: RelatedFuturesResponse?, probabilityObservedAt: Date?,
                      deliveryInterrupted: Bool = false, now: Date, reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        let host = BaseballGamePageAdapter10868.Host(
            probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
            now: now, calendar: calendar, locale: locale)
        let phase = BaseballGamePageAdapter10868.phase(event, now: now)
        let served = history.flatMap { $0.eventId == event.id ? $0 : nil }
        let historyInput = served.map {
            BaseballHistoryAdapter10868.history(
                $0, event: event, phase: phase,
                host: BaseballHistoryAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        } ?? BaseballHistoryAdapter10868.unavailable(event: event, phase: phase)
        let cards = BaseballStoriesAdapter10868.finalCards(event, markets: markets, related: related)
        let picked = reading.selections
        let totals = BaseballStoriesAdapter10868.totals(
            event, markets: markets, cards: cards, selected: picked.total,
            host: BaseballRunMilestonesAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        let homeRuns = BaseballStoriesAdapter10868.homeRuns(cards, event: event)
        let strikeouts = BaseballStoriesAdapter10868.strikeouts(cards, event: event, selected: picked.strikeout)
        let series = BaseballStoriesAdapter10868.series(event, related: related, question: picked.seriesQuestion,
                                                        option: picked.seriesOption)
        let originals = BaseballOriginalsAdapter10868.originals(
            event, markets: markets,
            host: BaseballOriginalsAdapter10868.Host(now: now, calendar: calendar, locale: locale),
            tint: BaseballGamePageAdapter10868.tints(event).home, selection: reading.selection)
        let input = BaseballPageInputAdapter10868.input(
            event, history: historyInput, homeRuns: homeRuns, strikeouts: strikeouts, totals: totals,
            series: series, originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals)
    }
}
