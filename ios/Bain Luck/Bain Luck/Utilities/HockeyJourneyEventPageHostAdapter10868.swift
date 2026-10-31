import SwiftUI

/// #10868 — THE HOCKEY JOURNEY SCREEN'S HOST GLUE: what `EventDetailView` would
/// mount for an NHL game, with one line, once Native adopts it.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: an NHL event page opens on the paired
/// chances, the two-team history and the points and assists stories, and every
/// full-size card, the All props catalogue, an original's Details and About open
/// over it and close back to the same place.
///
/// What it owns is only the screen's own reading state: which mode is shown,
/// which story is held, which player and milestone each story is on, the held
/// original and the disclosures. It builds the page input from the values the
/// page already holds (passed in — it reads no view model, opens no network,
/// subscribes to nothing, runs no timer and ranks nothing).
///
/// The input is recomputed from those values on every body pass. No owner
/// supplies a revision that covers every value the adapters read (served
/// odds, opening/prematch readings, ESPN state, box values, history rows,
/// markets), and a partial memo would hold a changed score or chance on
/// screen, so none is kept here; any cache needs that complete owner
/// revision first (performance work, routed).
///
/// Proposed mount (NOT applied — `EventDetailView` is Native's). The switch
/// below does NOT exist: `ReleaseSurfaces` (Utilities/ReleaseSurfaces.swift)
/// is the project's per-surface gate, and adding `hockeyJourneyPageEnabled`
/// to it is Native's call.
/// ```swift
/// if ReleaseSurfaces.hockeyJourneyPageEnabled, HockeyJourneyEventPageHost10868.applies(event) {
///     HockeyJourneyEventPageHost10868(
///         event: vm.headline(event), history: vm.history,
///         markets: vm.gameMarkets, boxScore: vm.relatedFutures?.boxScore,
///         probabilityObservedAt: vm.displayedProbabilityObservedAt(event),
///         deliveryInterrupted: vm.liveUpdateStatus == .interrupted,
///         now: now,
///         onInteraction: { /* the page's existing reader hold */ })
/// }
/// ```
/// Backout is that switch off; no data or route is touched by either state.
///
/// Without a history response (not arrived, or failed) the page still shows
/// its chances, stories and All props; only the chart slot says "History
/// unavailable" (`HockeyJourneyHistoryAdapter10868.unavailable`), with no
/// working chart control and no retry. The real load/error/retry contract is
/// Native's.
///
/// WHOSE HISTORY (#10868 hockey F1): the held `history` is this game's only
/// when its `eventId` is exactly `event.id` — no name or time matching —
/// decided once in `build`. Another game's body is treated as no body: the
/// chart says "History unavailable", and no before-the-start forecast is read
/// from it. The forecast's ladder pair is taken from that same identity-checked
/// body (`pmSpreadData.projectedFinal`), never from a separate value, so it
/// cannot come from another game. The legacy `ladderHome` / `ladderAway`
/// parameters stay for compatibility only and are not read.
///
/// History controls: only Full chart opens anything (the full-size history
/// reader). The history adapter offers Details and Inspect as unavailable
/// until their owner contracts exist, so the shared callback never enables a
/// control that does nothing.
struct HockeyJourneyEventPageHost10868: View {
    let event: EventDetail
    let history: EventHistoryResponse?
    let markets: GameMarketsResponse?
    let boxScore: [String: [String: Double]]?
    let probabilityObservedAt: Date?
    var deliveryInterrupted: Bool = false
    /// LEGACY, kept for compatibility and NOT trusted: the ladder pair is read
    /// from the identity-checked `history` body itself, and these never
    /// override it (#10868 hockey F1).
    var ladderHome: Double? = nil
    var ladderAway: Double? = nil
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any reader action the stream
    /// or a card starts. Appearance and reads call nothing.
    var onInteraction: (() -> Void)? = nil

    /// NHL games only; which NHL games get this screen is the adopting owner's call.
    static func applies(_ event: EventDetail) -> Bool {
        (event.sport ?? "").lowercased().hasPrefix("icehockey_nhl")
    }

    /// A non-page mode shown over the page.
    struct Presented: Identifiable, Equatable {
        let mode: HockeyJourneyPageMode10868
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
        let input: HockeyJourneyPageInput10868
        let originals: HockeyJourneyPageOriginals10868
    }

    /// The screen's own reading state, as the builders take it.
    struct Reading: Equatable {
        var story: HockeyJourneyPageCard10868? = nil
        var pointsPlayer: String? = nil
        var pointsMilestone: String? = nil
        var assistsPlayer: String? = nil
        var assistsMilestone: String? = nil
        var selection: OriginalMarketDetails9483.Selection? = nil
        var readerOpen = false
        var wide = false
    }

    @State private var presented: Presented?
    @State private var story: HockeyJourneyPageCard10868?
    @State private var pointsPlayer: String?
    @State private var pointsMilestone: String?
    @State private var assistsPlayer: String?
    @State private var assistsMilestone: String?
    @State private var selection: OriginalMarketDetails9483.Selection?
    @State private var pointsChoices = false
    @State private var pointsTiming = false
    @State private var assistsChoices = false
    @State private var assistsTiming = false
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

