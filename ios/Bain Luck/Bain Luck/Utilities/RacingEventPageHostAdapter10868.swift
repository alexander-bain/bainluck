import SwiftUI

/// #10868 — THE RACING SCREEN'S HOST GLUE: what `FuturesDetailView` would mount
/// for a race's driver-winner market, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: a race page opens on the drivers'
/// named win chances and their history, and the full-size chart, "All props",
/// an original's Details and the race About open over it and close back to the
/// same place.
///
/// What it owns is only the screen's own reading state: which mode is shown and
/// the held original. It builds the page input from the values the page already
/// holds (passed in — it reads no view model, opens no network, subscribes to
/// nothing, runs no timer and ranks nothing). The input is recomputed from those
/// values on every body pass: no owner supplies a revision covering every value
/// the adapters read (each outcome's price, clock and grade, the market status,
/// every history point), and a partial memo would hold a changed chance on
/// screen, so none is kept here (Design's complete-input rule, hockey host).
///
/// Proposed mount (NOT applied — `FuturesDetailView` is Native's). The switch
/// below does NOT exist: `ReleaseSurfaces` (Utilities/ReleaseSurfaces.swift) is
/// the project's per-surface gate, and adding `racingPageEnabled` to it is
/// Native's call. Neither does the history value: the page holds no
/// `/history` body today (`EvolutionChartView` fetches its own timeline).
/// ```swift
/// if ReleaseSurfaces.racingPageEnabled, RacingEventPageHost10868.applies(market) {
///     RacingEventPageHost10868(
///         race: market, history: heldFuturesHistory, now: now,
///         onInteraction: { /* the page's existing reader hold */ })
/// }
/// ```
/// Backout is that switch off; no data or route is touched by either state.
///
/// Without a history response (not arrived, or failed) the page still shows its
/// headline and All props; only the chart slot says "History unavailable"
/// (`RacingHistoryAdapter10868.unavailable`), with no working chart control and
/// no retry. The real load/error/retry contract is Native's.
///
/// Controls: Full chart and a headline driver open the full-size history; the
/// headline ⓘ opens the race About; All props opens the catalogue and a card
/// opens its Details. History Details and inspection are offered unavailable by
/// part two, so no enabled control does nothing. The owner's interaction hook
/// goes to the presentation, which calls it once before each page, catalogue
/// and Details action (and never for full-size content or stream cards); the
/// stream's own interaction intent reaches it too.
struct RacingEventPageHost10868: View {
    let race: FuturesMarketDetail
    let history: FuturesHistoryResponse?
    /// Other market bodies the host holds for the same race, for All props.
    var markets: [FuturesMarketDetail] = []
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any page action. Appearance
    /// and reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// Motorsport field-winner boards only; which race markets get this screen
    /// is the adopting owner's call.
    static func applies(_ market: FuturesMarketDetail) -> Bool {
        market.llmSportCategory?.lowercased() == "motorsports" && market.mutuallyExclusive == true
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: RacingEventPageMode10868
        var id: String {
            switch mode {
            case .page: "page"
            case .reader(let card): "reader.\(card.rawValue)"
            case .catalogue: "catalogue"
            case .original: "original"
            case .about(let topic): "about.\(topic.rawValue)"
            }
        }
    }

    struct Built {
        let input: RacingEventPageInput10868
        let originals: RacingEventPageOriginals10868
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var selection: OriginalMarketDetails9483.Selection? = nil
        var readerOpen = false
        var wide = false
    }

    @State private var presented: Presented?
    @State private var selection: OriginalMarketDetails9483.Selection?
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

    private func page(_ built: Built, mode: RacingEventPageMode10868) -> RacingEventPagePresentation10868 {
        RacingEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAbout: { topic in open(.about(topic)) },
            onAllProps: { open(.catalogue) },
            onOriginalSelect: { chosen in
                selection = chosen
                open(.original)
            },
            onOriginalHistory: nil,
            onStoryIntent: { intent in handle(intent) },
            onHeadlineOpen: { _ in open(.reader(.history)) },
            onHistoryAction: { id in
                if id == RacingHistoryAdapter10868.expandActionID { open(.reader(.history)) }
            },
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onInteraction: onInteraction)
    }

    /// The exact mode. The presentation already called the hook before this.
    private func open(_ mode: RacingEventPageMode10868) {
        presented = Presented(mode: mode)
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse, .open, .pause, .resume, .applyUpdates:
            break // the stream offers no card and none of these controls
        }
    }

    private func make() -> Built {
        Self.build(race: race, history: history, markets: markets, now: now,
                   reading: Reading(selection: selection, readerOpen: presented != nil,
                                    wide: sizeClass == .regular))
    }

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. A missing
    /// history response leaves only the chart slot unavailable.
    static func build(race: FuturesMarketDetail, history: FuturesHistoryResponse?,
                      markets: [FuturesMarketDetail] = [], now: Date, reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        let host = RacingFieldPageAdapter10868.Host(now: now, calendar: calendar, locale: locale)
        let chart: FieldHistoryInput10868 = history.map {
            RacingHistoryAdapter10868.history($0, market: race, host: host)
        } ?? RacingHistoryAdapter10868.unavailable(race, host: host)
        let originals = RacingOriginalsAdapter10868.originals(
            race: race, markets: markets, host: host,
            tint: RacingFieldPageAdapter10868.tint(0), selection: reading.selection)
        let input = RacingPageInputAdapter10868.input(
            race, history: chart, originalsCount: originals.catalogue?.originals.count,
            stream: .init(readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals)
    }
}
