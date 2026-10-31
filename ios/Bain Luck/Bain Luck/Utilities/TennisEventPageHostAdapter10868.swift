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
/// mount passes none: the page shows the players, the history, the dated
/// reading and All props, with no story stream, and no card callback is wired —
/// an owner that supplies a card supplies its routing with it. Every original
/// stays reachable in All props.
///
/// Without a history response (not arrived, or failed) the page still shows its
/// chances and All props; only the chart slot says "History unavailable"
/// (`TennisHistoryAdapter10868.unavailable`), with no working chart control, no
/// dated reading and no retry. The real load/error/retry contract is Native's.
///
/// Controls: Full chart and a headline player's open open the full-size history,
/// which holds what it shows (`TennisReadingAdapter10868.opening`, the pin's
/// `holdShown`). A tap on the plot holds the reading under it (or the break);
/// "Show latest recorded chance" holds the newest. Details and Inspect are
/// offered unavailable until their owner contracts exist, so the shared callback
/// never enables a control that does nothing. The About opens with no source
/// link (none is served). The page's hold (`onInteraction`) is handed to the
/// presentation, which calls it once before each page, catalogue or Details
/// action; full-size content keeps the exact callbacks with no second hold.
struct TennisEventPageHost10868: View {
    let event: EventDetail
    let history: EventHistoryResponse?
    let markets: GameMarketsResponse?
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    var now: Date = Date()
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
        /// without a history response or a readable row.
        let series: TennisChartReading9483.Series?
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var story: TennisEventPageCard10868? = nil
        var held: TennisChartReading9483.Held? = nil
        var selection: OriginalMarketDetails9483.Selection? = nil
        var readerOpen = false
        var wide = false
    }

    @State private var presented: Presented?
    @State private var story: TennisEventPageCard10868?
    @State private var held: TennisChartReading9483.Held?
    @State private var selection: OriginalMarketDetails9483.Selection?
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
        TennisEventPagePresentation10868(
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
            onHistoryPlotPosition: built.series.map { series -> (Double) -> Void in
                { position in held = TennisReadingAdapter10868.inspect(position, in: series) }
            },
            onShowLatestReading: built.series.map { series -> () -> Void in
                { held = TennisReadingAdapter10868.latest(in: series) }
            },
            onInteraction: onInteraction)
    }

    /// The exact mode; the presentation has already asked for the hold.
    private func open(_ mode: TennisEventPageMode10868) {
        presented = Presented(mode: mode)
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
                   now: now,
                   reading: Reading(story: story, held: held, selection: selection, readerOpen: presented != nil,
                                    wide: sizeClass == .regular))
    }

    /// The page input, originals and readout series from the passed values
    /// alone — pure, so every changed value reaches the screen on the next
    /// pass. A missing history response leaves only the chart slot unavailable.
    static func build(event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                      probabilityObservedAt: Date?, deliveryInterrupted: Bool = false, now: Date,
                      reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        let host = TennisMatchPageAdapter10868.Host(
            probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
            now: now, calendar: calendar, locale: locale)
        let phase = TennisMatchPageAdapter10868.phase(event, now: now)
        let historyInput = history.map {
            TennisHistoryAdapter10868.history(
                $0, event: event, phase: phase,
                host: TennisHistoryAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        } ?? TennisHistoryAdapter10868.unavailable(event: event, phase: phase)
        let series = history.flatMap { TennisReadingAdapter10868.series($0, event: event, now: now) }
        let dated = series.map { TennisReadingAdapter10868.reading($0, held: reading.held, event: event, now: now) }
        let originals = TennisOriginalsAdapter10868.originals(
            event, markets: markets,
            host: TennisOriginalsAdapter10868.Host(now: now, calendar: calendar, locale: locale),
            tint: TennisMatchPageAdapter10868.tints(event).home, selection: reading.selection)
        let input = TennisPageInputAdapter10868.input(
            event, history: historyInput, reading: dated,
            originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals, series: series)
    }
}
