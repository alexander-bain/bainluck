import SwiftUI

/// #10868 — THE COMBAT EVENT SCREEN'S HOST GLUE: what `EventDetailView` would
/// mount for an MMA or boxing event, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: an MMA or boxing event page opens on
/// the two fighters' chances and the probability history beside them, with All
/// props, an original's Details, the fight About and the full-size history
/// opening over it and closing back to the same place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held, each story's held original, the held catalogue
/// original and the timing disclosures. It builds the page input from the
/// values the page already holds (passed in — it reads no view model, opens no
/// network, subscribes to nothing, runs no timer and ranks nothing).
///
/// The input is recomputed from those values on every body pass, as the hockey
/// host's is (Design's complete-input invalidation note): no owner supplies a
/// revision covering every value the adapters read, so no partial memo is kept.
///
/// Proposed mount (NOT applied — `EventDetailView` is Native's). The switch
/// below does NOT exist: `ReleaseSurfaces` (Utilities/ReleaseSurfaces.swift) is
/// the project's per-surface gate, and adding `combatEventPageEnabled` to it is
/// Native's call.
/// ```swift
/// if ReleaseSurfaces.combatEventPageEnabled, CombatEventPageHost10868.applies(event) {
///     CombatEventPageHost10868(
///         event: vm.headline(event), history: vm.history, markets: vm.gameMarkets,
///         probabilityObservedAt: vm.displayedProbabilityObservedAt(event),
///         deliveryInterrupted: vm.liveUpdateStatus == .interrupted,
///         now: now,
///         onInteraction: { /* the page's existing reader hold */ })
/// }
/// ```
/// Backout is that switch off; no data or route is touched by either state.
///
/// STORY MEMBERSHIP. The four fight stories need an owner-proved membership
/// (`CombatStoryAdapter10868.Membership`) that no production owner supplies,
/// so the proposed mount passes none and the page shows the fighters, the
/// history and All props with no story stream. Every original stays reachable
/// in All props.
///
/// Without a history response (not arrived, or failed) the page still shows its
/// chances and All props; only the chart slot says "History unavailable"
/// (`CombatHistoryAdapter10868.unavailable`), with no working chart control and
/// no retry. The real load/error/retry contract is Native's.
///
/// Controls: only Full chart (and a headline fighter's open) opens anything —
/// the full-size history. Details and Inspect are offered unavailable until
/// their owner contracts exist, so the shared callback never enables a control
/// that does nothing. The About opens with no source link (none is served).
/// The page's hold (`onInteraction`) is handed to the presentation, which calls
/// it once before each page, catalogue or Details action; stream cards request
/// it through the stream's own `.interaction` intent; full-size content keeps
/// the exact callbacks with no second hold.
struct CombatEventPageHost10868: View {
    let event: EventDetail
    let history: EventHistoryResponse?
    let markets: GameMarketsResponse?
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    var now: Date = Date()
    /// No production owner supplies one; nil shows no stories.
    var membership: CombatStoryAdapter10868.Membership? = nil
    /// The page's existing hold, requested BEFORE any reader action. Appearance
    /// and reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// MMA and boxing only; which combat events get this screen is the adopting owner's call.
    static func applies(_ event: EventDetail) -> Bool {
        CombatBoutPageAdapter10868.applies(event)
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: CombatEventPageMode10868
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
        let input: CombatEventPageInput10868
        let originals: CombatEventPageOriginals10868
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var story: CombatEventPageCard10868? = nil
        var methods = CombatStoryAdapter10868.Selection()
        var rounds = CombatStoryAdapter10868.Selection()
        var knockout = CombatStoryAdapter10868.Selection()
        var duration = CombatStoryAdapter10868.Selection()
        var selection: OriginalMarketDetails9483.Selection? = nil
        var readerOpen = false
        var wide = false
    }

    @State private var presented: Presented?
    @State private var story: CombatEventPageCard10868?
    @State private var methodsHeld = CombatStoryAdapter10868.Selection()
    @State private var roundsHeld = CombatStoryAdapter10868.Selection()
    @State private var knockoutHeld = CombatStoryAdapter10868.Selection()
    @State private var durationHeld = CombatStoryAdapter10868.Selection()
    @State private var selection: OriginalMarketDetails9483.Selection?
    @State private var methodTiming = false
    @State private var roundTiming = false
    @State private var knockoutTiming = false
    @State private var durationTiming = false
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

