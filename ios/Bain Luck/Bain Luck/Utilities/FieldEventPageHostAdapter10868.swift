import SwiftUI

/// #10868 — THE FIELD SCREEN'S HOST GLUE: what `FuturesDetailView` would mount
/// for a championship field's winner market, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: a cricket, rugby, darts or chess field
/// page opens on the contenders' named win chances and their history, the field
/// and movement stories sit below, and the full-size chart, "All props", an
/// original's Details and the About open over it and close back to the same
/// place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// the held original, the chosen contender, the chart's Auto / Full scale and
/// the displayed story. It builds the page input from the values the page
/// already holds (passed in — it reads no view model, opens no network,
/// subscribes to nothing, runs no timer and ranks nothing). The input is
/// recomputed from those values on every body pass: no owner supplies a
/// revision covering every value the adapters read, and a partial memo would
/// hold a changed chance on screen, so none is kept here (Design's
/// complete-input rule, hockey host). The scale choice is page-local state, so
/// it holds across the page and the full-size chart and across a data refresh.
///
/// WHICH MARKETS (proposed, NOT applied): `applies` admits a served winner field
/// — `mutually_exclusive`, market `category` `"championship"` — whose served
/// `llm_sport_category` is one of the four this screen is proven on with
/// retained real bodies: cricket (2027 IPL Champion), rugby (2027 Men's Rugby
/// World Cup Winner), darts (PDC World Championship Winner), chess (U.S. Women's
/// Chess Championship Winner). Not admitted, each for a named reason in the
/// return: the volleyball championship body is served with category
/// `basketball`; the LA28 lacrosse qualification board is not mutually
/// exclusive (each country qualifies independently) and has its own approved
/// quiet design; motorsports and golf have their own screens; no production
/// body of a poker, horse-racing or Olympic skating field reaches the app.
///
/// Proposed mount (NOT applied — `FuturesDetailView` is Native's). The switch
/// below does NOT exist: `ReleaseSurfaces` (Utilities/ReleaseSurfaces.swift) is
/// the project's per-surface gate, and adding `fieldPageEnabled` to it is
/// Native's call. Neither does the history value: the page holds no `/history`
/// body today (`EvolutionChartView` fetches its own timeline).
/// ```swift
/// if ReleaseSurfaces.fieldPageEnabled, FieldEventPageHost10868.applies(market) {
///     FieldEventPageHost10868(
///         field: market, history: heldFuturesHistory, now: now,
///         onInteraction: { /* the page's existing reader hold */ })
/// }
/// ```
/// Backout is that switch off; no data or route is touched by either state.
///
/// Without a usable history response (not arrived, failed, or another market's)
/// the page still shows its headline, the field card and All props; the chart
/// slot says "History unavailable" and the movement card is absent. The real
/// load/error/retry contract is Native's.
///
/// Controls: Full chart and a headline contender open the full-size history;
/// the scale control switches Auto / Full; the headline ⓘ opens the About; a
/// field-card bar puts that contender in the chart and its Details opens the
/// original; a movement endpoint opens the full-size history; All props opens
/// the catalogue and a card opens its Details; the stream's Previous / Next and
/// "Open full card" move and open the stories. History Details and inspection
/// are offered unavailable by part two, so no enabled control does nothing.
struct FieldEventPageHost10868: View {
    let field: FuturesMarketDetail
    let history: FuturesHistoryResponse?
    /// Other market bodies the host holds for the same field, for All props.
    var markets: [FuturesMarketDetail] = []
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any page action. Appearance
    /// and reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// The served categories this screen is proven on with retained real bodies.
    static let provenSports: Set<String> = ["cricket", "rugby", "darts", "chess"]

    /// A served winner field of a proven sport; which markets get this screen
    /// is the adopting owner's call.
    static func applies(_ market: FuturesMarketDetail) -> Bool {
        guard market.mutuallyExclusive == true,
              market.category?.lowercased() == FieldEventPageAdapter10868.championshipCategory,
              let sport = market.llmSportCategory?.lowercased()
        else { return false }
        return provenSports.contains(sport)
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: FieldEventPageMode10868
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
        let input: FieldEventPageInput10868
        let originals: FieldEventPageOriginals10868
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var selection: OriginalMarketDetails9483.Selection? = nil
        /// The contender chosen in the field card, by served outcome id.
        var chosen: Int? = nil
        /// The chart's Full scale; false is Auto.
        var full = false
        var displayed: FieldEventPageCard10868? = nil
        var readerOpen = false
        var wide = false
    }

