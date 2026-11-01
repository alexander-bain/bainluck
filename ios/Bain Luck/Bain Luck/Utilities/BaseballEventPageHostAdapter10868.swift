import SwiftUI

/// #10868 — THE BASEBALL GAME SCREEN'S HOST GLUE: what `EventDetailView` would
/// mount for an MLB game, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: an MLB event page opens on both
/// teams' chances and runs, the win probability history and the stories the
/// game has content for in its phase — run milestones, extra innings and the
/// series before and during play; home runs, the strikeout ladder, the final
/// total against every offered run line, extra innings and the series after
/// the final — and every full-size card, the All props catalogue, an
/// original's Details and each story original's Details open over it and
/// close back to the same place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held, which strikeout target, run line, extra-innings
/// outcome and series market and outcome each story is on, the held original, the run milestones' timing
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
///         extraInnings: [], // Native's admitted readings, once its model decodes them
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
/// (`MLBOriginalDetails11284`), frozen as it was on screen. A run milestone's
/// Details (`milestoneDetails`), before first pitch and during play, open the
/// exact original its run line was built with. They first say the chance the
/// card showed, with its own clock or absence words
/// (`BaseballRunMilestonesAdapter10868.details`), and are resolved against the
/// card and originals of the SAME build. Every original stays reachable
/// through All props.
///
/// ONE HOLD PER ACTION (`routes`). The page's hold (`onInteraction`) is asked
/// for exactly once before each page action lands, and never by a routing
/// callback after it. A story card's select, Details and disclosure write
/// reach the stream's activation hook first, and the stream's open sends its
/// interaction before the open: that `.interaction` is the hold, so the
/// card's callback and the open route with no second one. Full-size content
/// calls the same callbacks with no activation and is already held while it
/// is open, so nothing there holds again. The anchor's Full chart, All props
/// and a catalogue original's selection have no stream hook, so each holds
/// once here, then lands. Appearance and binding reads ask for nothing.
///
/// EXTRA INNINGS INPUT. `extraInnings` is the owner's explicit admission of
/// each served extra-innings row's pregame chance and recorded in-game chance
/// (`BaseballExtraInningsAdmission10868`), keyed by the row's exact provider
/// identity. `GameMarketOther` does not decode the served `pregame_mark`, so
/// until Native's model and history adoption supply these values the default
/// is empty and the story shows the production card's outcomes and venue
/// results with each chance's own absence words — a partial card, said so.
struct BaseballEventPageHost10868: View {
    let event: EventDetail
    let history: EventHistoryResponse?
    let markets: GameMarketsResponse?
    let related: RelatedFuturesResponse?
    /// The owner's admitted extra-innings readings; empty admits none.
    var extraInnings: [BaseballExtraInningsAdmission10868] = []
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    var now: Date = Date()
    /// The page's existing hold, requested exactly once BEFORE each page
    /// action (see `routes`). Appearance, reads and full-size content call
    /// nothing.
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
        /// The event this pass was built for.
        let eventID: Int
        /// Before first pitch and during play: the result `input.totals` was
        /// drawn from, with the exact original behind each drawn row. Nil after
        /// the final or with no run ladder.
        let milestones: BaseballRunMilestonesAdapter10868.Milestones?
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
        let routes = Self.routes(
            built, hold: onInteraction,
            present: { presented = Presented(mode: $0) },
            select: { selection = $0 },
            browse: { story = $0 },
            show: { original in showStoryOriginal(original) })
        return BaseballEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAllProps: routes.allProps,
            onOriginalSelect: routes.originalSelect,
            onOriginalHistory: nil,
            onStoryIntent: routes.storyIntent,
            onHistoryAction: routes.historyAction,
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onHomeRunDetails: routes.storyDetails,
            onStrikeoutSelect: { selections.strikeout = $0 },
            onStrikeoutDetails: routes.storyDetails,
            onTotalSelect: { selections.total = $0 },
            onTotalMilestoneDetails: routes.milestoneDetails,
            onTotalLineDetails: routes.storyDetails,
            onSeriesMarket: { question in
                // A market change resets the outcome: an outcome belongs to one market.
                selections.seriesQuestion = question
                selections.seriesOption = nil
            },
            onSeriesOption: { question, option in
                selections.seriesQuestion = question
                selections.seriesOption = option
            },
            onSeriesDetails: routes.storyDetails,
            onExtraInningsSelect: { selections.extraInnings = $0 },
            onExtraInningsDetails: routes.storyDetails,
            totalTimingExpanded: $totalTiming)
    }

    /// Where each page action lands, with the page's one hold.
    struct Routes {
        /// All props: one hold, then the catalogue.
        let allProps: () -> Void
        /// A catalogue original: one hold, then the exact selection, then its Details.
        let originalSelect: (OriginalMarketDetails9483.Selection) -> Void
        /// The anchor's Full chart: one hold, then the full-size history.
        /// Any other id lands nowhere and holds nothing.
        let historyAction: (String) -> Void
        /// The stream's requests: `.interaction` is the hold; `.browse` and
        /// `.open` (each sent after it) land with no hold of their own.
        let storyIntent: (StoryStreamPresentation10868.Intent) -> Void
        /// A story original's Details: no hold of its own — on the page the
        /// card's stream hook already asked, and full-size content is held.
        let storyDetails: (String) -> Void
        /// A run milestone's Details, by the row's exact id: no hold of its
        /// own, for the same reasons as `storyDetails`.
        let milestoneDetails: (String) -> Void
    }

    /// One pass's routes — pure: building them calls nothing. `hold` is the
    /// page's hold; `present`, `select`, `browse` and `show` are the host's
    /// own writes, each handed the exact mode, selection, card or original. A
    /// Details id resolves only an original this pass's stories carry
    /// (`BaseballStoriesAdapter10868.original`), never a neighbour. A run
    /// milestone's id resolves only against this pass's drawn card and the
    /// originals of the same result (`BaseballRunMilestonesAdapter10868
    /// .details`). An id that resolves none shows nothing.
    static func routes(_ built: Built, hold: (() -> Void)?,
                       present: @escaping (BaseballEventPageMode10868) -> Void,
                       select: @escaping (OriginalMarketDetails9483.Selection) -> Void,
                       browse: @escaping (BaseballEventPageCard10868?) -> Void,
                       show: @escaping (MLBOriginal11284) -> Void) -> Routes {
        let input = built.input
        return Routes(
            allProps: {
                hold?()
                present(.catalogue)
            },
            originalSelect: { chosen in
                hold?()
                select(chosen)
                present(.original)
            },
            historyAction: { id in
                guard id == HockeyJourneyHistoryAdapter10868.expandActionID else { return }
                hold?()
                present(.reader(.history))
            },
            storyIntent: { intent in
                switch intent {
                case .interaction:
                    hold?()
                case .browse(_, let target):
                    browse(BaseballEventPageCard10868(rawValue: target.id))
                case .open(let target):
                    if let card = BaseballEventPageCard10868(rawValue: target.id) { present(.reader(card)) }
                case .pause, .resume, .applyUpdates:
                    break // the manual stream offers none of these controls
                }
            },
            storyDetails: { id in
                guard let original = BaseballStoriesAdapter10868.original(id, in: input) else { return }
                show(original)
            },
            milestoneDetails: { id in
                guard let original = BaseballRunMilestonesAdapter10868.details(
                    id, totals: input.totals, phase: input.phase, milestones: built.milestones,
                    eventID: built.eventID) else { return }
                show(original)
            })
    }

    /// The exact original the held stories carry, frozen as shown, over the
    /// page or over the full-size reader the request came from. No hold: the
    /// request that reached here already asked for it.
    private func showStoryOriginal(_ original: MLBOriginal11284) {
        if presented == nil {
            pageStoryOriginal = original
        } else {
            readerStoryOriginal = original
        }
    }

    private func make() -> Built {
        Self.build(event: event, history: history, markets: markets, related: related,
                   extraInnings: extraInnings,
                   probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
                   now: now,
                   reading: Reading(story: story, selections: selections, selection: selection,
                                    readerOpen: presented != nil, wide: sizeClass == .regular))
    }

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. A missing (or
    /// another event's) history response leaves only the chart slot
    /// unavailable: this filter and the history wrapper's own exact event
    /// guard both refuse it.
    static func build(event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                      related: RelatedFuturesResponse?,
                      extraInnings: [BaseballExtraInningsAdmission10868] = [],
                      probabilityObservedAt: Date?,
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
        let runHost = BaseballRunMilestonesAdapter10868.Host(now: now, calendar: calendar, locale: locale)
        // Before first pitch and during play, the run milestones card and the
        // originals behind its rows are ONE result, so Details resolve against
        // the very card drawn. After the final, the stories adapter's final
        // run-line card, unchanged. Either way the same `totals` the stories
        // adapter would have given.
        let milestones = phase == .final ? nil : BaseballRunMilestonesAdapter10868.milestones(
            event, markets: markets, host: runHost, selectedMilestoneID: picked.total)
        let totals: BaseballTotalsStory10868? = phase == .final
            ? BaseballStoriesAdapter10868.totals(event, markets: markets, cards: cards, selected: picked.total,
                                                 host: runHost)
            : milestones.map { BaseballTotalsStory10868.milestones($0.input) }
        let homeRuns = BaseballStoriesAdapter10868.homeRuns(cards, event: event)
        let strikeouts = BaseballStoriesAdapter10868.strikeouts(cards, event: event, selected: picked.strikeout)
        let series = BaseballStoriesAdapter10868.series(event, related: related, question: picked.seriesQuestion,
                                                        option: picked.seriesOption)
        let extra = BaseballExtraInningsAdapter10868.story(
            event, markets: markets, admissions: extraInnings, selected: picked.extraInnings,
            host: BaseballRunMilestonesAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        let originals = BaseballOriginalsAdapter10868.originals(
            event, markets: markets,
            host: BaseballOriginalsAdapter10868.Host(now: now, calendar: calendar, locale: locale),
            tint: BaseballGamePageAdapter10868.tints(event).home, selection: reading.selection)
        let input = BaseballPageInputAdapter10868.input(
            event, history: historyInput, homeRuns: homeRuns, strikeouts: strikeouts, totals: totals,
            extraInnings: extra, series: series, originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals, eventID: event.id, milestones: milestones)
    }
}
