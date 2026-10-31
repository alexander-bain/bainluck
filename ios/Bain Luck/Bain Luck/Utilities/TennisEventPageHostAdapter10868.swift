import SwiftUI

/// #10868 — THE TENNIS MATCH SCREEN'S HOST GLUE: what `EventDetailView` would
/// mount for a tennis event, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: a tennis event page opens on
/// the two players' chances with the set score and the probability history
/// beside them; a tap on the history holds a dated recorded chance; All props,
/// an original's Details, the match About and the full-size history open over
/// it and close back to the same place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held, the held history reading (`TennisChartReading9483.Held`,
/// as `TennisReadingPin9483` holds it on today's chart) and the held catalogue
/// original. It builds the page input from the values the page already holds
/// (passed in — it reads no view model, opens no network, subscribes to
/// nothing, runs no timer and ranks nothing).
///
/// The input is recomputed from those values on every body pass, as the hockey
/// and combat hosts' are (Design's complete-input invalidation note): no owner
/// supplies a revision covering every value the adapters read, so no partial
/// memo is kept. The held reading is resolved against the series of THAT pass
/// (`Series.resolve`): a reading that is no longer exactly there shows as
/// unavailable, never as a neighbour.
///
/// Proposed mount (NOT applied — `EventDetailView` is Native's). The switch
/// below does NOT exist: `ReleaseSurfaces` (Utilities/ReleaseSurfaces.swift) is
/// the project's per-surface gate, and adding `tennisEventPageEnabled` to it is
/// Native's call.
/// ```swift
/// if ReleaseSurfaces.tennisEventPageEnabled, TennisEventPageHost10868.applies(event) {
///     TennisEventPageHost10868(
///         event: vm.headline(event), history: vm.history, markets: vm.gameMarkets,
///         probabilityObservedAt: vm.displayedProbabilityObservedAt(event),
///         deliveryInterrupted: vm.liveUpdateStatus == .interrupted,
///         now: now,
///         onInteraction: { /* the page's existing reader hold */ })
/// }
/// ```
/// Backout is that switch off; no data or route is touched by either state.
///
/// STORY CARDS. No production owner proves which original belongs to which of
/// the four tennis stories (see `TennisPageInputAdapter10868`), so the proposed
/// mount passes none and the page shows the players, the history, the dated
/// reading and All props, with no story stream. When an owner does supply cards
/// (`cards`, a `TennisCardsAdapter10868.Supplied` for this event), the host
/// admits them (`TennisCardsAdapter10868.admit`), the page offers the ones its
/// own mount rule shows, and their actions reach the host: a totals milestone or
/// an exact finish is held as the reader's choice; a handicap panel or a routed
/// Details opens exactly that catalogue original, never a neighbour. A card's
/// Details control is offered only when what that card shows on this pass
/// resolves to exactly one catalogue original (`detailsControls`, decided
/// before the control is drawn); otherwise the card keeps its comparisons and
/// offers no Details. Every original stays reachable in All props.
///
/// EVENT IDENTITY. A history response whose `event_id` is not this event's is
/// refused whole (`TennisHistoryAdapter10868.admitted`), for the chart AND for
/// the dated reading: no foreign plot, baseline, series, held or latest reading,
/// and no plot-reading control. The rest of the page is unaffected.
///
/// Without a history response (not arrived, or failed) the page still shows its
/// chances and All props; only the chart slot says "History unavailable"
/// (`TennisHistoryAdapter10868.unavailable`), with no working chart control, no
/// dated reading and no retry. The real load/error/retry contract is Native's.
///
/// Controls: Full chart and a headline player's open open the full-size history,
/// which holds what it shows (`TennisReadingAdapter10868.opening`, the pin's
/// `holdShown`). A tap on the plot holds the reading under it (or the break);
/// "Show latest recorded chance" holds the newest. Both exist only while this
/// event's readout series exists. The history's Details and Inspect are offered
/// unavailable until their owner contracts exist, so the shared callback never
/// enables a control that does nothing. The About opens with no source link
/// (none is served). The page's hold (`onInteraction`) is handed to the
/// presentation, which calls it once before each page, catalogue or Details
/// action; full-size content keeps the exact callbacks with no second hold.
struct TennisEventPageHost10868: View {
    let event: EventDetail
    let history: EventHistoryResponse?
    let markets: GameMarketsResponse?
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    var now: Date = Date()
    /// An owner's admitted story cards for this event; nil (production today) shows none.
    var cards: TennisCardsAdapter10868.Supplied? = nil
    /// The page's existing hold, requested BEFORE any reader action. Appearance
    /// and reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// Tennis only, by the gate every tennis surface uses; which tennis events
    /// get this screen is the adopting owner's call.
    static func applies(_ event: EventDetail) -> Bool {
        TennisMatchPageAdapter10868.applies(event)
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: TennisEventPageMode10868
        var id: String {
            switch mode {
            case .page: "page"
            case .reader(let card): "reader.\(card.rawValue)"
            case .catalogue: "catalogue"
            case .original: "original"
            case .about: "about"
            }
        }
    }

