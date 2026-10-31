import SwiftUI

/// #10868 — THE CRICKET TEST-MATCH SCREEN'S HOST GLUE: what `EventDetailView`
/// would mount for a Test match, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: a Test-match event page opens on the
/// three originals' chances and their history, and the full-size history, a
/// story, the original markets, an original's Details, the headline's sources
/// and timing and the match About open over it and close back to the same
/// place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held and the held original. It builds the page input from the
/// values the page already holds (passed in — it reads no view model, opens no
/// network, subscribes to nothing, runs no timer and ranks nothing). The input
/// is recomputed from those values on every body pass: no owner supplies a
/// revision covering every value the adapters read (the served pair, the
/// pregame reading, the status and verdict, every history row, every market),
/// and a partial memo would hold a changed chance on screen, so none is kept
/// here (Design's complete-input rule, hockey host).
///
/// Proposed mount (NOT applied — `EventDetailView` is Native's). The switch
/// below does NOT exist: `ReleaseSurfaces` (Utilities/ReleaseSurfaces.swift) is
/// the project's per-surface gate, and adding `cricketTestPageEnabled` to it is
/// Native's call.
/// ```swift
/// if ReleaseSurfaces.cricketTestPageEnabled, CricketEventPageHost10868.applies(event) {
///     CricketEventPageHost10868(
///         event: vm.headline(event), history: vm.history, markets: vm.gameMarkets,
///         probabilityObservedAt: vm.displayedProbabilityObservedAt(event),
///         deliveryInterrupted: vm.liveUpdateStatus == .interrupted,
///         now: now,
///         onInteraction: { /* the page's existing reader hold */ })
/// }
/// ```
/// Backout is that switch off; no data or route is touched by either state.
///
/// Without a history response (not arrived, or failed) the page still shows its
/// title, headline, stories and originals; only the history says "History
/// unavailable" (`CricketHistoryAdapter10868.unavailable`), with no working
/// chart control and no retry. The real load/error/retry contract is Native's.
///
/// Controls: the history's Full chart opens the full-size history; an offered
/// story opens its reader through the stream; the headline's sources and timing
/// opens its exact payload; the title's ⓘ opens the About; the All-markets entry
/// opens the catalogue; an original opens its Details. The history's previous /
/// next / window controls and plot taps are not offered (part two supplies none,
/// and no callback is passed), and the outlook rows are static (no original
/// reference), so no enabled control does nothing. The owner's interaction hook
/// goes to the presentation, which calls it once before each page, catalogue and
/// Details action (never for full-size content or stream cards); the stream's
/// own interaction intent reaches it too.
struct CricketEventPageHost10868: View {
    let event: EventDetail
    let history: EventHistoryResponse?
    let markets: GameMarketsResponse?
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any page action. Appearance and
    /// reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// The served Test-match sport key only (`event_taxonomy.py` maps
    /// `cricket_test_match` to `test_match`). This screen lists a Draw / tie
    /// original; a limited-overs match (`cricket_international_t20`,
    /// `cricket_odi`, …) is the `cricket-t20` route's screen, not this one.
    /// Which events get this screen is the adopting owner's call.
    static func applies(_ event: EventDetail) -> Bool {
        (event.sport ?? "").lowercased() == "cricket_test_match"
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: CricketEventPageMode10868
        var id: String {
            switch mode {
            case .page: "page"
            case .reader(let card): "reader.\(card.rawValue)"
            case .catalogue: "catalogue"
            case .original: "original"
            case .about: "about"
            case .sourceInfo: "sourceInfo"
            }
        }
    }

    struct Built {
        let input: CricketEventPageInput10868
        let originals: CricketEventPageOriginals10868
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var story: CricketEventPageCard10868? = nil
        var selection: OriginalMarketDetails9483.Selection? = nil
        var readerOpen = false
        var wide = false
    }

    @State private var presented: Presented?
    @State private var story: CricketEventPageCard10868?
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

    private func page(_ built: Built, mode: CricketEventPageMode10868) -> CricketEventPagePresentation10868 {
        CricketEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAbout: { open(.about) },
            onSourceInfo: { info in open(.sourceInfo(info)) },
            onAllProps: { open(.catalogue) },
            onOriginalSelect: { chosen in
                selection = chosen
                open(.original)
            },
            onOriginalHistory: nil,
            onStoryIntent: { intent in handle(intent) },
            onHistoryExpand: { open(.reader(.history)) },
            onInteraction: onInteraction)
    }

    /// The exact mode. The presentation already called the hook before this.
    private func open(_ mode: CricketEventPageMode10868) {
        presented = Presented(mode: mode)
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse(_, let target):
            story = CricketEventPageCard10868(rawValue: target.id)
        case .open(let target):
            if let card = CricketEventPageCard10868(rawValue: target.id) { open(.reader(card)) }
        case .pause, .resume, .applyUpdates:
            break // the manual stream offers none of these controls
        }
    }

    private func make() -> Built {
        Self.build(event: event, history: history, markets: markets,
                   probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
                   now: now,
                   reading: Reading(story: story, selection: selection, readerOpen: presented != nil,
                                    wide: sizeClass == .regular))
    }

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. A missing
    /// history response leaves only the history unavailable.
    static func build(event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                      probabilityObservedAt: Date?, deliveryInterrupted: Bool = false, now: Date,
                      reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        let host = CricketEventPageAdapter10868.Host(
            probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
            now: now, calendar: calendar, locale: locale)
        let phase = CricketEventPageAdapter10868.phase(event, now: now)
        let chart: CricketHistoryInput10868 = history.map {
            CricketHistoryAdapter10868.history(
                $0, event: event, phase: phase,
                host: HockeyJourneyHistoryAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        } ?? CricketHistoryAdapter10868.unavailable(event)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let originals = CricketOriginalsAdapter10868.originals(
            event, markets: markets,
            host: HockeyJourneyOriginalsAdapter10868.Host(now: now, calendar: calendar, locale: locale),
            tint: tints.home, selection: reading.selection)
        let input = CricketPageInputAdapter10868.input(
            event, history: chart, originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals)
    }
}