    private func page(_ built: Built, mode: CombatEventPageMode10868) -> CombatEventPagePresentation10868 {
        CombatEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAbout: { open(.about) },
            onAboutSource: nil,
            onAllProps: { open(.catalogue) },
            onOriginalSelect: { chosen in
                selection = chosen
                open(.original)
            },
            onOriginalHistory: nil,
            onCatalogueCategory: nil,
            onCatalogueMore: nil,
            onStoryIntent: { intent in handle(intent) },
            onHeadlineOpen: { _ in open(.reader(.history)) },
            onHistoryAction: { id in
                if id == CombatHistoryAdapter10868.expandActionID { open(.reader(.history)) }
            },
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onMethodSelect: { methodsHeld = .init(rowID: $0.methodID, originalID: $0.originalID) },
            onMethodDetails: { details(marketID: $0.marketID, originalID: $0.originalID, in: built.originals) },
            methodTimingExpanded: $methodTiming,
            onRoundSelect: { roundsHeld = .init(rowID: $0.slotID, originalID: $0.originalID) },
            onRoundDetails: { details(marketID: $0.marketID, originalID: $0.originalID, in: built.originals) },
            roundTimingExpanded: $roundTiming,
            onKnockoutSelect: { knockoutHeld = .init(rowID: $0.methodID, originalID: $0.originalID) },
            onKnockoutDetails: { details(marketID: $0.marketID, originalID: $0.originalID, in: built.originals) },
            knockoutTimingExpanded: $knockoutTiming,
            onDurationSelect: { durationHeld = .init(rowID: $0.durationMarketID, originalID: $0.originalID) },
            onDurationDetails: { details(marketID: $0.marketID, originalID: $0.originalID, in: built.originals) },
            durationTimingExpanded: $durationTiming,
            onInteraction: onInteraction)
    }

    /// The exact mode; the presentation has already asked for the hold.
    private func open(_ mode: CombatEventPageMode10868) {
        presented = Presented(mode: mode)
    }

    /// A card's Details: the one catalogue original with this market and side,
    /// else nothing — never a neighbour.
    private func details(marketID: String, originalID: String, in originals: CombatEventPageOriginals10868) {
        guard let held = Self.detailsSelection(marketID: marketID, originalID: originalID, in: originals) else { return }
        selection = held
        open(.original)
    }

    /// The catalogue selection a card's exact original names: exactly one
    /// original whose identity carries this market and this side.
    static func detailsSelection(marketID: String, originalID: String,
                                 in originals: CombatEventPageOriginals10868) -> OriginalMarketDetails9483.Selection? {
        guard let catalogue = originals.catalogue else { return nil }
        let found = catalogue.originals.filter { $0.identity.market == marketID && $0.identity.side == originalID }
        guard found.count == 1 else { return nil }
        return OriginalMarketDetails9483.Selection(scope: catalogue.scope, identity: found[0].identity)
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse(_, let target):
            story = CombatEventPageCard10868(rawValue: target.id)
        case .open(let target):
            if let card = CombatEventPageCard10868(rawValue: target.id) { open(.reader(card)) }
        case .pause, .resume, .applyUpdates:
            break // the manual stream offers none of these controls
        }
    }

    private func make() -> Built {
        Self.build(event: event, history: history, markets: markets,
                   probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
                   now: now, membership: membership,
                   reading: Reading(story: story, methods: methodsHeld, rounds: roundsHeld, knockout: knockoutHeld,
                                    duration: durationHeld, selection: selection, readerOpen: presented != nil,
                                    wide: sizeClass == .regular))
    }

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. A missing
    /// history response leaves only the chart slot unavailable.
    static func build(event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                      probabilityObservedAt: Date?, deliveryInterrupted: Bool = false, now: Date,
                      membership: CombatStoryAdapter10868.Membership? = nil, reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        let host = CombatBoutPageAdapter10868.Host(
            probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
            now: now, calendar: calendar, locale: locale)
        let phase = CombatBoutPageAdapter10868.phase(event, now: now)
        let historyInput = history.map {
            CombatHistoryAdapter10868.history(
                $0, event: event, phase: phase,
                host: CombatHistoryAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        } ?? CombatHistoryAdapter10868.unavailable(event: event, phase: phase)
        let stories = CombatStoryAdapter10868.Host(now: now, calendar: calendar, locale: locale)
        let methods = CombatStoryAdapter10868.methods(event, markets: markets, membership: membership,
                                                      host: stories, selection: reading.methods)
        let rounds = CombatStoryAdapter10868.rounds(event, markets: markets, membership: membership,
                                                    host: stories, selection: reading.rounds)
        let knockout = CombatStoryAdapter10868.knockout(event, markets: markets, membership: membership,
                                                        host: stories, selection: reading.knockout)
        let duration = CombatStoryAdapter10868.duration(event, markets: markets, membership: membership,
                                                        host: stories, selection: reading.duration)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let originals = CombatOriginalsAdapter10868.originals(
            event, markets: markets,
            host: CombatOriginalsAdapter10868.Host(now: now, calendar: calendar, locale: locale),
            tint: tints.home, selection: reading.selection)
        let input = CombatPageInputAdapter10868.input(
            event, history: historyInput, methods: methods, rounds: rounds, knockout: knockout, duration: duration,
            originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals)
    }
}