    private func page(_ built: Built, mode: HockeyJourneyPageMode10868) -> HockeyJourneyEventPagePresentation10868 {
        HockeyJourneyEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAbout: { open(.about) },
            onAllProps: { open(.catalogue) },
            onOriginalSelect: { chosen in
                selection = chosen
                open(.original)
            },
            onOriginalHistory: nil,
            onStoryIntent: { intent in handle(intent) },
            onOpenStory: { card in open(.reader(card)) },
            onHistoryAction: { id in
                if id == HockeyJourneyHistoryAdapter10868.expandActionID { open(.reader(.history)) }
            },
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onPointsSelect: { pointsMilestone = $0 },
            onPointsChoosePlayer: { pointsPlayer = $0; pointsMilestone = nil },
            onPointsDetails: nil,
            onAssistsSelect: { assistsMilestone = $0 },
            onAssistsChoosePlayer: { assistsPlayer = $0; assistsMilestone = nil },
            onAssistsDetails: nil,
            pointsChoicesExpanded: $pointsChoices,
            pointsTimingExpanded: $pointsTiming,
            assistsChoicesExpanded: $assistsChoices,
            assistsTimingExpanded: $assistsTiming)
    }

    /// The hold first, then the exact mode — never the reverse.
    private func open(_ mode: HockeyJourneyPageMode10868) {
        onInteraction?()
        presented = Presented(mode: mode)
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent) {
        switch intent {
        case .interaction:
            onInteraction?()
        case .browse(_, let target):
            story = HockeyJourneyPageCard10868(rawValue: target.id)
        case .open(let target):
            if let card = HockeyJourneyPageCard10868(rawValue: target.id) { open(.reader(card)) }
        case .pause, .resume, .applyUpdates:
            break // the manual stream offers none of these controls
        }
    }

    private func make() -> Built {
        Self.build(event: event, history: history, markets: markets, boxScore: boxScore,
                   probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
                   ladderHome: ladderHome, ladderAway: ladderAway, now: now,
                   reading: Reading(story: story, pointsPlayer: pointsPlayer, pointsMilestone: pointsMilestone,
                                    assistsPlayer: assistsPlayer, assistsMilestone: assistsMilestone,
                                    selection: selection, readerOpen: presented != nil,
                                    wide: sizeClass == .regular))
    }

    /// The page input and originals from the passed values alone — pure, so
    /// every changed value reaches the screen on the next pass. A missing
    /// history response leaves only the chart slot unavailable, and another
    /// game's body (`eventId` not exactly `event.id`) is decided here, once, to
    /// be no body at all. The forecast's ladder pair is the own body's
    /// `pmSpreadData.projectedFinal`; the legacy `ladderHome` / `ladderAway`
    /// arguments are accepted for compatibility and ignored.
    static func build(event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                      boxScore: [String: [String: Double]]?, probabilityObservedAt: Date?,
                      deliveryInterrupted: Bool = false, ladderHome: Double? = nil, ladderAway: Double? = nil,
                      now: Date, reading: Reading = Reading(),
                      calendar: Calendar = .current, locale: Locale = .current) -> Built {
        let own = history.flatMap { $0.eventId == event.id ? $0 : nil }
        let ladder = own?.pmSpreadData?.projectedFinal
        let host = HockeyJourneyPageAdapter10868.Host(
            probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
            ladderHome: ladder?.homeScore, ladderAway: ladder?.awayScore, now: now, calendar: calendar, locale: locale)
        let phase = HockeyJourneyPageAdapter10868.phase(event, now: now)
        let historyInput = own.map {
            HockeyJourneyHistoryAdapter10868.history(
                $0, event: event, phase: phase,
                host: HockeyJourneyHistoryAdapter10868.Host(now: now, calendar: calendar, locale: locale))
        } ?? HockeyJourneyHistoryAdapter10868.unavailable(event: event, phase: phase)
        let people = HockeyJourneyContributionAdapter10868.Host(
            boxScore: boxScore, now: now, calendar: calendar, locale: locale)
        let points = HockeyJourneyContributionAdapter10868.points(
            event, markets: markets, host: people,
            selectedPlayerID: reading.pointsPlayer, selectedMilestoneID: reading.pointsMilestone)
        let assists = HockeyJourneyContributionAdapter10868.assists(
            event, markets: markets, host: people,
            selectedPlayerID: reading.assistsPlayer, selectedMilestoneID: reading.assistsMilestone)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let originals = HockeyJourneyOriginalsAdapter10868.originals(
            event, markets: markets,
            host: HockeyJourneyOriginalsAdapter10868.Host(now: now, calendar: calendar, locale: locale),
            tint: tints.home, selection: reading.selection)
        let input = HockeyJourneyPageInputAdapter10868.input(
            event, history: historyInput, points: points, assists: assists,
            originalsCount: originals.catalogue?.originals.count,
            stream: .init(displayed: reading.story, readerOpen: reading.readerOpen, wide: reading.wide),
            host: host)
        return Built(input: input, originals: originals)
    }
}