    @State private var presented: Presented?
    @State private var selection: OriginalMarketDetails9483.Selection?
    @State private var chosen: Int?
    @State private var full = false
    @State private var displayed: FieldEventPageCard10868?
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

    private func page(_ built: Built, mode: FieldEventPageMode10868) -> FieldEventPagePresentation10868 {
        FieldEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAbout: { open(.about) },
            onAllProps: { open(.catalogue) },
            onOriginalSelect: { picked in
                selection = picked
                open(.original)
            },
            onOriginalHistory: nil,
            onStoryIntent: { intent in handle(intent, scope: built.input.stream.scope) },
            onHeadlineOpen: { _ in open(.reader(.history)) },
            onHistoryAction: { id in historyAction(id) },
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onFieldChoose: { ref in choose(ref) },
            onFieldOpenOriginal: { ref in
                selection = FieldEventOriginalsAdapter10868.selection(for: ref, in: built.originals)
                open(.original)
            },
            onMovementOpen: { _ in open(.reader(.history)) },
            onInteraction: onInteraction)
    }

    /// The exact mode. The presentation already called the hook before this.
    private func open(_ mode: FieldEventPageMode10868) {
        presented = Presented(mode: mode)
    }

    private func historyAction(_ id: String) {
        switch id {
        case FieldEventHistoryAdapter10868.expandActionID: open(.reader(.history))
        case FieldEventHistoryAdapter10868.scaleActionID: full.toggle()
        default: break // Details is offered unavailable
        }
    }

    /// The field card's exact contender, kept only while it is this market's.
    private func choose(_ ref: FieldChooserOriginalRef10868) {
        chosen = Self.chosenID(ref, in: field)
    }

    /// The served outcome id an exact field-card ref names in this market, or nil.
    static func chosenID(_ ref: FieldChooserOriginalRef10868, in market: FuturesMarketDetail) -> Int? {
        guard ref.marketID == String(market.id), ref.source == FieldEventPageAdapter10868.venueKey(market),
              let id = Int(ref.outcomeID), FieldEventPageAdapter10868.outcome(id, in: market) != nil
        else { return nil }
        return id
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent, scope: String) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse(_, let ref):
            if let card = FieldEventPageInputAdapter10868.card(ref, scope: scope) { displayed = card }
        case .open(let ref):
            if let card = FieldEventPageInputAdapter10868.card(ref, scope: scope) { open(.reader(card)) }
        case .pause, .resume, .applyUpdates:
            break // the manual stream offers none of these controls
        }
    }

    private func make() -> Built {
        Self.build(field: field, history: history, markets: markets, now: now,
                   reading: Reading(selection: selection, chosen: chosen, full: full, displayed: displayed,
                                    readerOpen: presented != nil, wide: sizeClass == .regular))
    }

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. A missing or
    /// foreign history response leaves only the chart slot unavailable and the
    /// movement card absent.
    static func build(field: FuturesMarketDetail, history: FuturesHistoryResponse?,
                      markets: [FuturesMarketDetail] = [], now: Date, reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        let host = FieldEventPageAdapter10868.Host(now: now, calendar: calendar, locale: locale,
                                                   chosen: reading.chosen)
        let chart: FieldHistoryInput10868 = history.map {
            FieldEventHistoryAdapter10868.history($0, market: field, full: reading.full, host: host)
        } ?? FieldEventHistoryAdapter10868.unavailable(field, host: host)
        let originals = FieldEventOriginalsAdapter10868.originals(
            field: field, markets: markets, host: host,
            tint: FieldEventPageAdapter10868.tint(0), selection: reading.selection)
        let input = FieldEventPageInputAdapter10868.input(
            field, history: chart,
            field: FieldEventStoriesAdapter10868.field(field, host: host),
            movement: FieldEventStoriesAdapter10868.movement(history, market: field, host: host),
            originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.displayed, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals)
    }
}