    struct Built {
        let input: TennisEventPageInput10868
        let originals: TennisEventPageOriginals10868
        /// The readout series this pass read, for the host's next hold; nil
        /// without this event's history response or a readable row.
        let series: TennisChartReading9483.Series?
        /// The owner's cards as supplied, for routing their Details.
        let cards: TennisCardsAdapter10868.Supplied?
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var story: TennisEventPageCard10868? = nil
        var held: TennisChartReading9483.Held? = nil
        var selection: OriginalMarketDetails9483.Selection? = nil
        var cards = TennisCardsAdapter10868.Held()
        var readerOpen = false
        var wide = false
    }

    @State private var presented: Presented?
    @State private var story: TennisEventPageCard10868?
    @State private var held: TennisChartReading9483.Held?
    @State private var selection: OriginalMarketDetails9483.Selection?
    @State private var cardsHeld = TennisCardsAdapter10868.Held()
    @State private var totalTiming = false
    @State private var handicapExplanation = false
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        let built = make()
        page(built, mode: .page)
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

    private func page(_ built: Built, mode: TennisEventPageMode10868) -> TennisEventPagePresentation10868 {
        let controls = Self.readingControls(built.series) { held = $0 }
        let cardDetails = Self.detailsControls(built) { resolved in details(resolved) }
        return TennisEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAbout: { open(.about) },
            onAllProps: { open(.catalogue) },
            onOriginalSelect: { chosen in
                selection = chosen
                open(.original)
            },
            onOriginalHistory: nil,
            onStoryIntent: { intent in handle(intent) },
            onHeadlineOpen: { _ in openHistory(built.series) },
            onHistoryAction: { id in
                if id == TennisHistoryAdapter10868.expandActionID { openHistory(built.series) }
            },
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: controls.plot,
            onShowLatestReading: controls.latest,
            onSetDetails: cardDetails.sets,
            onTotalSelect: { id in cardsHeld.totalMilestoneID = id },
            onTotalDetails: cardDetails.totals,
            totalTimingExpanded: $totalTiming,
            onExactSelect: { scope, id in
                cardsHeld.exactScopeID = scope
                cardsHeld.exactOriginalID = id
            },
            onExactDetails: cardDetails.exact,
            onExactRecover: {
                cardsHeld.exactScopeID = nil
                cardsHeld.exactOriginalID = nil
            },
            onHandicapSelect: { chosen in
                details(TennisCardsAdapter10868.handicapSelection(chosen, in: built.originals))
            },
            handicapExplanationExpanded: $handicapExplanation,
            onInteraction: onInteraction)
    }

    /// The plot tap and "Show latest recorded chance", each holding through
    /// `hold`. Both exist only while this event's readout series does: without
    /// a history response, or with another event's, neither is offered.
    static func readingControls(_ series: TennisChartReading9483.Series?,
                                hold: @escaping (TennisChartReading9483.Held?) -> Void)
        -> (plot: ((Double) -> Void)?, latest: (() -> Void)?) {
        guard let series else { return (nil, nil) }
        return ({ position in hold(TennisReadingAdapter10868.inspect(position, in: series)) },
                { hold(TennisReadingAdapter10868.latest(in: series)) })
    }

    /// The story cards' Details callbacks for one pass.
    struct DetailsControls {
        var sets: ((String) -> Void)? = nil
        var totals: ((String) -> Void)? = nil
        /// (scope id, original id), exactly as the card names them.
        var exact: ((String, String) -> Void)? = nil
    }

    /// Each card's Details callback, or nil — decided from THIS pass's shown
    /// cards and catalogue before any control is drawn
    /// (`TennisCardsAdapter10868.detailsAvailability`), so a leaf never draws
    /// a Details control that would open nothing. A supplied callback still
    /// resolves the id it is handed and opens only exactly that catalogue
    /// original; it never opens another in its place. The page and the
    /// full-size reader get the same callbacks; the presentation adds the
    /// page's one hold, and the reader none.
    static func detailsControls(_ built: Built,
                                open: @escaping (OriginalMarketDetails9483.Selection) -> Void) -> DetailsControls {
        let cards = built.cards
        let originals = built.originals
        let mounted = TennisEventPageModel10868(built.input).exact
        let available = TennisCardsAdapter10868.detailsAvailability(built.input, supplied: cards, originals: originals)
        return DetailsControls(
            sets: available.sets ? { (id: String) -> Void in
                if let resolved = TennisCardsAdapter10868.setDetails(id, supplied: cards, originals: originals) {
                    open(resolved)
                }
            } : nil,
            totals: available.totals ? { (id: String) -> Void in
                if let resolved = TennisCardsAdapter10868.totalDetails(id, supplied: cards, originals: originals) {
                    open(resolved)
                }
            } : nil,
            exact: available.exact ? { (scope: String, id: String) -> Void in
                if let resolved = TennisCardsAdapter10868.exactDetails(
                    scopeID: scope, originalID: id, mounted: mounted, supplied: cards, originals: originals) {
                    open(resolved)
                }
            } : nil)
    }

    /// The exact mode; the presentation has already asked for the hold.
    private func open(_ mode: TennisEventPageMode10868) {
        presented = Presented(mode: mode)
    }

    /// A card's Details: the exact catalogue original it resolved, held and
    /// opened; nothing when it resolved none (a handicap panel's choice outside
    /// the page's catalogue).
    private func details(_ resolved: OriginalMarketDetails9483.Selection?) {
        guard let resolved else { return }
        selection = resolved
        open(.original)
    }

    /// The full-size history, holding what it shows so neither a later arrival
    /// nor the return moves the reading the reader opened on.
    private func openHistory(_ series: TennisChartReading9483.Series?) {
        if let series { held = TennisReadingAdapter10868.opening(held, in: series) }
        open(.reader(.history))
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse(_, let target):
            story = TennisEventPageCard10868(rawValue: target.id)
        case .open(let target):
            if let card = TennisEventPageCard10868(rawValue: target.id) { open(.reader(card)) }
        case .pause, .resume, .applyUpdates:
            break // the manual stream offers none of these controls
        }
    }

    private func make() -> Built {
        Self.build(event: event, history: history, markets: markets,
                   probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
                   now: now, cards: cards,
                   reading: Reading(story: story, held: held, selection: selection, cards: cardsHeld,
                                    readerOpen: presented != nil, wide: sizeClass == .regular))
    }

    /// The page input, originals and readout series from the passed values
    /// alone — pure, so every changed value reaches the screen on the next
    /// pass. A missing or foreign history response leaves only the chart slot
    /// and the dated reading unavailable.
    static func build(event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                      probabilityObservedAt: Date?, deliveryInterrupted: Bool = false, now: Date,
                      cards: TennisCardsAdapter10868.Supplied? = nil,
                      reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        let host = TennisMatchPageAdapter10868.Host(
            probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
            now: now, calendar: calendar, locale: locale)
        let phase = TennisMatchPageAdapter10868.phase(event, now: now)
        // One identity gate for the chart and the dated reading alike.
        let admitted = TennisHistoryAdapter10868.admitted(history, for: event)
        let historyInput = admitted.map {
            TennisHistoryAdapter10868.history(
                $0, event: event, phase: phase,
                host: TennisHistoryAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        } ?? TennisHistoryAdapter10868.unavailable(event: event, phase: phase)
        let series = admitted.flatMap { TennisReadingAdapter10868.series($0, event: event, now: now) }
        let dated = series.map { TennisReadingAdapter10868.reading($0, held: reading.held, event: event, now: now) }
        let tint = TennisMatchPageAdapter10868.tints(event).home
        let originals = TennisOriginalsAdapter10868.originals(
            event, markets: markets,
            host: TennisOriginalsAdapter10868.Host(now: now, calendar: calendar, locale: locale),
            tint: tint, selection: reading.selection)
        let stories = TennisCardsAdapter10868.admit(cards, event: event, phase: phase, originals: originals,
                                                     held: reading.cards, tint: tint)
        let input = TennisPageInputAdapter10868.input(
            event, history: historyInput, reading: dated,
            sets: stories.sets, totals: stories.totals, exact: stories.exact, handicaps: stories.handicaps,
            originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals, series: series,
                     cards: cards?.eventID == event.id ? cards : nil)
    }
}
